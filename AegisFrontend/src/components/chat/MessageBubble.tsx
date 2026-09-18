/**
 * Aegis Modern Message Bubble
 * React.memo cached message item with rich markdown typography, milestone checklist, and mutation cards.
 */

import React, { useState } from 'react';
import {
  Clock,
  ThumbsUp,
  ThumbsDown,
  CheckSquare,
  FileCode2,
  Copy,
  Check,
  Zap,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { TaskMessage } from '@/types';
import { MilestoneItem } from '@/components/domain/MilestoneItem';
import { FileMutationCard } from '@/components/domain/FileMutationCard';
import { SubagentReportCard } from './SubagentReportCard';
import {
  AegisAiAvatar,
  AegisUserAvatar,
  AegisSystemAvatar,
} from '@/components/common/AegisAvatar';

interface MessageBubbleProps {
  message: TaskMessage;
  onOpenFile: (path: string) => void;
}

function parseMessageContent(content: string): string {
  if (!content || typeof content !== 'string') return '';
  const trimmed = content.trim();
  if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
    try {
      const parsed = JSON.parse(trimmed);
      if (parsed && typeof parsed === 'object') {
        if (typeof parsed.message === 'string') return parsed.message;
        if (typeof parsed.content === 'string') return parsed.content;
        if (typeof parsed.response === 'string') return parsed.response;
        if (typeof parsed.result === 'string') return parsed.result;
        if (typeof parsed.answer === 'string') return parsed.answer;
      }
    } catch {
      // not valid JSON, fallback to original content
    }
  }
  return content;
}

export const MessageBubble: React.FC<MessageBubbleProps> = React.memo(
  ({ message, onOpenFile }) => {
    const [copied, setCopied] = useState(false);
    const displayContent = parseMessageContent(message.content);

    const handleCopy = () => {
      navigator.clipboard.writeText(displayContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    };

    if (message.role === 'user') {
      return (
        <div className="flex items-start gap-3 justify-end select-none animate-in fade-in duration-150">
          <div className="bg-brand-600 text-white rounded-2xl rounded-tr-xs px-4 py-2.5 max-w-[85%] text-xs leading-relaxed shadow-sm whitespace-pre-wrap">
            {displayContent}
          </div>
          <AegisUserAvatar size="md" glow className="mt-0.5" />
        </div>
      );
    }

    if (message.role === 'system') {
      return (
        <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-700 text-xs flex items-center gap-2.5 select-none shadow-2xs">
          <AegisSystemAvatar size="sm" />
          <span className="leading-relaxed">{displayContent}</span>
        </div>
      );
    }

    return (
      <div className="flex items-start gap-3 animate-in fade-in duration-150">
        <AegisAiAvatar size="md" glow className="mt-0.5" />

        <div className="flex-1 space-y-3 min-w-0">
          <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-xs p-4 text-xs leading-relaxed shadow-xs space-y-3.5">
            {/* Markdown Main Text */}
            <div className="prose prose-sm max-w-none text-slate-800 font-sans leading-relaxed">
              <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                {displayContent}
              </ReactMarkdown>
            </div>

            {/* Milestones Checklist */}
            {message.milestones && message.milestones.length > 0 && (
              <div className="p-3 bg-slate-50/80 rounded-xl border border-slate-200/80 space-y-2">
                <div className="text-[11px] font-semibold text-slate-700 flex items-center gap-1.5 select-none">
                  <CheckSquare className="w-3.5 h-3.5 text-brand-600" />
                  <span>阶段目标与里程碑达成 (State Machine Milestones)</span>
                </div>
                <div className="space-y-1">
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
                <div className="text-[11px] font-semibold text-slate-700 flex items-center gap-1 select-none">
                  <FileCode2 className="w-3.5 h-3.5 text-brand-600" />
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
            <div className="flex items-center justify-between text-[11px] text-slate-400 pt-2 border-t border-slate-100 select-none">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {message.durationMs ? `${(message.durationMs / 1000).toFixed(1)}s` : '刚刚'}
                </span>
                {message.tokensUsed && (
                  <span className="flex items-center gap-1 font-mono">
                    <Zap className="w-3 h-3 text-amber-500" />
                    <span>{message.tokensUsed} tok</span>
                  </span>
                )}
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  onClick={handleCopy}
                  className="p-1 hover:text-slate-700 hover:bg-slate-100 rounded transition flex items-center gap-1 text-[10px]"
                  title="复制内容"
                >
                  {copied ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                  <span>{copied ? '已复制' : '复制'}</span>
                </button>
                <button className="p-1 hover:text-slate-700 hover:bg-slate-100 rounded transition" title="赞同">
                  <ThumbsUp className="w-3 h-3" />
                </button>
                <button className="p-1 hover:text-slate-700 hover:bg-slate-100 rounded transition" title="反馈">
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
