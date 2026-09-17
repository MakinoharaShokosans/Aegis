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
          title="新会话"
        >
          <Plus className="w-4 h-4" />
        </button>
        <div className="mt-auto">
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
          <div className="w-5 h-5 rounded bg-brand-600 flex items-center justify-center text-white text-xs font-bold">
            A
          </div>
          <span className="font-bold text-sm tracking-tight text-gray-900">
            deepseek <span className="text-gray-500 font-semibold text-xs tracking-wider">HARNESS</span>
          </span>
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
          <span>新会话</span>
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
            <button className="p-1 hover:text-gray-700 hover:bg-gray-200 rounded">
              <Search className="w-3.5 h-3.5" />
            </button>
            <button className="p-1 hover:text-gray-700 hover:bg-gray-200 rounded">
              <ListFilter className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Directory & Task Tree */}
        <div className="mt-1 flex-1 overflow-y-auto space-y-1">
          <div className="flex items-center gap-1.5 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-100 rounded cursor-pointer">
            <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
            <span>📁 Aegis</span>
          </div>

          <div className="pl-4 space-y-0.5">
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

      {/* Footer Settings */}
      <div className="p-3 border-t border-border-subtle">
        <button className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-200 hover:text-gray-900 rounded-md transition">
          <Settings className="w-4 h-4 text-gray-500" />
          <span className="font-medium">设置与偏好</span>
        </button>
      </div>
    </aside>
  );
};
