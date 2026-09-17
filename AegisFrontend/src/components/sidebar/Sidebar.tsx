import React, { useState } from 'react';
import {
  PanelLeftClose,
  PanelLeft,
  Plus,
  FolderTree,
  Settings,
  ChevronDown,
  MessageSquare,
  Shield,
  BrainCircuit,
  Activity,
  Trash2,
  FolderPlus,
  Edit2,
} from 'lucide-react';
import { useUiStore } from '@/stores/useUiStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { useTaskStore } from '@/stores/useTaskStore';

export const Sidebar: React.FC = () => {
  const {
    sidebarOpen,
    toggleSidebar,
    openWorkspaceModal,
    setSettingsModalOpen,
    setMemoryDrawerOpen,
  } = useUiStore();

  const {
    workspaces,
    activeWorkspaceId,
    sessions,
    activeSessionId,
    setActiveSession,
    createSession,
    deleteSession,
    memories,
  } = useWorkspaceStore();

  const { setCurrentTaskId } = useTaskStore();
  const [searchFilter, setSearchFilter] = useState('');

  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0];

  const filteredSessions = sessions.filter((s) =>
    s.title.toLowerCase().includes(searchFilter.toLowerCase())
  );

  const handleNewSession = async () => {
    const newSess = await createSession('新任务会话');
    setActiveSession(newSess.id);
    setCurrentTaskId(null);
  };

  if (!sidebarOpen) {
    return (
      <div className="flex flex-col items-center py-3 px-2 border-r border-border-subtle bg-canvas-secondary w-12 h-screen select-none shrink-0">
        <button
          onClick={toggleSidebar}
          className="p-1.5 rounded-md hover:bg-gray-200 text-gray-600 hover:text-gray-900 transition"
          title="展开侧边栏"
        >
          <PanelLeft className="w-5 h-5" />
        </button>
        <button
          onClick={handleNewSession}
          className="mt-4 p-1.5 rounded-md bg-brand-600 hover:bg-brand-700 text-white shadow-sm transition"
          title="新建会话 (⌘N)"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          onClick={() => setMemoryDrawerOpen(true)}
          className="mt-2 p-1.5 rounded-md hover:bg-purple-100 text-purple-600 transition"
          title="工作区共享记忆"
        >
          <BrainCircuit className="w-4 h-4" />
        </button>
        <div className="mt-auto flex flex-col items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500" title="Sidecar 存活: :8001 / :8002 / :8003" />
          <button
            onClick={() => setSettingsModalOpen(true)}
            className="p-1.5 rounded-md hover:bg-gray-200 text-gray-600 hover:text-gray-900 transition"
            title="系统设置与安全闸门"
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <aside className="flex flex-col w-64 h-screen border-r border-border-subtle bg-canvas-secondary select-none shrink-0">
      {/* Brand Header */}
      <div className="flex items-center justify-between px-3.5 py-3 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded bg-brand-600 flex items-center justify-center text-white text-xs font-bold shadow-xs">
            <Shield className="w-3.5 h-3.5" />
          </div>
          <div className="flex flex-col">
            <span className="font-bold text-sm tracking-tight text-gray-900">
              Aegis<span className="text-brand-600 font-extrabold">Agent</span>
            </span>
            <span className="text-[10px] text-gray-400 font-mono leading-none">Runtime UI v4.0</span>
          </div>
        </div>
        <button
          onClick={toggleSidebar}
          className="p-1 rounded hover:bg-gray-200 text-gray-500 hover:text-gray-800 transition"
          title="折叠侧边栏"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* New Session Action */}
      <div className="p-3">
        <button
          onClick={handleNewSession}
          className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-xs shadow-sm transition active:scale-[0.98]"
        >
          <Plus className="w-4 h-4" />
          <span>新建会话</span>
          <span className="ml-auto text-[10px] text-blue-200 font-mono">⌘N</span>
        </button>
      </div>

      {/* Workspace & Sessions Section */}
      <div className="flex-1 flex flex-col min-h-0 px-3">
        {/* Workspace Card Header */}
        <div className="flex items-center justify-between text-xs font-semibold text-gray-500 py-1.5">
          <span className="flex items-center gap-1">
            <FolderTree className="w-3.5 h-3.5 text-brand-600" />
            工作区 (一等公民)
          </span>
          <div className="flex items-center gap-1 text-gray-400">
            <button
              onClick={() => openWorkspaceModal('create')}
              className="p-1 hover:text-brand-600 hover:bg-gray-200 rounded"
              title="新建工作区"
            >
              <FolderPlus className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => openWorkspaceModal('edit')}
              className="p-1 hover:text-gray-700 hover:bg-gray-200 rounded"
              title="编辑当前工作区"
            >
              <Edit2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Directory & Task Tree */}
        <div className="mt-1 flex-1 overflow-y-auto space-y-1">
          {/* Active Workspace Node */}
          <div className="flex items-center justify-between px-2 py-1.5 text-xs font-medium text-gray-800 bg-gray-100/80 hover:bg-gray-200/70 rounded-md cursor-pointer group">
            <div className="flex items-center gap-1.5 truncate">
              <ChevronDown className="w-3.5 h-3.5 text-gray-500 shrink-0" />
              <span className="truncate">{activeWorkspace ? activeWorkspace.name : 'Aegis Core'}</span>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                openWorkspaceModal('delete');
              }}
              className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-100 text-gray-400 hover:text-red-600 transition"
              title="删除此工作区"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>

          {/* Workspace Shared Memory Entry */}
          <div className="pl-3.5 py-0.5">
            <button
              onClick={() => setMemoryDrawerOpen(true)}
              className="w-full flex items-center justify-between px-2 py-1 text-[11px] text-gray-600 hover:text-purple-700 hover:bg-purple-50 rounded transition"
            >
              <span className="flex items-center gap-1.5">
                <BrainCircuit className="w-3.5 h-3.5 text-purple-600" />
                <span>工作区共享记忆</span>
              </span>
              <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-purple-100 text-purple-700 font-mono">
                {memories.length}条定论
              </span>
            </button>
          </div>

          {/* Sessions List Header & Search */}
          <div className="pl-3.5 pt-2 pb-1 flex items-center justify-between text-[11px] font-medium text-gray-400">
            <span>会话列表 (1:N 级联)</span>
            <div className="relative">
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder="搜索会话..."
                className="w-24 px-1.5 py-0.5 text-[10px] bg-white border border-border-subtle rounded focus:outline-hidden"
              />
            </div>
          </div>

          {/* Sessions Tree Items */}
          <div className="pl-3.5 space-y-0.5">
            {filteredSessions.length === 0 ? (
              <div className="px-2 py-2 text-xs text-gray-400 italic">暂无历史任务会话</div>
            ) : (
              filteredSessions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => {
                    setActiveSession(s.id);
                    setCurrentTaskId('task-mock-default');
                  }}
                  className={`group w-full flex items-center justify-between px-2 py-1.5 text-xs rounded-md cursor-pointer transition ${
                    activeSessionId === s.id
                      ? 'bg-blue-50 text-brand-700 font-medium border-l-2 border-brand-600'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  }`}
                >
                  <div className="flex items-center gap-1.5 truncate flex-1">
                    <MessageSquare className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate">{s.title}</span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteSession(s.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-100 text-gray-400 hover:text-red-600 transition ml-1"
                    title="删除会话"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Sidecar Status & Footer Settings */}
      <div className="p-3 border-t border-border-subtle space-y-2 bg-canvas-secondary">
        {/* Sidecar Status Indicator */}
        <div className="flex items-center justify-between px-1 text-[10px] text-gray-500 font-mono">
          <span className="flex items-center gap-1">
            <Activity className="w-3 h-3 text-emerald-600" />
            Sidecars
          </span>
          <div className="flex items-center gap-1.5">
            <span className="text-emerald-700">RAG:8001 ●</span>
            <span className="text-emerald-700">Shell:8002 ●</span>
            <span className="text-emerald-700">Web:8003 ●</span>
          </div>
        </div>

        <button
          onClick={() => setSettingsModalOpen(true)}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-200 hover:text-gray-900 rounded-md transition"
        >
          <Settings className="w-4 h-4 text-gray-500" />
          <span className="font-medium">系统配置与安全闸门</span>
        </button>
      </div>
    </aside>
  );
};
