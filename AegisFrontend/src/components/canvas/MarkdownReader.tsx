/**
 * Aegis Modern Markdown & Specification Reader
 * GitHub/Vercel documentation style with syntax highlighting, copyable code blocks, and structured typography.
 */

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { Copy, Check, BookOpen } from 'lucide-react';

interface MarkdownReaderProps {
  content: string;
}

export const MarkdownReader: React.FC<MarkdownReaderProps> = ({ content }) => {
  const [copied, setCopied] = useState(false);

  const handleCopyAll = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="h-full overflow-y-auto bg-white p-6 md:p-10 select-text">
      {/* Top Floating Document Meta Bar */}
      <div className="max-w-4xl mx-auto flex items-center justify-between pb-4 mb-6 border-b border-slate-100 select-none">
        <div className="flex items-center gap-2 text-xs text-slate-500 font-medium">
          <BookOpen className="w-4 h-4 text-purple-600" />
          <span>结构化架构与技术规范阅读器</span>
        </div>

        <button
          onClick={handleCopyAll}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-600 text-xs transition"
          title="复制全文"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
          <span>{copied ? '已复制全文' : '复制全文'}</span>
        </button>
      </div>

      {/* Main Markdown Content */}
      <article className="max-w-4xl mx-auto prose prose-slate prose-headings:font-bold prose-headings:text-slate-900 prose-h1:text-xl prose-h2:text-lg prose-h3:text-base prose-p:text-slate-700 prose-p:leading-relaxed prose-code:font-mono prose-code:text-brand-700 prose-code:bg-slate-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none prose-pre:bg-slate-900 prose-pre:text-slate-100 prose-pre:rounded-xl prose-table:border prose-table:border-slate-200 prose-th:bg-slate-50 prose-th:p-2.5 prose-td:p-2.5 prose-blockquote:border-l-4 prose-blockquote:border-brand-500 prose-blockquote:bg-brand-50/40 prose-blockquote:py-1 prose-blockquote:px-4 prose-blockquote:rounded-r-lg">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
          {content}
        </ReactMarkdown>
      </article>
    </div>
  );
};
