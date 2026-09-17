/**
 * Aegis Modern Minimalist Chat Stage
 * Main conversation pane with dual-view mode (Chat / Trace), Hero Dashboard, and HITL gate cards.
 */

import React, { useRef, useEffect } from 'react';
import {
  Shield,
  Bot,
  Layers,
  Activity,
  Zap,
  AlertTriangle,
  Sparkles,
  BookOpen,
  FileCode2,
  ArrowRight,
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
  const { activeView, setActiveView, setContextDrawerOpen, setRagCenterModalOpen } = useUiStore();
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

  const handleQuickPrompt = (prompt: string) => {
    handleSend(prompt, {
      permissionLevel: 'workspace_write',
      model: 'Reasoning: DeepSeek-R1 / Fast: DeepSeek-V3',
    });
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

          <button
            onClick={() => setContextDrawerOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1 rounded-md text-slate-600 hover:text-slate-900 transition"
          >
            <Layers className="w-3.5 h-3.5 text-emerald-600" />
            <span>四层上下文透视</span>
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
            {/* Hero Welcome Dashboard (when no messages or task is new) */}
            {(!currentTask || currentTask.messages.length === 0) && (
              <div className="py-8 space-y-6 animate-in fade-in duration-200">
                <div className="text-center space-y-2">
                  <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-brand-600 to-brand-500 flex items-center justify-center mx-auto text-white shadow-card">
                    <Shield className="w-6 h-6" />
                  </div>
                  <h3 className="font-bold text-slate-900 text-lg">AegisAgent 智能体就绪</h3>
                  <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
                    基于双模型分层网关、三道接入层安全闸门与自适应 RAG 知识检索，安全调度工作区。
                  </p>
                </div>

                {/* Quick Action Prompt Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                  <button
                    onClick={() => handleQuickPrompt('请检索 11_http_api.md 与 01_architecture_overview.md，验证三道接入层闸门的实现次序')}
                    className="p-3.5 rounded-xl bg-white hover:bg-brand-50/40 border border-slate-200 hover:border-brand-200 text-left transition group shadow-2xs hover:shadow-xs flex flex-col justify-between space-y-2"
                  >
                    <div className="flex items-center gap-2 text-brand-600 font-semibold text-xs">
                      <BookOpen className="w-4 h-4" />
                      <span>检索鉴权与安全闸门规范</span>
                    </div>
                    <p className="text-[11px] text-slate-500 leading-relaxed">
                      调用 delegate_doc_search 提取 11_http_api.md 契约中的 Host/Origin/Token 要求
                    </p>
                    <div className="flex items-center gap-1 text-[10px] text-brand-600 font-medium pt-1">
                      <span>立即执行</span>
                      <ArrowRight className="w-2.5 h-2.5 group-hover:translate-x-0.5 transition" />
                    </div>
                  </button>

                  <button
                    onClick={() => handleQuickPrompt('请在 AegisAgent/src/agent_runtime/api/routes 下创建 files.py 路由，提供递归文件树与受限读写')}
                    className="p-3.5 rounded-xl bg-white hover:bg-blue-50/40 border border-slate-200 hover:border-blue-200 text-left transition group shadow-2xs hover:shadow-xs flex flex-col justify-between space-y-2"
                  >
                    <div className="flex items-center gap-2 text-blue-600 font-semibold text-xs">
                      <FileCode2 className="w-4 h-4" />
                      <span>实现工作区受限文件读写</span>
                    </div>
                    <p className="text-[11px] text-slate-500 leading-relaxed">
                      编写文件树扫描与内容覆写端点，严格防御 Path Traversal 路径穿越
                    </p>
                    <div className="flex items-center gap-1 text-[10px] text-blue-600 font-medium pt-1">
                      <span>立即执行</span>
                      <ArrowRight className="w-2.5 h-2.5 group-hover:translate-x-0.5 transition" />
                    </div>
                  </button>

                  <button
                    onClick={() => setRagCenterModalOpen(true)}
                    className="p-3.5 rounded-xl bg-white hover:bg-purple-50/40 border border-slate-200 hover:border-purple-200 text-left transition group shadow-2xs hover:shadow-xs flex flex-col justify-between space-y-2"
                  >
                    <div className="flex items-center gap-2 text-purple-600 font-semibold text-xs">
                      <Sparkles className="w-4 h-4" />
                      <span>RAG 知识库切片与检索测试</span>
                    </div>
                    <p className="text-[11px] text-slate-500 leading-relaxed">
                      进入知识库中心对工作区文档执行 AST 切片并进行密集+稀疏双路召回
                    </p>
                    <div className="flex items-center gap-1 text-[10px] text-purple-600 font-medium pt-1">
                      <span>打开知识库</span>
                      <ArrowRight className="w-2.5 h-2.5 group-hover:translate-x-0.5 transition" />
                    </div>
                  </button>

                  <button
                    onClick={() => handleQuickPrompt('请运行 pytest 验证 AegisAgent 的 234 个测试用例，并报告测试覆盖结果')}
                    className="p-3.5 rounded-xl bg-white hover:bg-emerald-50/40 border border-slate-200 hover:border-emerald-200 text-left transition group shadow-2xs hover:shadow-xs flex flex-col justify-between space-y-2"
                  >
                    <div className="flex items-center gap-2 text-emerald-600 font-semibold text-xs">
                      <Shield className="w-4 h-4" />
                      <span>运行全套单元与集成测试</span>
                    </div>
                    <p className="text-[11px] text-slate-500 leading-relaxed">
                      执行 pytest 验证安全闸门中间件、物理预算看门狗与 MCP 审查规则
                    </p>
                    <div className="flex items-center gap-1 text-[10px] text-emerald-600 font-medium pt-1">
                      <span>立即执行</span>
                      <ArrowRight className="w-2.5 h-2.5 group-hover:translate-x-0.5 transition" />
                    </div>
                  </button>
                </div>
              </div>
            )}

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
        telemetry={currentTask?.telemetry}
        disabled={currentTask?.status === 'waiting_for_approval'}
      />
    </div>
  );
};
