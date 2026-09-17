import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';

interface MarkdownReaderProps {
  content: string;
}

export const MarkdownReader: React.FC<MarkdownReaderProps> = ({ content }) => {
  return (
    <div className="h-full overflow-y-auto p-8 text-xs text-gray-800 prose prose-sm max-w-none leading-relaxed select-text">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
        {content}
      </ReactMarkdown>
    </div>
  );
};
