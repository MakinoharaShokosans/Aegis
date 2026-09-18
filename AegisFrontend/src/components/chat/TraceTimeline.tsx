import React, { useState } from 'react';
import {
  Compass,
  Cpu,
  Wrench,
  CheckCircle2,
  ShieldCheck,
  Bot,
  Clock,
  Activity,
  Target,
  Terminal,
  Workflow,
  Sparkles,
  ArrowRight,
  Share2,
  Check,
} from 'lucide-react';
import type { TraceStep } from '@/types';
import { useUiStore } from '@/stores/useUiStore';
import { useTaskStore } from '@/stores/useTaskStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { generateWorkflowMarkdown } from '@/utils/exportWorkflow';

interface TraceTimelineProps {
  steps: TraceStep[];
}

const nodeConfigs: Record<
  string,
  {
    name: string;
    badgeBg: string;
    badgeText: string;
    badgeBorder: string;
    dotBg: string;
    dotBorder: string;
    icon: React.ReactNode;
  }
> = {
  planner: {
    name: 'Planner (目标规划与里程碑)',
    badgeBg: 'bg-purple-50',
    badgeText: 'text-purple-700',
    badgeBorder: 'border-purple-200',
    dotBg: 'bg-purple-600',
    dotBorder: 'border-purple-600',
    icon: <Compass className="w-3.5 h-3.5 text-purple-600" />,
  },
  budget_guard: {
    name: 'BudgetGuard (预算与循环看门狗)',
    badgeBg: 'bg-slate-100',
    badgeText: 'text-slate-700',
    badgeBorder: 'border-slate-300',
    dotBg: 'bg-slate-600',
    dotBorder: 'border-slate-600',
    icon: <ShieldCheck className="w-3.5 h-3.5 text-slate-600" />,
  },
  executor: {
    name: 'Executor (动作翻译与指令生成)',
    badgeBg: 'bg-blue-50',
    badgeText: 'text-blue-700',
    badgeBorder: 'border-blue-200',
    dotBg: 'bg-blue-600',
    dotBorder: 'border-blue-600',
    icon: <Cpu className="w-3.5 h-3.5 text-blue-600" />,
  },
  tool_runner: {
    name: 'ToolRunner (受限工具执行)',
    badgeBg: 'bg-amber-50',
    badgeText: 'text-amber-800',
    badgeBorder: 'border-amber-200',
    dotBg: 'bg-amber-500',
    dotBorder: 'border-amber-500',
    icon: <Wrench className="w-3.5 h-3.5 text-amber-600" />,
  },
  evaluator: {
    name: 'Evaluator (阶段验收与收敛评估)',
    badgeBg: 'bg-emerald-50',
    badgeText: 'text-emerald-700',
    badgeBorder: 'border-emerald-200',
    dotBg: 'bg-emerald-600',
    dotBorder: 'border-emerald-600',
    icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />,
  },
  subagent: {
    name: 'Subagent (子智能体并行)',
    badgeBg: 'bg-rose-50',
    badgeText: 'text-rose-700',
    badgeBorder: 'border-rose-200',
    dotBg: 'bg-rose-600',
    dotBorder: 'border-rose-600',
    icon: <Bot className="w-3.5 h-3.5 text-rose-600" />,
  },
};

