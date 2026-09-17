import React from 'react';
import { FolderTree, FolderPlus, Edit2, ChevronDown, Trash2 } from 'lucide-react';
import type { Workspace } from '@/types';

interface WorkspaceTreeProps {
  activeWorkspace?: Workspace;
  onOpenCreate: () => void;
  onOpenEdit: () => void;
  onOpenDelete: () => void;
}

export const WorkspaceTree: React.FC<WorkspaceTreeProps> = ({
  activeWorkspace,
  onOpenCreate,
  onOpenEdit,
  onOpenDelete,
}) => {
  return (
    <div className="space-y-1 select-none">
      {/* Workspace Header */}
      <div className="flex items-center justify-between text-xs font-semibold text-gray-500 py-1.5">
        <span className="flex items-center gap-1">
          <FolderTree className="w-3.5 h-3.5 text-brand-600" />
          工作区 (一等公民)
        </span>
        <div className="flex items-center gap-1 text-gray-400">
          <button
            onClick={onOpenCreate}
            className="p-1 hover:text-brand-600 hover:bg-gray-200 rounded transition"
            title="新建工作区 (Ctrl+Shift+N)"
          >
            <FolderPlus className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onOpenEdit}
            className="p-1 hover:text-gray-700 hover:bg-gray-200 rounded transition"
            title="编辑当前工作区属性"
          >
            <Edit2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Active Workspace Card */}
      <div className="flex items-center justify-between px-2 py-1.5 text-xs font-medium text-gray-800 bg-gray-100/80 hover:bg-gray-200/70 rounded-md cursor-pointer group transition">
        <div className="flex items-center gap-1.5 truncate">
          <ChevronDown className="w-3.5 h-3.5 text-gray-500 shrink-0" />
          <span className="truncate">{activeWorkspace ? activeWorkspace.name : '选择工作区...'}</span>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onOpenDelete();
          }}
          className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-100 text-gray-400 hover:text-red-600 transition"
          title="级联删除此工作区"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
};
