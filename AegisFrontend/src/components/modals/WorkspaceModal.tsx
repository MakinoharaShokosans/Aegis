import React, { useState } from 'react';
import {
  X,
  FolderPlus,
  AlertTriangle,
  Trash2,
  Edit3,
  Check,
  HardDrive,
} from 'lucide-react';
import { useUiStore } from '@/stores/useUiStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';

export const WorkspaceModal: React.FC = () => {
  const { workspaceModalOpen, workspaceModalMode, closeWorkspaceModal } = useUiStore();
  const {
    workspaces,
    activeWorkspaceId,
    createWorkspace,
    updateWorkspace,
    deleteWorkspace,
  } = useWorkspaceStore();

  const activeWs = workspaces.find((w) => w.id === activeWorkspaceId);

  // Form states
  const [name, setName] = useState(activeWs?.name || '');
  const [rootPath, setRootPath] = useState(activeWs?.root_path || '/home/Skualeilu/Projects/');
  const [description, setDescription] = useState(activeWs?.description || '');
  const [confirmName, setConfirmName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!workspaceModalOpen) return null;

  const handleSubmitCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !rootPath.trim()) {
      setError('工作区名称与根目录路径不能为空');
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      await createWorkspace({ name, root_path: rootPath, description });
      closeWorkspaceModal();
    } catch (err: any) {
      setError(err.message || '创建工作区失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmitEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeWorkspaceId || !name.trim()) return;
    setIsSubmitting(true);
    try {
      await updateWorkspace(activeWorkspaceId, { name, description });
      closeWorkspaceModal();
    } catch (err: any) {
      setError(err.message || '更新工作区失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmitDelete = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeWs || confirmName !== activeWs.name) {
      setError(`请输入完全匹配的工作区名称 "${activeWs?.name}" 以确认级联删除`);
      return;
    }
    setIsSubmitting(true);
    try {
      await deleteWorkspace(activeWs.id);
      closeWorkspaceModal();
    } catch (err: any) {
      setError(err.message || '删除工作区失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="bg-white rounded-xl shadow-2xl border border-border-subtle w-full max-w-lg overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle bg-gray-50/50">
          <div className="flex items-center gap-2.5">
            <div
              className={`p-2 rounded-lg ${
                workspaceModalMode === 'delete' ? 'bg-red-100 text-red-600' : 'bg-brand-50 text-brand-600'
              }`}
            >
              {workspaceModalMode === 'delete' ? (
                <Trash2 className="w-5 h-5" />
              ) : workspaceModalMode === 'edit' ? (
                <Edit3 className="w-5 h-5" />
              ) : (
                <FolderPlus className="w-5 h-5" />
              )}
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 text-sm">
                {workspaceModalMode === 'delete'
                  ? '级联删除工作区'
                  : workspaceModalMode === 'edit'
                  ? '编辑工作区属性'
                  : '创建新项目工作区'}
              </h3>
              <p className="text-xs text-gray-500">
                {workspaceModalMode === 'delete'
                  ? '高危操作：级联清理名下所有会话、对话流水与局部情境记忆'
                  : '工作区作为物理真源 (Ground Truth) 与长期共享记忆承载体'}
              </p>
            </div>
          </div>
          <button
            onClick={closeWorkspaceModal}
            className="p-1 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body */}
        {workspaceModalMode === 'delete' ? (
          <form onSubmit={handleSubmitDelete} className="p-5 space-y-4 text-xs">
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-800 space-y-1">
              <div className="flex items-center gap-1.5 font-semibold">
                <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
                <span>此操作无法撤销！</span>
              </div>
              <p className="text-[11px] text-red-700 leading-relaxed">
                删除工作区 <strong>{activeWs?.name}</strong> 将永久清除其关联的数据库记录（会话、任务轨迹、会话记忆与工作区定论）。本地磁盘文件不会被物理删除。
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="block font-medium text-gray-700">
                请输入工作区名称 <span className="font-mono font-bold text-gray-900 select-all">{activeWs?.name}</span> 以确认：
              </label>
              <input
                type="text"
                value={confirmName}
                onChange={(e) => setConfirmName(e.target.value)}
                placeholder={activeWs?.name}
                className="w-full px-3 py-2 border border-border-subtle rounded-lg text-xs focus:ring-2 focus:ring-red-500 focus:outline-hidden"
              />
            </div>

            {error && <div className="text-red-600 text-[11px]">{error}</div>}

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-border-subtle">
              <button
                type="button"
                onClick={closeWorkspaceModal}
                className="px-3.5 py-1.5 rounded-lg border border-border-subtle text-gray-600 hover:bg-gray-100 transition"
              >
                取消
              </button>
              <button
                type="submit"
                disabled={isSubmitting || confirmName !== activeWs?.name}
                className="px-4 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white font-medium transition disabled:opacity-50"
              >
                {isSubmitting ? '正在级联删除...' : '确认删除工作区'}
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={workspaceModalMode === 'edit' ? handleSubmitEdit : handleSubmitCreate} className="p-5 space-y-3.5 text-xs">
            <div className="space-y-1">
              <label className="block font-medium text-gray-700">
                工作区名称 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如: Aegis Agent Core"
                required
                className="w-full px-3 py-2 border border-border-subtle rounded-lg text-xs focus:ring-2 focus:ring-brand-500 focus:outline-hidden"
              />
            </div>

            <div className="space-y-1">
              <label className="block font-medium text-gray-700 flex items-center justify-between">
                <span>本地物理根目录 (Root Path) <span className="text-red-500">*</span></span>
                <span className="text-[10px] text-gray-400 font-mono">必须为已存在的本地有效路径</span>
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={rootPath}
                  disabled={workspaceModalMode === 'edit'}
                  onChange={(e) => setRootPath(e.target.value)}
                  placeholder="/home/user/projects/my-project"
                  required
                  className="w-full pl-8 pr-3 py-2 border border-border-subtle rounded-lg text-xs font-mono disabled:bg-gray-100 focus:ring-2 focus:ring-brand-500 focus:outline-hidden"
                />
                <HardDrive className="w-4 h-4 text-gray-400 absolute left-2.5 top-2.5" />
              </div>
            </div>

            <div className="space-y-1">
              <label className="block font-medium text-gray-700">项目背景与架构说明</label>
              <textarea
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="简述该工作区的核心技术栈、职责分工与开发纪律..."
                className="w-full px-3 py-2 border border-border-subtle rounded-lg text-xs focus:ring-2 focus:ring-brand-500 focus:outline-hidden resize-none"
              />
            </div>

            {error && <div className="text-red-600 text-[11px]">{error}</div>}

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-border-subtle">
              <button
                type="button"
                onClick={closeWorkspaceModal}
                className="px-3.5 py-1.5 rounded-lg border border-border-subtle text-gray-600 hover:bg-gray-100 transition"
              >
                取消
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium transition disabled:opacity-50"
              >
                <Check className="w-3.5 h-3.5" />
                <span>{workspaceModalMode === 'edit' ? '保存修改' : '立即创建工作区'}</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