export const TraceTimeline: React.FC<TraceTimelineProps> = ({ steps }) => {
  const { setActiveView, setSelectedLlmCallId } = useUiStore();
  const { currentTaskId, tasks } = useTaskStore();
  const { workspaces, activeWorkspaceId } = useWorkspaceStore();
  const [copied, setCopied] = useState(false);
  const currentTask = currentTaskId ? tasks[currentTaskId] : null;

  const handleInspectLlm = (stepNode: string, stepNum: number) => {
    const matchingCall =
      currentTask?.llmCalls?.find((c) => c.node === stepNode && c.step === stepNum) ||
      currentTask?.llmCalls?.find((c) => c.node === stepNode);
    if (matchingCall) {
      setSelectedLlmCallId(matchingCall.id);
    }
    setActiveView('llm');
  };

  const handleCopyWorkflow = () => {
    const currentWs = workspaces.find((w) => w.id === activeWorkspaceId);
    const md = generateWorkflowMarkdown(currentTask, currentWs);
    navigator.clipboard.writeText(md);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!steps || steps.length === 0) {
    return (
      <div className="py-16 flex flex-col items-center justify-center text-center max-w-md mx-auto select-none space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-400">
          <Workflow className="w-6 h-6" />
        </div>
        <div className="space-y-1">
          <h4 className="font-semibold text-slate-800 text-sm">暂无执行轨迹 (No Active Trace)</h4>
          <p className="text-xs text-slate-500 leading-relaxed">
            启动任务后，此处将实时呈现 LangGraph 状态机跃迁流水、受限工具调用细节与节点决策结果。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 max-w-3xl mx-auto select-none pb-8">
      {/* Trace Subheader */}
      <div className="flex items-center justify-between text-xs text-slate-500 font-mono px-1 border-b border-slate-200 pb-2">
        <div className="flex items-center gap-1.5">
          <Workflow className="w-3.5 h-3.5 text-brand-600" />
          <span className="font-semibold text-slate-700">LangGraph 状态机流转与因果时序流水</span>
        </div>
        <div className="flex items-center gap-3 text-[11px]">
          <span>共 {steps.length} 个轨迹步</span>
          {currentTask && (
            <button
              onClick={handleCopyWorkflow}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 transition"
              title="一键复制全流程报告"
            >
              {copied ? (
                <>
                  <Check className="w-3 h-3 text-emerald-600" />
                  <span className="text-emerald-700 font-bold">已复制</span>
                </>
              ) : (
                <>
                  <Share2 className="w-3 h-3 text-brand-600" />
                  <span>复制全流程</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* State Machine Legend / Flow indicator */}
      <div className="flex items-center gap-1.5 overflow-x-auto py-1.5 px-2 bg-slate-50/80 rounded-lg border border-slate-200 text-[10px] font-mono text-slate-600">
        <span className="text-slate-400">流转拓扑:</span>
        <span className="px-1.5 py-0.5 rounded bg-purple-100 text-purple-800 font-medium">Planner</span>
        <ArrowRight className="w-3 h-3 text-slate-400 shrink-0" />
        <span className="px-1.5 py-0.5 rounded bg-slate-200 text-slate-800 font-medium">BudgetGuard</span>
        <ArrowRight className="w-3 h-3 text-slate-400 shrink-0" />
        <span className="px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 font-medium">Executor</span>
        <ArrowRight className="w-3 h-3 text-slate-400 shrink-0" />
        <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-medium">ToolRunner</span>
        <ArrowRight className="w-3 h-3 text-slate-400 shrink-0" />
        <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-medium">Evaluator</span>
      </div>

      {/* Timeline Steps */}
      <div className="relative pl-6 border-l-2 border-slate-200 space-y-4 pt-1">
        {steps.map((step, idx) => {
          const config = nodeConfigs[step.node] || nodeConfigs.executor;
          const isLlmNode = ['planner', 'executor', 'evaluator', 'subagent'].includes(step.node);

          return (
            <div key={step.id || `step-${idx}`} className="relative group">
              {/* Dot on Timeline */}
              <div
                className={`absolute -left-[31px] top-2 w-4 h-4 rounded-full bg-white border-2 ${config.dotBorder} flex items-center justify-center shadow-2xs`}
              >
                <div className={`w-1.5 h-1.5 rounded-full ${config.dotBg}`} />
              </div>

              {/* Step Card */}
              <div className="p-3.5 rounded-xl border border-slate-200/90 bg-white hover:border-slate-300 shadow-2xs space-y-2.5 transition">
                {/* 1. Header: Node Badge, Step #, Time, Tokens, AI Inspect Link */}
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-mono font-medium border ${config.badgeBg} ${config.badgeText} ${config.badgeBorder}`}
                    >
                      {config.icon}
                      <span>Step #{step.step}: {config.name}</span>
                    </span>

                    {isLlmNode && (
                      <button
                        onClick={() => handleInspectLlm(step.node, step.step)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 transition"
                        title="查看本步底层发送给大模型的 Prompt 与原始返回"
                      >
                        <Cpu className="w-3 h-3 text-blue-600" />
                        <span>AI 请求透视</span>
                      </button>
                    )}
                  </div>

                  <div className="flex items-center gap-3 text-[11px] font-mono text-slate-400">
                    <div className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      <span>{step.timestamp}</span>
                    </div>
                    {step.durationMs > 0 && (
                      <div className="flex items-center gap-1">
                        <Activity className="w-3 h-3" />
                        <span>{step.durationMs}ms</span>
                      </div>
                    )}
                    {step.tokenUsage !== undefined && step.tokenUsage > 0 && (
                      <div className="flex items-center gap-1 text-slate-600 font-medium">
                        <Cpu className="w-3 h-3 text-slate-400" />
                        <span>{step.tokenUsage.toLocaleString()} tokens</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* 2. 入参摘要 / 意图目标 */}
                {step.inputSummary && (
                  <div className="text-xs text-slate-700 bg-slate-50/80 p-2.5 rounded-lg border border-slate-100 flex items-start gap-2">
                    <Target className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
                    <div className="flex-1 space-y-0.5">
                      <div className="text-[10px] font-mono text-slate-400 font-semibold">入参意图 / 目标:</div>
                      <div className="font-mono text-[11px] text-slate-800 leading-relaxed break-all">
                        {step.inputSummary}
                      </div>
                    </div>
                  </div>
                )}

                {/* 3. 工具调用与参数 (若有) */}
                {(step.tool || step.toolArgs) && (
                  <div className="text-xs bg-amber-50/50 p-2.5 rounded-lg border border-amber-200/80 space-y-1.5">
                    <div className="flex items-center gap-1.5 text-amber-900 font-semibold text-[11px]">
                      <Wrench className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                      <span>调用工具:</span>
                      <code className="px-1.5 py-0.2 bg-amber-100 text-amber-900 rounded font-mono text-[11px] border border-amber-300/60 font-bold">
                        {step.tool || 'tool'}
                      </code>
                    </div>
                    {step.toolArgs && (
                      <pre className="p-2 bg-white/90 rounded border border-amber-200 text-slate-800 text-[11px] font-mono overflow-x-auto whitespace-pre-wrap">
                        {typeof step.toolArgs === 'object'
                          ? JSON.stringify(step.toolArgs, null, 2)
                          : String(step.toolArgs)}
                      </pre>
                    )}
                  </div>
                )}

                {/* 4. 工具返回产物 (若有) */}
                {step.toolResult && (
                  <div className="text-xs bg-emerald-50/40 p-2.5 rounded-lg border border-emerald-200/80 space-y-1">
                    <div className="flex items-center gap-1.5 text-emerald-900 font-semibold text-[11px]">
                      <Terminal className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                      <span>工具返回结果:</span>
                    </div>
                    <pre className="p-2 bg-white/90 rounded border border-emerald-100 text-slate-800 text-[11px] font-mono overflow-x-auto max-h-48 whitespace-pre-wrap">
                      {step.toolResult}
                    </pre>
                  </div>
                )}

                {/* 5. 决策结果 / 出参判定 */}
                {step.outputSummary && (!step.toolResult || step.node !== 'tool_runner') && (
                  <div
                    className={`text-xs p-2.5 rounded-lg border flex items-start gap-2 ${
                      step.node === 'planner'
                        ? 'bg-purple-50/50 border-purple-100 text-purple-900'
                        : step.node === 'evaluator'
                        ? 'bg-emerald-50/50 border-emerald-100 text-emerald-900'
                        : step.node === 'budget_guard'
                        ? 'bg-slate-50 border-slate-200 text-slate-800'
                        : 'bg-blue-50/40 border-blue-100 text-blue-900'
                    }`}
                  >
                    <Sparkles
                      className={`w-3.5 h-3.5 shrink-0 mt-0.5 ${
                        step.node === 'planner'
                          ? 'text-purple-600'
                          : step.node === 'evaluator'
                          ? 'text-emerald-600'
                          : step.node === 'budget_guard'
                          ? 'text-slate-500'
                          : 'text-blue-600'
                      }`}
                    />
                    <div className="flex-1 space-y-0.5">
                      <div className="text-[10px] font-mono font-semibold opacity-70">
                        {step.node === 'planner'
                          ? '规划决策与指令 (Planner Decision):'
                          : step.node === 'evaluator'
                          ? '验收结论与收敛判定 (Evaluator Verdict):'
                          : step.node === 'budget_guard'
                          ? '看门狗安全巡检 (Budget Guard):'
                          : '动作决策与出参 (Action Output):'}
                      </div>
                      <div className="font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
                        {step.outputSummary}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
