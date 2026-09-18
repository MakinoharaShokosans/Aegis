/**
 * Aegis Projects & Sessions Tree Navigator
 * Features:
 * - Tree structure: Workspaces as parent folders, Sessions as children
 * - Collapsible folders with persisted or toggleable expansion state
 * - Active session highlight, relative timestamps (e.g., 14m, 1d, 3d), running indicator spinner
 * - Quick "+" session creation per workspace & global "FolderPlus" for new workspace
 * - Smooth vertical scrolling and search filtering
 */

import React, { useState } from 'react';
import {
  Folder,
  FolderOpen,
  FolderPlus,
  Plus,
  Trash2,
  ChevronDown,
  ChevronRight,
  ListFilter,
  Loader2,
  X,
  Search,
} from 'lucide-react';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { useTaskStore } from '@/stores/useTaskStore';
import { useUiStore } from '@/stores/useUiStore';
import { formatRelativeTime } from '@/utils/time';
import type { Session } from '@/types';

export const ProjectsTree: React.FC = () => {
  const {
    workspaces,
    workspaceSessions,
    activeWorkspaceId,
    activeSessionId,
    setActiveWorkspace,
    setActiveSession,
    createSession,
    deleteSession,
  } = useWorkspaceStore();

  const { tasks, currentTaskId, setCurrentTaskId } = useTaskStore();
  const { openWorkspaceModal } = useUiStore();

  // Expansion state per workspace ID (default all open)
  const [collapsedMap, setCollapsedMap] = useState<Record<string, boolean>>({});
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const toggleCollapse = (wsId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setCollapsedMap((prev) => ({
      ...prev,
      [wsId]: !prev[wsId],
    }));
  };

  const handleSelectWorkspace = async (wsId: string) => {
    if (activeWorkspaceId !== wsId) {
      await setActiveWorkspace(wsId);
    }
  };

  const handleSelectSession = async (wsId: string, sessId: string) => {
    if (activeWorkspaceId !== wsId) {
      await setActiveWorkspace(wsId);
    }
    await setActiveSession(sessId);
    setCurrentTaskId(null);
  };

  const handleCreateSession = async (wsId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    // Ensure folder is expanded
    setCollapsedMap((prev) => ({ ...prev, [wsId]: false }));
    const newSess = await createSession('新任务会话', wsId);
    await setActiveSession(newSess.id);
    setCurrentTaskId(null);
  };

  const handleDeleteSession = async (sessId: string, wsId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await deleteSession(sessId, wsId);
  };

  // Determine if a session is currently running an active task
  const isSessionRunning = (sessId: string) => {
    if (!sessId) return false;
    const currentTask = currentTaskId ? tasks[currentTaskId] : null;
    if (currentTask && currentTask.session_id === sessId) {
      return (
        currentTask.status === 'running' ||
        currentTask.status === 'waiting_for_approval'
      );
    }
    return false;
  };

  // Filter workspaces & sessions
  const query = searchQuery.trim().toLowerCase();
  const filteredWorkspaces = workspaces.filter((ws) => {
    if (!query) return true;
    const matchWsName = ws.name.toLowerCase().includes(query);
    const sessions = workspaceSessions[ws.id] || [];
    const matchSessions = sessions.some((s) => s.title.toLowerCase().includes(query));
    return matchWsName || matchSessions;
  });

  return (
    <div className="flex flex-col h-full select-none text-slate-700">
      {/* Top Header: Projects + Action Icons */}
      <div className="flex items-center justify-between px-2 py-2 mb-1">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold text-slate-500 tracking-wide">
            Projects
          </span>
          {workspaces.length > 0 && (
            <span className="text-[10px] text-slate-400 font-mono">
              ({workspaces.length})
            </span>
          )}
        </div>

        <div className="flex items-center gap-1 text-slate-400">
          <button
            onClick={() => setShowSearch(!showSearch)}
            className={`p-1 rounded hover:bg-slate-100 hover:text-slate-700 transition ${
              showSearch || searchQuery ? 'text-brand-600 bg-slate-100' : ''
            }`}
            title="搜索工作区与会话"
          >
            <ListFilter className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => openWorkspaceModal('create')}
            className="p-1 rounded hover:bg-slate-100 hover:text-slate-800 transition"
            title="接入本地工程工作区"
          >
            <FolderPlus className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Optional Search Bar */}
      {showSearch && (
        <div className="relative mb-2 px-1">
          <Search className="w-3 h-3 text-slate-400 absolute left-3 top-2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索工作区或会话..."
            autoFocus
            className="w-full pl-7 pr-6 py-1 text-xs bg-slate-50 border border-slate-200 rounded-md focus:outline-none focus:border-brand-500 text-slate-800"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      )}

      {/* Main Tree List - Vertically Scrollable */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
        {workspaces.length === 0 ? (
          <div className="text-center py-8 px-2 space-y-3">
            <div className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400">
              <Folder className="w-4 h-4" />
            </div>
            <div className="text-xs text-slate-500">尚未接入任何本地工程</div>
            <button
              onClick={() => openWorkspaceModal('create')}
              className="px-3 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold shadow-xs transition inline-flex items-center gap-1.5"
            >
              <FolderPlus className="w-3.5 h-3.5" />
              <span>接入工作区</span>
            </button>
          </div>
        ) : filteredWorkspaces.length === 0 ? (
          <div className="text-center py-8 text-xs text-slate-400">
            无匹配的工作区或会话
          </div>
        ) : (
          filteredWorkspaces.map((ws) => {
            const isCollapsed = !!collapsedMap[ws.id];
            const isCurrentWsActive = activeWorkspaceId === ws.id;
            const sessions: Session[] = workspaceSessions[ws.id] || [];
            const filteredSessions = query
              ? sessions.filter((s) => s.title.toLowerCase().includes(query))
              : sessions;

            return (
              <div key={ws.id} className="space-y-0.5">
                {/* Workspace Folder Row */}
                <div
                  onClick={() => {
                    handleSelectWorkspace(ws.id);
                    toggleCollapse(ws.id);
                  }}
                  className={`group flex items-center justify-between px-1.5 py-1 rounded-md cursor-pointer transition ${
                    isCurrentWsActive
                      ? 'text-slate-900 font-semibold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70'
                  }`}
                >
                  <div className="flex items-center gap-1.5 truncate flex-1 min-w-0">
                    <button
                      onClick={(e) => toggleCollapse(ws.id, e)}
                      className="p-0.5 text-slate-400 hover:text-slate-600 rounded transition shrink-0"
                    >
                      {isCollapsed ? (
                        <ChevronRight className="w-3 h-3" />
                      ) : (
                        <ChevronDown className="w-3 h-3" />
                      )}
                    </button>

                    {isCollapsed ? (
                      <Folder className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    ) : (
                      <FolderOpen className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    )}

                    <span className="truncate text-xs">{ws.name}</span>
                  </div>

                  {/* Hover Actions: Quick Add Session */}
                  <div className="flex items-center opacity-0 group-hover:opacity-100 transition shrink-0">
                    <button
                      onClick={(e) => handleCreateSession(ws.id, e)}
                      className="p-0.5 text-slate-400 hover:text-brand-600 hover:bg-slate-200/50 rounded transition"
                      title="在此工作区新建会话"
                    >
                      <Plus className="w-3 h-3" />
                    </button>
                  </div>
                </div>

                {/* Child Sessions List */}
                {!isCollapsed && (
                  <div className="space-y-0.5">
                    {filteredSessions.length === 0 ? (
                      <div className="pl-7 py-1 text-[11px] text-slate-400 italic flex items-center justify-between pr-2">
                        <span>暂无会话</span>
                        <button
                          onClick={(e) => handleCreateSession(ws.id, e)}
                          className="text-brand-600 hover:text-brand-700 flex items-center gap-0.5 font-medium not-italic"
                        >
                          <Plus className="w-2.5 h-2.5" />
                          <span>新建</span>
                        </button>
                      </div>
                    ) : (
                      filteredSessions.map((sess) => {
                        const isSelected =
                          activeSessionId === sess.id && activeWorkspaceId === ws.id;
                        const running = isSessionRunning(sess.id);
                        const relTime = formatRelativeTime(
                          sess.updated_at || sess.created_at
                        );

                        return (
                          <div
                            key={sess.id}
                            onClick={() => handleSelectSession(ws.id, sess.id)}
                            className={`group relative flex items-center justify-between pl-7 pr-2 py-1.5 rounded-md cursor-pointer transition text-xs ${
                              isSelected
                                ? 'bg-slate-200/80 text-slate-900 font-medium'
                                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/80'
                            }`}
                          >
                            <span className="truncate flex-1 min-w-0 pr-1.5">
                              {sess.title}
                            </span>

                            {/* Right Status / Timestamp / Delete */}
                            <div className="flex items-center shrink-0">
                              {running ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-500" />
                              ) : (
                                <>
                                  <span className="text-[11px] text-slate-400 font-mono group-hover:hidden">
                                    {relTime}
                                  </span>
                                  <button
                                    onClick={(e) => handleDeleteSession(sess.id, ws.id, e)}
                                    className="hidden group-hover:flex p-0.5 text-slate-400 hover:text-rose-600 rounded transition"
                                    title="删除会话"
                                  >
                                    <Trash2 className="w-3 h-3" />
                                  </button>
                                </>
                              )}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
