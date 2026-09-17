import React from 'react';
import {
  Bot,
  User,
  Shield,
  Clock,
  ThumbsUp,
  ThumbsDown,
  CheckSquare,
  FileCode2,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { TaskMessage } from '@/types';
import { MilestoneItem } from '@/components/domain/MilestoneItem';
import { FileMutationCard } from '@/components/domain/FileMutationCard';
import { SubagentReportCard } from './SubagentReportCard';

interface MessageBubbleProps {
  message: TaskMessage;
  onOpenFile: (path: string) => void;
}

export const MessageBubble: React.FC<MessageBubbleProps> = React.memo(
  ({ message, onOpenFile }) => {
    if (message.role === 'user') {
      return (
        <div className="flex items-start gap-3 justify-end select-none">
          <div className="bg-brand-600 text-white rounded-2xl rounded-tr-xs px-4 py-2.5 max-w-[85%] text-xs leading-relaxed shadow-sm">
            {message.content}
          </div>
          <div className="w-7 h-7 rounded-full bg-brand-700 text-white flex items-center justify-center shrink-0 text-xs font-bold shadow-xs">
            <User className="w-4 h-4" />
          </div>
        </div>
      );
    }

    if (message.role === 'system') {
      return (
        <div className="p-3 bg-gray-100 border border-gray-200 rounded-xl text-gray-700 text-xs flex items-center gap-2 select-none">
          <Shield className="w-4 h-4 text-gray-500 shrink-0" />
          <span>{message.content}</span>
        </div>
      );
    }

    return (
      <div className="flex items-start gap-3">
        <div className="w-7 h-7 rounded-full bg-brand-50 border border-brand-200 text-brand-600 flex items-center justify-center shrink-0 text-xs font-bold shadow-xs select-none">
          <Bot className="w-4 h-4" />
        </div>
        <div className="flex-1 space-y-3.5 min-w-0">
          <div className="bg-white border border-border-subtle rounded-2xl rounded-tl-xs p-4 text-xs leading-relaxed shadow-xs space-y-3.5">
            {/* Markdown Main Text */}
            <div className="prose prose-sm max-w-none text-gray-800">
              <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                {message.content}
              </ReactMarkdown>
            </div>

            {/* Milestones Checklist */}
            {message.milestones && message.milestones.length > 0 && (
              <div className="p-3 bg-gray-50/80 rounded-xl border border-gray-200/70 space-y-2">
                <div className="text-[11px] font-semibold text-gray-600 flex items-center gap-1.5 select-none">
                  <CheckSquare className="w-3.5 h-3.5 text-brand-600" />
                  <span>阶段目标与里程碑达成 (State Machine Milestones)</span>
                </div>
                <div className="space-y-0.5">
                  {message.milestones.map((m) => (
                    <MilestoneItem key={m.id} milestone={m} />
                  ))}
                </div>
              </div>
            )}

            {/* Subagent Report Envelopes */}
            {message.subagentReports && message.subagentReports.length > 0 && (
              <div className="space-y-2">
                {message.subagentReports.map((report, idx) => (
                  <SubagentReportCard key={idx} report={report} onOpenCitation={onOpenFile} />
                ))}
              </div>
            )}

            {/* File Mutations Grid */}
            {message.fileMutations && message.fileMutations.length > 0 && (
              <div className="space-y-2 pt-1">
                <div className="text-[11px] font-semibold text-gray-600 flex items-center gap-1 select-none">
                  <FileCode2 className="w-3.5 h-3.5 text-blue-600" />
                  <span>本次工作区改动 ({message.fileMutations.length} 个文件)</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {message.fileMutations.map((mut, idx) => (
                    <FileMutationCard key={idx} mutation={mut} onOpen={onOpenFile} />
                  ))}
                </div>
              </div>
            )}

            {/* Footer Meta */}
            <div className="flex items-center justify-between text-[11px] text-gray-400 pt-2 border-t border-gray-100 select-none">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {message.durationMs ? `${(message.durationMs / 1000).toFixed(1)}s` : '刚刚'}
                </span>
                {message.tokensUsed && <span>📊 {message.tokensUsed} tok</span>}
              </div>
              <div className="flex items-center gap-2">
                <button className="p-1 hover:text-gray-700 hover:bg-gray-100 rounded" title="赞同">
                  <ThumbsUp className="w-3 h-3" />
                </button>
                <button className="p-1 hover:text-gray-700 hover:bg-gray-100 rounded" title="反馈">
                  <ThumbsDown className="w-3 h-3" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }
);
