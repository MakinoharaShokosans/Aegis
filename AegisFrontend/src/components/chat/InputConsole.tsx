import React, { useState } from 'react';
import { Paperclip, ArrowUp } from 'lucide-react';
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

  const handleSubmit = () => {
    if (!inputVal.trim() || disabled) return;
    onSend(inputVal.trim(), { permissionLevel, model: selectedModel });
    setInputVal('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="p-3 border-t border-border-subtle bg-canvas-secondary space-y-2 select-none">
      <div className="max-w-3xl mx-auto space-y-2">
        {/* Input Box */}
        <div className="relative rounded-2xl border border-border-subtle bg-white shadow-xs focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-100 transition p-2.5 space-y-2">
          <textarea
            rows={2}
            value={inputVal}
            disabled={disabled}
            onChange={(e) => setInputVal(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入任务目标，/ 调用 Slash 指令，@ 引用工作区文档、规范或共享记忆..."
            className="w-full text-xs text-gray-800 placeholder-gray-400 focus:outline-hidden resize-none leading-relaxed disabled:bg-gray-50"
          />

          {/* Controls Bar */}
          <div className="flex items-center justify-between pt-1 border-t border-gray-100 text-xs">
            <div className="flex items-center gap-2">
              {/* Permission Baseline Selector */}
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
                onClick={handleSubmit}
                disabled={!inputVal.trim() || disabled}
                className="p-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white transition disabled:opacity-40 disabled:hover:bg-brand-600 shadow-xs"
              >
                <ArrowUp className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Telemetry Status Bar */}
        <div className="flex items-center justify-between text-[10px] font-mono text-gray-500 px-1">
          <div className="flex items-center gap-3">
            <span>🔄 {telemetry?.rounds || 5} 轮 {telemetry?.steps || 14} 步</span>
            <span>⚡ {telemetry?.tokenSpeed || 271} tok/s</span>
            <span>📊 {((telemetry?.totalTokens || 28500) / 1000).toFixed(1)}k tok</span>
            <span className="text-emerald-700">🎯 缓存命中 99.8%</span>
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
