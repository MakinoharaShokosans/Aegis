import React, { useState, useMemo } from 'react';
import {
  Cpu,
  Clock,
  Activity,
  Copy,
  Check,
  Search,
  Wrench,
  CheckCircle2,
  Bot,
  Compass,
  FileJson,
  MessageSquare,
  Sparkles,
  Terminal,
  Share2,
} from 'lucide-react';
import type { LlmCallRecord } from '@/types';
import { useTaskStore } from '@/stores/useTaskStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { generateWorkflowMarkdown } from '@/utils/exportWorkflow';

interface LlmInvocationInspectorProps {
  calls: LlmCallRecord[];
  selectedCallId?: string | null;
  onSelectCall?: (id: string) => void;
}

const nodeVisuals: Record<
  string,
  {
    name: string;
    icon: React.ReactNode;
    badgeBg: string;
    badgeText: string;
    badgeBorder: string;
  }
> = {
  planner: {
    name: 'Planner (目标规划)',
    icon: <Compass className="w-3.5 h-3.5 text-purple-600" />,
    badgeBg: 'bg-purple-50',
    badgeText: 'text-purple-700',
    badgeBorder: 'border-purple-200',
  },
  executor: {
    name: 'Executor (动作翻译)',
    icon: <Cpu className="w-3.5 h-3.5 text-blue-600" />,
    badgeBg: 'bg-blue-50',
    badgeText: 'text-blue-700',
    badgeBorder: 'border-blue-200',
  },
  evaluator: {
    name: 'Evaluator (阶段验收)',
    icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />,
    badgeBg: 'bg-emerald-50',
    badgeText: 'text-emerald-700',
    badgeBorder: 'border-emerald-200',
  },
  subagent: {
    name: 'Subagent (子智能体)',
    icon: <Bot className="w-3.5 h-3.5 text-rose-600" />,
    badgeBg: 'bg-rose-50',
    badgeText: 'text-rose-700',
    badgeBorder: 'border-rose-200',
  },
  research: {
    name: 'Research (隔离调研)',
    icon: <Sparkles className="w-3.5 h-3.5 text-cyan-600" />,
    badgeBg: 'bg-cyan-50',
    badgeText: 'text-cyan-700',
    badgeBorder: 'border-cyan-200',
  },
  code_search: {
    name: 'CodeSearch (代码检索)',
    icon: <Terminal className="w-3.5 h-3.5 text-amber-600" />,
    badgeBg: 'bg-amber-50',
    badgeText: 'text-amber-800',
    badgeBorder: 'border-amber-200',
  },
};

