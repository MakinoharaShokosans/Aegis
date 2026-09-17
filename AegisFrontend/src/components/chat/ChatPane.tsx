import React, { useRef, useEffect } from 'react';
import {
  Shield,
  Bot,
  Layers,
  Activity,
  Zap,
  AlertTriangle,
} from 'lucide-react';
import { useUiStore } from '@/stores/useUiStore';
import { useTaskStore } from '@/stores/useTaskStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import type { PermissionLevel } from '@/types';
import { MessageBubble } from './MessageBubble';
import { HitlApprovalCard } from './HitlApprovalCard';
import { TraceTimeline } from './TraceTimeline';
import { InputConsole } from './InputConsole';

export const ChatPane: React.FC = () => {
  const { activeView, setActiveView, setContextDrawerOpen } = useUiStore();
  const {
    currentTaskId,
    tasks,
    submitTask,
    approveAction,
    rejectAction,
  } = useTaskStore();
  const { openFileFromWorkspace, activeSessionId } = useWorkspaceStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const currentTask = currentTaskId ? tasks[currentTaskId] : null;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentTask?.messages, currentTask?.traceSteps]);

  const handleSend = async (prompt: string, options: { permissionLevel: PermissionLevel; model: string }) => {
    const sessId = activeSessionId || 'sess-default';
    await submitTask(sessId, prompt, options);
  };

  const handleOpenFile = (path: string) => {
    openFileFromWorkspace(path);
  };

  return (
    <div className="flex flex-col h-screen bg-canvas-primary select-none">
      {/* 1. Sub-Header: Mode Switcher & Subagents Indicator */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border-subtle bg-canvas-secondary">
        <div className="flex items-center gap-1 bg-gray-200/80 p-0.5 rounded-lg text-xs font-medium">
          <button
            onClick={() => setActiveView('chat')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition ${
              activeView === 'chat'
                ? 'bg-white text-gray-900 shadow-2xs font-semibold'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <Bot className="w-3.5 h-3.5 text-brand-600" />
            <span>对话协商</span>
          </button>
          <button
            onClick={() => setActiveView('trace')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition ${
              activeView === 'trace'
                ? 'bg-white text-gray-900 shadow-2xs font-semibold'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <Activity className="w-3.5 h-3.5 text-purple-600" />
            <span>执行轨迹 (Trace)</span>
          </button>
          <button
            onClick={() => setContextDrawerOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1 rounded-md text-gray-600 hover:text-gray-900 transition"
          >
            <Layers className="w-3.5 h-3.5 text-blue-600" />
            <span>四层上下文透视</span>
          </button>
        </div>

        {/* Subagents Status Pill */}
        <div className="flex items-center gap-2">
          {currentTask?.subagents && currentTask.subagents.some((s) => s.status === 'running') && (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-50 border border-purple-200 text-purple-700 text-[11px] font-medium animate-pulse">
              <Zap className="w-3 h-3" />
              1 个子智能体运行中
            </span>
          )}
          {currentTask?.status === 'waiting_for_approval' && (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 border border-amber-300 text-amber-800 text-[11px] font-medium">
              <AlertTriangle className="w-3 h-3 text-amber-600" />
              等待人机审批 (HITL)
            </span>
          )}
        </div>
      </div>

      {/* 2. Main Stage Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {activeView === 'trace' ? (
          <TraceTimeline steps={currentTask?.traceSteps || []} />
        ) : (
          <div className="space-y-6 max-w-3xl mx-auto">
            {(!currentTask || currentTask.messages.length === 0) && (
              <div className="text-center py-16 space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-brand-50 border border-brand-100 flex items-center justify-center mx-auto text-brand-600 shadow-sm">
                  <Shield className="w-6 h-6" />
                </div>
                <h3 className="font-bold text-gray-800 text-base">AegisAgent 智能体就绪</h3>
                <p className="text-xs text-gray-400 max-w-md mx-auto">
                  输入任务目标，调用双模型分层网关拆解里程碑、分派文档知识检索子智能体并安全执行工作区操作。
                </p>
              </div>
            )}

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
        telemetry={currentTask?.telemetry}
        disabled={currentTask?.status === 'waiting_for_approval'}
      />
    </div>
  );
};
