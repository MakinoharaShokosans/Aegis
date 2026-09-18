/**
 * Aegis Modern Minimalist Chat Stage
 * Main conversation pane with dual-view mode (Chat / Trace), Hero Dashboard, and HITL gate cards.
 */

import React, { useRef, useEffect } from 'react';
import {
  Bot,
  Activity,
  Zap,
  AlertTriangle,
  FolderTree,
  Plus,
} from 'lucide-react';
import { AegisLogo } from '@/components/common/AegisLogo';
import { useUiStore } from '@/stores/useUiStore';
import { useTaskStore } from '@/stores/useTaskStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import type { PermissionLevel } from '@/types';
import { MessageBubble } from './MessageBubble';
import { HitlApprovalCard } from './HitlApprovalCard';
import { TraceTimeline } from './TraceTimeline';
import { InputConsole } from './InputConsole';

export const ChatPane: React.FC = () => {
  const { activeView, setActiveView, openWorkspaceModal } = useUiStore();
  const {
    currentTaskId,
    tasks,
    submitTask,
    approveAction,
    rejectAction,
    cancelCurrentTask,
  } = useTaskStore();
  const {
    openFileFromWorkspace,
    activeSessionId,
    activeWorkspaceId,
    workspaces,
    setActiveWorkspace,
    createSession,
  } = useWorkspaceStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const currentTask = currentTaskId ? tasks[currentTaskId] : null;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentTask?.messages, currentTask?.traceSteps]);

  const handleSend = async (prompt: string, options: { permissionLevel: PermissionLevel; model: string }) => {
    let wsId = activeWorkspaceId;
    if (!wsId) {
      if (workspaces.length > 0) {
        await setActiveWorkspace(workspaces[0].id);
        wsId = workspaces[0].id;
      } else {
        openWorkspaceModal('create');
        return;
      }
    }

    let sessId = activeSessionId;
    if (!sessId) {
      const sessionTitle = prompt.trim().slice(0, 24) || '新任务会话';
      const newSess = await createSession(sessionTitle);
      sessId = newSess.id;
    }
    await submitTask(sessId, prompt, options);
  };

  const handleOpenFile = (path: string) => {
    openFileFromWorkspace(path);
  };

  return (
    <div className="flex flex-col h-full bg-white select-none relative">
      {/* 1. Sub-Header: Mode Switcher & Real-time Guards Pill */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-200 bg-slate-50/70 z-10">
        <div className="flex items-center gap-1 bg-slate-200/80 p-0.5 rounded-lg text-xs font-medium">
          <button
            onClick={() => setActiveView('chat')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition ${
              activeView === 'chat'
                ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Bot className="w-3.5 h-3.5 text-brand-600" />
            <span>对话协商</span>
          </button>

          <button
            onClick={() => setActiveView('trace')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition ${
              activeView === 'trace'
                ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Activity className="w-3.5 h-3.5 text-purple-600" />
            <span>执行轨迹 (Trace)</span>
          </button>
        </div>

        {/* Subagent / HITL Status Badge */}
        <div className="flex items-center gap-2">
          {currentTask?.subagents && currentTask.subagents.some((s) => s.status === 'running') && (
            <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-purple-50 border border-purple-200 text-purple-700 text-[11px] font-medium animate-pulse">
              <Zap className="w-3 h-3 text-purple-600" />
              <span>1 个子智能体运行中</span>
            </span>
          )}

          {currentTask?.status === 'waiting_for_approval' && (
            <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-50 border border-amber-300 text-amber-800 text-[11px] font-medium">
              <AlertTriangle className="w-3 h-3 text-amber-600" />
              <span>等待人机审批 (HITL)</span>
            </span>
          )}
        </div>
      </div>

      {/* 2. Main Stage Content */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
        {activeView === 'trace' ? (
          <TraceTimeline steps={currentTask?.traceSteps || []} />
        ) : (
          <div className="space-y-6 max-w-3xl mx-auto">
            {/* 1. When no workspace connected at all */}
            {workspaces.length === 0 ? (
              <div className="py-12 space-y-6 animate-in fade-in duration-200 text-center max-w-lg mx-auto">
                <div className="w-16 h-16 rounded-2xl bg-brand-50 border border-brand-200 flex items-center justify-center mx-auto text-brand-600 shadow-card">
                  <FolderTree className="w-8 h-8" />
                </div>
                <div className="space-y-2">
                  <h3 className="font-bold text-slate-900 text-xl">请先接入本地工程工作区</h3>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    工作区作为物理真源 (Ground Truth)，代表本地代码工程根目录。智能体在此工作区下开启任务会话、执行受限读写并沉淀长期记忆。
                  </p>
                </div>
                <button
                  onClick={() => openWorkspaceModal('create')}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-700 text-white font-medium text-xs shadow-md transition"
                >
                  <Plus className="w-4 h-4" />
                  <span>立即接入工作区 (Connect Workspace)</span>
                </button>
              </div>
            ) : (!currentTask || currentTask.messages.length === 0) ? (
              <div className="py-16 flex flex-col items-center justify-center text-center select-none animate-in fade-in duration-300 relative">
                {/* Background decorative glow */}
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none -z-10">
                  <div className="w-72 h-72 bg-brand-500/5 rounded-full blur-3xl" />
                  <div className="w-48 h-48 bg-purple-500/5 rounded-full blur-2xl -translate-y-4" />
                </div>

                {/* Aegis Shield Brand Emblem */}
                <div className="relative mb-5 group transition-transform duration-300 hover:scale-105">
                  <AegisLogo size="xl" glow showStatus status="online" />
                </div>

                {/* Title and Tagline */}
                <h2 className="text-xl font-bold text-slate-900 tracking-tight">AegisAgent</h2>
                <p className="text-xs text-slate-500 mt-1.5 max-w-sm leading-relaxed">
                  高可信代码智能体 · 物理真源隔离与全流程安全护航
                </p>

                {/* Active Workspace Info Pill */}
                <div className="mt-4 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-slate-50 border border-slate-200/80 text-[11px] text-slate-600 shadow-2xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-500" />
                  <span>当前工作区：</span>
                  <span className="font-semibold text-slate-800">
                    {workspaces.find((w) => w.id === activeWorkspaceId)?.name || '未选择'}
                  </span>
                </div>
              </div>
            ) : null}

            {/* Conversation Messages */}
            {currentTask?.messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} onOpenFile={handleOpenFile} />
            ))}

            {/* HITL Interactive Approval Card */}
            {currentTask?.status === 'waiting_for_approval' && currentTask.pendingApproval && (
              <HitlApprovalCard
                approval={currentTask.pendingApproval}
                onApprove={(apprId, decision, feedback) =>
                  approveAction(currentTask.id, apprId, decision, feedback)
                }
                onReject={(apprId, reason) => rejectAction(currentTask.id, apprId, reason)}
              />
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* 3. Floating Bottom Input Console */}
      <InputConsole
        onSend={handleSend}
        onCancel={cancelCurrentTask}
        telemetry={currentTask?.telemetry}
        isExecuting={currentTask?.status === 'running'}
        disabled={currentTask?.status === 'waiting_for_approval'}
      />
    </div>
  );
};
