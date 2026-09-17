import React from 'react';
import {
  PanelLeftClose,
  PanelLeft,
  Plus,
  Search,
  ListFilter,
  FolderTree,
  Settings,
  ChevronDown,
  MessageSquare,
  Shield,
  BrainCircuit,
  Activity,
} from 'lucide-react';
import { useUiStore } from '@/stores/useUiStore';
import { useTaskStore } from '@/stores/useTaskStore';

export const Sidebar: React.FC = () => {
  const { sidebarOpen, toggleSidebar } = useUiStore();
  const { currentTaskId, setCurrentTaskId, tasks } = useTaskStore();

  const taskList = Object.values(tasks);

  if (!sidebarOpen) {
    return (
      <div className="flex flex-col items-center py-3 px-2 border-r border-border-subtle bg-canvas-secondary w-12 h-screen select-none">
        <button
          onClick={toggleSidebar}
          className="p-1.5 rounded-md hover:bg-gray-200 text-gray-600 hover:text-gray-900 transition"
          title="展开侧边栏"
        >
          <PanelLeft className="w-5 h-5" />
        </button>
        <button
          onClick={() => setCurrentTaskId(null)}
          className="mt-4 p-1.5 rounded-md bg-brand-600 hover:bg-brand-700 text-white shadow-sm transition"
          title="新建会话"
        >
          <Plus className="w-4 h-4" />
        </button>
        <div className="mt-auto flex flex-col items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500" title="Sidecar 服务正常 (:8001/:8002/:8003)" />
          <button
            className="p-1.5 rounded-md hover:bg-gray-200 text-gray-600 hover:text-gray-900 transition"
            title="设置"
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <aside className="flex flex-col w-64 h-screen border-r border-border-subtle bg-canvas-secondary select-none">
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
            <span className="text-[10px] text-gray-400 font-mono leading-none">Runtime UI v2.0</span>
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
          onClick={() => setCurrentTaskId(null)}
          className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-xs shadow-sm transition active:scale-[0.98]"
        >
          <Plus className="w-4 h-4" />
          <span>新建会话</span>
          <span className="ml-auto text-[10px] text-blue-200 font-mono">⌘N</span>
        </button>
      </div>

      {/* Workspace & Sessions Section */}
      <div className="flex-1 flex flex-col min-h-0 px-3">
        <div className="flex items-center justify-between text-xs font-semibold text-gray-500 py-1.5">
          <span className="flex items-center gap-1">
            <FolderTree className="w-3.5 h-3.5" />
            工作区
          </span>
          <div className="flex items-center gap-1 text-gray-400">
            <button className="p-1 hover:text-gray-700 hover:bg-gray-200 rounded" title="搜索会话">
              <Search className="w-3.5 h-3.5" />
            </button>
            <button className="p-1 hover:text-gray-700 hover:bg-gray-200 rounded" title="过滤">
              <ListFilter className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Directory & Task Tree */}
        <div className="mt-1 flex-1 overflow-y-auto space-y-1">
          {/* Active Workspace Node */}
          <div className="flex items-center justify-between px-2 py-1 text-xs font-medium text-gray-800 bg-gray-100/70 hover:bg-gray-100 rounded cursor-pointer">
            <div className="flex items-center gap-1.5 truncate">
              <ChevronDown className="w-3.5 h-3.5 text-gray-500 shrink-0" />
              <span className="truncate">📁 Aegis Core</span>
            </div>
            <span className="text-[10px] text-gray-400 font-mono shrink-0">:root</span>
          </div>

          {/* Workspace Shared Memory Shortcut */}
          <div className="pl-3.5 py-0.5">
            <button className="w-full flex items-center gap-1.5 px-2 py-1 text-[11px] text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded transition">
              <BrainCircuit className="w-3 h-3 text-purple-600" />
              <span>工作区共享记忆 (3条定论)</span>
            </button>
          </div>

          {/* Session List */}
          <div className="pl-3.5 space-y-0.5">
            {taskList.length === 0 ? (
              <div className="px-2 py-2 text-xs text-gray-400 italic">暂无历史任务</div>
            ) : (
              taskList.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setCurrentTaskId(t.id)}
                  className={`w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-left rounded-md transition ${
                    currentTaskId === t.id
                      ? 'bg-blue-50 text-brand-700 font-medium border-l-2 border-brand-600'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  }`}
                >
                  <MessageSquare className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate flex-1">{t.title || t.prompt || '未命名任务'}</span>
                  <span className="text-[10px] text-gray-400 shrink-0">刚刚</span>
                </button>
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

        <button className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-200 hover:text-gray-900 rounded-md transition">
          <Settings className="w-4 h-4 text-gray-500" />
          <span className="font-medium">系统配置与安全闸门</span>
        </button>
      </div>
    </aside>
  );
};
