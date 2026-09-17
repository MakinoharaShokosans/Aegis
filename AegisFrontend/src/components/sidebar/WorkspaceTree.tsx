/**
 * Aegis Modern File System Tree Explorer
 * Renders recursive workspace directory tree with language-specific SVG icons and click-to-open handlers.
 */

import React, { useState } from 'react';
import {
  Folder,
  FolderOpen,
  FileText,
  FileCode,
  FileJson,
  FileCog,
  Terminal,
  ChevronRight,
  ChevronDown,
  RefreshCw,
  Search,
  File,
} from 'lucide-react';
import type { FileNode } from '@/types';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';

interface WorkspaceTreeProps {
  onOpenCreate?: () => void;
}

const getFileIcon = (fileName: string) => {
  if (fileName.endsWith('.py')) {
    return <FileCode className="w-3.5 h-3.5 text-blue-500 shrink-0" />;
  }
  if (fileName.endsWith('.ts') || fileName.endsWith('.tsx') || fileName.endsWith('.js') || fileName.endsWith('.jsx')) {
    return <FileCode className="w-3.5 h-3.5 text-sky-500 shrink-0" />;
  }
  if (fileName.endsWith('.md')) {
    return <FileText className="w-3.5 h-3.5 text-indigo-500 shrink-0" />;
  }
  if (fileName.endsWith('.json') || fileName.endsWith('.yaml') || fileName.endsWith('.yml') || fileName.endsWith('.toml')) {
    return <FileJson className="w-3.5 h-3.5 text-amber-500 shrink-0" />;
  }
  if (fileName.endsWith('.c') || fileName.endsWith('.h') || fileName.endsWith('.cpp')) {
    return <FileCog className="w-3.5 h-3.5 text-purple-500 shrink-0" />;
  }
  if (fileName.endsWith('.sh') || fileName.endsWith('.bash')) {
    return <Terminal className="w-3.5 h-3.5 text-emerald-600 shrink-0" />;
  }
  return <File className="w-3.5 h-3.5 text-slate-400 shrink-0" />;
};

interface FileTreeNodeItemProps {
  node: FileNode;
  depth: number;
  searchFilter: string;
  onOpenFile: (path: string) => void;
}

