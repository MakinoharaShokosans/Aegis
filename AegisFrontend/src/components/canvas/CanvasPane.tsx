import React, { useState } from 'react';
import {
  FileText,
  X,
  Maximize2,
  Minimize2,
  Copy,
  AlertTriangle,
  Code2,
  BookOpen,
  Save,
  GitCompare,
  Check,
} from 'lucide-react';
import Editor, { DiffEditor } from '@monaco-editor/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { useUiStore } from '@/stores/useUiStore';

export const CanvasPane: React.FC = () => {
  const {
    tabs,
    activeTabId,
    closeTab,
    setActiveTab,
    updateTabContent,
    saveCurrentTab,
    openTab,
  } = useWorkspaceStore();
  const { previewFullScreen, togglePreviewFullScreen } = useUiStore();

  const [viewMode, setViewMode] = useState<'editor' | 'preview' | 'diff'>('preview');
  const [copied, setCopied] = useState(false);

  const activeTab = tabs.find((t) => t.id === activeTabId) || tabs[0];

  if (!activeTab) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-canvas-secondary text-gray-400 p-8 select-none">
        <div className="w-14 h-14 rounded-2xl bg-white border border-border-subtle flex items-center justify-center mb-3 shadow-2xs">
          <BookOpen className="w-7 h-7 text-purple-600" />
        </div>
        <p className="text-sm font-bold text-gray-700">工作区深度画布视窗 (Doc & Canvas Stage)</p>
        <p className="text-xs text-gray-400 mt-1 text-center max-w-sm">
          在对话流中点击文档知识卡片、技术规范或工作区文件，可在此实时阅读 Markdown 架构规范、编辑源码与审查 Diff
        </p>
        <button
          onClick={() =>
            openTab({
              filePath: 'documents/agent_runtime/11_http_api.md',
              title: '11_http_api.md',
              language: 'markdown',
              content: '# 11_http_api.md\n\nHTTP API 规范阅读中...',
            })
          }
          className="mt-4 px-3 py-1.5 rounded-lg bg-white hover:bg-gray-100 border border-border-subtle text-xs text-gray-700 font-medium transition shadow-2xs"
        >
          打开默认规范文档
        </button>
      </div>
    );
  }

  const isMarkdown =
    activeTab.language === 'markdown' ||
    activeTab.filePath.endsWith('.md') ||
    activeTab.filePath.endsWith('.markdown');

  const handleCopyPath = () => {
    navigator.clipboard.writeText(activeTab.filePath);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col h-screen bg-white select-none">
      {/* 1. Multi-Tab Manager Header */}
      <div className="flex items-center justify-between border-b border-border-subtle bg-canvas-secondary px-2 pt-1">
        {/* Tabs Bar */}
        <div className="flex items-center gap-1 overflow-x-auto max-w-[75%] no-scrollbar">
          {tabs.map((tab) => {
            const isActive = tab.id === activeTab.id;
            return (
              <div
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`group flex items-center gap-2 px-3 py-1.5 text-xs rounded-t-lg cursor-pointer border-t-2 transition ${
                  isActive
                    ? 'bg-white border-brand-600 text-gray-900 font-semibold shadow-xs'
                    : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-100'
                }`}
              >
                {tab.filePath.endsWith('.py') ? (
                  <span className="text-xs">🐍</span>
                ) : tab.filePath.endsWith('.md') ? (
                  <BookOpen className="w-3.5 h-3.5 text-purple-600" />
                ) : (
                  <FileText className="w-3.5 h-3.5 text-blue-500" />
                )}
                <span className="truncate max-w-[140px]">{tab.title}</span>
                {tab.isModified && <span className="w-1.5 h-1.5 rounded-full bg-amber-500" title="已修改未保存" />}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(tab.id);
                  }}
                  className="p-0.5 rounded-full hover:bg-gray-200 text-gray-400 group-hover:text-gray-600"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            );
          })}
        </div>

        {/* Right Top Actions */}
        <div className="flex items-center gap-1 text-gray-500 pb-1">
          {/* Mode Switcher */}
          <div className="flex items-center bg-gray-200/80 rounded-lg p-0.5 text-xs mr-1">
            {isMarkdown && (
              <button
                onClick={() => setViewMode('preview')}
                className={`flex items-center gap-1 px-2 py-1 rounded-md transition ${
                  viewMode === 'preview' ? 'bg-white text-gray-900 shadow-2xs font-semibold' : 'text-gray-600'
                }`}
                title="Markdown 架构规范阅读模式"
              >
                <BookOpen className="w-3.5 h-3.5 text-purple-600" />
                <span className="text-[11px]">规范阅读</span>
              </button>
            )}
            <button
              onClick={() => setViewMode('editor')}
              className={`flex items-center gap-1 px-2 py-1 rounded-md transition ${
                viewMode === 'editor' ? 'bg-white text-gray-900 shadow-2xs font-semibold' : 'text-gray-600'
              }`}
              title="Monaco 源码编辑模式"
            >
              <Code2 className="w-3.5 h-3.5 text-blue-600" />
              <span className="text-[11px]">源码编辑</span>
            </button>
            <button
              onClick={() => setViewMode('diff')}
              className={`flex items-center gap-1 px-2 py-1 rounded-md transition ${
                viewMode === 'diff' ? 'bg-white text-gray-900 shadow-2xs font-semibold' : 'text-gray-600'
              }`}
              title="Side-by-side Git Diff 对比"
            >
              <GitCompare className="w-3.5 h-3.5 text-emerald-600" />
              <span className="text-[11px]">Diff 对比</span>
            </button>
          </div>

          {activeTab.isModified && (
            <button
              onClick={saveCurrentTab}
              className="flex items-center gap-1 px-2 py-1 bg-brand-600 hover:bg-brand-700 text-white rounded-md text-[11px] font-medium shadow-xs transition"
              title="保存文件 (Ctrl+S)"
            >
              <Save className="w-3 h-3" />
              <span>保存</span>
            </button>
          )}

          <button
            onClick={togglePreviewFullScreen}
            className="p-1.5 hover:bg-gray-200 rounded-md text-gray-600 transition"
            title={previewFullScreen ? '退出全屏' : '全屏'}
          >
            {previewFullScreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* 2. Live Sync Alert Banner */}
      {activeTab.isStale && (
        <div className="flex items-center justify-between px-4 py-1.5 bg-amber-50 border-b border-amber-200 text-amber-900 text-xs">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <span>⚠️ 该文档/代码已在磁盘更新，当前显示为缓存旧内容。</span>
          </div>
          <button
            onClick={() => updateTabContent(activeTab.id, activeTab.content)}
            className="px-2.5 py-0.5 rounded bg-white hover:bg-amber-100 text-amber-900 border border-amber-300 font-medium text-[11px] shadow-2xs transition"
          >
            重新载入
          </button>
        </div>
      )}

      {/* 3. Sub-Header: Path Breadcrumbs & Language */}
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-border-subtle bg-white text-xs text-gray-500">
        <span className="font-mono text-[11px] truncate text-gray-700">{activeTab.filePath}</span>
        <div className="flex items-center gap-2 shrink-0">
          <span className="px-2 py-0.5 rounded bg-gray-100 text-gray-700 text-[10px] font-mono uppercase">
            {activeTab.language}
          </span>
          <button
            onClick={handleCopyPath}
            className="flex items-center gap-1 p-1 hover:bg-gray-100 rounded text-gray-500 transition"
            title="复制文件路径"
          >
            {copied ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
          </button>
        </div>
      </div>

      {/* 4. Content Area: Markdown Reader / Monaco Editor / Git Diff */}
      <div className="flex-1 min-h-0 bg-white">
        {viewMode === 'preview' && isMarkdown ? (
          <div className="h-full overflow-y-auto p-8 text-xs text-gray-800 prose prose-sm max-w-none leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
              {activeTab.content}
            </ReactMarkdown>
          </div>
        ) : viewMode === 'diff' ? (
          <DiffEditor
            height="100%"
            language={activeTab.language}
            original={activeTab.content.replace(/\/\/.*\n/g, '')}
            modified={activeTab.content}
            theme="vs-light"
            options={{
              readOnly: true,
              minimap: { enabled: false },
              fontSize: 12,
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
            }}
          />
        ) : (
          <Editor
            height="100%"
            language={activeTab.language}
            value={activeTab.content}
            onChange={(val) => updateTabContent(activeTab.id, val || '')}
            theme="vs-light"
            options={{
              minimap: { enabled: true },
              fontSize: 12,
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              wordWrap: 'on',
              tabSize: 2,
            }}
          />
        )}
      </div>
    </div>
  );
};
