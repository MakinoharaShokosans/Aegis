import React, { useState } from 'react';
import {
  Shield,
  FolderTree,
  ChevronDown,
  Plus,
  BookOpen,
  Settings,
  Key,
  CheckCircle2,
  Activity,
} from 'lucide-react';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { useUiStore } from '@/stores/useUiStore';

export const AppHeader: React.FC = () => {
  const { workspaces, activeWorkspaceId, setActiveWorkspace } = useWorkspaceStore();
  const { openWorkspaceModal, setRagCenterModalOpen, setSettingsModalOpen } = useUiStore();

  const [wsDropdownOpen, setWsDropdownOpen] = useState(false);

  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0];

  return (
    <header className="flex items-center justify-between h-11 px-3 border-b border-border-subtle bg-canvas-secondary select-none text-xs">
      {/* Left: Brand & Workspace Switcher */}
      <div className="flex items-center gap-3">
        {/* Brand */}
        <div className="flex items-center gap-2 pr-2 border-r border-border-subtle">
          <div className="w-5 h-5 rounded bg-brand-600 flex items-center justify-center text-white shadow-2xs">
            <Shield className="w-3.5 h-3.5" />
          </div>
          <span className="font-bold text-gray-900 tracking-tight">
            Aegis<span className="text-brand-600 font-extrabold">Agent</span>
          </span>
        </div>

        {/* Workspace Dropdown */}
        <div className="relative">
          <button
            onClick={() => setWsDropdownOpen(!wsDropdownOpen)}
            className="flex items-center gap-1.5 px-2 py-1 rounded bg-white hover:bg-gray-50 border border-border-subtle text-gray-800 font-medium shadow-2xs transition"
          >
            <FolderTree className="w-3.5 h-3.5 text-brand-600" />
            <span className="truncate max-w-[180px]">
              {activeWorkspace ? activeWorkspace.name : '选择工作区...'}
            </span>
            <ChevronDown className="w-3 h-3 text-gray-400" />
          </button>

          {wsDropdownOpen && (
            <div
              className="absolute left-0 top-full mt-1 w-64 bg-white rounded-lg shadow-xl border border-border-subtle py-1 z-50 animate-in fade-in zoom-in-95 duration-100"
              onMouseLeave={() => setWsDropdownOpen(false)}
            >
              <div className="px-3 py-1.5 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                工作区列表 (Workspaces)
              </div>
              <div className="max-h-56 overflow-y-auto">
                {workspaces.map((ws) => (
                  <button
                    key={ws.id}
                    onClick={() => {
                      setActiveWorkspace(ws.id);
                      setWsDropdownOpen(false);
                    }}
                    className={`w-full flex flex-col text-left px-3 py-1.5 hover:bg-gray-100 transition ${
                      ws.id === activeWorkspaceId ? 'bg-blue-50/70 text-brand-700 font-medium' : 'text-gray-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="truncate">{ws.name}</span>
                      {ws.id === activeWorkspaceId && <CheckCircle2 className="w-3 h-3 text-brand-600 shrink-0" />}
                    </div>
                    <span className="text-[10px] text-gray-400 font-mono truncate">{ws.root_path}</span>
                  </button>
                ))}
              </div>

              <div className="border-t border-border-subtle mt-1 pt-1 px-1">
                <button
                  onClick={() => {
                    setWsDropdownOpen(false);
                    openWorkspaceModal('create');
                  }}
                  className="w-full flex items-center gap-1.5 px-2 py-1.5 text-xs text-brand-600 hover:bg-blue-50 rounded transition font-medium"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>新建工作区 (Ctrl+Shift+N)</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Workspace Root Path Pill */}
        {activeWorkspace && (
          <span className="hidden md:inline-block px-2 py-0.5 rounded bg-gray-100/80 border border-gray-200 text-gray-500 font-mono text-[10px] truncate max-w-[280px]">
            {activeWorkspace.root_path}
          </span>
        )}
      </div>

      {/* Right: Modules, Sidecars, Security & Settings */}
      <div className="flex items-center gap-2">
        {/* RAG Knowledge Base Center Button */}
        <button
          onClick={() => setRagCenterModalOpen(true)}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-white hover:bg-purple-50 text-gray-700 hover:text-purple-700 border border-border-subtle font-medium transition shadow-2xs"
          title="打开 AegisRAG 知识库与文档索引管理中心"
        >
          <BookOpen className="w-3.5 h-3.5 text-purple-600" />
          <span>RAG 知识库</span>
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
        </button>

        {/* System Settings Button */}
        <button
          onClick={() => setSettingsModalOpen(true)}
          className="flex items-center gap-1 px-2 py-1 rounded bg-white hover:bg-gray-100 text-gray-700 border border-border-subtle font-medium transition shadow-2xs"
          title="系统配置与三道接入层安全闸门"
        >
          <Settings className="w-3.5 h-3.5 text-gray-500" />
          <span className="hidden sm:inline">设置</span>
        </button>

        {/* Token Guard Pill */}
        <div className="hidden lg:flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-50 border border-emerald-200 text-emerald-800 text-[10px] font-mono">
          <Key className="w-3 h-3 text-emerald-600" />
          <span>令牌: ●●●●●● (有效)</span>
        </div>

        {/* Sidecar Services Pulse */}
        <div className="hidden xl:flex items-center gap-2 px-2 py-0.5 rounded bg-gray-100 border border-gray-200 text-[10px] font-mono text-gray-600">
          <Activity className="w-3 h-3 text-emerald-600" />
          <span>Sidecars:</span>
          <span className="text-emerald-700 font-medium">RAG:8001 ●</span>
          <span className="text-emerald-700 font-medium">Shell:8002 ●</span>
          <span className="text-emerald-700 font-medium">Web:8003 ●</span>
        </div>
      </div>
    </header>
  );
};
