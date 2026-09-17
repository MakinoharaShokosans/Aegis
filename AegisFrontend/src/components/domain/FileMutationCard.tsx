import React from 'react';
import { ExternalLink, FileCode, FileText, Code2, Settings } from 'lucide-react';
import type { FileMutation } from '@/types';
import { Badge } from '@/components/ui/Badge';

interface FileMutationCardProps {
  mutation: FileMutation;
  onOpen: (path: string) => void;
}

const actionBadges = {
  create: <Badge variant="success" size="xs">NEW</Badge>,
  modify: <Badge variant="info" size="xs">MODIFY</Badge>,
  delete: <Badge variant="danger" size="xs">DELETE</Badge>,
};

export const FileMutationCard: React.FC<FileMutationCardProps> = ({ mutation, onOpen }) => {
  const filename = mutation.path.split('/').pop() || mutation.path;

  const getFileIcon = () => {
    if (mutation.path.endsWith('.py')) return <span className="text-xs">🐍</span>;
    if (mutation.path.endsWith('.md')) return <FileText className="w-3.5 h-3.5 text-purple-600 shrink-0" />;
    if (mutation.path.endsWith('.c') || mutation.path.endsWith('.cpp'))
      return <Code2 className="w-3.5 h-3.5 text-blue-600 shrink-0" />;
    if (mutation.path.endsWith('.toml') || mutation.path.endsWith('.json'))
      return <Settings className="w-3.5 h-3.5 text-amber-600 shrink-0" />;
    return <FileCode className="w-3.5 h-3.5 text-gray-500 shrink-0" />;
  };

  return (
    <div className="p-2.5 rounded-xl border border-border-subtle bg-gray-50/60 hover:bg-white hover:border-brand-300 transition space-y-1 group shadow-2xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 truncate max-w-[170px]">
          {getFileIcon()}
          <span className="font-mono font-medium text-gray-900 text-xs truncate">{filename}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {actionBadges[mutation.action]}
          <button
            onClick={() => onOpen(mutation.path)}
            className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-white hover:bg-blue-50 border border-border-subtle text-brand-600 text-[10px] font-medium transition"
            title="在右侧画布中打开"
          >
            <span>打开</span>
            <ExternalLink className="w-2.5 h-2.5" />
          </button>
        </div>
      </div>
      <div className="text-[10px] text-gray-400 font-mono truncate">{mutation.path}</div>
      {mutation.summary && (
        <p className="text-[11px] text-gray-600 line-clamp-2 leading-relaxed">{mutation.summary}</p>
      )}
    </div>
  );
};
