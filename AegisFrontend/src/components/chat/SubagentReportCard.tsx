import React from 'react';
import { Search, Globe } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { CitationBadge } from '@/components/domain/CitationBadge';

interface SubagentReport {
  type: 'doc_search' | 'research';
  title: string;
  queries?: string[];
  citations?: string[];
  summary: string;
  isExternal?: boolean;
}

interface SubagentReportCardProps {
  report: SubagentReport;
  onOpenCitation: (path: string) => void;
}

export const SubagentReportCard: React.FC<SubagentReportCardProps> = ({
  report,
  onOpenCitation,
}) => {
  const isDocSearch = report.type === 'doc_search';

  return (
    <div
      className={`p-3.5 rounded-xl border space-y-2 select-none shadow-2xs ${
        isDocSearch
          ? 'border-purple-200 bg-purple-50/40'
          : 'border-amber-200 bg-amber-50/40'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 font-semibold text-xs text-gray-900">
          {isDocSearch ? (
            <Search className="w-3.5 h-3.5 text-purple-600 shrink-0" />
          ) : (
            <Globe className="w-3.5 h-3.5 text-amber-600 shrink-0" />
          )}
          <span>{report.title}</span>
        </div>
        <Badge
          variant={isDocSearch ? 'purple' : 'warning'}
          size="xs"
        >
          {isDocSearch ? '3轮自适应 RAG' : '外部数据隔离'}
        </Badge>
      </div>

      {/* Summary */}
      <p className="text-gray-700 text-[11px] leading-relaxed">{report.summary}</p>

      {/* Queries attempted */}
      {report.queries && report.queries.length > 0 && (
        <div className="flex items-center gap-1.5 text-[10px] text-gray-500 font-mono overflow-x-auto">
          <span className="text-gray-400">检索改词:</span>
          {report.queries.map((q, idx) => (
            <span key={idx} className="px-1.5 py-0.2 bg-white rounded border border-gray-200">
              "{q}"
            </span>
          ))}
        </div>
      )}

      {/* Citations */}
      {report.citations && report.citations.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {report.citations.map((cite, cIdx) => (
            <CitationBadge key={cIdx} citation={cite} onClick={onOpenCitation} />
          ))}
        </div>
      )}
    </div>
  );
};