export const LlmInvocationInspector: React.FC<LlmInvocationInspectorProps> = ({
  calls,
  selectedCallId,
  onSelectCall,
}) => {
  const [internalSelectedId, setInternalSelectedId] = useState<string | null>(null);
  const [filterNode, setFilterNode] = useState<string>('all');
  const [filterTier, setFilterTier] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'messages' | 'tools' | 'response' | 'raw'>('messages');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [workflowCopied, setWorkflowCopied] = useState(false);

  const { currentTaskId, tasks } = useTaskStore();
  const { workspaces, activeWorkspaceId } = useWorkspaceStore();
  const currentTask = currentTaskId ? tasks[currentTaskId] : null;

  const handleCopyWorkflow = () => {
    const currentWs = workspaces.find((w) => w.id === activeWorkspaceId);
    const md = generateWorkflowMarkdown(currentTask, currentWs);
    navigator.clipboard.writeText(md);
    setWorkflowCopied(true);
    setTimeout(() => setWorkflowCopied(false), 2000);
  };

  const activeSelectedId = selectedCallId || internalSelectedId || (calls.length > 0 ? calls[calls.length - 1].id : null);

  const handleSelect = (id: string) => {
    setInternalSelectedId(id);
    onSelectCall?.(id);
  };

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1800);
  };

  // Filtered Calls
  const filteredCalls = useMemo(() => {
    return calls.filter((c) => {
      if (filterNode !== 'all' && c.node !== filterNode) return false;
      if (filterTier !== 'all' && c.tier !== filterTier) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const inModel = (c.model || '').toLowerCase().includes(q);
        const inNode = (c.node || '').toLowerCase().includes(q);
        const inResp = (c.response?.content || '').toLowerCase().includes(q);
        const inMsgs = c.messages?.some(
          (m) => (m.content || '').toLowerCase().includes(q) || (m.role || '').toLowerCase().includes(q)
        );
        return inModel || inNode || inResp || inMsgs;
      }
      return true;
    });
  }, [calls, filterNode, filterTier, searchQuery]);

  const selectedCall = useMemo(() => {
    return calls.find((c) => c.id === activeSelectedId) || (filteredCalls.length > 0 ? filteredCalls[0] : null);
  }, [calls, activeSelectedId, filteredCalls]);

  // Statistics
  const totalTokens = useMemo(() => calls.reduce((acc, c) => acc + (c.tokens || 0), 0), [calls]);
  const avgDuration = useMemo(() => {
    if (calls.length === 0) return 0;
    const totalMs = calls.reduce((acc, c) => acc + (c.durationMs || 0), 0);
    return Math.round(totalMs / calls.length);
  }, [calls]);

  if (!calls || calls.length === 0) {
    return (
      <div className="py-20 flex flex-col items-center justify-center text-center max-w-md mx-auto select-none space-y-4">
        <div className="w-14 h-14 rounded-2xl bg-brand-50 border border-brand-200 flex items-center justify-center text-brand-600 shadow-2xs">
          <Cpu className="w-7 h-7" />
        </div>
        <div className="space-y-1.5">
          <h4 className="font-bold text-slate-800 text-base">暂无 AI 底层请求记录 (No LLM Calls)</h4>
          <p className="text-xs text-slate-500 leading-relaxed max-w-sm">
            当启动任务且状态机流转时，系统将在此实时捕获并结构化呈现每次对大模型发起的底层 HTTP/Prompt 消息序列与原始返回。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-slate-50/50 -m-4 md:-m-6 overflow-hidden select-none">
      {/* 1. Top Statistics & Filter Bar */}
      <div className="bg-white border-b border-slate-200 px-4 py-2.5 flex flex-wrap items-center justify-between gap-3 shrink-0 shadow-2xs">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-slate-800 font-semibold text-xs">
            <Cpu className="w-4 h-4 text-brand-600" />
            <span>大模型底层调用透视</span>
            <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[11px] font-mono font-medium border border-slate-200">
              共 {calls.length} 次
            </span>
          </div>

          <div className="hidden sm:flex items-center gap-2 text-[11px] font-mono text-slate-500 border-l border-slate-200 pl-3">
            <span className="flex items-center gap-1">
              <Activity className="w-3 h-3 text-purple-500" />
              <span>累计物理消耗:</span>
              <strong className="text-slate-700 font-bold">{totalTokens.toLocaleString()} tok</strong>
            </span>
            {avgDuration > 0 && (
              <span className="flex items-center gap-1 border-l border-slate-200 pl-2">
                <Clock className="w-3 h-3 text-amber-500" />
                <span>平均时延:</span>
                <strong className="text-slate-700 font-bold">{avgDuration}ms</strong>
              </span>
            )}
          </div>
        </div>

        {/* Filters & Search */}
        <div className="flex items-center gap-2 flex-wrap text-xs">
          {/* Node Filter */}
          <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200/80 text-[11px]">
            <button
              onClick={() => setFilterNode('all')}
              className={`px-2 py-0.5 rounded-md font-medium transition ${
                filterNode === 'all' ? 'bg-white text-slate-900 shadow-2xs font-semibold' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              全部节点
            </button>
            <button
              onClick={() => setFilterNode('planner')}
              className={`px-2 py-0.5 rounded-md font-medium transition ${
                filterNode === 'planner' ? 'bg-white text-purple-700 shadow-2xs font-semibold' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Planner
            </button>
            <button
              onClick={() => setFilterNode('executor')}
              className={`px-2 py-0.5 rounded-md font-medium transition ${
                filterNode === 'executor' ? 'bg-white text-blue-700 shadow-2xs font-semibold' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Executor
            </button>
            <button
              onClick={() => setFilterNode('evaluator')}
              className={`px-2 py-0.5 rounded-md font-medium transition ${
                filterNode === 'evaluator' ? 'bg-white text-emerald-700 shadow-2xs font-semibold' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Evaluator
            </button>
          </div>

          {/* Tier Filter */}
          <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200/80 text-[11px]">
            <button
              onClick={() => setFilterTier('all')}
              className={`px-2 py-0.5 rounded-md font-medium transition ${
                filterTier === 'all' ? 'bg-white text-slate-900 shadow-2xs font-semibold' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              全层级
            </button>
            <button
              onClick={() => setFilterTier('reasoning')}
              className={`px-2 py-0.5 rounded-md font-medium transition ${
                filterTier === 'reasoning' ? 'bg-white text-purple-700 shadow-2xs font-semibold' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Reasoning
            </button>
            <button
              onClick={() => setFilterTier('fast')}
              className={`px-2 py-0.5 rounded-md font-medium transition ${
                filterTier === 'fast' ? 'bg-white text-blue-700 shadow-2xs font-semibold' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Fast
            </button>
          </div>

          {/* Search box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索 Prompt / 输出..."
              className="pl-7 pr-2.5 py-1 rounded-lg border border-slate-200 bg-slate-50 text-[11px] focus:outline-none focus:bg-white focus:border-brand-500 w-36 sm:w-44 transition"
            />
          </div>

          {/* Copy Full Workflow Button */}
          {currentTask && (
            <button
              onClick={handleCopyWorkflow}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-[11px] font-mono font-medium shadow-2xs transition"
              title="一键复制本次任务全流程 Markdown 报告"
            >
              {workflowCopied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-600" />
                  <span className="text-emerald-700 font-bold">全流程已复制</span>
                </>
              ) : (
                <>
                  <Share2 className="w-3.5 h-3.5 text-brand-600" />
                  <span>复制全流程</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* 2. Main Master-Detail Stage */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Left Pane: Invocations List */}
        <div className="w-full md:w-80 lg:w-96 border-r border-slate-200 bg-white flex flex-col shrink-0 overflow-y-auto divide-y divide-slate-100">
          <div className="px-3 py-2 bg-slate-50/70 text-[11px] font-mono text-slate-500 font-semibold border-b border-slate-100 flex items-center justify-between">
            <span>调用时序记录 ({filteredCalls.length})</span>
            <span>Step / Tier</span>
          </div>

          {filteredCalls.map((c, idx) => {
            const visual = nodeVisuals[c.node] || {
              name: c.node,
              icon: <Cpu className="w-3.5 h-3.5 text-slate-600" />,
              badgeBg: 'bg-slate-100',
              badgeText: 'text-slate-700',
              badgeBorder: 'border-slate-200',
            };
            const isSelected = c.id === selectedCall?.id;

            return (
              <button
                key={c.id || `call-${idx}`}
                onClick={() => handleSelect(c.id)}
                className={`p-3 text-left transition relative flex flex-col gap-1.5 group ${
                  isSelected ? 'bg-brand-50/60 border-l-4 border-l-brand-600 pl-2.5' : 'hover:bg-slate-50'
                }`}
              >
                {/* Header: Node badge, Step #, Tier, Time */}
                <div className="flex items-center justify-between gap-1 w-full">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${visual.badgeBg} ${visual.badgeText} ${visual.badgeBorder}`}
                    >
                      {visual.icon}
                      <span>Step #{c.step}: {c.node}</span>
                    </span>

                    <span
                      className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-semibold uppercase ${
                        c.tier === 'reasoning'
                          ? 'bg-purple-100 text-purple-800'
                          : 'bg-blue-100 text-blue-800'
                      }`}
                    >
                      {c.tier}
                    </span>
                  </div>

                  <span className="text-[10px] font-mono text-slate-400">{c.timestamp}</span>
                </div>

                {/* Model Name & Metrics */}
                <div className="flex items-center justify-between text-[11px] font-mono text-slate-500">
                  <span className="truncate max-w-[170px] text-slate-800 font-semibold">{c.model}</span>
                  <div className="flex items-center gap-2 text-[10px]">
                    {c.durationMs !== undefined && (
                      <span className="text-slate-500">{c.durationMs}ms</span>
                    )}
                    {c.tokens !== undefined && (
                      <span className="text-purple-700 font-semibold">{c.tokens.toLocaleString()} tok</span>
                    )}
                  </div>
                </div>

                {/* Snippet / preview */}
                <div className="text-[11px] text-slate-500 line-clamp-2 leading-relaxed break-all font-mono bg-slate-50 p-1.5 rounded border border-slate-100">
                  {c.response?.content
                    ? c.response.content.slice(0, 120)
                    : c.response?.tool_calls && c.response.tool_calls.length > 0
                    ? `[调用工具]: ${c.response.tool_calls.map((t) => t.name).join(', ')}`
                    : (c.messages?.[c.messages.length - 1]?.content || '空请求')}
                </div>
              </button>
            );
          })}
        </div>

        {/* Right Pane: Selected Call Deep Inspector */}
        {selectedCall ? (
          <div className="flex-1 flex flex-col bg-white overflow-hidden">
            {/* Header: Selected Call Meta & Quick Actions */}
            <div className="px-4 py-3 border-b border-slate-200 bg-slate-50/50 flex flex-wrap items-center justify-between gap-2 shrink-0">
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-slate-900 text-sm font-mono">
                    Step #{selectedCall.step} : {selectedCall.node.toUpperCase()}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${
                      selectedCall.tier === 'reasoning'
                        ? 'bg-purple-100 text-purple-800 border border-purple-200'
                        : 'bg-blue-100 text-blue-800 border border-blue-200'
                    }`}
                  >
                    Tier: {selectedCall.tier}
                  </span>
                  <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-800 text-[11px] font-mono font-semibold border border-slate-200">
                    模型: {selectedCall.model}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-[11px] font-mono text-slate-500">
                  <span>时戳: {selectedCall.timestamp}</span>
                  {selectedCall.durationMs !== undefined && <span>耗时: {selectedCall.durationMs}ms</span>}
                  {selectedCall.tokens !== undefined && (
                    <span>消耗 Token: {selectedCall.tokens.toLocaleString()}</span>
                  )}
                  {selectedCall.response?.finish_reason && (
                    <span>结束状态: {selectedCall.response.finish_reason}</span>
                  )}
                </div>
              </div>

              {/* Copy Full Call JSON */}
              <button
                onClick={() =>
                  handleCopy(JSON.stringify(selectedCall, null, 2), `full-${selectedCall.id}`)
                }
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-mono font-medium shadow-2xs transition"
              >
                {copiedKey === `full-${selectedCall.id}` ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-600" />
                    <span className="text-emerald-700 font-bold">已复制完整 JSON</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5 text-slate-500" />
                    <span>复制完整调用报文</span>
                  </>
                )}
              </button>
            </div>

            {/* Sub-Tabs */}
            <div className="flex items-center gap-1 px-4 py-2 border-b border-slate-200 bg-white text-xs font-medium shrink-0">
              <button
                onClick={() => setActiveTab('messages')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition ${
                  activeTab === 'messages'
                    ? 'bg-brand-50 text-brand-700 font-bold'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`}
              >
                <MessageSquare className="w-3.5 h-3.5" />
                <span>Prompt 消息序列 ({selectedCall.messages?.length || 0})</span>
              </button>

              <button
                onClick={() => setActiveTab('tools')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition ${
                  activeTab === 'tools'
                    ? 'bg-brand-50 text-brand-700 font-bold'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`}
              >
                <Wrench className="w-3.5 h-3.5" />
                <span>工具定义 Schema ({selectedCall.tools?.length || 0})</span>
              </button>

              <button
                onClick={() => setActiveTab('response')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition ${
                  activeTab === 'response'
                    ? 'bg-brand-50 text-brand-700 font-bold'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`}
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>模型原始响应</span>
              </button>

              <button
                onClick={() => setActiveTab('raw')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition ${
                  activeTab === 'raw'
                    ? 'bg-brand-50 text-brand-700 font-bold'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`}
              >
                <FileJson className="w-3.5 h-3.5" />
                <span>Raw JSON</span>
              </button>
            </div>

            {/* Tab Content Body */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* TAB 1: Messages Sequence */}
              {activeTab === 'messages' && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs text-slate-500 font-mono">
                    <span>发送给大模型的完整上下文消息列表 (按注入时序排列):</span>
                    <span>共 {selectedCall.messages?.length || 0} 条消息</span>
                  </div>

                  {(selectedCall.messages || []).map((msg, mIdx) => {
                    const role = msg.role || 'user';
                    const roleBadgeClass =
                      role === 'system'
                        ? 'bg-purple-100 text-purple-800 border-purple-200'
                        : role === 'user'
                        ? 'bg-blue-100 text-blue-800 border-blue-200'
                        : role === 'assistant'
                        ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
                        : 'bg-amber-100 text-amber-900 border-amber-200';

                    const copyId = `msg-${mIdx}-${selectedCall.id}`;

                    return (
                      <div
                        key={mIdx}
                        className="rounded-xl border border-slate-200/90 bg-white shadow-2xs overflow-hidden"
                      >
                        {/* Message Card Header */}
                        <div className="px-3.5 py-2 bg-slate-50/80 border-b border-slate-100 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase border ${roleBadgeClass}`}
                            >
                              {role}
                            </span>
                            <span className="text-[11px] font-mono text-slate-400">
                              #{(mIdx + 1).toString().padStart(2, '0')}
                            </span>
                            {msg.tool_call_id && (
                              <span className="text-[10px] font-mono text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                                tool_call_id: {msg.tool_call_id}
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-mono text-slate-400">
                              {msg.content ? `${msg.content.length} 字符` : '无文本'}
                            </span>
                            <button
                              onClick={() => handleCopy(msg.content || JSON.stringify(msg, null, 2), copyId)}
                              className="p-1 rounded hover:bg-slate-200 text-slate-500 hover:text-slate-800 transition"
                              title="复制该条消息内容"
                            >
                              {copiedKey === copyId ? (
                                <Check className="w-3.5 h-3.5 text-emerald-600" />
                              ) : (
                                <Copy className="w-3.5 h-3.5" />
                              )}
                            </button>
                          </div>
                        </div>

                        {/* Message Content */}
                        <div className="p-3">
                          {msg.content ? (
                            <pre className="text-xs text-slate-800 font-mono whitespace-pre-wrap break-words leading-relaxed overflow-x-auto max-h-96">
                              {msg.content}
                            </pre>
                          ) : msg.tool_calls ? (
                            <pre className="text-xs text-slate-800 font-mono whitespace-pre-wrap break-words bg-slate-50 p-2 rounded border border-slate-100">
                              {JSON.stringify(msg.tool_calls, null, 2)}
                            </pre>
                          ) : (
                            <div className="text-xs text-slate-400 italic">空内容</div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* TAB 2: Tools Schema */}
              {activeTab === 'tools' && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs text-slate-500 font-mono">
                    <span>注册并挂载给大模型的 Function Calling Tools Schema:</span>
                    <span>共 {selectedCall.tools?.length || 0} 个可用工具</span>
                  </div>

                  {selectedCall.tools && selectedCall.tools.length > 0 ? (
                    <div className="space-y-3">
                      {selectedCall.tools.map((t: any, tIdx: number) => {
                        const toolName = t.function?.name || t.name || `Tool #${tIdx + 1}`;
                        const toolDesc = t.function?.description || t.description || '';
                        const toolParams = t.function?.parameters || t.parameters || {};

                        return (
                          <div
                            key={tIdx}
                            className="rounded-xl border border-slate-200 bg-white p-3 shadow-2xs space-y-2"
                          >
                            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                              <div className="flex items-center gap-2">
                                <code className="px-2 py-0.5 rounded bg-amber-50 text-amber-900 border border-amber-200 font-mono text-xs font-bold">
                                  {toolName}
                                </code>
                              </div>
                              <button
                                onClick={() =>
                                  handleCopy(JSON.stringify(t, null, 2), `tool-${tIdx}-${selectedCall.id}`)
                                }
                                className="p-1 rounded hover:bg-slate-100 text-slate-500 hover:text-slate-800 transition text-[11px] flex items-center gap-1 font-mono"
                              >
                                {copiedKey === `tool-${tIdx}-${selectedCall.id}` ? (
                                  <Check className="w-3.5 h-3.5 text-emerald-600" />
                                ) : (
                                  <Copy className="w-3.5 h-3.5" />
                                )}
                                <span>复制 Schema</span>
                              </button>
                            </div>

                            {toolDesc && (
                              <p className="text-xs text-slate-600 leading-relaxed font-sans">{toolDesc}</p>
                            )}

                            <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                              <div className="text-[10px] font-mono text-slate-400 font-semibold mb-1">
                                入参规范 (Parameters Schema):
                              </div>
                              <pre className="text-[11px] text-slate-800 font-mono overflow-x-auto whitespace-pre-wrap">
                                {JSON.stringify(toolParams, null, 2)}
                              </pre>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="py-12 text-center text-xs text-slate-400 font-mono">
                      本次调用未挂载 Function Tools（纯文本或结构化输出模式）。
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: Model Response */}
              {activeTab === 'response' && (
                <div className="space-y-4">
                  {/* Text Content */}
                  <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-2xs space-y-2">
                    <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                      <div className="flex items-center gap-1.5 font-bold text-xs text-slate-800 font-mono">
                        <Sparkles className="w-3.5 h-3.5 text-brand-600" />
                        <span>模型文本返回 (Response Content):</span>
                      </div>
                      <button
                        onClick={() =>
                          handleCopy(selectedCall.response?.content || '', `resp-text-${selectedCall.id}`)
                        }
                        className="p-1 rounded hover:bg-slate-100 text-slate-500 hover:text-slate-800 transition text-[11px] flex items-center gap-1 font-mono"
                      >
                        {copiedKey === `resp-text-${selectedCall.id}` ? (
                          <Check className="w-3.5 h-3.5 text-emerald-600" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                        <span>复制文本</span>
                      </button>
                    </div>

                    <pre className="text-xs text-slate-800 font-mono whitespace-pre-wrap break-words leading-relaxed overflow-x-auto max-h-96">
                      {selectedCall.response?.content || '(无文本直接返回)'}
                    </pre>
                  </div>

                  {/* Tool Calls */}
                  {selectedCall.response?.tool_calls && selectedCall.response.tool_calls.length > 0 && (
                    <div className="rounded-xl border border-amber-200 bg-amber-50/30 p-3.5 shadow-2xs space-y-2">
                      <div className="flex items-center justify-between border-b border-amber-100 pb-2">
                        <div className="flex items-center gap-1.5 font-bold text-xs text-amber-900 font-mono">
                          <Wrench className="w-3.5 h-3.5 text-amber-600" />
                          <span>生成的工具调用 (Generated Tool Calls):</span>
                        </div>
                        <button
                          onClick={() =>
                            handleCopy(
                              JSON.stringify(selectedCall.response.tool_calls, null, 2),
                              `resp-tools-${selectedCall.id}`
                            )
                          }
                          className="p-1 rounded hover:bg-amber-100 text-amber-800 transition text-[11px] flex items-center gap-1 font-mono"
                        >
                          {copiedKey === `resp-tools-${selectedCall.id}` ? (
                            <Check className="w-3.5 h-3.5 text-emerald-600" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                          <span>复制 Tool Calls</span>
                        </button>
                      </div>

                      <div className="space-y-2">
                        {selectedCall.response.tool_calls.map((tc, tcIdx) => (
                          <div
                            key={tcIdx}
                            className="bg-white p-2.5 rounded-lg border border-amber-200 space-y-1.5"
                          >
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] font-mono text-slate-400">#{tcIdx + 1}</span>
                              <code className="px-1.5 py-0.5 bg-amber-100 text-amber-900 rounded font-mono text-xs font-bold">
                                {tc.name}
                              </code>
                              {tc.id && (
                                <span className="text-[10px] font-mono text-slate-400">id: {tc.id}</span>
                              )}
                            </div>
                            <pre className="text-xs text-slate-800 font-mono whitespace-pre-wrap bg-slate-50 p-2 rounded border border-slate-100 overflow-x-auto">
                              {typeof tc.args === 'object' ? JSON.stringify(tc.args, null, 2) : String(tc.args)}
                            </pre>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 4: Raw JSON */}
              {activeTab === 'raw' && (
                <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-2xs space-y-2">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                    <span className="font-bold text-xs text-slate-800 font-mono">
                      原始完整报文数据快照 (Full JSON Snapshot):
                    </span>
                    <button
                      onClick={() =>
                        handleCopy(JSON.stringify(selectedCall, null, 2), `raw-json-${selectedCall.id}`)
                      }
                      className="p-1 rounded hover:bg-slate-100 text-slate-500 hover:text-slate-800 transition text-[11px] flex items-center gap-1 font-mono"
                    >
                      {copiedKey === `raw-json-${selectedCall.id}` ? (
                        <Check className="w-3.5 h-3.5 text-emerald-600" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                      <span>复制全部 JSON</span>
                    </button>
                  </div>
                  <pre className="text-[11px] text-slate-800 font-mono whitespace-pre-wrap break-words overflow-x-auto max-h-[500px]">
                    {JSON.stringify(selectedCall, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-center p-8 text-xs text-slate-400 font-mono">
            请从左侧选择一条调用记录进行详情检视。
          </div>
        )}
      </div>
    </div>
  );
};
