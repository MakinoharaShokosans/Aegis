import React from 'react';
import type { TraceStep } from '@/types';
import { Badge } from '@/components/ui/Badge';

interface TraceTimelineProps {
  steps: TraceStep[];
}

export const TraceTimeline: React.FC<TraceTimelineProps> = ({ steps }) => {
  return (
    <div className="space-y-4 max-w-3xl mx-auto select-none">
      <div className="flex items-center justify-between text-xs text-gray-500 font-mono px-1">
        <span>LangGraph 节点状态机跃迁与因果时序流水 (EventBus)</span>
        <span>单步耗时与 Token 增量</span>
      </div>

      <div className="relative pl-6 border-l-2 border-gray-200 space-y-4">
        {steps.map((step) => (
          <div key={step.id} className="relative group">
            <div className="absolute -left-[31px] top-1.5 w-4 h-4 rounded-full bg-white border-2 border-brand-600 flex items-center justify-center">
              <div className="w-1.5 h-1.5 rounded-full bg-brand-600" />
            </div>
            <div className="p-3.5 rounded-xl border border-border-subtle bg-white hover:border-brand-300 shadow-2xs space-y-2 transition">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-mono text-xs">
                  <Badge variant="info" size="xs">
                    Step #{step.step}: {step.node}
                  </Badge>
                  <span className="text-gray-400">{step.timestamp}</span>
                </div>
                <div className="flex items-center gap-2 text-[11px] font-mono text-gray-500">
                  <span>⏱ {step.durationMs}ms</span>
                  {step.tokenUsage && <span>📊 {step.tokenUsage} tok</span>}
                </div>
              </div>
              {step.inputSummary && (
                <div className="text-xs text-gray-700 font-mono bg-gray-50 p-2 rounded-lg border border-gray-100">
                  <span className="text-gray-400">入参摘要: </span>
                  {step.inputSummary}
                </div>
              )}
              {step.outputSummary && (
                <div className="text-xs text-gray-800 font-mono bg-blue-50/40 p-2 rounded-lg border border-blue-100">
                  <span className="text-blue-500">出参判定: </span>
                  {step.outputSummary}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
