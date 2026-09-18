import React, { useState, useEffect } from 'react';
import {
  X,
  Layers,
  Sparkles,
  Brain,
  MessageSquare,
  Copy,
  Check,
  Activity,
  Loader2,
} from 'lucide-react';
import { useUiStore } from '@/stores/useUiStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { useTaskStore } from '@/stores/useTaskStore';
import { sessionApi } from '@/api';
import type { SessionContextResponse } from '@/types';

export const ContextDrawer: React.FC = () => {
  const { contextDrawerOpen, setContextDrawerOpen } = useUiStore();
  const { memories, activeSessionId } = useWorkspaceStore();
  const { currentTaskId, tasks } = useTaskStore();

  const [copied, setCopied] = useState(false);
  const [contextData, setContextData] = useState<SessionContextResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const currentTask = currentTaskId ? tasks[currentTaskId] : null;

  // 尝试从后端获取最新的真实上下文装配切片
  useEffect(() => {
    if (contextDrawerOpen && activeSessionId) {
      setIsLoading(true);
      sessionApi
        .getContext(activeSessionId)
        .then((res) => {
          setContextData(res);
        })
        .catch((err) => {
          console.warn('Failed to load session context preview, fallback to store:', err);
        })
        .finally(() => {
          setIsLoading(false);
        });
    }
  }, [contextDrawerOpen, activeSessionId]);

  if (!contextDrawerOpen) return null;

  // 基础系统提示词
  const systemPrompt = `You are AegisAgent, an advanced deterministic autonomous coding and engineering assistant.
Workspace is Ground Truth. Always verify contracts against documents/*.md before modifying source code.
Dual-Tier Execution: High-level planning with Reasoning model (gpt-5.6-terra), leaf actions with Fast model (gpt-5.4-mini / gpt-5.6-luna).
HITL Security Discipline: Out-of-bounds file writes or network egress commands must be suspended for human approval.`;

  // 计算四层 Token 真实分布
  const layer1Tokens = contextData?.layers_breakdown?.system_tokens ?? 850;
  
  // Layer 2 Token (工作区共享记忆与画像)
  const layer2Memories = memories.length > 0 ? memories : (contextData?.workspace_memories || []);
  const layer2Tokens =
    contextData?.layers_breakdown?.workspace_memory_tokens ??
    layer2Memories.reduce((acc, m) => acc + Math.max(10, Math.ceil((m.content || '').length / 2) + 20), 0);

  // Layer 3 Token (会话压缩摘要)
  const layer3Summary = contextData?.session_memory?.summary || '';
  const layer3Tokens =
    contextData?.layers_breakdown?.session_memory_tokens ??
    (layer3Summary ? Math.max(20, Math.ceil(layer3Summary.length / 2)) : 0);

  // Layer 4 Token (活跃轮次)
  const activeMessages = currentTask?.messages || [];
  const layer4Tokens =
    contextData?.layers_breakdown?.active_turns_tokens ??
    activeMessages.reduce((acc, m) => {
      if (m.tokensUsed && m.tokensUsed > 0) return acc + m.tokensUsed;
      return acc + Math.max(8, Math.ceil((m.content || '').length / 2));
    }, 0);

  // 会话当前活跃上下文窗口总占用
  const totalContextTokens =
    contextData?.budget?.total_context_tokens ??
    (currentTask?.telemetry?.contextTokens ?? (layer1Tokens + layer2Tokens + layer3Tokens + layer4Tokens));

  const maxContextTokens = contextData?.budget?.session_token_limit ?? 32000;
  const contextWaterPct = Number(((totalContextTokens / maxContextTokens) * 100).toFixed(1));

  // 任务全生命周期累计物理消耗 (思考链 + 工具调用 + 验证)
  const totalPhysicalTokens = currentTask?.telemetry?.totalTokens || 0;

  const assembledPreview = `# [Layer 1: System Prompt & Rules (~${layer1Tokens} tok)]\n${systemPrompt}\n\n# [Layer 2: Workspace Shared Memories & User Profile (~${layer2Tokens} tok)]\n${layer2Memories
    .map((m) => `## [${m.category}] ${m.title}\n${m.content}`)
    .join('\n\n')}\n\n# [Layer 3: Session Compressed Memory Summary (~${layer3Tokens} tok)]\n${
    layer3Summary || '暂无已压缩历史轮次'
  }\n\n# [Layer 4: Active Sliding Window Turns (~${layer4Tokens} tok)]\n${
    activeMessages.map((m) => `[${m.role.toUpperCase()}] ${m.content}`).join('\n\n') || '无活跃对话轮次'
  }`;

  const handleCopyAll = () => {
    navigator.clipboard.writeText(assembledPreview);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-2xs animate-in fade-in duration-150">
      <div className="w-full max-w-xl bg-white h-full shadow-2xl border-l border-border-subtle flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle bg-canvas-secondary">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-blue-100 text-blue-700">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-gray-900 text-sm">四层上下文装配透视器</h3>
                {isLoading && <Loader2 className="w-3 h-3 text-brand-600 animate-spin" />}
              </div>
              <p className="text-[11px] text-gray-500">Context Assembly Inspector (送入大模型的单次 Prompt 最终视界)</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyAll}
              className="flex items-center gap-1 px-2.5 py-1 rounded bg-white hover:bg-gray-100 border border-border-subtle text-gray-700 text-xs transition"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? '已复制视界' : '复制全文'}</span>
            </button>
            <button
              onClick={() => setContextDrawerOpen(false)}
              className="p-1 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-200 transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Dual Metric Indicator Cards */}
        <div className="px-5 py-3 border-b border-border-subtle bg-slate-50/80 space-y-2 text-xs">
          {/* Top Row: Context Window vs Task Physical Cumulative */}
          <div className="grid grid-cols-2 gap-3">
            {/* 1. Context Window */}
            <div className="p-2.5 rounded-lg bg-blue-50/60 border border-blue-200/80 space-y-1">
              <div className="flex items-center justify-between font-semibold text-blue-900 text-[11px]">
                <span className="flex items-center gap-1">
                  <Layers className="w-3.5 h-3.5 text-blue-600" />
                  当前会话上下文窗口
                </span>
                <span className="font-mono">{contextWaterPct}% 水位</span>
              </div>
              <div className="font-mono text-sm font-bold text-blue-950">
                {totalContextTokens.toLocaleString()} <span className="text-[11px] font-normal text-blue-700">/ 32,000 tok</span>
              </div>
              <div className="text-[10px] text-blue-600">80% 触发 40% 滚动切片压缩</div>
            </div>

            {/* 2. Task Physical Tokens */}
            <div className="p-2.5 rounded-lg bg-amber-50/60 border border-amber-200/80 space-y-1">
              <div className="flex items-center justify-between font-semibold text-amber-900 text-[11px]">
                <span className="flex items-center gap-1">
                  <Activity className="w-3.5 h-3.5 text-amber-600" />
                  本轮任务物理累计消耗
                </span>
                <span className="font-mono text-[10px] text-amber-700">全状态机</span>
              </div>
              <div className="font-mono text-sm font-bold text-amber-950">
                {totalPhysicalTokens.toLocaleString()} <span className="text-[11px] font-normal text-amber-700">/ 200k 预算</span>
              </div>
              <div className="text-[10px] text-amber-600">Planner + CoT + 工具执行总计</div>
            </div>
          </div>

          {/* Context Window Multi-layer Progress Bar */}
          <div className="space-y-1 pt-1">
            <div className="flex items-center justify-between text-[10px] font-mono text-slate-500">
              <span>四层上下文分布比例</span>
              <span>上限 32,000 Tokens (高水位线: 25,600)</span>
            </div>
            <div className="h-2 w-full bg-slate-200 rounded-full overflow-hidden flex relative">
              <div
                style={{ width: `${Math.min(100, (layer1Tokens / maxContextTokens) * 100)}%` }}
                className="bg-amber-400 h-full"
                title={`Layer 1 系统底模: ${layer1Tokens} tok`}
              />
              <div
                style={{ width: `${Math.min(100, (layer2Tokens / maxContextTokens) * 100)}%` }}
                className="bg-purple-500 h-full"
                title={`Layer 2 共享记忆: ${layer2Tokens} tok`}
              />
              <div
                style={{ width: `${Math.min(100, (layer3Tokens / maxContextTokens) * 100)}%` }}
                className="bg-emerald-500 h-full"
                title={`Layer 3 压缩摘要: ${layer3Tokens} tok`}
              />
              <div
                style={{ width: `${Math.min(100, (layer4Tokens / maxContextTokens) * 100)}%` }}
                className="bg-blue-500 h-full"
                title={`Layer 4 活跃轮次: ${layer4Tokens} tok`}
              />
            </div>
          </div>
        </div>

        {/* 4 Layers Accordion View */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs font-mono">
          {/* Layer 1 */}
          <div className="border border-border-subtle rounded-xl overflow-hidden shadow-2xs">
            <div className="px-3.5 py-2 bg-amber-50/50 border-b border-amber-100 font-semibold text-gray-800 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-amber-900">
                <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                第一层：内置系统提示词与安全纪律 (System Prompt & Canary)
              </span>
              <span className="text-[11px] font-mono text-amber-700 bg-amber-100/70 px-1.5 py-0.5 rounded">
                ~{layer1Tokens} tok
              </span>
            </div>
            <pre className="p-3 bg-white text-gray-700 text-[11px] whitespace-pre-wrap leading-relaxed overflow-x-auto">
              {systemPrompt}
            </pre>
          </div>

          {/* Layer 2 */}
          <div className="border border-border-subtle rounded-xl overflow-hidden shadow-2xs">
            <div className="px-3.5 py-2 bg-purple-50/50 border-b border-purple-100 font-semibold text-gray-800 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-purple-900">
                <Brain className="w-3.5 h-3.5 text-purple-600" />
                第二层：工作区长期记忆与用户画像 (Workspace Shared Memories & Profile)
              </span>
              <span className="text-[11px] font-mono text-purple-700 bg-purple-100/70 px-1.5 py-0.5 rounded">
                ~{layer2Tokens} tok ({layer2Memories.length} 条)
              </span>
            </div>
            <div className="p-3 bg-white space-y-2 text-gray-700 text-[11px]">
              {layer2Memories.length > 0 ? (
                layer2Memories.map((m) => (
                  <div key={m.id || m.title} className="p-2 bg-purple-50/30 rounded border border-purple-100/80">
                    <div className="font-bold text-purple-950">[{m.category}] {m.title}</div>
                    <div className="text-gray-700 mt-0.5 whitespace-pre-wrap">{m.content}</div>
                  </div>
                ))
              ) : (
                <div className="text-gray-400 italic py-1">暂无工作区跨会话共享记忆与画像</div>
              )}
            </div>
          </div>

          {/* Layer 3 */}
          <div className="border border-border-subtle rounded-xl overflow-hidden shadow-2xs">
            <div className="px-3.5 py-2 bg-emerald-50/50 border-b border-emerald-100 font-semibold text-gray-800 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-emerald-900">
                <Layers className="w-3.5 h-3.5 text-emerald-600" />
                第三层：会话已压缩情境记忆 (Session Compressed Summary)
              </span>
              <span className="text-[11px] font-mono text-emerald-700 bg-emerald-100/70 px-1.5 py-0.5 rounded">
                ~{layer3Tokens} tok
              </span>
            </div>
            <div className="p-3 bg-white text-gray-600 text-[11px] space-y-1">
              {layer3Summary ? (
                <div className="whitespace-pre-wrap leading-relaxed">{layer3Summary}</div>
              ) : (
                <div className="text-gray-400 italic py-1">暂无已压缩历史轮次（当前所有交互均完整保留在活跃滑窗视界内）</div>
              )}
            </div>
          </div>

          {/* Layer 4 */}
          <div className="border border-border-subtle rounded-xl overflow-hidden shadow-2xs">
            <div className="px-3.5 py-2 bg-blue-50/50 border-b border-blue-100 font-semibold text-gray-800 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-blue-900">
                <MessageSquare className="w-3.5 h-3.5 text-blue-600" />
                第四层：活跃滑窗对话轮次 (Active Turns in Session Window)
              </span>
              <span className="text-[11px] font-mono text-blue-700 bg-blue-100/70 px-1.5 py-0.5 rounded">
                ~{layer4Tokens} tok ({activeMessages.length} 轮)
              </span>
            </div>
            <div className="p-3 bg-white space-y-2 text-gray-700 text-[11px]">
              {activeMessages.length > 0 ? (
                activeMessages.map((msg) => (
                  <div key={msg.id} className="p-2 bg-blue-50/20 rounded border border-blue-100/70">
                    <div className="font-bold uppercase text-blue-950 text-[10px] flex items-center justify-between">
                      <span>{msg.role} ({msg.timestamp}):</span>
                      {msg.tokensUsed !== undefined && msg.tokensUsed > 0 && (
                        <span className="text-slate-400 font-normal">{msg.tokensUsed} tok</span>
                      )}
                    </div>
                    <div className="mt-0.5 truncate text-gray-800">
                      {msg.content.slice(0, 160)}{msg.content.length > 160 ? '...' : ''}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-gray-400 italic py-1">当前会话暂无活跃轮次</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
