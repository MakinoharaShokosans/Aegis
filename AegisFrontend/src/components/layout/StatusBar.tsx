/**
 * Aegis Modern Minimalist Bottom Status Bar
 */

import React from 'react';
import {
  ShieldCheck,
  Zap,
  Activity,
  Layers,
  Sparkles,
  Command,
  BookOpen,
} from 'lucide-react';
import { useTaskStore } from '@/stores/useTaskStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { useUiStore } from '@/stores/useUiStore';

export const StatusBar: React.FC = () => {
  const { currentTaskId, tasks } = useTaskStore();
  const { activeWorkspaceId, workspaces, activeSessionId } = useWorkspaceStore();
  const { setContextDrawerOpen, setRagCenterModalOpen, setSettingsModalOpen } = useUiStore();

  const currentTask = currentTaskId ? tasks[currentTaskId] : null;
  const currentWorkspace = workspaces.find((w) => w.id === activeWorkspaceId);
  const telemetry = currentTask?.telemetry;

  return (
    <footer className="h-7 px-3 bg-white border-t border-slate-200 flex items-center justify-between text-[11px] text-slate-500 select-none z-20">
      {/* Left: Backend connection & Session State */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-emerald-600 font-medium">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Aegis Core :8000 (在线)</span>
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
        </div>

        <div className="h-3 w-[1px] bg-slate-200" />

        <div className="flex items-center gap-1.5 text-slate-600 truncate max-w-[200px]">
          <span className="text-slate-400">工作区:</span>
          <span className="font-medium text-slate-700 truncate">{currentWorkspace?.name || '默认工作区'}</span>
        </div>

        {activeSessionId && (
          <>
            <div className="h-3 w-[1px] bg-slate-200" />
            <div className="hidden sm:flex items-center gap-1 font-mono text-[10px] text-slate-400">
              <span>会话: {activeSessionId.slice(0, 12)}</span>
            </div>
          </>
        )}
      </div>

      {/* Center: Live Telemetry (Speed, Cache, Water level) */}
      <div className="hidden md:flex items-center gap-4">
        {telemetry && (
          <>
            <div className="flex items-center gap-1 text-slate-600">
              <Zap className="w-3 h-3 text-amber-500" />
              <span>速度:</span>
              <span className="font-mono font-medium text-slate-800">{telemetry.tokenSpeed} tok/s</span>
            </div>

            <div className="flex items-center gap-1 text-slate-600">
              <Sparkles className="w-3 h-3 text-blue-500" />
              <span>缓存命中:</span>
              <span className="font-mono font-medium text-slate-800">{(telemetry.cacheHitRate * 100).toFixed(1)}%</span>
            </div>

            <button
              onClick={() => setContextDrawerOpen(true)}
              className="flex items-center gap-1.5 hover:text-brand-600 transition"
              title="查看 Token 水位与四层上下文分布"
            >
              <Layers className="w-3 h-3 text-brand-500" />
              <span>水位:</span>
              <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden border border-slate-200">
                <div
                  className={`h-full rounded-full transition-all ${
                    telemetry.waterLevelPct > 70
                      ? 'bg-amber-500'
                      : telemetry.waterLevelPct > 85
                      ? 'bg-rose-500'
                      : 'bg-emerald-500'
                  }`}
                  style={{ width: `${Math.min(telemetry.waterLevelPct, 100)}%` }}
                />
              </div>
              <span className="font-mono font-medium text-slate-800">{telemetry.waterLevelPct}%</span>
            </button>
          </>
        )}
      </div>

      {/* Right: Sidecar badges & Quick Shortcuts */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 font-mono text-[10px]">
          <button
            onClick={() => setRagCenterModalOpen(true)}
            className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-50 hover:bg-purple-50 text-purple-700 border border-slate-200 hover:border-purple-200 transition"
            title="AegisRAG 微服务 (:8001)"
          >
            <BookOpen className="w-3 h-3 text-purple-500" />
            <span>RAG:8001</span>
          </button>

          <button
            onClick={() => setSettingsModalOpen(true)}
            className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-50 hover:bg-slate-100 text-slate-600 border border-slate-200 transition"
            title="Sidecars: Bash (:8002) / Web (:8003)"
          >
            <Activity className="w-3 h-3 text-emerald-500" />
            <span>Shell:8002</span>
          </button>
        </div>

        <div className="hidden lg:flex items-center gap-1 text-slate-400">
          <Command className="w-3 h-3" />
          <span>Cmd+K 快捷指令</span>
        </div>
      </div>
    </footer>
  );
};
