import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';

interface CodeBlockProps {
  code: string;
  language?: string;
  title?: string;
  showLineNumbers?: boolean;
  className?: string;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({
  code,
  language = 'bash',
  title,
  showLineNumbers = false,
  className = '',
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const lines = code.trim().split('\n');

  return (
    <div className={`rounded-xl border border-border-subtle bg-gray-900 text-gray-100 overflow-hidden font-mono text-[11px] shadow-xs ${className}`}>
      {/* Top Header */}
      {(title || language) && (
        <div className="flex items-center justify-between px-3 py-1.5 bg-gray-800/80 border-b border-gray-700/60 text-gray-400 text-[10px]">
          <span className="truncate">{title || language}</span>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 hover:text-white transition"
            title="复制代码"
          >
            {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
            <span>{copied ? '已复制' : '复制'}</span>
          </button>
        </div>
      )}

      {/* Code Body */}
      <div className="p-3 overflow-x-auto leading-relaxed">
        {showLineNumbers ? (
          <div className="table w-full">
            {lines.map((line, idx) => (
              <div key={idx} className="table-row">
                <span className="table-cell select-none pr-3 text-gray-500 text-right w-6">
                  {idx + 1}
                </span>
                <span className="table-cell whitespace-pre">{line}</span>
              </div>
            ))}
          </div>
        ) : (
          <pre className="whitespace-pre-wrap">{code}</pre>
        )}
      </div>
    </div>
  );
};
