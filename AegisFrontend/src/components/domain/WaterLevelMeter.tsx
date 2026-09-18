import React from 'react';
import { Droplet } from 'lucide-react';

interface WaterLevelMeterProps {
  currentPct?: number;
  maxPct?: number;
  activeTokens?: number;
  totalLimit?: number;
  className?: string;
}

export const WaterLevelMeter: React.FC<WaterLevelMeterProps> = ({
  currentPct,
  maxPct = 80,
  activeTokens,
  totalLimit = 32000,
  className = '',
}) => {
  const pct = activeTokens !== undefined
    ? totalLimit > 0 ? (activeTokens / totalLimit) * 100 : 0
    : (currentPct ?? 0);

  const isHigh = pct >= maxPct;
  const isModerate = pct >= 50 && pct < maxPct;

  const colorClass = isHigh
    ? 'text-amber-700 bg-amber-50 border-amber-200'
    : isModerate
    ? 'text-blue-700 bg-blue-50 border-blue-200'
    : 'text-emerald-700 bg-emerald-50 border-emerald-200';

  const barColor = isHigh ? 'bg-amber-500' : isModerate ? 'bg-blue-500' : 'bg-emerald-500';

  return (
    <div className={`flex items-center gap-2 px-2 py-1 rounded-md border text-[10px] font-mono ${colorClass} ${className}`}>
      <Droplet className="w-3 h-3 shrink-0" />
      <span>
        水位: {pct.toFixed(1)}% / {maxPct}%
      </span>
      {activeTokens !== undefined && (
        <span className="text-slate-400 font-normal">
          ({(activeTokens / 1000).toFixed(1)}k / {totalLimit / 1000}k tok)
        </span>
      )}
      <div className="w-12 h-1.5 bg-slate-200 rounded-full overflow-hidden shrink-0">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  );
};
