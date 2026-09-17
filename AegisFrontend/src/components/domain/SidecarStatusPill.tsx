import React from 'react';
import { Activity } from 'lucide-react';

interface SidecarStatusProps {
  ragOnline?: boolean;
  shellOnline?: boolean;
  webOnline?: boolean;
  className?: string;
}

export const SidecarStatusPill: React.FC<SidecarStatusProps> = ({
  ragOnline = true,
  shellOnline = true,
  webOnline = true,
  className = '',
}) => {
  return (
    <div
      className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-gray-100/90 border border-gray-200 text-[10px] font-mono text-gray-600 ${className}`}
    >
      <Activity className="w-3 h-3 text-emerald-600 shrink-0" />
      <span className="font-semibold text-gray-700">Sidecars:</span>
      <span className={ragOnline ? 'text-emerald-700 font-medium' : 'text-red-600'}>
        RAG:8001 {ragOnline ? '●' : '○'}
      </span>
      <span className={shellOnline ? 'text-emerald-700 font-medium' : 'text-red-600'}>
        Shell:8002 {shellOnline ? '●' : '○'}
      </span>
      <span className={webOnline ? 'text-emerald-700 font-medium' : 'text-red-600'}>
        Web:8003 {webOnline ? '●' : '○'}
      </span>
    </div>
  );
};
