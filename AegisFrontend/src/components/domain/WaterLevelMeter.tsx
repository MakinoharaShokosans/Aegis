import React from 'react';
import { Droplet } from 'lucide-react';

interface WaterLevelMeterProps {
  currentPct: number;
  maxPct?: number;
  activeTokens?: number;
  totalLimit?: number;
  className?: string;
}

export const WaterLevelMeter: React.FC<WaterLevelMeterProps> = ({
  currentPct,
  maxPct = 80,
  activeTokens,
  totalLimit = 80000,
  className = '',
}) => {
  const isHigh = currentPct >= maxPct;
  const isModerate = currentPct >= 50 && currentPct < maxPct;

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
        水位: {currentPct.toFixed(1)}% / {maxPct}%
      </span>
      {activeTokens !== undefined && (
        <span className="text-gray-400 font-normal">
          ({(activeTokens / 1000).toFixed(1)}k / {totalLimit / 1000}k tok)
        </span>
      )}
      <div className="w-12 h-1.5 bg-gray-200 rounded-full overflow-hidden shrink-0">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${Math.min(currentPct, 100)}%` }}
        />
      </div>
    </div>
  );
};
