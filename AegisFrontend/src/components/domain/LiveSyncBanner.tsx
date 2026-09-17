import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface LiveSyncBannerProps {
  onReload: () => void;
  isLoading?: boolean;
}

export const LiveSyncBanner: React.FC<LiveSyncBannerProps> = ({ onReload, isLoading = false }) => {
  return (
    <div className="flex items-center justify-between px-4 py-1.5 bg-amber-50 border-b border-amber-200 text-amber-900 text-xs animate-in slide-in-from-top-1 duration-150 select-none">
      <div className="flex items-center gap-2">
        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
        <span>⚠️ 该文档/代码已在底层磁盘被修改，当前视窗显示为缓存旧内容。</span>
      </div>
      <button
        onClick={onReload}
        disabled={isLoading}
        className="flex items-center gap-1 px-2.5 py-0.5 rounded bg-white hover:bg-amber-100 text-amber-900 border border-amber-300 font-medium text-[11px] shadow-2xs transition disabled:opacity-50"
      >
        <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
        <span>重新载入</span>
      </button>
    </div>
  );
};
