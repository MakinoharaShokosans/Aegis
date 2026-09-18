import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useWorkspaceStore } from '../useWorkspaceStore';
import { workspaceApi, sessionApi, fileApi } from '@/api';

describe('useWorkspaceStore', () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      workspaces: [],
      activeWorkspaceId: null,
      isLoadingWorkspaces: false,
      workspaceSessions: {},
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

  it('should fetch session turns and set currentTaskId on setActiveSession', async () => {
    const mockTurns = [
      {
        id: '1',
        session_id: 'sess-1',
        turn_index: 1,
        role: 'user' as const,
        content: '历史提问 1',
        token_count: 50,
        created_at: new Date().toISOString(),
      },
      {
        id: '2',
        session_id: 'sess-1',
        turn_index: 2,
        role: 'assistant' as const,
        content: '历史答复 1',
        token_count: 120,
        created_at: new Date().toISOString(),
      },
    ];

    vi.spyOn(sessionApi, 'getTurns').mockResolvedValue(mockTurns);

    const store = useWorkspaceStore.getState();
    await store.setActiveSession('sess-1');

    expect(useWorkspaceStore.getState().activeSessionId).toBe('sess-1');
    const taskId = 'sess-history-sess-1';
    const { useTaskStore } = await import('../useTaskStore');
    expect(useTaskStore.getState().currentTaskId).toBe(taskId);
    expect(useTaskStore.getState().tasks[taskId].messages.length).toBe(2);
    expect(useTaskStore.getState().tasks[taskId].messages[0].content).toBe('历史提问 1');
  });

  it('should support creating and deleting sessions under specific workspaces in tree', async () => {
    const mockCreatedSession = {
      id: 'sess-new-1',
      workspace_id: 'ws-2',
      title: '在线测视力网页构想',
      status: 'active' as const,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    vi.spyOn(sessionApi, 'create').mockResolvedValue(mockCreatedSession);
    vi.spyOn(sessionApi, 'delete').mockResolvedValue({ success: true, session_id: 'sess-new-1' });

    useWorkspaceStore.setState({
      workspaces: [
        { id: 'ws-1', name: 'Aegis', root_path: '/path/1', created_at: '', updated_at: '' },
        { id: 'ws-2', name: 'EyesPro', root_path: '/path/2', created_at: '', updated_at: '' },
      ],
      activeWorkspaceId: 'ws-1',
      workspaceSessions: {
        'ws-1': [],
        'ws-2': [],
      },
    });

    const store = useWorkspaceStore.getState();
    const created = await store.createSession('在线测视力网页构想', 'ws-2');

    expect(created.id).toBe('sess-new-1');
    expect(useWorkspaceStore.getState().activeWorkspaceId).toBe('ws-2');
    expect(useWorkspaceStore.getState().activeSessionId).toBe('sess-new-1');
    expect(useWorkspaceStore.getState().workspaceSessions['ws-2'].length).toBe(1);

    // Delete session
    await store.deleteSession('sess-new-1', 'ws-2');
    expect(useWorkspaceStore.getState().workspaceSessions['ws-2'].length).toBe(0);
    expect(useWorkspaceStore.getState().activeSessionId).toBeNull();
  });
});
