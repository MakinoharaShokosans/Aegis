import React, { useState } from 'react';
import {
  Users,
  Shield,
  Copy,
  Share2,
  MoreHorizontal,
  Bot,
  User,
  ExternalLink,
  ThumbsUp,
  ThumbsDown,
  RotateCw,
  Plus,
  Paperclip,
  ArrowUp,
  Sparkles,
  Layers,
  Activity,
  Zap,
  BarChart3,
  Flame,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { useUiStore } from '@/stores/useUiStore';
import { useTaskStore } from '@/stores/useTaskStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import type { FileMutation } from '@/types';

export const ChatPane: React.FC = () => {
  const { activeView, setActiveView } = useUiStore();
  const { currentTaskId, tasks, upsertTask, appendMessage } = useTaskStore();
  const { openTab } = useWorkspaceStore();

  const [inputVal, setInputVal] = useState('');
  const [selectedModel, setSelectedModel] = useState('DeepSeek V4.1 Flash High');
  const [permissionLevel, setPermissionLevel] = useState<'readonly' | 'workspace_write' | 'full_access'>('workspace_write');

  const currentTask = currentTaskId ? tasks[currentTaskId] : null;

  const handleSend = () => {
    if (!inputVal.trim()) return;

    let taskId = currentTaskId;
    if (!taskId) {
      taskId = `task-${Date.now()}`;
      upsertTask({
        id: taskId,
        title: inputVal.slice(0, 40),
        prompt: inputVal,
        status: 'running',
        permissionLevel,
        model: 'deepseek-chat',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messages: [
          {
            id: `msg-${Date.now()}`,
            role: 'user',
            content: inputVal,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
          {
            id: `msg-${Date.now() + 1}`,
            role: 'assistant',
            content: `### 正在分析与执行任务\n\n已成功启动智能体编排流水线。正在扫描相关模块和工作区上下文。\n\n- [x] 解析用户需求意图\n- [x] 分派子代理进行代码架构检索\n- [ ] 生成并应用改动补丁`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            durationMs: 1420,
            fileMutations: [
              {
                path: 'AegisAgent/event_bus.py',
                action: 'modify',
                summary: '任务事件总线：扩展叶子工具广播及子智能体状态事件',
              },
              {
                path: 'AegisAgent/api/auth.py',
                action: 'modify',
                summary: '接入层三道安全闸门：Host 防重绑定与恒定时间令牌',
              },
              {
                path: 'documents/11_http_api.md',
                action: 'create',
                summary: 'API 契约：新增任务鉴权与 SSE 端点定义',
              },
            ],
          },
        ],
        traceSteps: [
          {
            id: 'trace-1',
            node: 'planner',
            step: 1,
            durationMs: 420,
            timestamp: new Date().toISOString(),
          },
          {
            id: 'trace-2',
            node: 'subagent',
            step: 2,
            durationMs: 1000,
            timestamp: new Date().toISOString(),
          },
        ],
        subagents: [
          { id: 'sub-1', name: 'Codebase Researcher', role: '代码检索', status: 'completed', stepCount: 4 },
          { id: 'sub-2', name: 'Security Auditor', role: '安全审计', status: 'running', stepCount: 2 },
        ],
        telemetry: {
          rounds: 1,
          steps: 6,
          tokenSpeed: 271,
          totalTokens: 14850,
          cacheHitRate: 0.998,
        },
      });
      useTaskStore.getState().setCurrentTaskId(taskId);
    } else {
      appendMessage(taskId, {
        id: `msg-${Date.now()}`,
        role: 'user',
        content: inputVal,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      });
    }

    setInputVal('');
  };

  const handleOpenFile = (mutation: FileMutation) => {
    openTab({
      filePath: mutation.path,
      title: mutation.path.split('/').pop() || mutation.path,
      language: mutation.path.endsWith('.py') ? 'python' : mutation.path.endsWith('.md') ? 'markdown' : 'plaintext',
      content: `# ${mutation.path}\n\n// 查看文件变更内容：\n// ${mutation.summary || '无摘要说明'}`,
    });
  };

  return (
    <div className="flex flex-col h-screen bg-canvas-primary border-r border-border-subtle relative">
      {/* 1. Top Header Bar */}
      <header className="flex items-center justify-between px-4 py-2.5 border-b border-border-subtle bg-white shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <h2 className="font-semibold text-xs text-gray-800 truncate max-w-md">
            {currentTask?.title || '新会话 - 探索项目完成度与架构定位'}
          </h2>
          {/* Subagent Count Badge */}
          <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-brand-700 text-[11px] font-medium border border-blue-200 shrink-0">
            <Users className="w-3 h-3" />
            <span>{currentTask?.subagents.length || 6} 个子代理</span>
          </div>
          {/* Mode Badge */}
          <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 text-[11px] font-medium border border-gray-200 shrink-0">
            <Sparkles className="w-3 h-3 text-amber-500" />
            <span>标准模式</span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-1 text-gray-500">
          <button className="p-1.5 hover:bg-gray-100 rounded text-gray-600 transition" title="复制对话">
            <Copy className="w-3.5 h-3.5" />
          </button>
          <button className="p-1.5 hover:bg-gray-100 rounded text-gray-600 transition" title="分享">
            <Share2 className="w-3.5 h-3.5" />
          </button>
          <button className="p-1.5 hover:bg-gray-100 rounded text-gray-600 transition" title="更多">
            <MoreHorizontal className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* 2. View Switcher Tabs (Chat vs Trace) */}
      <div className="flex items-center px-4 border-b border-border-subtle bg-canvas-secondary shrink-0">
        <button
          onClick={() => setActiveView('chat')}
          className={`flex items-center gap-1.5 py-2 px-3 text-xs font-medium border-b-2 transition ${
            activeView === 'chat'
              ? 'border-brand-600 text-brand-600 bg-white'
              : 'border-transparent text-gray-500 hover:text-gray-900'
          }`}
        >
          <Bot className="w-3.5 h-3.5" />
          <span>对话</span>
        </button>
        <button
          onClick={() => setActiveView('trace')}
          className={`flex items-center gap-1.5 py-2 px-3 text-xs font-medium border-b-2 transition ${
            activeView === 'trace'
              ? 'border-brand-600 text-brand-600 bg-white'
              : 'border-transparent text-gray-500 hover:text-gray-900'
          }`}
        >
          <Activity className="w-3.5 h-3.5" />
          <span>轨迹</span>
          {currentTask?.traceSteps && currentTask.traceSteps.length > 0 && (
            <span className="px-1.5 py-0.2 rounded-full bg-gray-200 text-[10px] text-gray-700 font-mono">
              {currentTask.traceSteps.length}
            </span>
          )}
        </button>
      </div>

      {/* 3. Main Message & Trace Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5 pb-36">
        {activeView === 'chat' ? (
          <>
            {/* If no current task messages */}
            {!currentTask || currentTask.messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-64 text-center text-gray-400 space-y-2">
                <Bot className="w-10 h-10 text-gray-300" />
                <p className="text-sm font-medium text-gray-600">输入任务以启动智能体协同执行</p>
                <p className="text-xs text-gray-400">支持多子代理委派、代码检索、全自动测试与产物审查</p>
              </div>
            ) : (
              currentTask.messages.map((msg) => (
                <div key={msg.id} className="flex flex-col space-y-2">
                  <div className="flex items-center gap-2 text-xs font-medium text-gray-600">
                    {msg.role === 'user' ? (
                      <div className="w-5 h-5 rounded-full bg-gray-200 flex items-center justify-center text-gray-700">
                        <User className="w-3 h-3" />
                      </div>
                    ) : (
                      <div className="w-5 h-5 rounded-full bg-brand-100 flex items-center justify-center text-brand-700">
                        <Bot className="w-3 h-3" />
                      </div>
                    )}
                    <span className="text-gray-900 font-semibold">{msg.role === 'user' ? '你' : 'Aegis Agent'}</span>
                    <span className="text-[11px] text-gray-400">{msg.timestamp}</span>
                  </div>

                  <div className="pl-7 text-xs leading-relaxed text-gray-800 prose prose-sm max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                      {msg.content}
                    </ReactMarkdown>

                    {/* File Mutations Section */}
                    {msg.fileMutations && msg.fileMutations.length > 0 && (
                      <div className="mt-3.5 space-y-2">
                        <div className="text-[11px] font-semibold text-gray-600 flex items-center gap-1">
                          <span>本次文件改动</span>
                          <span className="text-brand-600 font-mono">
                            {msg.fileMutations.map((m) => `</> ${m.path.split('/').pop()}`).join(' ')}
                          </span>
                        </div>

                        {/* 2-Column Mutation Cards */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                          {msg.fileMutations.map((mutation, idx) => (
                            <div
                              key={idx}
                              className="flex items-start justify-between p-2.5 rounded-lg border border-border-subtle bg-canvas-secondary hover:border-gray-300 transition"
                            >
                              <div className="flex items-start gap-2 min-w-0 pr-2">
                                {mutation.path.endsWith('.py') ? (
                                  <span className="text-sm">🐍</span>
                                ) : (
                                  <span className="text-sm">📄</span>
                                )}
                                <div className="min-w-0">
                                  <div className="text-xs font-semibold text-gray-800 truncate">
                                    {mutation.path.split('/').pop()}
                                  </div>
                                  <div className="text-[11px] text-gray-500 truncate mt-0.5">
                                    {mutation.summary || mutation.path}
                                  </div>
                                </div>
                              </div>
                              <button
                                onClick={() => handleOpenFile(mutation)}
                                className="flex items-center gap-1 px-2 py-1 text-[11px] font-medium text-brand-600 hover:bg-blue-100 rounded bg-blue-50 border border-blue-200 shrink-0 transition"
                              >
                                <span>打开</span>
                                <ExternalLink className="w-3 h-3" />
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Message Actions */}
                  {msg.role === 'assistant' && (
                    <div className="flex items-center gap-2 pl-7 pt-1 text-gray-400 text-xs">
                      <button className="p-1 hover:text-gray-700 hover:bg-gray-100 rounded" title="赞同">
                        <ThumbsUp className="w-3.5 h-3.5" />
                      </button>
                      <button className="p-1 hover:text-gray-700 hover:bg-gray-100 rounded" title="不赞同">
                        <ThumbsDown className="w-3.5 h-3.5" />
                      </button>
                      <button className="p-1 hover:text-gray-700 hover:bg-gray-100 rounded" title="复制">
                        <Copy className="w-3.5 h-3.5" />
                      </button>
                      <button className="p-1 hover:text-gray-700 hover:bg-gray-100 rounded" title="重新生成">
                        <RotateCw className="w-3.5 h-3.5" />
                      </button>
                      {msg.durationMs && (
                        <span className="ml-auto text-[11px] text-gray-400">
                          ⏱ 用时 {(msg.durationMs / 1000).toFixed(1)}s
                        </span>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </>
        ) : (
          /* Trace Stream View */
          <div className="space-y-3">
            <div className="text-xs font-semibold text-gray-700 flex items-center justify-between pb-2 border-b border-border-subtle">
              <span className="flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-brand-600" />
                执行流轨迹追踪 (Execution Trace)
              </span>
              <span className="text-[11px] text-gray-400 font-mono">
                {currentTask?.traceSteps.length || 0} 个步骤
              </span>
            </div>

            {(!currentTask || currentTask.traceSteps.length === 0) ? (
              <div className="text-center py-12 text-xs text-gray-400">暂无执行轨迹</div>
            ) : (
              currentTask.traceSteps.map((step) => (
                <div
                  key={step.id}
                  className="p-3 rounded-lg border border-border-subtle bg-white shadow-xs space-y-1.5 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-semibold text-brand-600">
                      Step {step.step}: [{step.node}]
                    </span>
                    <span className="text-[11px] text-gray-400 font-mono">{step.durationMs}ms</span>
                  </div>
                  <div className="text-[11px] text-gray-600 bg-canvas-secondary p-2 rounded font-mono">
                    Node: {step.node} | Timestamp: {step.timestamp}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* 4. Floating Input Console & System Telemetry */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-white via-white to-transparent pt-3 px-4 pb-2 border-t border-border-subtle">
        {/* Input Box Container */}
        <div className="bg-white border border-gray-300 rounded-xl shadow-sm focus-within:border-brand-500 focus-within:ring-1 focus-within:ring-brand-500 transition">
          <textarea
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="发送消息创建任务，/ 调用指令，@ 文件或对话"
            className="w-full h-16 p-3 text-xs text-gray-900 bg-transparent resize-none outline-none placeholder:text-gray-400"
          />

          {/* Action Toolbar */}
          <div className="flex items-center justify-between px-3 py-2 border-t border-gray-100">
            {/* Left Controls */}
            <div className="flex items-center gap-1.5">
              <button className="p-1 hover:bg-gray-100 rounded text-gray-500" title="添加上下文">
                <Plus className="w-4 h-4" />
              </button>
              <button className="p-1 hover:bg-gray-100 rounded text-gray-500" title="上传附件">
                <Paperclip className="w-4 h-4" />
              </button>
              {/* Permission Badge Selector */}
              <button
                onClick={() =>
                  setPermissionLevel((prev) =>
                    prev === 'workspace_write' ? 'full_access' : prev === 'full_access' ? 'readonly' : 'workspace_write'
                  )
                }
                className="flex items-center gap-1 px-2 py-1 rounded bg-guard-bg text-guard-text border border-guard-border text-[11px] font-medium transition"
              >
                <Shield className="w-3 h-3" />
                <span>
                  {permissionLevel === 'workspace_write'
                    ? '🛡 工作区内修改'
                    : permissionLevel === 'full_access'
                    ? '⚡ 全权限模式'
                    : '🔒 只读免审批'}
                </span>
              </button>
            </div>

            {/* Right Controls */}
            <div className="flex items-center gap-2">
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="text-[11px] font-medium text-gray-700 bg-gray-50 border border-gray-200 rounded px-2 py-1 outline-none cursor-pointer"
              >
                <option value="DeepSeek V4.1 Flash High">DeepSeek V4.1 Flash High</option>
                <option value="DeepSeek Reasoner (R1)">DeepSeek Reasoner (R1)</option>
                <option value="DeepSeek Chat (V3)">DeepSeek Chat (V3)</option>
              </select>

              <button
                onClick={handleSend}
                disabled={!inputVal.trim()}
                className={`p-1.5 rounded-full text-white shadow-xs transition ${
                  inputVal.trim()
                    ? 'bg-brand-600 hover:bg-brand-700 active:scale-95'
                    : 'bg-gray-300 cursor-not-allowed'
                }`}
              >
                <ArrowUp className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* System Telemetry Status Bar */}
        <div className="flex items-center justify-between mt-2 px-1 text-[11px] font-mono text-gray-500 select-none">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <RotateCw className="w-3 h-3 text-gray-400" />
              {currentTask?.telemetry.rounds || 22} 轮 {currentTask?.telemetry.steps || 634} 步
            </span>
            <span>|</span>
            <span className="flex items-center gap-1 text-amber-600">
              <Zap className="w-3 h-3" />
              {currentTask?.telemetry.tokenSpeed || 271} tok/s
            </span>
            <span>|</span>
            <span className="flex items-center gap-1">
              <BarChart3 className="w-3 h-3" />
              {currentTask?.telemetry.totalTokens ? `${(currentTask.telemetry.totalTokens / 1000000).toFixed(1)}M` : '109M'} tok
            </span>
            <span>|</span>
            <span className="flex items-center gap-1 text-emerald-600 font-medium">
              <Flame className="w-3 h-3" />
              缓存命中 {currentTask?.telemetry.cacheHitRate ? `${(currentTask.telemetry.cacheHitRate * 100).toFixed(1)}%` : '99.8%'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
