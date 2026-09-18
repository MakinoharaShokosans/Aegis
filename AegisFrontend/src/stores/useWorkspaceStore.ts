import { create } from 'zustand';
import type {
  Workspace,
  WorkspaceMemory,
  Session,
  FileNode,
  OpenTab,
  TaskMessage,
  WorkspaceCreatePayload,
  WorkspaceUpdatePayload,
} from '@/types';
import { workspaceApi, sessionApi, fileApi } from '@/api';
import { useUiStore } from './useUiStore';
import { useTaskStore } from './useTaskStore';

interface WorkspaceState {
  // Workspaces
  workspaces: Workspace[];
  activeWorkspaceId: string | null;
  isLoadingWorkspaces: boolean;
  workspaceError: string | null;

  // Sessions
  workspaceSessions: Record<string, Session[]>;
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
  setActiveSession: (id: string | null) => Promise<void>;
  createSession: (title?: string, workspaceId?: string) => Promise<Session>;
  deleteSession: (id: string, workspaceId?: string) => Promise<void>;

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

  fetchWorkspaces: async () => {
    set({ isLoadingWorkspaces: true, workspaceError: null });
    try {
      const data = await workspaceApi.list();
      set({ workspaces: data, isLoadingWorkspaces: false });

      // Fetch sessions for all workspaces in parallel
      const sessionMap: Record<string, Session[]> = {};
      await Promise.allSettled(
        data.map(async (ws) => {
          try {
            const list = await sessionApi.list(ws.id);
            sessionMap[ws.id] = list;
          } catch {
            sessionMap[ws.id] = [];
          }
        })
      );
      set({ workspaceSessions: sessionMap });

      if (data.length > 0) {
        const currentActive = get().activeWorkspaceId;
        const targetId = currentActive && data.some((w) => w.id === currentActive) ? currentActive : data[0].id;
        await get().setActiveWorkspace(targetId);
      } else {
        // 无工作区时，弹出工作区创建引导弹窗，让用户显式确认路径与参数
        useUiStore.getState().openWorkspaceModal('create');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '连接后端工作区失败';
      set({ isLoadingWorkspaces: false, workspaceError: msg });
    }
  },

  setActiveWorkspace: async (id: string) => {
    const currentSessions = get().workspaceSessions[id] || [];
    set({ activeWorkspaceId: id, sessions: currentSessions });
    await Promise.allSettled([
      get().fetchSessions(id),
      get().fetchMemories(id),
      get().fetchFileTree(id),
    ]);
  },

  createWorkspace: async (payload: WorkspaceCreatePayload) => {
    const ws = await workspaceApi.create(payload);
    set((state) => ({
      workspaces: [ws, ...state.workspaces],
      workspaceSessions: { ...state.workspaceSessions, [ws.id]: [] },
    }));
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
      const updatedSessions = { ...state.workspaceSessions };
      delete updatedSessions[id];
      const nextActive = remaining.length > 0 ? remaining[0].id : null;
      return {
        workspaces: remaining,
        workspaceSessions: updatedSessions,
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
      const sessions = await sessionApi.list(workspaceId);
      set((state) => ({
        workspaceSessions: {
          ...state.workspaceSessions,
          [workspaceId]: sessions,
        },
        sessions: state.activeWorkspaceId === workspaceId ? sessions : state.sessions,
        isLoadingSessions: false,
      }));
      if (get().activeWorkspaceId === workspaceId) {
        if (sessions.length > 0) {
          const currentSession = get().activeSessionId;
          const targetSessionId =
            currentSession && sessions.some((s) => s.id === currentSession)
              ? currentSession
              : sessions[0].id;
          await get().setActiveSession(targetSessionId);
        } else {
          await get().setActiveSession(null);
        }
      }
    } catch {
      set((state) => ({
        workspaceSessions: {
          ...state.workspaceSessions,
          [workspaceId]: [],
        },
        sessions: state.activeWorkspaceId === workspaceId ? [] : state.sessions,
        isLoadingSessions: false,
      }));
      if (get().activeWorkspaceId === workspaceId) {
        await get().setActiveSession(null);
      }
    }
  },

  setActiveSession: async (id: string | null) => {
    set({ activeSessionId: id });
    if (!id) {
      useTaskStore.getState().setCurrentTaskId(null);
      return;
    }

    // 1. 如果任务 Store 中已有该会话的任务及消息，优先复用活跃上下文
    const existingTask = Object.values(useTaskStore.getState().tasks).find(
      (t) => t.session_id === id
    );
    if (existingTask && existingTask.messages.length > 0) {
      useTaskStore.getState().setCurrentTaskId(existingTask.id);
      return;
    }

    try {
      const turns = await sessionApi.getTurns(id);
      if (turns && turns.length > 0) {
        const taskId = `sess-history-${id}`;
        const messages: TaskMessage[] = turns.map((t) => ({
          id: `turn-${t.id}`,
          role: t.role,
          content: t.content,
          timestamp: new Date(t.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          tokensUsed: t.token_count,
        }));

        const totalSessionTokens = turns.reduce((acc, cur) => acc + (cur.token_count || 0), 0);
        const ctxTokens = 850 + (get().memories.length * 60) + totalSessionTokens;
        const waterPct = Number(((ctxTokens / 32000) * 100).toFixed(1));

        useTaskStore.getState().upsertTask({
          id: taskId,
          session_id: id,
          title: turns[0]?.content?.slice(0, 30) || '历史任务会话',
          prompt: turns[0]?.content || '',
          status: 'completed',
          permissionLevel: 'workspace_write',
          model: 'Dual-Tier Model Gateway',
          createdAt: turns[0]?.created_at || new Date().toISOString(),
          updatedAt: turns[turns.length - 1]?.created_at || new Date().toISOString(),
          messages,
          traceSteps: [],
          subagents: [],
          telemetry: {
            rounds: turns.length,
            steps: turns.length,
            tokenSpeed: 0,
            totalTokens: totalSessionTokens,
            contextTokens: ctxTokens,
            maxContextTokens: 32000,
            maxBudgetTokens: 200000,
            cacheHitRate: 1.0,
            waterLevelPct: waterPct,
            maxWaterLevelPct: 80,
          },
        });
        useTaskStore.getState().setCurrentTaskId(taskId);
      } else {
        useTaskStore.getState().setCurrentTaskId(null);
      }
    } catch (err) {
      console.error('Failed to load session turns:', err);
      useTaskStore.getState().setCurrentTaskId(null);
    }
  },

  createSession: async (title?: string, workspaceId?: string) => {
    const wsId = workspaceId || get().activeWorkspaceId;
    if (!wsId) throw new Error('请先选择或创建工作区');
    const session = await sessionApi.create(wsId, title || '新任务会话');
    
    set((state) => {
      const currentList = state.workspaceSessions[wsId] || [];
      const updatedList = [session, ...currentList.filter((s) => s.id !== session.id)];
      const updatedMap = {
        ...state.workspaceSessions,
        [wsId]: updatedList,
      };
      const isActiveWorkspace = state.activeWorkspaceId === wsId;
      return {
        workspaceSessions: updatedMap,
        sessions: isActiveWorkspace ? updatedList : state.sessions,
        activeWorkspaceId: wsId,
        activeSessionId: session.id,
      };
    });
    
    useTaskStore.getState().setCurrentTaskId(null);
    return session;
  },

  deleteSession: async (id: string, workspaceId?: string) => {
    const state = get();
    let targetWsId = workspaceId;
    if (!targetWsId) {
      for (const [wsId, sessList] of Object.entries(state.workspaceSessions)) {
        if (sessList.some((s) => s.id === id)) {
          targetWsId = wsId;
          break;
        }
      }
    }
    if (!targetWsId) {
      targetWsId = state.activeWorkspaceId || undefined;
    }

    await sessionApi.delete(id);

    set((currentState) => {
      const updatedMap = { ...currentState.workspaceSessions };
      if (targetWsId && updatedMap[targetWsId]) {
        updatedMap[targetWsId] = updatedMap[targetWsId].filter((s) => s.id !== id);
      }
      
      const currentSessions = currentState.activeWorkspaceId && updatedMap[currentState.activeWorkspaceId]
        ? updatedMap[currentState.activeWorkspaceId]
        : currentState.sessions.filter((s) => s.id !== id);

      const nextActiveId =
        currentState.activeSessionId === id
          ? (currentSessions.length > 0 ? currentSessions[0].id : null)
          : currentState.activeSessionId;

      return {
        workspaceSessions: updatedMap,
        sessions: currentSessions,
        activeSessionId: nextActiveId,
      };
    });

    const nextActive = get().activeSessionId;
    await get().setActiveSession(nextActive);
  },

  fetchMemories: async (workspaceId: string) => {
    set({ isLoadingMemories: true });
    try {
      const memView = await workspaceApi.getMemory(workspaceId);
      const facts: WorkspaceMemory[] = [];
      (memView.user_profile || []).forEach((item, idx) => {
        facts.push({
          id: `user-${idx}`,
          workspace_id: workspaceId,
          category: 'user_profile',
          title: `用户画像 / 偏好 #${idx + 1}`,
          content: item,
          pinned: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      });
      (memView.confirmed_architecture || []).forEach((item, idx) => {
        facts.push({
          id: `arch-${idx}`,
          workspace_id: workspaceId,
          category: 'confirmed_architecture',
          title: `知识库与领域定论 #${idx + 1}`,
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
          title: `工程准则与业务规范 #${idx + 1}`,
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
          title: `避坑与禁忌清单: ${item.action}`,
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
