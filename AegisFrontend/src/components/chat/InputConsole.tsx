/**
 * Aegis Modern Input Console
 * Floating bottom console with Slash command helpers, dual-model gateway selector, and token telemetry.
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowUp,
  Shield,
  Cpu,
  Sparkles,
  Paperclip,
  BookOpen,
  Terminal,
  Square,
  RotateCcw,
} from 'lucide-react';
import type { PermissionLevel, TelemetryStats } from '@/types';
import { systemApi } from '@/api';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';

interface InputConsoleProps {
  onSend: (prompt: string, options: { permissionLevel: PermissionLevel; model: string }) => void;
  onCancel?: () => void;
  telemetry?: TelemetryStats;
  disabled?: boolean;
  isExecuting?: boolean;
}

interface ModelOption {
  value: string;
  label: string;
}

const DEFAULT_MODEL_OPTIONS: ModelOption[] = [
  {
    value: 'Dual-Tier: gpt-5.6-terra + gpt-5.4-mini',
    label: 'Dual-Tier: gpt-5.6-terra + gpt-5.4-mini (默认)',
  },
  {
    value: 'Dual-Tier: gpt-5.6-terra + gpt-5.6-luna',
    label: 'Dual-Tier: gpt-5.6-terra + gpt-5.6-luna (高性能)',
  },
  {
    value: 'Fast Only: gpt-5.4-mini',
    label: 'Fast Only: gpt-5.4-mini',
  },
  {
    value: 'Fast Only: gpt-5.6-luna',
    label: 'Fast Only: gpt-5.6-luna',
  },
];

export const InputConsole: React.FC<InputConsoleProps> = ({
  onSend,
  onCancel,
  telemetry,
  disabled = false,
  isExecuting = false,
}) => {
  const { activeSessionId } = useWorkspaceStore();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [inputVal, setInputVal] = useState('');
  const [permissionLevel, setPermissionLevel] = useState<PermissionLevel>('workspace_write');
  const [modelOptions, setModelOptions] = useState<ModelOption[]>(DEFAULT_MODEL_OPTIONS);
  const [selectedModel, setSelectedModel] = useState<string>(DEFAULT_MODEL_OPTIONS[0].value);
  const [showSlashMenu, setShowSlashMenu] = useState(false);

  useEffect(() => {
    textareaRef.current?.focus();
  }, [activeSessionId]);

  useEffect(() => {
    let mounted = true;
    systemApi.getModels().then((data) => {
      if (!mounted || !data) return;
      const opts: ModelOption[] = [];
      const reasoningEndpoints = data.reasoning?.endpoints || [];
      const fastEndpoints = data.fast?.endpoints || [];

      if (reasoningEndpoints.length > 0 && fastEndpoints.length > 0) {
        reasoningEndpoints.forEach((r) => {
          fastEndpoints.forEach((f) => {
            opts.push({
              value: `Dual-Tier: ${r.model} + ${f.model}`,
              label: `Dual-Tier: ${r.name || r.model} + ${f.name || f.model}`,
            });
          });
        });
      }
      fastEndpoints.forEach((f) => {
        opts.push({
          value: `Fast Only: ${f.model}`,
          label: `Fast Only: ${f.name || f.model}`,
        });
      });

      if (opts.length > 0) {
        setModelOptions(opts);
        setSelectedModel((prev) => (opts.some((o) => o.value === prev) ? prev : opts[0].value));
      }
    }).catch(() => {
      // Keep defaults
    });

    return () => {
      mounted = false;
    };
  }, []);

  const handleSubmit = () => {
    if (!inputVal.trim() || disabled) return;
    onSend(inputVal.trim(), { permissionLevel, model: selectedModel });
    setInputVal('');
    setShowSlashMenu(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setInputVal(val);
    if (val.startsWith('/')) {
      setShowSlashMenu(true);
    } else {
      setShowSlashMenu(false);
    }
  };

  const insertSlashCommand = (cmd: string) => {
    setInputVal(cmd + ' ');
    setShowSlashMenu(false);
  };

  return (
    <div className="p-3 border-t border-slate-200 bg-slate-50/80 space-y-2 select-none z-10">
      <div className="max-w-3xl mx-auto space-y-2 relative">
        {/* Slash Command Quick Popup */}
        {showSlashMenu && (
          <div className="absolute bottom-full mb-2 left-0 w-72 bg-white rounded-xl shadow-modal border border-slate-200 py-1.5 z-50 animate-in fade-in zoom-in-95 duration-100 text-xs">
            <div className="px-3 py-1 text-[10px] font-semibold text-slate-400 uppercase">
              快捷指令 (Slash Commands)
            </div>
            <button
              onClick={() => insertSlashCommand('/rag 检索')}
              className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-slate-50 text-slate-700 text-left transition"
            >
              <BookOpen className="w-3.5 h-3.5 text-purple-600" />
              <div>
                <span className="font-semibold text-slate-900">/rag &lt;query&gt;</span>
                <p className="text-[10px] text-slate-400">调用 RAG 知识检索子智能体</p>
              </div>
            </button>
            <button
              onClick={() => insertSlashCommand('/test 运行测试')}
              className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-slate-50 text-slate-700 text-left transition"
            >
              <Terminal className="w-3.5 h-3.5 text-emerald-600" />
              <div>
                <span className="font-semibold text-slate-900">/test</span>
                <p className="text-[10px] text-slate-400">执行 pytest 单元测试套件</p>
              </div>
            </button>
            <button
              onClick={() => insertSlashCommand('/plan 规划')}
              className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-slate-50 text-slate-700 text-left transition"
            >
              <Sparkles className="w-3.5 h-3.5 text-brand-600" />
              <div>
                <span className="font-semibold text-slate-900">/plan &lt;goal&gt;</span>
                <p className="text-[10px] text-slate-400">使用 Reasoning 模型拆解里程碑</p>
              </div>
            </button>
          </div>
        )}

        {/* Input Box Card */}
        <div className="relative rounded-2xl border border-slate-200 bg-white shadow-card focus-within:border-brand-500 focus-within:ring-3 focus-within:ring-brand-50 transition p-3 space-y-2.5">
          <textarea
            ref={textareaRef}
            rows={2}
            value={inputVal}
            disabled={disabled || isExecuting}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={
              isExecuting
                ? '智能体正在执行当前任务中，可点击右侧红色按钮停止...'
                : '输入任务目标，输入 / 触发快捷指令，输入 @ 引用工作区规范或文档...'
            }
            className="w-full text-xs text-slate-800 placeholder-slate-400 focus:outline-none resize-none leading-relaxed disabled:bg-slate-50 font-sans"
          />

          {/* Bottom Bar: Permission / Model Selector & Send Button */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-xs">
            <div className="flex items-center gap-2">
              {/* Permission Baseline Selector */}
              <div className="flex items-center gap-1">
                <Shield className="w-3.5 h-3.5 text-brand-600" />
                <select
                  value={permissionLevel}
                  disabled={isExecuting}
                  onChange={(e) => setPermissionLevel(e.target.value as PermissionLevel)}
                  className="px-2 py-1 rounded-md bg-slate-50 hover:bg-slate-100 border border-slate-200 text-[11px] font-medium text-slate-700 focus:outline-none cursor-pointer disabled:opacity-50"
                >
                  <option value="read_only">只读免审批 (read_only)</option>
                  <option value="workspace_write">工作区写入 (workspace_write - 默认)</option>
                  <option value="full_permissions">全权限模式 (full_permissions - 需审批)</option>
                </select>
              </div>

              {/* Dual-Tier Model Selector */}
              <div className="hidden sm:flex items-center gap-1">
                <Cpu className="w-3.5 h-3.5 text-purple-600" />
                <select
                  value={selectedModel}
                  disabled={isExecuting}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="px-2 py-1 rounded-md bg-slate-50 hover:bg-slate-100 border border-slate-200 text-[11px] font-medium text-slate-700 focus:outline-none cursor-pointer disabled:opacity-50"
                >
                  {modelOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={isExecuting}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition disabled:opacity-40"
                title="添加工作区附件"
              >
                <Paperclip className="w-4 h-4" />
              </button>

              {isExecuting ? (
                <button
                  type="button"
                  onClick={onCancel}
                  className="p-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white transition shadow-xs flex items-center justify-center animate-pulse"
                  title="停止当前正在执行的任务"
                >
                  <Square className="w-4 h-4 fill-white" />
                </button>
              ) : (
                <button
                  onClick={handleSubmit}
                  disabled={!inputVal.trim() || disabled}
                  className="p-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white transition disabled:opacity-40 disabled:hover:bg-brand-600 shadow-xs flex items-center justify-center"
                  title="发送任务 (Enter)"
                >
                  <ArrowUp className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Context & Task Status Bar */}
        <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 px-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="flex items-center gap-1">
              <RotateCcw className="w-3 h-3 text-slate-400" />
              <span>{telemetry?.rounds ?? 0} 轮 {telemetry?.steps ?? 0} 步</span>
            </span>
            <span>·</span>
            <span title="当前送入大模型 Prompt 活跃滑窗视界大小 (上限 32k 限制)">
              上下文水位: {(telemetry?.contextTokens ?? (telemetry ? 850 : 0)).toLocaleString()} / 32,000 ({telemetry?.waterLevelPct ?? 0}%)
            </span>
            <span>·</span>
            <span title="本轮任务全状态机思考链路与工具调用累计产生的实际物理 Token 消耗 (对标 200k 预算)">
              任务消耗: {(telemetry?.totalTokens ?? 0).toLocaleString()} tokens
            </span>
          </div>

          <div className="hidden sm:flex items-center gap-1 text-slate-400">
            按 <kbd className="px-1 py-0.5 bg-slate-100 border border-slate-200 rounded text-[9px]">Enter</kbd> 发送 / <kbd className="px-1 py-0.5 bg-slate-100 border border-slate-200 rounded text-[9px]">Shift+Enter</kbd> 换行
          </div>
        </div>
      </div>
    </div>
  );
};
