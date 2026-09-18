import { create } from 'zustand';
import type {
  Workspace,
  WorkspaceMemory,
  Session,
  FileNode,
  OpenTab,
  WorkspaceCreatePayload,
  WorkspaceUpdatePayload,
} from '@/types';
import { workspaceApi, sessionApi, fileApi } from '@/api';

interface WorkspaceState {
  // Workspaces
  workspaces: Workspace[];
  activeWorkspaceId: string | null;
  isLoadingWorkspaces: boolean;
  workspaceError: string | null;

  // Sessions
  sessions: Session[];
  activeSessionId: string | null;
  isLoadingSessions: boolean;

  // Memories
  memories: WorkspaceMemory[];
  isLoadingMemories: boolean;

  // File Tree
  fileTree: FileNode | null;
  isLoadingFileTree: boolean;

  // Canvas Tabs
  tabs: OpenTab[];
  activeTabId: string | null;

  // Actions - Workspaces
  fetchWorkspaces: () => Promise<void>;
  setActiveWorkspace: (id: string) => Promise<void>;
  createWorkspace: (payload: WorkspaceCreatePayload) => Promise<Workspace>;
  updateWorkspace: (id: string, payload: WorkspaceUpdatePayload) => Promise<void>;
  deleteWorkspace: (id: string) => Promise<void>;

  // Actions - Sessions
  fetchSessions: (workspaceId: string) => Promise<void>;
  setActiveSession: (id: string | null) => void;
  createSession: (title?: string) => Promise<Session>;
  deleteSession: (id: string) => Promise<void>;

  // Actions - Memories
  fetchMemories: (workspaceId: string) => Promise<void>;
  createMemory: (payload: { category: string; title: string; content: string; pinned?: boolean }) => Promise<void>;
  deleteMemory: (memoryId: string) => Promise<void>;

  // Actions - Files & Canvas Tabs
  fetchFileTree: (workspaceId: string) => Promise<void>;
  openTab: (tab: Omit<OpenTab, 'id'>) => void;
  openFileFromWorkspace: (relativePath: string) => Promise<void>;
  closeTab: (tabId: string) => void;
  setActiveTab: (tabId: string) => void;
  updateTabContent: (tabId: string, content: string) => void;
  saveCurrentTab: () => Promise<void>;
  setTabStale: (filePath: string, isStale: boolean) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  workspaces: [],
  activeWorkspaceId: null,
  isLoadingWorkspaces: false,
  workspaceError: null,

  sessions: [],
  activeSessionId: null,
  isLoadingSessions: false,

  memories: [],
  isLoadingMemories: false,

  fileTree: null,
  isLoadingFileTree: false,

  tabs: [],
  activeTabId: null,

