import { create } from 'zustand';
import type { Workspace, WorkspaceMemory, Session, FileNode, OpenTab, WorkspaceCreatePayload, WorkspaceUpdatePayload } from '@/types';
import { api } from '@/services/api';

interface WorkspaceState {
  // Workspaces
  workspaces: Workspace[];
  activeWorkspaceId: string | null;
  isLoadingWorkspaces: boolean;

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

  sessions: [],
  activeSessionId: null,
  isLoadingSessions: false,

  memories: [],
  isLoadingMemories: false,

  fileTree: null,
  isLoadingFileTree: false,

  tabs: [
    {
      id: 'tab-init-welcome',
      filePath: 'documents/agent_runtime/01_architecture_overview.md',
      title: '01_architecture_overview.md',
      language: 'markdown',
      content: `# AegisAgent 核心架构概览与技术设计\n\n欢迎来到 **AegisAgent + Workspace** 交互控制台。\n\n### 核心系统特征：\n1. **多工作区实体一等公民**：以物理根目录为 Ground Truth，隔离独立项目。\n2. **1:N 级联任务会话**：会话级 80%/40% 高低水位压缩与情境记忆。\n3. **三道接入层安全闸门**：Host 防 DNS 重绑定、Origin 防跨站、恒定时间 Token 鉴权。\n4. **双模型分层网关**：Reasoning 思考层 (DeepSeek-R1 / o1) + Fast 动作层 (DeepSeek-V3 / GPT-4o-mini)。\n5. **文档知识检索子智能体**：3 轮自适应改词 RAG，严格白名单行号引用与确定性拒答。\n6. **HITL 权限越级交互审批**：高危网络/系统动作阻塞式阻断与人工放行。\n`,
    },
  ],
  activeTabId: 'tab-init-welcome',

  fetchWorkspaces: async () => {
    set({ isLoadingWorkspaces: true });
    try {
      const data = await api.listWorkspaces();
      set({ workspaces: data, isLoadingWorkspaces: false });
      if (data.length > 0 && !get().activeWorkspaceId) {
        await get().setActiveWorkspace(data[0].id);
      }
    } catch {
      // Fallback local mock workspace if backend not initialized
      const fallbackWorkspaces: Workspace[] = [
        {
          id: 'ws-aegis-core',
          name: 'Aegis Core Runtime',
          root_path: '/home/Skualeilu/Projects/Aegis',
          description: 'AegisAgent 智能体核心运行时与多工作区调度系统',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          session_count: 3,
          memory_count: 3,
        },
      ];
      set({ workspaces: fallbackWorkspaces, activeWorkspaceId: 'ws-aegis-core', isLoadingWorkspaces: false });
      await get().fetchSessions('ws-aegis-core');
      await get().fetchMemories('ws-aegis-core');
    }
  },

  setActiveWorkspace: async (id: string) => {
    set({ activeWorkspaceId: id });
    await Promise.all([get().fetchSessions(id), get().fetchMemories(id), get().fetchFileTree(id)]);
  },

  createWorkspace: async (payload: WorkspaceCreatePayload) => {
    try {
      const ws = await api.createWorkspace(payload);
      set((state) => ({ workspaces: [ws, ...state.workspaces] }));
      await get().setActiveWorkspace(ws.id);
      return ws;
    } catch (err) {
      // Fallback local creation
      const newWs: Workspace = {
        id: `ws-${Date.now()}`,
        name: payload.name,
        root_path: payload.root_path,
        description: payload.description,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        session_count: 0,
        memory_count: 0,
      };
      set((state) => ({ workspaces: [newWs, ...state.workspaces] }));
      await get().setActiveWorkspace(newWs.id);
      return newWs;
    }
  },

  updateWorkspace: async (id: string, payload: WorkspaceUpdatePayload) => {
    try {
      const updated = await api.updateWorkspace(id, payload);
      set((state) => ({
        workspaces: state.workspaces.map((w) => (w.id === id ? { ...w, ...updated } : w)),
      }));
    } catch {
      set((state) => ({
        workspaces: state.workspaces.map((w) => (w.id === id ? { ...w, ...payload } : w)),
      }));
    }
  },

