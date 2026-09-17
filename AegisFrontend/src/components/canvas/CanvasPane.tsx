/**
 * Aegis Modern Canvas Stage
 * Integrates TabBar, Markdown Reader, Monaco Light Editor, and Git Diff Viewer.
 */

import React, { useState } from 'react';
import {
  BookOpen,
  Copy,
  Check,
  FileCode,
} from 'lucide-react';
import Editor, { DiffEditor } from '@monaco-editor/react';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { useUiStore } from '@/stores/useUiStore';
import { LiveSyncBanner } from '@/components/domain/LiveSyncBanner';
import { TabBar } from './TabBar';
import { MarkdownReader } from './MarkdownReader';

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
      <div className="flex flex-col items-center justify-center h-full bg-slate-50 text-slate-400 p-8 select-none">
        <div className="w-14 h-14 rounded-2xl bg-white border border-slate-200 flex items-center justify-center mb-3 shadow-xs">
          <BookOpen className="w-7 h-7 text-purple-600" />
        </div>
        <p className="text-sm font-bold text-slate-800">工作区深度画布视窗 (Doc & Canvas Stage)</p>
        <p className="text-xs text-slate-400 mt-1.5 text-center max-w-sm leading-relaxed">
          在左侧文件树或对话流中点击文档与源码文件，可在此实时阅读 Markdown 架构规范、编辑代码与审查 Diff
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
          className="mt-4 px-3.5 py-1.5 rounded-lg bg-white hover:bg-slate-100 border border-slate-200 text-xs text-slate-700 font-medium transition shadow-2xs"
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
    <div className="flex flex-col h-full bg-white select-none">
      {/* 1. Multi-Tab Manager Header */}
      <TabBar
        tabs={tabs}
        activeTab={activeTab}
        viewMode={viewMode}
        isMarkdown={isMarkdown}
        previewFullScreen={previewFullScreen}
        onSelectTab={setActiveTab}
        onCloseTab={closeTab}
        onChangeViewMode={setViewMode}
        onSave={saveCurrentTab}
        onToggleFullScreen={togglePreviewFullScreen}
      />

      {/* 2. Live Sync Alert Banner */}
      {activeTab.isStale && (
        <LiveSyncBanner
          onReload={() => updateTabContent(activeTab.id, activeTab.content)}
        />
      )}

      {/* 3. Sub-Header: Path Breadcrumbs & Language */}
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-slate-200 bg-white text-xs text-slate-500">
        <div className="flex items-center gap-1.5 truncate">
          <FileCode className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <span className="font-mono text-[11px] truncate text-slate-700">{activeTab.filePath}</span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="px-2 py-0.5 rounded bg-slate-100 border border-slate-200 text-slate-700 text-[10px] font-mono uppercase">
            {activeTab.language}
          </span>
          <button
            onClick={handleCopyPath}
            className="flex items-center gap-1 p-1 hover:bg-slate-100 rounded text-slate-500 hover:text-slate-800 transition"
            title="复制文件路径"
          >
            {copied ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
          </button>
        </div>
      </div>

      {/* 4. Content Area: Markdown Reader / Monaco Editor / Git Diff */}
      <div className="flex-1 min-h-0 bg-white">
        {viewMode === 'preview' && isMarkdown ? (
          <MarkdownReader content={activeTab.content} />
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
