/**
 * Aegis Modern Session List
 * Renders sessions with status indicators, turn counts, relative timestamps, and deletion.
 */

import React, { useState } from 'react';
import {
  MessageSquare,
  Trash2,
  Search,
  Plus,
  Clock,
  ChevronRight,
} from 'lucide-react';
import type { Session } from '@/types';

interface SessionListProps {
  sessions: Session[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onNewSession?: () => void;
}

export const SessionList: React.FC<SessionListProps> = ({
  sessions,
  activeSessionId,
  onSelectSession,
  onDeleteSession,
  onNewSession,
}) => {
  const [searchFilter, setSearchFilter] = useState('');

  const filtered = sessions.filter((s) =>
    s.title.toLowerCase().includes(searchFilter.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full space-y-2 select-none">
      {/* Search Input */}
      <div className="relative px-1">
        <Search className="w-3 h-3 text-slate-400 absolute left-3 top-2.5" />
        <input
          type="text"
          value={searchFilter}
          onChange={(e) => setSearchFilter(e.target.value)}
          placeholder="搜索会话..."
          className="w-full pl-7 pr-3 py-1 text-[11px] bg-slate-50 border border-slate-200 rounded-md focus:outline-none focus:border-brand-500 text-slate-800"
        />
      </div>

      {/* Session Items */}
      <div className="flex-1 overflow-y-auto space-y-1 pr-1">
        {filtered.length === 0 ? (
          <div className="text-center py-10 px-2 space-y-2">
            <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400">
              <MessageSquare className="w-4 h-4" />
            </div>
            <p className="text-xs text-slate-400">
              {sessions.length === 0 ? '当前工作区暂无会话' : '暂无匹配的会话任务'}
            </p>
            {onNewSession && (
              <button
                onClick={onNewSession}
                className="text-xs text-brand-600 hover:text-brand-700 font-medium inline-flex items-center gap-1"
              >
                <Plus className="w-3 h-3" />
                <span>新建会话</span>
              </button>
            )}
          </div>
        ) : (
          filtered.map((s) => {
            const isActive = activeSessionId === s.id;
            return (
              <div
                key={s.id}
                onClick={() => onSelectSession(s.id)}
                className={`group relative flex flex-col p-2 rounded-lg cursor-pointer transition border ${
                  isActive
                    ? 'bg-brand-50/60 border-brand-200 text-slate-900 shadow-2xs'
                    : 'bg-white hover:bg-slate-50 border-slate-150 text-slate-700 hover:border-slate-200'
                }`}
              >
                <div className="flex items-start justify-between gap-1.5">
                  <div className="flex items-center gap-1.5 truncate flex-1 font-medium text-xs">
                    <MessageSquare
                      className={`w-3.5 h-3.5 shrink-0 ${
                        isActive ? 'text-brand-600' : 'text-slate-400 group-hover:text-slate-600'
                      }`}
                    />
                    <span className="truncate font-semibold">{s.title}</span>
                  </div>

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteSession(s.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-rose-100 text-slate-400 hover:text-rose-600 transition shrink-0"
                    title="删除会话"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>

                <div className="flex items-center justify-between mt-1 text-[10px] text-slate-400 font-mono">
                  <span className="flex items-center gap-1">
                    <Clock className="w-2.5 h-2.5" />
                    <span>{s.created_at ? new Date(s.created_at).toLocaleDateString() : '刚刚'}</span>
                  </span>
                  {isActive && (
                    <span className="flex items-center gap-0.5 text-brand-600 font-sans font-medium text-[10px]">
                      <span>当前</span>
                      <ChevronRight className="w-2.5 h-2.5" />
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
