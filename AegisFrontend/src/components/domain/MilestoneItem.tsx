import React from 'react';
import { CheckCircle2, Square, Loader2, XCircle } from 'lucide-react';
import type { MilestoneItem as MilestoneItemType } from '@/types';

interface MilestoneItemProps {
  milestone: MilestoneItemType;
  onToggle?: (id: string) => void;
}

export const MilestoneItem: React.FC<MilestoneItemProps> = ({ milestone, onToggle }) => {
  const isCompleted = milestone.status === 'completed';
  const isInProgress = milestone.status === 'in_progress';
  const isFailed = milestone.status === 'failed';

  return (
    <div
      onClick={() => onToggle?.(milestone.id)}
      className="flex items-center gap-2 py-1 px-1.5 rounded-lg text-xs text-gray-700 hover:bg-gray-100/60 transition cursor-pointer select-none"
    >
      {isCompleted ? (
        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
      ) : isInProgress ? (
        <Loader2 className="w-3.5 h-3.5 text-brand-600 animate-spin shrink-0" />
      ) : isFailed ? (
        <XCircle className="w-3.5 h-3.5 text-red-600 shrink-0" />
      ) : (
        <Square className="w-3.5 h-3.5 text-gray-400 shrink-0" />
      )}
      <span className={`leading-tight ${isCompleted ? 'line-through text-gray-400' : 'text-gray-800'}`}>
        {milestone.title}
      </span>
    </div>
  );
};
