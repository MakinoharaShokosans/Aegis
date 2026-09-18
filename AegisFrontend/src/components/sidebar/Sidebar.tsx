/**
 * Aegis Modern Minimalist Sidebar
 * Supports segmented switching between Sessions, Files, and Memory Pools.
 */

import React, { useState } from 'react';
import {
  PanelLeftClose,
  PanelLeft,
  Plus,
  Settings,
  BrainCircuit,
  MessageSquare,
  FolderTree,
  FolderPlus,
  Layers,
} from 'lucide-react';
import { useUiStore } from '@/stores/useUiStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { useTaskStore } from '@/stores/useTaskStore';
import { ProjectsTree } from './ProjectsTree';
import { WorkspaceTree } from './WorkspaceTree';

export const Sidebar: React.FC = () => {
  const {
    sidebarOpen,
    toggleSidebar,
    openWorkspaceModal,
    setSettingsModalOpen,
    setMemoryDrawerOpen,
    setContextDrawerOpen,
  } = useUiStore();

  const {
    activeWorkspaceId,
    memories,
    createSession,
    setActiveSession,
  } = useWorkspaceStore();

  const { setCurrentTaskId } = useTaskStore();

  const [activeTab, setActiveTab] = useState<'projects' | 'files' | 'memory'>('projects');

  const handleNewSession = async () => {
    if (!activeWorkspaceId) {
      openWorkspaceModal('create');
      return;
    }
    const newSess = await createSession('新任务会话');
    setActiveSession(newSess.id);
    setCurrentTaskId(null);
  };

  if (!sidebarOpen) {
    return (
      <aside className="flex flex-col items-center py-3 px-2 border-r border-slate-200 bg-white w-12 h-full select-none shrink-0 z-10 shadow-2xs">
        <button
          onClick={toggleSidebar}
          className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-800 transition"
          title="展开侧边栏"
        >
          <PanelLeft className="w-4 h-4" />
        </button>

        <button
          onClick={() => openWorkspaceModal('create')}
          className="mt-4 p-2 rounded-lg bg-amber-500 hover:bg-amber-600 text-white shadow-xs transition"
          title="接入本地工程工作区"
        >
          <FolderPlus className="w-4 h-4" />
        </button>

        <button
          onClick={handleNewSession}
          disabled={!activeWorkspaceId}
          className="mt-2 p-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white shadow-xs transition disabled:opacity-40"
          title="新建任务会话"
        >
          <Plus className="w-4 h-4" />
        </button>

        <div className="my-3 w-6 h-[1px] bg-slate-200" />

        <button
          onClick={() => {
            toggleSidebar();
            setActiveTab('projects');
          }}
          className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-brand-600 transition"
          title="项目与会话树 (Projects)"
        >
          <MessageSquare className="w-4 h-4" />
        </button>

        <button
          onClick={() => {
            toggleSidebar();
            setActiveTab('files');
          }}
          className="mt-1 p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 hover:text-brand-600 transition"
          title="工作区文件树"
        >
          <FolderTree className="w-4 h-4" />
        </button>

        <button
          onClick={() => setMemoryDrawerOpen(true)}
          className="mt-1 p-1.5 rounded-lg hover:bg-purple-50 text-purple-600 transition"
          title="长期共享记忆池"
        >
          <BrainCircuit className="w-4 h-4" />
        </button>

        <div className="mt-auto flex flex-col items-center gap-2">
          <button
            onClick={() => setSettingsModalOpen(true)}
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-800 transition"
            title="系统设置与安全闸门"
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </aside>
    );
  }

  return (
    <aside className="flex flex-col w-64 h-full border-r border-slate-200 bg-white select-none shrink-0 z-10">
      {/* Sidebar Top Navigation Header */}
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-slate-100">
        <span className="font-semibold text-xs text-slate-700">资源导航</span>
        <button
          onClick={toggleSidebar}
          className="p-1 rounded-md hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition"
          title="折叠侧边栏"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* Segmented View Switcher */}
      <div className="px-3 pt-2.5 pb-1">
        <div className="flex items-center p-0.5 bg-slate-100 rounded-lg text-xs font-medium text-slate-600">
          <button
            onClick={() => setActiveTab('projects')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1 rounded-md transition ${
              activeTab === 'projects'
                ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                : 'hover:text-slate-900'
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5 text-brand-600" />
            <span>项目树</span>
          </button>

          <button
            onClick={() => setActiveTab('files')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1 rounded-md transition ${
              activeTab === 'files'
                ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                : 'hover:text-slate-900'
            }`}
          >
            <FolderTree className="w-3.5 h-3.5 text-amber-500" />
            <span>文件</span>
          </button>

          <button
            onClick={() => setActiveTab('memory')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1 rounded-md transition ${
              activeTab === 'memory'
                ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                : 'hover:text-slate-900'
            }`}
          >
            <BrainCircuit className="w-3.5 h-3.5 text-purple-600" />
            <span>记忆</span>
          </button>
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 flex flex-col min-h-0 p-3 pt-1">
        {activeTab === 'projects' && <ProjectsTree />}

        {activeTab === 'files' && <WorkspaceTree />}

        {activeTab === 'memory' && (
          <div className="flex flex-col h-full space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-500 font-medium px-1">
              <span>长期记忆池 ({memories.length})</span>
              <button
                onClick={() => setMemoryDrawerOpen(true)}
                className="text-brand-600 hover:text-brand-700 text-[11px] font-semibold"
              >
                查看全部
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
              {memories.length === 0 ? (
                <div className="text-center py-8 text-xs text-slate-400 italic">暂无沉淀记忆</div>
              ) : (
                memories.slice(0, 6).map((m) => (
                  <div
                    key={m.id}
                    onClick={() => setMemoryDrawerOpen(true)}
                    className="p-2 rounded-lg bg-slate-50 hover:bg-purple-50/50 border border-slate-200/80 cursor-pointer transition text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-800 truncate">{m.title}</span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-purple-100 text-purple-700 font-mono">
                        {m.category === 'user_profile'
                          ? '画像'
                          : m.category === 'confirmed_architecture'
                          ? '知识库'
                          : m.category === 'project_conventions'
                          ? '准则'
                          : '避坑'}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500 line-clamp-2 mt-1">{m.content}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer Settings & Context Button */}
      <div className="p-3 border-t border-slate-100 space-y-1.5 bg-slate-50/60">
        <button
          onClick={() => setContextDrawerOpen(true)}
          className="w-full flex items-center justify-between px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg transition"
        >
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-emerald-600" />
            <span>四层上下文透视</span>
          </div>
          <span className="text-[10px] text-emerald-700 font-mono font-medium">80%/40%</span>
        </button>

        <button
          onClick={() => setSettingsModalOpen(true)}
          className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg transition"
        >
          <Settings className="w-4 h-4 text-slate-500" />
          <span className="font-medium">安全闸门与配置</span>
        </button>
      </div>
    </aside>
  );
};
