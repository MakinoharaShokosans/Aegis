/**
 * Aegis Modern Input Console
 * Floating bottom console with Slash command helpers, dual-model gateway selector, and token telemetry.
 */

import React, { useState } from 'react';
import {
  ArrowUp,
  Shield,
  Cpu,
  Sparkles,
  Paperclip,
  BookOpen,
  Terminal,
} from 'lucide-react';
import type { PermissionLevel, TelemetryStats } from '@/types';
import { WaterLevelMeter } from '@/components/domain/WaterLevelMeter';

interface InputConsoleProps {
  onSend: (prompt: string, options: { permissionLevel: PermissionLevel; model: string }) => void;
  telemetry?: TelemetryStats;
  disabled?: boolean;
}

export const InputConsole: React.FC<InputConsoleProps> = ({
  onSend,
  telemetry,
  disabled = false,
}) => {
  const [inputVal, setInputVal] = useState('');
  const [permissionLevel, setPermissionLevel] = useState<PermissionLevel>('workspace_write');
  const [selectedModel, setSelectedModel] = useState('Reasoning: DeepSeek-R1 / Fast: DeepSeek-V3');
  const [showSlashMenu, setShowSlashMenu] = useState(false);

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
            rows={2}
            value={inputVal}
            disabled={disabled}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="输入任务目标，输入 / 触发快捷指令，输入 @ 引用工作区规范或文档..."
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
                  onChange={(e) => setPermissionLevel(e.target.value as PermissionLevel)}
                  className="px-2 py-1 rounded-md bg-slate-50 hover:bg-slate-100 border border-slate-200 text-[11px] font-medium text-slate-700 focus:outline-none cursor-pointer"
                >
                  <option value="readonly">🔒 只读免审批 (readonly)</option>
                  <option value="workspace_write">🛡 工作区写入 (workspace_write - 默认)</option>
                  <option value="full_access">⚡ 全权限模式 (full_access - 需审批)</option>
                </select>
              </div>

              {/* Dual-Tier Model Selector */}
              <div className="hidden sm:flex items-center gap-1">
                <Cpu className="w-3.5 h-3.5 text-purple-600" />
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="px-2 py-1 rounded-md bg-slate-50 hover:bg-slate-100 border border-slate-200 text-[11px] font-medium text-slate-700 focus:outline-none cursor-pointer"
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
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
                title="添加工作区附件"
              >
                <Paperclip className="w-4 h-4" />
              </button>

              <button
                onClick={handleSubmit}
                disabled={!inputVal.trim() || disabled}
                className="p-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white transition disabled:opacity-40 disabled:hover:bg-brand-600 shadow-xs flex items-center justify-center"
                title="发送任务 (Enter)"
              >
                <ArrowUp className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Telemetry Status Bar */}
        <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 px-1">
          <div className="flex items-center gap-3">
            <span>🔄 {telemetry?.rounds || 5} 轮 {telemetry?.steps || 14} 步</span>
            <span>⚡ {telemetry?.tokenSpeed || 271} tok/s</span>
            <span>📊 {((telemetry?.totalTokens || 28500) / 1000).toFixed(1)}k tok</span>
            <span className="text-emerald-700 font-medium">🎯 缓存 99.8%</span>
          </div>

          <WaterLevelMeter
            currentPct={telemetry?.waterLevelPct || 32}
            maxPct={telemetry?.maxWaterLevelPct || 80}
            activeTokens={telemetry?.totalTokens || 28500}
          />
        </div>
      </div>
    </div>
  );
};