const FileTreeNodeItem: React.FC<FileTreeNodeItemProps> = ({
  node,
  depth,
  searchFilter,
  onOpenFile,
}) => {
  const [isOpen, setIsOpen] = useState(depth < 2);

  const isDirectory = node.type === 'directory';
  const matchesSearch =
    !searchFilter ||
    node.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
    node.path.toLowerCase().includes(searchFilter.toLowerCase());

  if (isDirectory) {
    const hasChildren = node.children && node.children.length > 0;
    const filteredChildren = node.children?.filter((c) =>
      !searchFilter || c.name.toLowerCase().includes(searchFilter.toLowerCase()) || c.path.toLowerCase().includes(searchFilter.toLowerCase())
    );

    if (searchFilter && (!filteredChildren || filteredChildren.length === 0) && !matchesSearch) {
      return null;
    }

    return (
      <div className="select-none text-xs">
        <div
          onClick={() => setIsOpen(!isOpen)}
          style={{ paddingLeft: `${depth * 12 + 6}px` }}
          className="flex items-center gap-1.5 py-1 pr-2 rounded-md hover:bg-slate-100/80 cursor-pointer text-slate-700 hover:text-slate-900 group transition"
        >
          {isOpen ? (
            <ChevronDown className="w-3 h-3 text-slate-400 shrink-0" />
          ) : (
            <ChevronRight className="w-3 h-3 text-slate-400 shrink-0" />
          )}

          {isOpen ? (
            <FolderOpen className="w-3.5 h-3.5 text-amber-500 shrink-0" />
          ) : (
            <Folder className="w-3.5 h-3.5 text-amber-500 shrink-0" />
          )}

          <span className="font-medium truncate flex-1">{node.name}</span>
          {hasChildren && (
            <span className="text-[10px] text-slate-400 font-mono opacity-0 group-hover:opacity-100 transition">
              {node.children?.length}
            </span>
          )}
        </div>

        {isOpen && node.children && (
          <div className="space-y-0.5">
            {node.children.map((child) => (
              <FileTreeNodeItem
                key={child.path}
                node={child}
                depth={depth + 1}
                searchFilter={searchFilter}
                onOpenFile={onOpenFile}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  // File item
  if (searchFilter && !matchesSearch) return null;

  return (
    <div
      onClick={() => onOpenFile(node.path)}
      style={{ paddingLeft: `${depth * 12 + 20}px` }}
      className="flex items-center gap-2 py-1 pr-2 rounded-md hover:bg-slate-100/90 cursor-pointer text-slate-600 hover:text-brand-700 group transition text-xs select-none"
    >
      {getFileIcon(node.name)}
      <span className="truncate flex-1 font-mono text-[11px]">{node.name}</span>
      {node.size !== undefined && (
        <span className="text-[10px] text-slate-400 font-mono opacity-0 group-hover:opacity-100 transition">
          {node.size > 1024 ? `${(node.size / 1024).toFixed(1)}k` : `${node.size}b`}
        </span>
      )}
    </div>
  );
};

export const WorkspaceTree: React.FC<WorkspaceTreeProps> = () => {
  const { fileTree, isLoadingFileTree, fetchFileTree, activeWorkspaceId, openFileFromWorkspace } =
    useWorkspaceStore();
  const [searchFilter, setSearchFilter] = useState('');

  const handleRefresh = () => {
    if (activeWorkspaceId) {
      fetchFileTree(activeWorkspaceId);
    }
  };

  // Mock initial file tree structure if empty
  const treeData: FileNode = fileTree || {
    name: 'Aegis',
    path: '',
    type: 'directory',
    children: [
      {
        name: 'documents',
        path: 'documents',
        type: 'directory',
        children: [
          { name: '01_architecture_overview.md', path: 'documents/agent_runtime/01_architecture_overview.md', type: 'file', size: 12400 },
          { name: '11_http_api.md', path: 'documents/agent_runtime/11_http_api.md', type: 'file', size: 18200 },
          { name: '07_security_gates.md', path: 'documents/agent_runtime/07_security_gates.md', type: 'file', size: 9400 },
          { name: 'api_documentation.md', path: 'documents/api_documentation.md', type: 'file', size: 19900 },
        ],
      },
      {
        name: 'AegisAgent',
        path: 'AegisAgent',
        type: 'directory',
        children: [
          {
            name: 'src',
            path: 'AegisAgent/src',
            type: 'directory',
            children: [
              { name: 'auth.py', path: 'AegisAgent/src/agent_runtime/api/auth.py', type: 'file', size: 4500 },
              { name: 'app.py', path: 'AegisAgent/src/agent_runtime/api/app.py', type: 'file', size: 7200 },
              { name: 'task_registry.py', path: 'AegisAgent/src/agent_runtime/api/task_registry.py', type: 'file', size: 8100 },
            ],
          },
          { name: 'pyproject.toml', path: 'AegisAgent/pyproject.toml', type: 'file', size: 1200 },
        ],
      },
      {
        name: 'AegisRAG',
        path: 'AegisRAG',
        type: 'directory',
        children: [
          { name: 'server.py', path: 'AegisRAG/src/server.py', type: 'file', size: 5400 },
          { name: 'retriever.py', path: 'AegisRAG/src/retriever.py', type: 'file', size: 6800 },
        ],
      },
    ],
  };

  return (
    <div className="flex flex-col h-full space-y-2 select-none">
      {/* Search & Actions Bar */}
      <div className="flex items-center gap-1.5 px-1">
        <div className="relative flex-1">
          <Search className="w-3 h-3 text-slate-400 absolute left-2 top-2" />
          <input
            type="text"
            placeholder="搜索文件..."
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            className="w-full pl-7 pr-2 py-1 text-[11px] bg-slate-50 border border-slate-200 rounded-md focus:outline-none focus:border-brand-500 text-slate-800"
          />
        </div>
        <button
          onClick={handleRefresh}
          className={`p-1 rounded hover:bg-slate-100 text-slate-500 hover:text-slate-800 transition ${
            isLoadingFileTree ? 'animate-spin text-brand-600' : ''
          }`}
          title="刷新工作区文件树"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Tree View */}
      <div className="flex-1 overflow-y-auto pr-1 space-y-0.5">
        <FileTreeNodeItem
          node={treeData}
          depth={0}
          searchFilter={searchFilter}
          onOpenFile={(path) => openFileFromWorkspace(path)}
        />
      </div>
    </div>
  );
};
