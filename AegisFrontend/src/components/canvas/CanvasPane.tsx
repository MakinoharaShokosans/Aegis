import React from 'react';
import {
  FileCode2,
  FileText,
  X,
  Plus,
  Columns,
  Maximize2,
  Minimize2,
  Copy,
  AlertTriangle,
  Code2,
  BookOpen,
} from 'lucide-react';
import Editor from '@monaco-editor/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { useUiStore } from '@/stores/useUiStore';

export const CanvasPane: React.FC = () => {
  const { tabs, activeTabId, closeTab, setActiveTab, updateTabContent } = useWorkspaceStore();
  const { previewFullScreen, togglePreviewFullScreen } = useUiStore();
  const [viewMode, setViewMode] = React.useState<'editor' | 'preview'>('editor');

  const activeTab = tabs.find((t) => t.id === activeTabId) || tabs[0];

  if (!activeTab) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-canvas-secondary text-gray-400 p-8 select-none">
        <FileCode2 className="w-12 h-12 text-gray-300 mb-3" />
        <p className="text-sm font-medium text-gray-600">工作区文档与深度视窗 (Doc & Canvas Stage)</p>
        <p className="text-xs text-gray-400 mt-1 text-center max-w-sm">
          在对话流中点击文档知识卡片、技术规范或工作区文件，可在此实时预览 Markdown 架构规范、编辑源码与审查 Diff
        </p>
      </div>
    );
  }

  const isMarkdown = activeTab.language === 'markdown' || activeTab.filePath.endsWith('.md');

  return (
    <div className="flex flex-col h-screen bg-white select-none">
      {/* 1. Multi-Tab Manager Header */}
      <div className="flex items-center justify-between border-b border-border-subtle bg-canvas-secondary px-2 pt-1">
        {/* Tabs Bar */}
        <div className="flex items-center gap-1 overflow-x-auto max-w-[80%] no-scrollbar">
          {tabs.map((tab) => {
            const isActive = tab.id === activeTab.id;
            return (
              <div
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`group flex items-center gap-2 px-3 py-1.5 text-xs rounded-t-md cursor-pointer border-t-2 transition ${
                  isActive
                    ? 'bg-white border-brand-600 text-gray-900 font-medium shadow-xs'
                    : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-100'
                }`}
              >
                {tab.filePath.endsWith('.py') ? (
                  <span className="text-xs">🐍</span>
                ) : (
                  <FileText className="w-3.5 h-3.5 text-blue-500" />
                )}
                <span className="truncate max-w-[140px]">{tab.title}</span>
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
          {isMarkdown && (
            <div className="flex items-center bg-gray-200 rounded p-0.5 text-xs mr-1">
              <button
                onClick={() => setViewMode('editor')}
                className={`p-1 rounded ${viewMode === 'editor' ? 'bg-white text-gray-900 shadow-xs' : 'text-gray-600'}`}
                title="源码模式"
              >
                <Code2 className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setViewMode('preview')}
                className={`p-1 rounded ${viewMode === 'preview' ? 'bg-white text-gray-900 shadow-xs' : 'text-gray-600'}`}
                title="阅读模式"
              >
                <BookOpen className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          <button className="p-1 hover:bg-gray-200 rounded" title="新建标签">
            <Plus className="w-3.5 h-3.5" />
          </button>
          <button className="p-1 hover:bg-gray-200 rounded" title="分屏">
            <Columns className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={togglePreviewFullScreen}
            className="p-1 hover:bg-gray-200 rounded"
            title={previewFullScreen ? '退出全屏' : '全屏'}
          >
            {previewFullScreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* 2. Live Sync Alert Banner */}
      {activeTab.isStale && (
        <div className="flex items-center justify-between px-3 py-1.5 bg-sync-bg border-b border-sync-border text-sync-text text-xs">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <span>⚠️ 文件已更新，当前显示为旧内容。</span>
          </div>
          <button
            onClick={() => updateTabContent(activeTab.id, activeTab.content)}
            className="px-2 py-0.5 rounded bg-white hover:bg-amber-50 text-amber-800 border border-amber-300 font-medium text-[11px] shadow-2xs transition"
          >
            重新载入
          </button>
        </div>
      )}

      {/* 3. Sub-Header: Path Breadcrumbs & Language */}
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-border-subtle bg-white text-xs text-gray-500">
        <span className="font-mono text-[11px] truncate">{activeTab.filePath}</span>
        <div className="flex items-center gap-2 shrink-0">
          <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-700 text-[10px] font-mono uppercase">
            {activeTab.language}
          </span>
          <button className="p-1 hover:bg-gray-100 rounded text-gray-500" title="复制路径">
            <Copy className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* 4. Content Area: Monaco Editor or Markdown Reader */}
      <div className="flex-1 min-h-0 bg-white">
        {isMarkdown && viewMode === 'preview' ? (
          <div className="h-full overflow-y-auto p-6 text-xs text-gray-800 prose prose-sm max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
              {activeTab.content}
            </ReactMarkdown>
          </div>
        ) : (
          <Editor
            height="100%"
            language={activeTab.language}
            value={activeTab.content}
            onChange={(val) => updateTabContent(activeTab.id, val || '')}
            theme="light"
            options={{
              fontSize: 12.5,
              fontFamily: 'JetBrains Mono, Fira Code, Menlo, monospace',
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              lineNumbers: 'on',
              folding: true,
              wordWrap: 'on',
              automaticLayout: true,
              renderLineHighlight: 'all',
            }}
          />
        )}
      </div>
    </div>
  );
};
