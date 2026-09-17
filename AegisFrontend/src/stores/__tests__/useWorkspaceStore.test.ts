import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useWorkspaceStore } from '../useWorkspaceStore';
import { workspaceApi, sessionApi, fileApi } from '@/api';

describe('useWorkspaceStore', () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      workspaces: [],
      activeWorkspaceId: null,
      isLoadingWorkspaces: false,
      sessions: [],
      activeSessionId: null,
      isLoadingSessions: false,
      memories: [],
      isLoadingMemories: false,
      fileTree: null,
      isLoadingFileTree: false,
      tabs: [],
      activeTabId: null,
    });
    vi.restoreAllMocks();
  });

  it('should fetch workspaces and set active workspace', async () => {
    const mockWorkspaces = [
      {
        id: 'ws-1',
        name: 'Aegis Core',
        root_path: '/home/aegis',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ];

    vi.spyOn(workspaceApi, 'list').mockResolvedValue(mockWorkspaces);
    vi.spyOn(sessionApi, 'list').mockResolvedValue([]);
    vi.spyOn(workspaceApi, 'getMemory').mockResolvedValue({
      scope: 'workspace',
      project_conventions: ['Convention 1'],
      confirmed_architecture: ['Arch 1'],
      failed_attempts: [],
    });
    vi.spyOn(fileApi, 'getTree').mockResolvedValue({ name: 'root', path: '', type: 'directory' });

    const store = useWorkspaceStore.getState();
    await store.fetchWorkspaces();

    expect(useWorkspaceStore.getState().workspaces.length).toBe(1);
    expect(useWorkspaceStore.getState().activeWorkspaceId).toBe('ws-1');
  });

  it('should manage canvas tabs: open, switch, update dirty content, and close', () => {
    const store = useWorkspaceStore.getState();

    // 1. Open new tab
    store.openTab({
      filePath: 'src/app.py',
      title: 'app.py',
      language: 'python',
      content: 'print("hello")',
    });

    const state1 = useWorkspaceStore.getState();
    expect(state1.tabs.length).toBe(1);
    expect(state1.activeTabId).toBe(state1.tabs[0].id);
    expect(state1.tabs[0].filePath).toBe('src/app.py');

    const tabId = state1.tabs[0].id;

    // 2. Update tab content (mark as modified)
    store.updateTabContent(tabId, 'print("updated content")');
    const state2 = useWorkspaceStore.getState();
    expect(state2.tabs[0].content).toBe('print("updated content")');
    expect(state2.tabs[0].isModified).toBe(true);

    // 3. Open second tab
    store.openTab({
      filePath: 'src/main.ts',
      title: 'main.ts',
      language: 'typescript',
      content: 'console.log("ts")',
    });

    const state3 = useWorkspaceStore.getState();
    expect(state3.tabs.length).toBe(2);
    expect(state3.activeTabId).toBe(state3.tabs[1].id);

    // 4. Switch tab
    store.setActiveTab(tabId);
    expect(useWorkspaceStore.getState().activeTabId).toBe(tabId);

    // 5. Close tab
    store.closeTab(tabId);
    const state4 = useWorkspaceStore.getState();
    expect(state4.tabs.length).toBe(1);
    expect(state4.activeTabId).toBe(state4.tabs[0].id);
  });

  it('should save active tab content via fileApi.saveContent and clear modified flag', async () => {
    const mockSave = vi.spyOn(fileApi, 'saveContent').mockResolvedValue({
      path: 'src/app.py',
      status: 'saved',
      size: 100,
    });

    useWorkspaceStore.setState({
      activeWorkspaceId: 'ws-1',
      tabs: [
        {
          id: 'tab-1',
          filePath: 'src/app.py',
          title: 'app.py',
          language: 'python',
          content: 'final code',
          isModified: true,
        },
      ],
      activeTabId: 'tab-1',
    });

    const store = useWorkspaceStore.getState();
    await store.saveCurrentTab();

    expect(mockSave).toHaveBeenCalledWith('ws-1', 'src/app.py', 'final code');
    expect(useWorkspaceStore.getState().tabs[0].isModified).toBe(false);
  });
});
