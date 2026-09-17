import React, { useState } from 'react';
import { MessageSquare, Trash2 } from 'lucide-react';
import type { Session } from '@/types';

interface SessionListProps {
  sessions: Session[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
}

export const SessionList: React.FC<SessionListProps> = ({
  sessions,
  activeSessionId,
  onSelectSession,
  onDeleteSession,
}) => {
  const [searchFilter, setSearchFilter] = useState('');

  const filtered = sessions.filter((s) =>
    s.title.toLowerCase().includes(searchFilter.toLowerCase())
  );

  return (
    <div className="space-y-1 select-none">
      {/* Header & Search */}
      <div className="pt-2 pb-1 flex items-center justify-between text-[11px] font-medium text-gray-400">
        <span>会话列表 (1:N 级联)</span>
        <input
          type="text"
          value={searchFilter}
          onChange={(e) => setSearchFilter(e.target.value)}
          placeholder="搜索会话..."
          className="w-24 px-1.5 py-0.5 text-[10px] bg-white border border-border-subtle rounded focus:outline-hidden"
        />
      </div>

      {/* Items */}
      <div className="space-y-0.5">
        {filtered.length === 0 ? (
          <div className="px-2 py-2 text-xs text-gray-400 italic">暂无历史任务会话</div>
        ) : (
          filtered.map((s) => (
            <div
              key={s.id}
              onClick={() => onSelectSession(s.id)}
              className={`group w-full flex items-center justify-between px-2 py-1.5 text-xs rounded-md cursor-pointer transition ${
                activeSessionId === s.id
                  ? 'bg-blue-50 text-brand-700 font-medium border-l-2 border-brand-600'
                  : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
              }`}
            >
              <div className="flex items-center gap-1.5 truncate flex-1">
                <MessageSquare className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{s.title}</span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteSession(s.id);
                }}
                className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-100 text-gray-400 hover:text-red-600 transition ml-1"
                title="删除会话"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