  fetchWorkspaces: async () => {
    set({ isLoadingWorkspaces: true, workspaceError: null });
    try {
      let data = await workspaceApi.list();
      // 如果后端工作区为空，自动初始化主工程默认工作区
      if (data.length === 0) {
        try {
          const defaultWs = await workspaceApi.create({
            name: 'Aegis Core',
            root_path: '/home/Skualeilu/Projects/Aegis',
            description: 'AegisAgent 智能体核心运行时工作区',
          });
          data = [defaultWs];
        } catch {
          // 忽略创建失败
        }
      }

      set({ workspaces: data, isLoadingWorkspaces: false });
      if (data.length > 0) {
        const currentActive = get().activeWorkspaceId;
        const targetId = currentActive && data.some((w) => w.id === currentActive) ? currentActive : data[0].id;
        await get().setActiveWorkspace(targetId);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '连接后端工作区失败';
      set({ isLoadingWorkspaces: false, workspaceError: msg });
    }
  },

  setActiveWorkspace: async (id: string) => {
    set({ activeWorkspaceId: id });
    await Promise.allSettled([
      get().fetchSessions(id),
      get().fetchMemories(id),
      get().fetchFileTree(id),
    ]);
  },

  createWorkspace: async (payload: WorkspaceCreatePayload) => {
    const ws = await workspaceApi.create(payload);
    set((state) => ({ workspaces: [ws, ...state.workspaces] }));
    await get().setActiveWorkspace(ws.id);
    return ws;
  },

  updateWorkspace: async (id: string, payload: WorkspaceUpdatePayload) => {
    const updated = await workspaceApi.update(id, payload);
    set((state) => ({
      workspaces: state.workspaces.map((w) => (w.id === id ? { ...w, ...updated } : w)),
    }));
  },

  deleteWorkspace: async (id: string) => {
    await workspaceApi.delete(id);
    set((state) => {
      const remaining = state.workspaces.filter((w) => w.id !== id);
      const nextActive = remaining.length > 0 ? remaining[0].id : null;
      return {
        workspaces: remaining,
        activeWorkspaceId: nextActive,
      };
    });
    const nextId = get().activeWorkspaceId;
    if (nextId) {
      await get().setActiveWorkspace(nextId);
    }
  },

  fetchSessions: async (workspaceId: string) => {
    set({ isLoadingSessions: true });
    try {
      let sessions = await sessionApi.list(workspaceId);
      if (sessions.length === 0) {
        try {
          const defaultSession = await sessionApi.create(workspaceId, '默认会话');
          sessions = [defaultSession];
        } catch {
          // 忽略创建失败
        }
      }
      set({ sessions, isLoadingSessions: false });
      if (sessions.length > 0) {
        const currentSession = get().activeSessionId;
        if (!currentSession || !sessions.some((s) => s.id === currentSession)) {
          set({ activeSessionId: sessions[0].id });
        }
      }
    } catch {
      set({ sessions: [], isLoadingSessions: false });
    }
  },

  setActiveSession: (id: string | null) => set({ activeSessionId: id }),

  createSession: async (title?: string) => {
    const wsId = get().activeWorkspaceId;
    if (!wsId) throw new Error('No active workspace');
    const session = await sessionApi.create(wsId, title);
    set((state) => ({ sessions: [session, ...state.sessions], activeSessionId: session.id }));
    return session;
  },

  deleteSession: async (id: string) => {
    await sessionApi.delete(id);
    set((state) => {
      const remaining = state.sessions.filter((s) => s.id !== id);
      const nextActive = remaining.length > 0 ? remaining[0].id : null;
      return {
        sessions: remaining,
        activeSessionId: nextActive,
      };
    });
  },

  fetchMemories: async (workspaceId: string) => {
    set({ isLoadingMemories: true });
    try {
      const memView = await workspaceApi.getMemory(workspaceId);
      const facts: WorkspaceMemory[] = [];
      (memView.confirmed_architecture || []).forEach((item, idx) => {
        facts.push({
          id: `arch-${idx}`,
          workspace_id: workspaceId,
          category: 'confirmed_architecture',
          title: `架构定论 #${idx + 1}`,
          content: item,
          pinned: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      });
      (memView.project_conventions || []).forEach((item, idx) => {
        facts.push({
          id: `conv-${idx}`,
          workspace_id: workspaceId,
          category: 'project_conventions',
          title: `约定规范 #${idx + 1}`,
          content: item,
          pinned: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      });
      (memView.failed_attempts || []).forEach((item, idx) => {
        facts.push({
          id: `fail-${idx}`,
          workspace_id: workspaceId,
          category: 'global_failed_attempts',
          title: `避坑指引: ${item.action}`,
          content: `失败原因: ${item.failure_reason}${item.conclusion ? `\n结论: ${item.conclusion}` : ''}`,
          pinned: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      });
      set({ memories: facts, isLoadingMemories: false });
    } catch {
      set({ memories: [], isLoadingMemories: false });
    }
  },

  createMemory: async (payload) => {
    const wsId = get().activeWorkspaceId;
    if (!wsId) return;
    await workspaceApi.promoteFact(wsId, {
      fact: payload.content,
      category: payload.category,
    });
    await get().fetchMemories(wsId);
  },

  deleteMemory: async () => {
    // 记忆删除接口可按需触发刷新
    const wsId = get().activeWorkspaceId;
    if (wsId) {
      await get().fetchMemories(wsId);
    }
  },

  fetchFileTree: async (workspaceId: string) => {
    set({ isLoadingFileTree: true });
    try {
      const tree = await fileApi.getTree(workspaceId);
      set({ fileTree: tree, isLoadingFileTree: false });
    } catch {
      set({ fileTree: null, isLoadingFileTree: false });
    }
  },

  openTab: (tabData) => {
    const { tabs } = get();
    const existing = tabs.find((t) => t.filePath === tabData.filePath);
    if (existing) {
      set({ activeTabId: existing.id });
      return;
    }
    const newTab: OpenTab = {
      ...tabData,
      id: `tab-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
    };
    set({
      tabs: [...tabs, newTab],
      activeTabId: newTab.id,
    });
  },

  openFileFromWorkspace: async (relativePath: string) => {
    const wsId = get().activeWorkspaceId;
    if (!wsId) return;

    try {
      const resp = await fileApi.getContent(wsId, relativePath);
      get().openTab({
        filePath: relativePath,
        title: relativePath.split('/').pop() || relativePath,
        language: resp.language || 'plaintext',
        content: resp.content || '',
        isModified: false,
        isStale: false,
      });
    } catch {
      // 容错打开空文件
      get().openTab({
        filePath: relativePath,
        title: relativePath.split('/').pop() || relativePath,
        language: 'plaintext',
        content: `// 无法读取文件: ${relativePath}`,
        isModified: false,
      });
    }
  },

  closeTab: (tabId: string) => {
    const { tabs, activeTabId } = get();
    const filtered = tabs.filter((t) => t.id !== tabId);
    let nextActive = activeTabId;
    if (activeTabId === tabId) {
      const closedIndex = tabs.findIndex((t) => t.id === tabId);
      if (filtered.length > 0) {
        const newIndex = Math.min(closedIndex, filtered.length - 1);
        nextActive = filtered[newIndex].id;
      } else {
        nextActive = null;
      }
    }
    set({ tabs: filtered, activeTabId: nextActive });
  },

  setActiveTab: (tabId: string) => set({ activeTabId: tabId }),

  updateTabContent: (tabId: string, content: string) => {
    set((state) => ({
      tabs: state.tabs.map((t) => (t.id === tabId ? { ...t, content, isModified: true } : t)),
    }));
  },

  saveCurrentTab: async () => {
    const { tabs, activeTabId, activeWorkspaceId } = get();
    const currentTab = tabs.find((t) => t.id === activeTabId);
    if (!currentTab || !activeWorkspaceId || !currentTab.filePath) return;

    try {
      await fileApi.saveContent(activeWorkspaceId, currentTab.filePath, currentTab.content);
      set((state) => ({
        tabs: state.tabs.map((t) => (t.id === activeTabId ? { ...t, isModified: false, isStale: false } : t)),
      }));
    } catch {
      // ignore
    }
  },

  setTabStale: (filePath: string, isStale: boolean) => {
    set((state) => ({
      tabs: state.tabs.map((t) => (t.filePath === filePath ? { ...t, isStale } : t)),
    }));
  },
}));
