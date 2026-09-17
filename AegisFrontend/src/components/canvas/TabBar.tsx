import React from 'react';
import {
  FileText,
  X,
  Maximize2,
  Minimize2,
  Code2,
  BookOpen,
  Save,
  GitCompare,
} from 'lucide-react';
import type { OpenTab } from '@/types';
import { Button } from '@/components/ui/Button';

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
    <div className="flex items-center justify-between border-b border-border-subtle bg-canvas-secondary px-2 pt-1 select-none">
      {/* Tabs List */}
      <div className="flex items-center gap-1 overflow-x-auto max-w-[75%] no-scrollbar">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTab.id;
          return (
            <div
              key={tab.id}
              onClick={() => onSelectTab(tab.id)}
              className={`group flex items-center gap-2 px-3 py-1.5 text-xs rounded-t-lg cursor-pointer border-t-2 transition ${
                isActive
                  ? 'bg-white border-brand-600 text-gray-900 font-semibold shadow-xs'
                  : 'border-transparent text-gray-500 hover:text-gray-800 hover:bg-gray-100'
              }`}
            >
              {tab.filePath.endsWith('.py') ? (
                <span className="text-xs">🐍</span>
              ) : tab.filePath.endsWith('.md') ? (
                <BookOpen className="w-3.5 h-3.5 text-purple-600 shrink-0" />
              ) : (
                <FileText className="w-3.5 h-3.5 text-blue-500 shrink-0" />
              )}
              <span className="truncate max-w-[140px]">{tab.title}</span>
              {tab.isModified && <span className="w-1.5 h-1.5 rounded-full bg-amber-500" title="已修改未保存" />}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onCloseTab(tab.id);
                }}
                className="p-0.5 rounded-full hover:bg-gray-200 text-gray-400 group-hover:text-gray-600"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          );
        })}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 text-gray-500 pb-1">
        {/* Mode Switcher */}
        <div className="flex items-center bg-gray-200/80 rounded-lg p-0.5 text-xs mr-1">
          {isMarkdown && (
            <button
              onClick={() => onChangeViewMode('preview')}
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
            onClick={() => onChangeViewMode('editor')}
            className={`flex items-center gap-1 px-2 py-1 rounded-md transition ${
              viewMode === 'editor' ? 'bg-white text-gray-900 shadow-2xs font-semibold' : 'text-gray-600'
            }`}
            title="Monaco 源码编辑模式"
          >
            <Code2 className="w-3.5 h-3.5 text-blue-600" />
            <span className="text-[11px]">源码编辑</span>
          </button>
          <button
            onClick={() => onChangeViewMode('diff')}
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
          <Button
            variant="primary"
            size="xs"
            onClick={onSave}
            leftIcon={<Save className="w-3 h-3" />}
            title="保存修改 (Ctrl+S)"
          >
            保存
          </Button>
        )}

        <button
          onClick={onToggleFullScreen}
          className="p-1.5 hover:bg-gray-200 rounded-md text-gray-600 transition"
          title={previewFullScreen ? '退出全屏' : '全屏'}
        >
          {previewFullScreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
        </button>
      </div>
    </div>
  );
};