  deleteWorkspace: async (id: string) => {
    try {
      await api.deleteWorkspace(id);
    } catch {
      // ignore
    }
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
      const sessions = await api.listSessions(workspaceId);
      set({ sessions, isLoadingSessions: false });
      if (sessions.length > 0 && !get().activeSessionId) {
        set({ activeSessionId: sessions[0].id });
      }
    } catch {
      const fallbackSessions: Session[] = [
        {
          id: 'sess-auth-gate',
          workspace_id: workspaceId,
          title: '接入层三道安全闸门与鉴权中间件落地',
          status: 'active',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: 'sess-rag-hybrid',
          workspace_id: workspaceId,
          title: 'RAG 混合召回与 Cross-Encoder 语法感知切分',
          status: 'active',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: 'sess-water-level',
          workspace_id: workspaceId,
          title: '记忆引擎 80%/40% 水位线压缩机制验证',
          status: 'active',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ];
      set({ sessions: fallbackSessions, activeSessionId: 'sess-auth-gate', isLoadingSessions: false });
    }
  },

  setActiveSession: (id: string | null) => set({ activeSessionId: id }),

  createSession: async (title?: string) => {
    const wsId = get().activeWorkspaceId;
    if (!wsId) throw new Error('No active workspace');
    try {
      const session = await api.createSession(wsId, title);
      set((state) => ({ sessions: [session, ...state.sessions], activeSessionId: session.id }));
      return session;
    } catch {
      const newSession: Session = {
        id: `sess-${Date.now()}`,
        workspace_id: wsId,
        title: title || '新会话任务',
        status: 'active',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      set((state) => ({ sessions: [newSession, ...state.sessions], activeSessionId: newSession.id }));
      return newSession;
    }
  },

  deleteSession: async (id: string) => {
    try {
      await api.deleteSession(id);
    } catch {
      // ignore
    }
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
      const memoryView = await api.getWorkspaceMemory(workspaceId);
      const mappedMemories: WorkspaceMemory[] = [];
      memoryView.confirmed_architecture.forEach((item, idx) => {
        mappedMemories.push({
          id: `arch-${idx}`,
          workspace_id: workspaceId,
          category: 'confirmed_architecture',
          title: item.length > 25 ? `${item.slice(0, 25)}...` : item,
          content: item,
          pinned: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      });
      memoryView.project_conventions.forEach((item, idx) => {
        mappedMemories.push({
          id: `conv-${idx}`,
          workspace_id: workspaceId,
          category: 'project_conventions',
          title: item.length > 25 ? `${item.slice(0, 25)}...` : item,
          content: item,
          pinned: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      });
      memoryView.failed_attempts.forEach((item, idx) => {
        mappedMemories.push({
          id: `fail-${idx}`,
          workspace_id: workspaceId,
          category: 'global_failed_attempts',
          title: item.action.length > 25 ? `${item.action.slice(0, 25)}...` : item.action,
          content: `失败原因: ${item.failure_reason}\n结论: ${item.conclusion || ''}`,
          pinned: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      });
      set({ memories: mappedMemories, isLoadingMemories: false });
    } catch {
      const fallbackMemories: WorkspaceMemory[] = [
        {
          id: 'mem-1',
          workspace_id: workspaceId,
          category: 'confirmed_architecture',
          title: '三道接入层闸门前置拓扑',
          content: '所有进入 Agent 的请求必须依次通过 Host 闸门 -> Origin 闸门 -> Token 恒定时间闸门，且严禁绕过。',
          pinned: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: 'mem-2',
          workspace_id: workspaceId,
          category: 'project_conventions',
          title: '双模型分层调用原则',
          content: '规划反思与大局拆解必须使用 Reasoning 模型 (DeepSeek-R1 / o1, temp=0.0)，动作执行使用 Fast 模型 (temp=0.2)。',
          pinned: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: 'mem-3',
          workspace_id: workspaceId,
          category: 'global_failed_attempts',
          title: '严禁在沙箱外直接执行 rm -rf 或 sudo',
          content: '所有文件增删改必须通过工作区受限 FileOps 或带有 512MB 限制的 Sidecar 沙箱执行。',
          pinned: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ];
      set({ memories: fallbackMemories, isLoadingMemories: false });
    }
  },

  createMemory: async (payload) => {
    const wsId = get().activeWorkspaceId;
    if (!wsId) return;
    try {
      if (payload.category === 'global_failed_attempts') {
        await api.recordWorkspaceFailure(wsId, {
          action: payload.title,
          failure_reason: payload.content,
          conclusion: payload.title,
        });
      } else {
        await api.promoteWorkspaceFact(wsId, {
          fact: `${payload.title}: ${payload.content}`,
          category: payload.category,
        });
      }
      await get().fetchMemories(wsId);
    } catch {
      const localMem: WorkspaceMemory = {
        id: `mem-${Date.now()}`,
        workspace_id: wsId,
        category: payload.category as WorkspaceMemory['category'],
        title: payload.title,
        content: payload.content,
        pinned: !!payload.pinned,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      set((state) => ({ memories: [localMem, ...state.memories] }));
    }
  },

  deleteMemory: async (memoryId: string) => {
    const wsId = get().activeWorkspaceId;
    if (!wsId) return;
    set((state) => ({ memories: state.memories.filter((m) => m.id !== memoryId) }));
  },

  fetchFileTree: async (workspaceId: string) => {
    set({ isLoadingFileTree: true });
    try {
      const tree = await api.getFileTree(workspaceId);
      set({ fileTree: tree, isLoadingFileTree: false });
    } catch {
      set({ isLoadingFileTree: false });
    }
  },

  openTab: (tabData) => {
    set((state) => {
      const existing = state.tabs.find((t) => t.filePath === tabData.filePath);
      if (existing) {
        return { activeTabId: existing.id };
      }
      const newTab: OpenTab = {
        ...tabData,
        id: `tab-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
      };
      return {
        tabs: [...state.tabs, newTab],
        activeTabId: newTab.id,
      };
    });
  },

  openFileFromWorkspace: async (relativePath: string) => {
    const wsId = get().activeWorkspaceId;
    const existing = get().tabs.find((t) => t.filePath === relativePath);
    if (existing) {
      set({ activeTabId: existing.id });
      return;
    }

    try {
      if (wsId) {
        const fileData = await api.getFileContent(wsId, relativePath);
        get().openTab({
          filePath: fileData.path,
          title: fileData.path.split('/').pop() || fileData.path,
          language: fileData.language,
          content: fileData.content,
        });
        return;
      }
    } catch {
      // Fallback
    }

    const title = relativePath.split('/').pop() || relativePath;
    const language = relativePath.endsWith('.py') ? 'python' : relativePath.endsWith('.md') ? 'markdown' : 'plaintext';
    get().openTab({
      filePath: relativePath,
      title,
      language,
      content: `# ${relativePath}\n\n// AegisAgent 实时读取文档/代码内容`,
    });
  },

  closeTab: (tabId) => {
    set((state) => {
      const remaining = state.tabs.filter((t) => t.id !== tabId);
      let nextActive = state.activeTabId;
      if (state.activeTabId === tabId) {
        nextActive = remaining.length > 0 ? remaining[remaining.length - 1].id : null;
      }
      return {
        tabs: remaining,
        activeTabId: nextActive,
      };
    });
  },

  setActiveTab: (tabId) => set({ activeTabId: tabId }),

  updateTabContent: (tabId, content) => {
    set((state) => ({
      tabs: state.tabs.map((t) => (t.id === tabId ? { ...t, content, isModified: true, isStale: false } : t)),
    }));
  },

  saveCurrentTab: async () => {
    const activeTab = get().tabs.find((t) => t.id === get().activeTabId);
    const wsId = get().activeWorkspaceId;
    if (!activeTab || !wsId) return;

    try {
      await api.saveFileContent(wsId, activeTab.filePath, activeTab.content);
      set((state) => ({
        tabs: state.tabs.map((t) => (t.id === activeTab.id ? { ...t, isModified: false } : t)),
      }));
    } catch {
      // ignore
    }
  },

  setTabStale: (filePath, isStale) => {
    set((state) => ({
      tabs: state.tabs.map((t) => (t.filePath === filePath ? { ...t, isStale } : t)),
    }));
  },
}));
