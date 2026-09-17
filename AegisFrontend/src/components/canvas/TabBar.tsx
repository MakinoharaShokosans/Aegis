/**
 * Aegis Modern Canvas Tab Bar
 * Clean white tab navigation with file type SVG icons, dirty indicators, and view mode toggle.
 */

import React from 'react';
import {
  FileText,
  FileCode,
  FileJson,
  FileCog,
  X,
  Maximize2,
  Minimize2,
  Code2,
  BookOpen,
  Save,
  GitCompare,
} from 'lucide-react';
import type { OpenTab } from '@/types';

interface TabBarProps {
  tabs: OpenTab[];
  activeTab: OpenTab;
  viewMode: 'editor' | 'preview' | 'diff';
  isMarkdown: boolean;
  previewFullScreen: boolean;
  onSelectTab: (tabId: string) => void;
  onCloseTab: (tabId: string) => void;
  onChangeViewMode: (mode: 'editor' | 'preview' | 'diff') => void;
  onSave: () => void;
  onToggleFullScreen: () => void;
}

const getTabIcon = (filePath: string) => {
  if (filePath.endsWith('.py')) {
    return <FileCode className="w-3.5 h-3.5 text-blue-500 shrink-0" />;
  }
  if (filePath.endsWith('.ts') || filePath.endsWith('.tsx') || filePath.endsWith('.js') || filePath.endsWith('.jsx')) {
    return <FileCode className="w-3.5 h-3.5 text-sky-500 shrink-0" />;
  }
  if (filePath.endsWith('.md')) {
    return <BookOpen className="w-3.5 h-3.5 text-purple-600 shrink-0" />;
  }
  if (filePath.endsWith('.json') || filePath.endsWith('.yaml') || filePath.endsWith('.yml')) {
    return <FileJson className="w-3.5 h-3.5 text-amber-500 shrink-0" />;
  }
  if (filePath.endsWith('.c') || filePath.endsWith('.h')) {
    return <FileCog className="w-3.5 h-3.5 text-purple-500 shrink-0" />;
  }
  return <FileText className="w-3.5 h-3.5 text-slate-400 shrink-0" />;
};

export const TabBar: React.FC<TabBarProps> = ({
  tabs,
  activeTab,
  viewMode,
  isMarkdown,
  previewFullScreen,
  onSelectTab,
  onCloseTab,
  onChangeViewMode,
  onSave,
  onToggleFullScreen,
}) => {
  return (
    <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/80 px-2 pt-1.5 select-none z-10">
      {/* Tabs List */}
      <div className="flex items-center gap-1 overflow-x-auto max-w-[70%] no-scrollbar">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTab.id;
          return (
            <div
              key={tab.id}
              onClick={() => onSelectTab(tab.id)}
              className={`group flex items-center gap-2 px-3 py-1.5 text-xs rounded-t-lg cursor-pointer border-t-2 transition ${
                isActive
                  ? 'bg-white border-brand-600 text-slate-900 font-semibold shadow-2xs'
                  : 'border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-100/70'
              }`}
            >
              {getTabIcon(tab.filePath)}
              <span className="truncate max-w-[140px] font-mono text-[11px]">{tab.title}</span>
              {tab.isModified && <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" title="已修改未保存" />}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onCloseTab(tab.id);
                }}
                className="p-0.5 rounded-md hover:bg-slate-200 text-slate-400 group-hover:text-slate-600 transition"
                title="关闭标签页"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          );
        })}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1.5 text-slate-500 pb-1">
        {/* Mode Switcher */}
        <div className="flex items-center bg-slate-200/70 rounded-lg p-0.5 text-xs">
          {isMarkdown && (
            <button
              onClick={() => onChangeViewMode('preview')}
              className={`flex items-center gap-1 px-2 py-1 rounded-md transition ${
                viewMode === 'preview' ? 'bg-white text-slate-900 shadow-2xs font-semibold' : 'text-slate-600 hover:text-slate-900'
              }`}
              title="Markdown 架构规范阅读模式"
            >
              <BookOpen className="w-3.5 h-3.5 text-purple-600" />
              <span className="text-[11px]">规范阅读</span>
            </button>
          )}
          <button
            onClick={() => onChangeViewMode('editor')}
            className={`flex items-center gap-1 px-2 py-1 rounded-md transition ${
              viewMode === 'editor' ? 'bg-white text-slate-900 shadow-2xs font-semibold' : 'text-slate-600 hover:text-slate-900'
            }`}
            title="Monaco 源码编辑模式"
          >
            <Code2 className="w-3.5 h-3.5 text-blue-600" />
            <span className="text-[11px]">源码编辑</span>
          </button>
          <button
            onClick={() => onChangeViewMode('diff')}
            className={`flex items-center gap-1 px-2 py-1 rounded-md transition ${
              viewMode === 'diff' ? 'bg-white text-slate-900 shadow-2xs font-semibold' : 'text-slate-600 hover:text-slate-900'
            }`}
            title="Side-by-side Git Diff 对比"
          >
            <GitCompare className="w-3.5 h-3.5 text-emerald-600" />
            <span className="text-[11px]">Diff 对比</span>
          </button>
        </div>

        {activeTab.isModified && (
          <button
            onClick={onSave}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-brand-600 hover:bg-brand-700 text-white font-medium text-xs shadow-2xs transition"
            title="保存修改 (Ctrl+S)"
          >
            <Save className="w-3 h-3" />
            <span>保存</span>
          </button>
        )}

        <button
          onClick={onToggleFullScreen}
          className="p-1.5 hover:bg-slate-100 rounded-md text-slate-500 hover:text-slate-800 transition"
          title={previewFullScreen ? '退出全屏' : '全屏画布'}
        >
          {previewFullScreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
        </button>
      </div>
    </div>
  );
};
