import React from 'react';
import { FileText, ExternalLink } from 'lucide-react';

interface CitationBadgeProps {
  citation: string;
  onClick: (path: string) => void;
}

export const CitationBadge: React.FC<CitationBadgeProps> = ({ citation, onClick }) => {
  const [filePath] = citation.split(':');

  return (
    <button
      onClick={() => onClick(filePath)}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white hover:bg-purple-100/70 border border-purple-200 text-purple-700 text-[10px] font-mono transition shadow-2xs group"
      title="点击在右侧画布中查看"
    >
      <FileText className="w-2.5 h-2.5 text-purple-500" />
      <span>{citation}</span>
      <ExternalLink className="w-2 h-2 text-purple-400 group-hover:text-purple-600" />
    </button>
  );
};
