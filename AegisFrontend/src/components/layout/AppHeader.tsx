/**
 * Aegis Modern Minimalist Top Navigation Header
 */

import React, { useState } from 'react';
import {
  Shield,
  FolderTree,
  ChevronDown,
  Plus,
  BookOpen,
  Settings,
  CheckCircle2,
  Database,
  Layers,
  Search,
  Command,
} from 'lucide-react';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { useUiStore } from '@/stores/useUiStore';

export const AppHeader: React.FC = () => {
  const { workspaces, activeWorkspaceId, setActiveWorkspace } = useWorkspaceStore();
  const {
    openWorkspaceModal,
    setRagCenterModalOpen,
    setSettingsModalOpen,
    setMemoryDrawerOpen,
    setContextDrawerOpen,
  } = useUiStore();

  const [wsDropdownOpen, setWsDropdownOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0];

  const filteredWorkspaces = workspaces.filter(
    (w) =>
      w.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      w.root_path.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <header className="flex items-center justify-between h-12 px-4 border-b border-slate-200 bg-white select-none text-xs z-30 shadow-2xs">
      {/* Left: Brand & Workspace Selector */}
      <div className="flex items-center gap-3">
        {/* Brand Shield Logo */}
        <div className="flex items-center gap-2 pr-3 border-r border-slate-200">
          <div className="w-6 h-6 rounded-lg bg-gradient-to-tr from-brand-600 to-brand-500 flex items-center justify-center text-white shadow-xs">
            <Shield className="w-3.5 h-3.5" />
          </div>
          <span className="font-bold text-slate-900 tracking-tight text-sm">
            Aegis<span className="text-brand-600 font-extrabold">Agent</span>
          </span>
          <span className="px-1.5 py-0.2 bg-brand-50 border border-brand-200 text-brand-700 font-mono text-[10px] rounded-md font-semibold">
            v4.0
          </span>
        </div>

        {/* Workspace Dropdown */}
        <div className="relative">
          <button
            onClick={() => setWsDropdownOpen(!wsDropdownOpen)}
            className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-800 font-medium transition shadow-2xs"
          >
            <FolderTree className="w-3.5 h-3.5 text-brand-600" />
            <span className="truncate max-w-[180px] font-semibold">
              {activeWorkspace ? activeWorkspace.name : '选择工作区...'}
            </span>
            <ChevronDown className="w-3 h-3 text-slate-400" />
          </button>

          {wsDropdownOpen && (
            <div
              className="absolute left-0 top-full mt-1.5 w-80 bg-white rounded-xl shadow-modal border border-slate-200 py-2 z-50 animate-in fade-in zoom-in-95 duration-100"
              onMouseLeave={() => setWsDropdownOpen(false)}
            >
              <div className="px-3 pb-2 border-b border-slate-100">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                  <input
                    type="text"
                    placeholder="过滤工作区名称或路径..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:border-brand-500 text-slate-800"
                    autoFocus
                  />
                </div>
              </div>

              <div className="max-h-60 overflow-y-auto px-1 py-1">
                {filteredWorkspaces.map((ws) => (
                  <button
                    key={ws.id}
                    onClick={() => {
                      setActiveWorkspace(ws.id);
                      setWsDropdownOpen(false);
                    }}
                    className={`w-full flex flex-col text-left px-3 py-2 rounded-lg hover:bg-slate-50 transition ${
                      ws.id === activeWorkspaceId ? 'bg-brand-50/70 text-brand-800 font-medium' : 'text-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="truncate font-semibold">{ws.name}</span>
                      {ws.id === activeWorkspaceId && <CheckCircle2 className="w-3.5 h-3.5 text-brand-600 shrink-0" />}
                    </div>
                    <span className="text-[11px] text-slate-400 font-mono truncate mt-0.5">{ws.root_path}</span>
                  </button>
                ))}
              </div>

              <div className="border-t border-slate-100 mt-1 pt-1.5 px-2">
                <button
                  onClick={() => {
                    setWsDropdownOpen(false);
                    openWorkspaceModal('create');
                  }}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs text-brand-600 hover:bg-brand-50 rounded-lg transition font-medium border border-dashed border-brand-200"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>新建工作区 (Create Workspace)</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Workspace Root Path Pill */}
        {activeWorkspace && (
          <span className="hidden xl:inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-slate-100/80 border border-slate-200 text-slate-500 font-mono text-[11px] truncate max-w-[320px]">
            <span>根路径:</span>
            <span className="text-slate-700 font-medium truncate">{activeWorkspace.root_path}</span>
          </span>
        )}
      </div>

      {/* Center: Command Palette Search Bar */}
      <div className="hidden md:flex items-center flex-1 max-w-xs mx-4">
        <button
          onClick={() => setRagCenterModalOpen(true)}
          className="w-full flex items-center justify-between px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-400 text-xs transition"
        >
          <div className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-slate-400" />
            <span>快捷搜索与规范检索...</span>
          </div>
          <kbd className="flex items-center gap-0.5 px-1.5 py-0.5 bg-white border border-slate-200 rounded text-[10px] font-mono text-slate-500 shadow-2xs">
            <Command className="w-2.5 h-2.5" />
            <span>K</span>
          </kbd>
        </button>
      </div>

      {/* Right: Modules, Drawers & System Settings */}
      <div className="flex items-center gap-2">
        {/* RAG Knowledge Base Center Button */}
        <button
          onClick={() => setRagCenterModalOpen(true)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white hover:bg-purple-50 text-slate-700 hover:text-purple-700 border border-slate-200 hover:border-purple-200 font-medium transition shadow-2xs"
          title="打开 AegisRAG 知识库与文档切片管理中心"
        >
          <BookOpen className="w-3.5 h-3.5 text-purple-600" />
          <span className="hidden sm:inline">RAG 知识库</span>
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
        </button>

        {/* Memory Pool Drawer Button */}
        <button
          onClick={() => setMemoryDrawerOpen(true)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white hover:bg-blue-50 text-slate-700 hover:text-brand-700 border border-slate-200 hover:border-blue-200 font-medium transition shadow-2xs"
          title="工作区长期记忆池 (架构定论与规范)"
        >
          <Database className="w-3.5 h-3.5 text-brand-600" />
          <span className="hidden md:inline">记忆池</span>
        </button>

        {/* 4-Tier Context Inspector */}
        <button
          onClick={() => setContextDrawerOpen(true)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white hover:bg-emerald-50 text-slate-700 hover:text-emerald-700 border border-slate-200 hover:border-emerald-200 font-medium transition shadow-2xs"
          title="四层上下文注入与 Token 水位透视"
        >
          <Layers className="w-3.5 h-3.5 text-emerald-600" />
          <span className="hidden md:inline">上下文</span>
        </button>

        {/* Settings Button */}
        <button
          onClick={() => setSettingsModalOpen(true)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 font-medium transition shadow-2xs"
          title="三道接入层安全闸门与系统设置"
        >
          <Settings className="w-3.5 h-3.5 text-slate-600" />
          <span className="hidden sm:inline">设置</span>
        </button>
      </div>
    </header>
  );
};
