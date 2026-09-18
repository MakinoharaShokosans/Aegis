import React, { useState } from 'react';
import {
  X,
  Layers,
  Sparkles,
  Brain,
  MessageSquare,
  Droplet,
  Copy,
  Check,
} from 'lucide-react';
import { useUiStore } from '@/stores/useUiStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { useTaskStore } from '@/stores/useTaskStore';

export const ContextDrawer: React.FC = () => {
  const { contextDrawerOpen, setContextDrawerOpen } = useUiStore();
  const { memories } = useWorkspaceStore();
  const { currentTaskId, tasks } = useTaskStore();

  const [copied, setCopied] = useState(false);

  if (!contextDrawerOpen) return null;

  const currentTask = currentTaskId ? tasks[currentTaskId] : null;

  const systemPrompt = `You are AegisAgent, an advanced deterministic autonomous coding and engineering assistant.
Workspace is Ground Truth. Always verify contracts against documents/*.md before modifying source code.
Dual-Tier Execution: High-level planning with Reasoning model (gpt-5.6-terra), leaf actions with Fast model (gpt-5.4-mini / gpt-5.6-luna).
HITL Security Discipline: Out-of-bounds file writes or network egress commands must be suspended for human approval.`;

  const assembledPreview = `# [Layer 1: System Prompt & Rules]\n${systemPrompt}\n\n# [Layer 2: Workspace Shared Memories]\n${memories
    .map((m) => `## [${m.category}] ${m.title}\n${m.content}`)
    .join('\n\n')}\n\n# [Layer 3: Session Compressed Memory Summary]\n- 阶段 1: 完成接入层三道安全闸门设计契约确认\n- 阶段 2: 提取 11_http_api.md 中 Auth Header 与 Error Code 规范\n\n# [Layer 4: Active Sliding Window Turns]\n${
    currentTask?.messages
      .map((m) => `[${m.role.toUpperCase()}] ${m.content}`)
      .join('\n\n') || '无活跃对话轮次'
  }`;

  const handleCopyAll = () => {
    navigator.clipboard.writeText(assembledPreview);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="w-full max-w-xl h-full bg-white shadow-2xl flex flex-col border-l border-border-subtle animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle bg-canvas-secondary">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-blue-100 text-blue-700">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 text-sm">四层上下文装配透视器</h3>
              <p className="text-[11px] text-gray-500">Context Assembly Inspector (送入大模型的最终视界)</p>
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

        {/* Water Level Gauge */}
        <div className="px-5 py-3 border-b border-border-subtle bg-blue-50/40 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <Droplet className="w-4 h-4 text-blue-600" />
            <span className="font-medium text-gray-800">当前会话记忆水位：32% (24.8k / 80k Tokens)</span>
          </div>
          <span className="text-[11px] text-gray-500">压缩阈值: 80% $\to$ 40%</span>
        </div>

        {/* 4 Layers Accordion View */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs font-mono">
          {/* Layer 1 */}
          <div className="border border-border-subtle rounded-xl overflow-hidden">
            <div className="px-3.5 py-2 bg-gray-50 border-b border-border-subtle font-semibold text-gray-800 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                第一层：内置系统提示词与安全纪律 (System Prompt)
              </span>
              <span className="text-[10px] text-gray-400">~850 tok</span>
            </div>
            <pre className="p-3 bg-white text-gray-700 text-[11px] whitespace-pre-wrap leading-relaxed overflow-x-auto">
              {systemPrompt}
            </pre>
          </div>

          {/* Layer 2 */}
          <div className="border border-border-subtle rounded-xl overflow-hidden">
            <div className="px-3.5 py-2 bg-gray-50 border-b border-border-subtle font-semibold text-gray-800 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Brain className="w-3.5 h-3.5 text-purple-600" />
                第二层：工作区长期共享记忆 (Workspace Shared Memories)
              </span>
              <span className="text-[10px] text-gray-400">~1,420 tok</span>
            </div>
            <div className="p-3 bg-white space-y-2 text-gray-700 text-[11px]">
              {memories.map((m) => (
                <div key={m.id} className="p-2 bg-gray-50 rounded border border-gray-100">
                  <div className="font-bold text-gray-900">[{m.category}] {m.title}</div>
                  <div className="text-gray-600 mt-0.5">{m.content}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Layer 3 */}
          <div className="border border-border-subtle rounded-xl overflow-hidden">
            <div className="px-3.5 py-2 bg-gray-50 border-b border-border-subtle font-semibold text-gray-800 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-emerald-600" />
                第三层：会话已压缩情境记忆 (Session Memory Summary)
              </span>
              <span className="text-[10px] text-gray-400">~620 tok</span>
            </div>
            <div className="p-3 bg-white text-gray-700 text-[11px] space-y-1">
              <div>- 阶段 1: 完成接入层三道安全闸门设计契约确认</div>
              <div>- 阶段 2: 提取 11_http_api.md 中 Auth Header 与 Error Code 规范</div>
            </div>
          </div>

          {/* Layer 4 */}
          <div className="border border-border-subtle rounded-xl overflow-hidden">
            <div className="px-3.5 py-2 bg-gray-50 border-b border-border-subtle font-semibold text-gray-800 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <MessageSquare className="w-3.5 h-3.5 text-blue-600" />
                第四层：活跃滑窗对话轮次 (Active Turns)
              </span>
              <span className="text-[10px] text-gray-400">~4,100 tok</span>
            </div>
            <div className="p-3 bg-white space-y-2 text-gray-700 text-[11px]">
              {currentTask?.messages.map((msg) => (
                <div key={msg.id} className="p-2 bg-gray-50 rounded border border-gray-100">
                  <div className="font-bold uppercase text-gray-800 text-[10px]">{msg.role} ({msg.timestamp}):</div>
                  <div className="mt-0.5 truncate">{msg.content.slice(0, 120)}...</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
