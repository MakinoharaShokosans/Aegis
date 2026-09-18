/**
 * Aegis Visual Directory Picker Modal
 * Allows users to visually browse and select local filesystem directories
 * with breadcrumb navigation, quick location tags, and search filtering.
 */

import React, { useState, useEffect } from 'react';
import {
  Folder,
  FolderOpen,
  ArrowUp,
  RefreshCw,
  Search,
  Check,
  X,
  HardDrive,
  ChevronRight,
  FolderCheck,
  Compass,
} from 'lucide-react';
import { fileApi } from '@/api';
import type { DirectoryEntry, QuickLocation } from '@/types';

interface DirectoryPickerModalProps {
  isOpen: boolean;
  initialPath?: string;
  onSelect: (selectedPath: string, suggestedName: string) => void;
  onClose: () => void;
}

export const DirectoryPickerModal: React.FC<DirectoryPickerModalProps> = ({
  isOpen,
  initialPath,
  onSelect,
  onClose,
}) => {
  const [currentPath, setCurrentPath] = useState<string>('');
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [isRoot, setIsRoot] = useState<boolean>(false);
  const [directories, setDirectories] = useState<DirectoryEntry[]>([]);
  const [quickLocations, setQuickLocations] = useState<QuickLocation[]>([]);
  const [selectedDirectory, setSelectedDirectory] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [filterQuery, setFilterQuery] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const loadDirectories = async (path?: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await fileApi.browseDirectories(path);
      if (resp && resp.current_path) {
        setCurrentPath(resp.current_path);
        setParentPath(resp.parent_path || null);
        setIsRoot(resp.is_root);
        setDirectories(resp.directories || []);
        setQuickLocations(resp.quick_locations || []);
        setSelectedDirectory(resp.current_path);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '无法读取该目录';
      setError(`${msg}（请确保 AegisAgent 后端服务正在运行）`);
      if (path) {
        setCurrentPath(path);
        setSelectedDirectory(path);
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadDirectories(initialPath);
    }
  }, [isOpen, initialPath]);

  if (!isOpen) return null;

  // Split path into breadcrumbs
  const breadcrumbSegments = currentPath.split('/').filter(Boolean);

  const handleBreadcrumbClick = (index: number) => {
    const targetPath = '/' + breadcrumbSegments.slice(0, index + 1).join('/');
    loadDirectories(targetPath);
  };

  const handleDirectoryClick = (dir: DirectoryEntry) => {
    setSelectedDirectory(dir.path);
  };

  const handleDirectoryDoubleClick = (dir: DirectoryEntry) => {
    loadDirectories(dir.path);
  };

  const handleConfirm = () => {
    const finalPath = selectedDirectory || currentPath;
    const name = finalPath.split('/').filter(Boolean).pop() || 'Workspace';
    onSelect(finalPath, name);
    onClose();
  };

  const filteredDirs = directories.filter((d) =>
    d.name.toLowerCase().includes(filterQuery.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-150 select-none">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-2xl overflow-hidden flex flex-col h-[560px]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 bg-slate-50/80">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-brand-50 text-brand-600 shadow-2xs">
              <Compass className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-sm">选择本地工程工作区目录</h3>
              <p className="text-[11px] text-slate-500">
                双击可进入子目录，单击选中当前目录作为工程根路径
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Quick Locations Jump Tags */}
        <div className="px-5 py-2 border-b border-slate-100 bg-white flex items-center gap-1.5 overflow-x-auto text-xs no-scrollbar">
          <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider shrink-0 mr-1">
            快速跳转:
          </span>
          {quickLocations.map((loc) => (
            <button
              key={loc.path}
              onClick={() => loadDirectories(loc.path)}
              className={`px-2.5 py-1 rounded-lg border text-xs font-medium shrink-0 transition flex items-center gap-1.5 ${
                currentPath === loc.path
                  ? 'bg-brand-50 border-brand-300 text-brand-700 shadow-2xs font-semibold'
                  : 'bg-slate-50 hover:bg-slate-100 border-slate-200 text-slate-600'
              }`}
            >
              <HardDrive className="w-3 h-3 text-slate-400" />
              <span>{loc.label}</span>
            </button>
          ))}
        </div>

        {/* Path Breadcrumbs Bar & Actions */}
        <div className="px-5 py-2.5 border-b border-slate-100 bg-slate-50/40 flex items-center justify-between gap-3">
          {/* Breadcrumbs */}
          <div className="flex items-center gap-1 overflow-x-auto text-xs font-mono flex-1 bg-white px-3 py-1.5 rounded-lg border border-slate-200">
            <button
              onClick={() => loadDirectories('/')}
              className={`p-0.5 rounded hover:text-brand-600 text-slate-500 font-bold ${
                isRoot ? 'text-brand-600' : ''
              }`}
              title="根目录 (/)"
            >
              /
            </button>

            {breadcrumbSegments.map((seg, idx) => (
              <React.Fragment key={idx}>
                <ChevronRight className="w-3 h-3 text-slate-300 shrink-0" />
                <button
                  onClick={() => handleBreadcrumbClick(idx)}
                  className={`hover:text-brand-600 hover:underline px-1 py-0.5 rounded truncate max-w-[140px] ${
                    idx === breadcrumbSegments.length - 1
                      ? 'text-slate-900 font-semibold'
                      : 'text-slate-500'
                  }`}
                >
                  {seg}
                </button>
              </React.Fragment>
            ))}
          </div>

          {/* Up & Refresh Buttons */}
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => parentPath && loadDirectories(parentPath)}
              disabled={isRoot || !parentPath || isLoading}
              className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-600 disabled:opacity-30 disabled:hover:bg-white transition shadow-2xs"
              title="返回上一级目录"
            >
              <ArrowUp className="w-4 h-4" />
            </button>
            <button
              onClick={() => loadDirectories(currentPath)}
              disabled={isLoading}
              className={`p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-600 transition shadow-2xs ${
                isLoading ? 'animate-spin text-brand-600' : ''
              }`}
              title="刷新目录列表"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Directory Search / Filter Bar */}
        <div className="px-5 pt-3 pb-1">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              placeholder="快速过滤当前目录下的子文件夹..."
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:border-brand-500 text-slate-800"
            />
          </div>
        </div>

        {/* Directories Grid / List */}
        <div className="flex-1 overflow-y-auto px-5 py-2.5 space-y-1.5">
          {error ? (
            <div className="text-center py-12 px-4 space-y-2">
              <div className="text-rose-500 font-semibold text-xs">{error}</div>
              <button
                onClick={() => loadDirectories(parentPath || '/')}
                className="text-xs text-brand-600 underline"
              >
                返回上级目录
              </button>
            </div>
          ) : isLoading ? (
            <div className="text-center py-16 text-xs text-slate-400">正在读取本地文件系统...</div>
          ) : filteredDirs.length === 0 ? (
            <div className="text-center py-12 px-4 space-y-3 border-2 border-dashed border-slate-200 rounded-xl">
              <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400">
                <FolderOpen className="w-5 h-5 text-slate-400" />
              </div>
              <div className="text-xs text-slate-600 font-medium">当前目录下暂无子文件夹</div>
              <p className="text-[11px] text-slate-400 max-w-sm mx-auto">
                您可以直接点击下方 <strong>“选择当前目录”</strong> 将该文件夹接入为工程工作区。
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {filteredDirs.map((dir) => {
                const isDirSelected = selectedDirectory === dir.path;
                return (
                  <div
                    key={dir.path}
                    onClick={() => handleDirectoryClick(dir)}
                    onDoubleClick={() => handleDirectoryDoubleClick(dir)}
                    className={`flex items-center justify-between p-2.5 rounded-xl border cursor-pointer transition ${
                      isDirSelected
                        ? 'bg-brand-50/80 border-brand-400 shadow-xs'
                        : 'bg-white hover:bg-slate-50 border-slate-200 text-slate-700'
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate flex-1 min-w-0">
                      {isDirSelected ? (
                        <FolderCheck className="w-4 h-4 text-brand-600 shrink-0" />
                      ) : (
                        <Folder className="w-4 h-4 text-amber-500 shrink-0" />
                      )}
                      <span className="font-semibold text-xs truncate text-slate-800">
                        {dir.name}
                      </span>
                    </div>

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDirectoryDoubleClick(dir);
                      }}
                      className="text-[10px] px-2 py-0.5 rounded-md bg-slate-100 hover:bg-brand-600 hover:text-white text-slate-500 transition shrink-0 ml-1"
                      title="进入此文件夹"
                    >
                      进入
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer Selection Summary & Action Bar */}
        <div className="px-5 py-3 border-t border-slate-200 bg-slate-50/80 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2 truncate flex-1 min-w-0">
            <span className="text-xs text-slate-400 shrink-0 font-medium">已选中:</span>
            <span className="text-xs font-mono font-semibold text-slate-800 truncate px-2 py-1 bg-white border border-slate-200 rounded-md">
              {selectedDirectory || currentPath}
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 text-xs font-medium transition"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold shadow-xs transition"
            >
              <Check className="w-3.5 h-3.5" />
              <span>选择此目录作为工作区</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
