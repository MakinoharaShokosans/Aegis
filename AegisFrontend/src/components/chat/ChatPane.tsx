import React, { useState, useRef, useEffect } from 'react';
import {
  Shield,
  Bot,
  User,
  ExternalLink,
  ThumbsUp,
  ThumbsDown,
  Paperclip,
  ArrowUp,
  Layers,
  Activity,
  Zap,
  AlertTriangle,
  CheckCircle2,
  Droplet,
  Clock,
  FileCode2,
  CheckSquare,
  Square,
  Search,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { useUiStore } from '@/stores/useUiStore';
import { useTaskStore } from '@/stores/useTaskStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import type { PermissionLevel } from '@/types';

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

  const [inputVal, setInputVal] = useState('');
  const [permissionLevel, setPermissionLevel] = useState<PermissionLevel>('workspace_write');
  const [selectedModel, setSelectedModel] = useState('Reasoning: DeepSeek-R1 / Fast: DeepSeek-V3');
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const currentTask = currentTaskId ? tasks[currentTaskId] : null;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentTask?.messages, currentTask?.traceSteps]);

  const handleSend = async () => {
    if (!inputVal.trim()) return;
    const prompt = inputVal;
    setInputVal('');
    const sessId = activeSessionId || 'sess-default';
    await submitTask(sessId, prompt, {
      permissionLevel,
      model: selectedModel,
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
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
          /* ================= Trace & Causality View ================= */
          <div className="space-y-4 max-w-3xl mx-auto">
            <div className="flex items-center justify-between text-xs text-gray-500 font-mono px-1">
              <span>LangGraph 节点跃迁与叶子工具事件流水 (EventBus)</span>
              <span>单步状态机耗时与 Token 增量</span>
            </div>

            <div className="relative pl-6 border-l-2 border-gray-200 space-y-4">
              {currentTask?.traceSteps.map((step) => (
                <div key={step.id} className="relative group">
                  <div className="absolute -left-[31px] top-1.5 w-4 h-4 rounded-full bg-white border-2 border-brand-600 flex items-center justify-center">
                    <div className="w-1.5 h-1.5 rounded-full bg-brand-600" />
                  </div>
                  <div className="p-3.5 rounded-xl border border-border-subtle bg-white hover:border-brand-300 shadow-2xs space-y-2 transition">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 font-mono text-xs">
                        <span className="px-2 py-0.5 rounded bg-brand-50 text-brand-700 font-bold uppercase">
                          Step #{step.step}: {step.node}
                        </span>
                        <span className="text-gray-400">{step.timestamp}</span>
                      </div>
                      <div className="flex items-center gap-2 text-[11px] font-mono text-gray-500">
                        <span>⏱ {step.durationMs}ms</span>
                        {step.tokenUsage && <span>📊 {step.tokenUsage} tok</span>}
                      </div>
                    </div>
                    {step.inputSummary && (
                      <div className="text-xs text-gray-700 font-mono bg-gray-50 p-2 rounded border border-gray-100">
                        <span className="text-gray-400">入参摘要: </span>
                        {step.inputSummary}
                      </div>
                    )}
                    {step.outputSummary && (
                      <div className="text-xs text-gray-800 font-mono bg-blue-50/40 p-2 rounded border border-blue-100">
                        <span className="text-blue-500">出参判定: </span>
                        {step.outputSummary}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          /* ================= Chat Stream View ================= */
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
              <div key={msg.id} className="space-y-3">
                {msg.role === 'user' ? (
                  /* User Prompt Card */
                  <div className="flex items-start gap-3 justify-end">
                    <div className="bg-brand-600 text-white rounded-2xl rounded-tr-xs px-4 py-2.5 max-w-[85%] text-xs leading-relaxed shadow-sm">
                      {msg.content}
                    </div>
                    <div className="w-7 h-7 rounded-full bg-brand-700 text-white flex items-center justify-center shrink-0 text-xs font-bold shadow-xs">
                      <User className="w-4 h-4" />
                    </div>
                  </div>
                ) : msg.role === 'system' ? (
                  /* System Alert Card */
                  <div className="p-3 bg-gray-100 border border-gray-200 rounded-xl text-gray-700 text-xs flex items-center gap-2">
                    <Shield className="w-4 h-4 text-gray-500 shrink-0" />
                    <span>{msg.content}</span>
                  </div>
                ) : (
                  /* Assistant Complex Response Card */
                  <div className="flex items-start gap-3">
                    <div className="w-7 h-7 rounded-full bg-brand-50 border border-brand-200 text-brand-600 flex items-center justify-center shrink-0 text-xs font-bold shadow-xs">
                      <Bot className="w-4 h-4" />
                    </div>
                    <div className="flex-1 space-y-3.5 min-w-0">
                      <div className="bg-white border border-border-subtle rounded-2xl rounded-tl-xs p-4 text-xs leading-relaxed shadow-xs space-y-3.5">
                        {/* Markdown Text */}
                        <div className="prose prose-sm max-w-none text-gray-800">
                          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                            {msg.content}
                          </ReactMarkdown>
                        </div>

                        {/* 1. Dynamic Milestones Checklist */}
                        {msg.milestones && msg.milestones.length > 0 && (
                          <div className="p-3 bg-gray-50/80 rounded-xl border border-gray-200/70 space-y-2">
                            <div className="text-[11px] font-semibold text-gray-600 flex items-center gap-1.5">
                              <CheckSquare className="w-3.5 h-3.5 text-brand-600" />
                              <span>阶段目标与里程碑达成 (State Machine Milestones)</span>
                            </div>
                            <div className="space-y-1.5 pl-1">
                              {msg.milestones.map((m) => (
                                <div key={m.id} className="flex items-center gap-2 text-xs text-gray-700">
                                  {m.status === 'completed' ? (
                                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                                  ) : (
                                    <Square className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                                  )}
                                  <span className={m.status === 'completed' ? 'line-through text-gray-500' : ''}>
                                    {m.title}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* 2. Subagent Report Envelopes (Doc Search & Research) */}
                        {msg.subagentReports && msg.subagentReports.length > 0 && (
                          <div className="space-y-2">
                            {msg.subagentReports.map((report, idx) => (
                              <div
                                key={idx}
                                className="p-3.5 rounded-xl border border-purple-200 bg-purple-50/40 space-y-2"
                              >
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-1.5 font-semibold text-purple-900 text-xs">
                                    <Search className="w-3.5 h-3.5 text-purple-600" />
                                    <span>{report.title}</span>
                                  </div>
                                  <span className="px-2 py-0.5 rounded bg-purple-100 text-purple-800 text-[10px] font-mono">
                                    RAG 确定性召回
                                  </span>
                                </div>
                                <p className="text-gray-700 text-[11px] leading-relaxed">{report.summary}</p>
                                {report.citations && (
                                  <div className="flex flex-wrap gap-1.5 pt-1">
                                    {report.citations.map((cite, cIdx) => (
                                      <button
                                        key={cIdx}
                                        onClick={() => handleOpenFile(cite.split(':')[0])}
                                        className="px-2 py-0.5 rounded bg-white hover:bg-purple-100 border border-purple-200 text-purple-700 text-[10px] font-mono transition flex items-center gap-1"
                                      >
                                        <span>📄 {cite}</span>
                                        <ExternalLink className="w-2.5 h-2.5" />
                                      </button>
                                    ))}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}

                        {/* 3. File Mutations Cards Grid */}
                        {msg.fileMutations && msg.fileMutations.length > 0 && (
                          <div className="space-y-2 pt-1">
                            <div className="text-[11px] font-semibold text-gray-600 flex items-center gap-1">
                              <FileCode2 className="w-3.5 h-3.5 text-blue-600" />
                              <span>本次工作区改动 ({msg.fileMutations.length} 个文件)</span>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                              {msg.fileMutations.map((mut, idx) => (
                                <div
                                  key={idx}
                                  className="p-2.5 rounded-xl border border-border-subtle bg-gray-50/60 hover:bg-white hover:border-brand-300 transition space-y-1 group"
                                >
                                  <div className="flex items-center justify-between">
                                    <span className="font-mono font-medium text-gray-900 truncate max-w-[170px]">
                                      {mut.path.split('/').pop()}
                                    </span>
                                    <button
                                      onClick={() => handleOpenFile(mut.path)}
                                      className="flex items-center gap-1 px-2 py-0.5 rounded bg-white hover:bg-blue-50 border border-border-subtle text-brand-600 text-[10px] font-medium transition"
                                    >
                                      <span>打开</span>
                                      <ExternalLink className="w-2.5 h-2.5" />
                                    </button>
                                  </div>
                                  <div className="text-[10px] text-gray-400 font-mono truncate">{mut.path}</div>
                                  <p className="text-[11px] text-gray-600 line-clamp-2">{mut.summary}</p>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Footer Meta: Time, Model, Feedback */}
                        <div className="flex items-center justify-between text-[11px] text-gray-400 pt-2 border-t border-gray-100">
                          <div className="flex items-center gap-3">
                            <span className="flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              {msg.durationMs ? `${(msg.durationMs / 1000).toFixed(1)}s` : '刚刚'}
                            </span>
                            {msg.tokensUsed && <span>📊 {msg.tokensUsed} tok</span>}
                          </div>
                          <div className="flex items-center gap-2">
                            <button className="p-1 hover:text-gray-700 hover:bg-gray-100 rounded" title="赞同">
                              <ThumbsUp className="w-3 h-3" />
                            </button>
                            <button className="p-1 hover:text-gray-700 hover:bg-gray-100 rounded" title="反馈">
                              <ThumbsDown className="w-3 h-3" />
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}

            {/* HITL Interactive Approval Card */}
            {currentTask?.status === 'waiting_for_approval' && currentTask.pendingApproval && (
              <div className="p-4 rounded-2xl border-2 border-amber-400 bg-amber-50/50 shadow-md space-y-3 animate-in fade-in zoom-in-95">
                <div className="flex items-center gap-2 text-amber-900 font-bold text-xs">
                  <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                  <span>🛡 人机协同权限越级审批卡片 (HITL Approval Required)</span>
                </div>
                <div className="text-xs text-amber-800 space-y-1">
                  <div>
                    检测到越级高危操作：<strong>{currentTask.pendingApproval.reason}</strong>
                  </div>
                  <pre className="p-2.5 bg-gray-900 text-emerald-400 font-mono text-[11px] rounded-lg overflow-x-auto">
                    $ {currentTask.pendingApproval.command}
                  </pre>
                </div>

                {!showRejectInput ? (
                  <div className="flex items-center gap-2 pt-1">
                    <button
                      onClick={() =>
                        approveAction(currentTask.id, currentTask.pendingApproval!.approval_id, 'once')
                      }
                      className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-xs transition"
                    >
                      批准本次 (Once)
                    </button>
                    <button
                      onClick={() =>
                        approveAction(currentTask.id, currentTask.pendingApproval!.approval_id, 'always')
                      }
                      className="px-3 py-1.5 rounded-lg bg-white hover:bg-gray-100 border border-amber-300 text-amber-900 text-xs font-medium transition"
                    >
                      当前会话免审 (Always)
                    </button>
                    <button
                      onClick={() => setShowRejectInput(true)}
                      className="px-3 py-1.5 rounded-lg bg-white hover:bg-red-50 border border-red-300 text-red-700 text-xs font-medium transition ml-auto"
                    >
                      拒绝并指示改道 (Reject)
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2 pt-1">
                    <input
                      type="text"
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      placeholder="输入拒绝原因与重规划指示（例如: 禁止推送远端，仅在本地创建 patch 文件）..."
                      className="w-full px-3 py-1.5 border border-red-300 rounded-lg text-xs bg-white focus:outline-hidden"
                    />
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setShowRejectInput(false)}
                        className="px-2.5 py-1 text-xs text-gray-500 hover:bg-gray-200 rounded"
                      >
                        取消
                      </button>
                      <button
                        onClick={() =>
                          rejectAction(
                            currentTask.id,
                            currentTask.pendingApproval!.approval_id,
                            rejectReason || '用户拒绝执行该高危指令'
                          )
                        }
                        className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white rounded text-xs font-medium"
                      >
                        确认拒绝
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* 3. Floating Bottom Input Console */}
      <div className="p-3 border-t border-border-subtle bg-canvas-secondary space-y-2 select-none">
        <div className="max-w-3xl mx-auto space-y-2">
          {/* Input Box */}
          <div className="relative rounded-2xl border border-border-subtle bg-white shadow-xs focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-100 transition p-2.5 space-y-2">
            <textarea
              rows={2}
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入任务目标，/ 调用 Slash 指令，@ 引用工作区文档、规范或共享记忆..."
              className="w-full text-xs text-gray-800 placeholder-gray-400 focus:outline-hidden resize-none leading-relaxed"
            />

            {/* Input Controls Bar */}
            <div className="flex items-center justify-between pt-1 border-t border-gray-100 text-xs">
              <div className="flex items-center gap-2">
                {/* Permission Level Selector */}
                <select
                  value={permissionLevel}
                  onChange={(e) => setPermissionLevel(e.target.value as PermissionLevel)}
                  className="px-2 py-1 rounded bg-gray-50 hover:bg-gray-100 border border-gray-200 text-[11px] font-medium text-gray-700 focus:outline-hidden cursor-pointer"
                >
                  <option value="readonly">🔒 只读免审批 (readonly)</option>
                  <option value="workspace_write">🛡 工作区修改 (workspace_write - 默认)</option>
                  <option value="full_access">⚡ 全权限模式 (full_access - 需审批)</option>
                </select>

                {/* Model Gateway Selector */}
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="hidden sm:inline-block px-2 py-1 rounded bg-gray-50 hover:bg-gray-100 border border-gray-200 text-[11px] font-medium text-gray-700 focus:outline-hidden cursor-pointer"
                >
                  <option value="Reasoning: DeepSeek-R1 / Fast: DeepSeek-V3">
                    🧠 Dual-Tier: DeepSeek-R1 + V3
                  </option>
                  <option value="Reasoning: OpenAI o1 / Fast: GPT-4o-mini">
                    🧠 Dual-Tier: OpenAI o1 + 4o-mini
                  </option>
                  <option value="Fast Only: DeepSeek-V3">⚡ Fast Only: DeepSeek-V3</option>
                </select>
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition"
                  title="添加附件"
                >
                  <Paperclip className="w-4 h-4" />
                </button>
                <button
                  onClick={handleSend}
                  disabled={!inputVal.trim()}
                  className="p-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white transition disabled:opacity-40 disabled:hover:bg-brand-600 shadow-xs"
                >
                  <ArrowUp className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          {/* 4. Real-time Telemetry Status Bar */}
          <div className="flex items-center justify-between text-[10px] font-mono text-gray-500 px-1">
            <div className="flex items-center gap-3">
              <span>🔄 {currentTask?.telemetry.rounds || 5} 轮 {currentTask?.telemetry.steps || 14} 步</span>
              <span>⚡ {currentTask?.telemetry.tokenSpeed || 271} tok/s</span>
              <span>📊 {((currentTask?.telemetry.totalTokens || 28500) / 1000).toFixed(1)}k tok</span>
              <span className="text-emerald-700">🎯 缓存命中 99.8%</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Droplet className="w-3 h-3 text-blue-600" />
              <span>记忆水位 {currentTask?.telemetry.waterLevelPct || 32}% / 80%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
