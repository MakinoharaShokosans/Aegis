import React, { useState, useEffect } from 'react';
import {
  X,
  FolderPlus,
  AlertTriangle,
  Trash2,
  Edit3,
  Check,
  HardDrive,
  FolderTree,
  CheckCircle2,
  ArrowRight,
  ListFilter,
} from 'lucide-react';
import { useUiStore } from '@/stores/useUiStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import { fileApi } from '@/api';
import { DirectoryPickerModal } from '@/components/common/DirectoryPickerModal';
import { Folder } from 'lucide-react';

export const WorkspaceModal: React.FC = () => {
  const { workspaceModalOpen, workspaceModalMode, openWorkspaceModal, closeWorkspaceModal } = useUiStore();
  const {
    workspaces,
    activeWorkspaceId,
    setActiveWorkspace,
    createWorkspace,
    updateWorkspace,
    deleteWorkspace,
  } = useWorkspaceStore();

  const activeWs = workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0];

  // Form states
  const [name, setName] = useState('');
  const [rootPath, setRootPath] = useState('/home/Skualeilu/Projects/Aegis');
  const [description, setDescription] = useState('');
  const [confirmName, setConfirmName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDirPicker, setShowDirPicker] = useState(false);
  const [isManualPathMode, setIsManualPathMode] = useState(false);
  const [isBrowsing, setIsBrowsing] = useState(false);

  const handleBrowseFolder = async () => {
    setIsBrowsing(true);
    try {
      const res = await fileApi.pickNativeDirectory(rootPath);
      if (res && res.success && res.path) {
        setRootPath(res.path);
        if (!name || name.startsWith('工作区 #') || name === 'Aegis Core') {
          setName(res.name || 'Workspace');
        }
        setIsBrowsing(false);
        return;
      }
      if (res && res.cancelled) {
        setIsBrowsing(false);
        return;
      }
    } catch {
      // ignore
    } finally {
      setIsBrowsing(false);
    }
    // Fallback to in-app directory picker modal
    setShowDirPicker(true);
  };

  // Sync active workspace attributes when entering edit or delete mode
  useEffect(() => {
    if (workspaceModalMode === 'edit' && activeWs) {
      setName(activeWs.name);
      setRootPath(activeWs.root_path);
      setDescription(activeWs.description || '');
    } else if (workspaceModalMode === 'create') {
      setName(workspaces.length === 0 ? 'Aegis Core' : `工作区 #${workspaces.length + 1}`);
      setRootPath('/home/Skualeilu/Projects/Aegis');
      setDescription('AegisAgent 智能体项目工作区');
    }
    setError(null);
    setConfirmName('');
  }, [workspaceModalMode, activeWs, workspaces.length, workspaceModalOpen]);

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
      await createWorkspace({ name: name.trim(), root_path: rootPath.trim(), description: description.trim() });
      closeWorkspaceModal();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '创建工作区失败';
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmitEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeWorkspaceId || !name.trim()) return;
    setIsSubmitting(true);
    try {
      await updateWorkspace(activeWorkspaceId, { name: name.trim(), description: description.trim() });
      closeWorkspaceModal();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '更新工作区失败';
      setError(msg);
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
      if (workspaces.length <= 1) {
        openWorkspaceModal('create');
      } else {
        openWorkspaceModal('manage');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '删除工作区失败';
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="bg-white rounded-xl shadow-2xl border border-slate-200 w-full max-w-xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 bg-slate-50/70">
          <div className="flex items-center gap-2.5">
            <div
              className={`p-2 rounded-lg ${
                workspaceModalMode === 'delete'
                  ? 'bg-rose-100 text-rose-600'
                  : workspaceModalMode === 'edit'
                  ? 'bg-blue-50 text-blue-600'
                  : workspaceModalMode === 'manage'
                  ? 'bg-purple-50 text-purple-600'
                  : 'bg-brand-50 text-brand-600'
              }`}
            >
              {workspaceModalMode === 'delete' ? (
                <Trash2 className="w-5 h-5" />
              ) : workspaceModalMode === 'edit' ? (
                <Edit3 className="w-5 h-5" />
              ) : workspaceModalMode === 'manage' ? (
                <FolderTree className="w-5 h-5" />
              ) : (
                <FolderPlus className="w-5 h-5" />
              )}
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-sm">
                {workspaceModalMode === 'delete'
                  ? '级联删除工作区'
                  : workspaceModalMode === 'edit'
                  ? '编辑工作区属性'
                  : workspaceModalMode === 'manage'
                  ? '工作区管理与快速切换'
                  : '创建新项目工作区'}
              </h3>
              <p className="text-xs text-slate-500">
                {workspaceModalMode === 'delete'
                  ? '高危操作：级联清理名下所有会话、对话流水与局部情境记忆'
                  : workspaceModalMode === 'manage'
                  ? '当前纳管的所有工程物理工作区与记忆真源'
                  : '工作区作为物理真源 (Ground Truth) 与长期共享记忆承载体'}
              </p>
            </div>
          </div>
          <button
            onClick={closeWorkspaceModal}
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Mode Navigation Tabs if in Manage/Create mode */}
        {(workspaceModalMode === 'manage' || workspaceModalMode === 'create') && workspaces.length > 0 && (
          <div className="flex border-b border-slate-200 px-5 pt-2 bg-slate-50/40">
            <button
              onClick={() => openWorkspaceModal('manage')}
              className={`flex items-center gap-1.5 pb-2.5 px-3 text-xs font-semibold border-b-2 transition ${
                workspaceModalMode === 'manage'
                  ? 'border-brand-600 text-brand-700'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <ListFilter className="w-3.5 h-3.5" />
              <span>已纳管工作区 ({workspaces.length})</span>
            </button>
            <button
              onClick={() => openWorkspaceModal('create')}
              className={`flex items-center gap-1.5 pb-2.5 px-3 text-xs font-semibold border-b-2 transition ${
                workspaceModalMode === 'create'
                  ? 'border-brand-600 text-brand-700'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <FolderPlus className="w-3.5 h-3.5" />
              <span>新建工作区</span>
            </button>
          </div>
        )}

        {/* Content Body */}
        {workspaceModalMode === 'manage' ? (
          <div className="p-5 space-y-3 max-h-[420px] overflow-y-auto">
            {workspaces.map((ws) => {
              const isActive = ws.id === activeWorkspaceId;
              return (
                <div
                  key={ws.id}
                  className={`p-3.5 rounded-xl border transition flex flex-col gap-2 ${
                    isActive
                      ? 'bg-brand-50/50 border-brand-300 shadow-2xs'
                      : 'bg-white hover:bg-slate-50 border-slate-200'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FolderTree className={`w-4 h-4 ${isActive ? 'text-brand-600' : 'text-slate-400'}`} />
                      <span className="font-bold text-slate-900 text-xs">{ws.name}</span>
                      {isActive && (
                        <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-brand-100 text-brand-800 text-[10px] font-semibold">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>当前活跃</span>
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-1.5">
                      {!isActive && (
                        <button
                          onClick={async () => {
                            await setActiveWorkspace(ws.id);
                            closeWorkspaceModal();
                          }}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-brand-600 hover:bg-brand-700 text-white text-xs font-medium transition shadow-2xs"
                        >
                          <span>切换进入</span>
                          <ArrowRight className="w-3 h-3" />
                        </button>
                      )}
                      <button
                        onClick={() => {
                          setActiveWorkspace(ws.id);
                          openWorkspaceModal('edit');
                        }}
                        className="p-1.5 rounded-md hover:bg-slate-200 text-slate-500 hover:text-slate-800 transition"
                        title="编辑属性"
                      >
                        <Edit3 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => {
                          setActiveWorkspace(ws.id);
                          openWorkspaceModal('delete');
                        }}
                        className="p-1.5 rounded-md hover:bg-rose-100 text-slate-400 hover:text-rose-600 transition"
                        title="删除工作区"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 text-[11px] text-slate-500 font-mono">
                    <HardDrive className="w-3 h-3 text-slate-400 shrink-0" />
                    <span className="truncate">{ws.root_path}</span>
                  </div>

                  {ws.description && (
                    <p className="text-[11px] text-slate-600 bg-slate-50 p-2 rounded-lg border border-slate-100">
                      {ws.description}
                    </p>
                  )}
                </div>
              );
            })}

            <div className="pt-2">
              <button
                onClick={() => openWorkspaceModal('create')}
                className="w-full flex items-center justify-center gap-2 py-2 rounded-xl border border-dashed border-brand-300 text-brand-600 hover:bg-brand-50/50 text-xs font-semibold transition"
              >
                <FolderPlus className="w-4 h-4" />
                <span>新建工作区 (Create Workspace)</span>
              </button>
            </div>
          </div>
        ) : workspaceModalMode === 'delete' ? (
          <form onSubmit={handleSubmitDelete} className="p-5 space-y-4 text-xs">
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-800 space-y-1">
              <div className="flex items-center gap-1.5 font-semibold">
                <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>此操作无法撤销！</span>
              </div>
              <p className="text-[11px] text-rose-700 leading-relaxed">
                删除工作区 <strong>{activeWs?.name}</strong> 将永久清除其关联的数据库记录（会话流水、任务轨迹、会话记忆与工作区定论）。本地磁盘文件不会被物理删除。
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="block font-medium text-slate-700">
                请输入工作区名称 <span className="font-mono font-bold text-slate-900 select-all">{activeWs?.name}</span> 以确认：
              </label>
              <input
                type="text"
                value={confirmName}
                onChange={(e) => setConfirmName(e.target.value)}
                placeholder={activeWs?.name}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs focus:ring-2 focus:ring-rose-500 focus:outline-hidden"
              />
            </div>

            {error && <div className="text-rose-600 text-[11px]">{error}</div>}

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => openWorkspaceModal('manage')}
                className="px-3.5 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100 transition"
              >
                返回
              </button>
              <button
                type="submit"
                disabled={isSubmitting || confirmName !== activeWs?.name}
                className="px-4 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white font-medium transition disabled:opacity-50"
              >
                {isSubmitting ? '正在级联删除...' : '确认删除工作区'}
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={workspaceModalMode === 'edit' ? handleSubmitEdit : handleSubmitCreate} className="p-5 space-y-4 text-xs">
            {/* Directory Selection Card (First & Prominent for create mode) */}
            <div className="space-y-1.5">
              <label className="block font-semibold text-slate-700 flex items-center justify-between">
                <span>本地物理工程目录 (Root Path) <span className="text-rose-500">*</span></span>
                {workspaceModalMode === 'create' && (
                  <button
                    type="button"
                    onClick={() => setIsManualPathMode(!isManualPathMode)}
                    className="text-[11px] text-brand-600 hover:text-brand-700 font-normal"
                  >
                    {isManualPathMode ? '切换为图形化选择' : '手动输入绝对路径'}
                  </button>
                )}
              </label>

              {workspaceModalMode === 'create' && !isManualPathMode ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleBrowseFolder}
                      disabled={isBrowsing}
                      className="flex-1 flex items-center justify-between p-3 rounded-xl bg-slate-50 hover:bg-brand-50/50 border border-slate-200 hover:border-brand-300 text-left transition group shadow-2xs"
                    >
                      <div className="flex items-center gap-2.5 truncate min-w-0">
                        <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center text-amber-700 shrink-0">
                          <Folder className="w-4 h-4" />
                        </div>
                        <div className="flex flex-col truncate min-w-0">
                          <span className="text-[10px] text-slate-400 font-medium">当前已选工程物理路径</span>
                          <span className="text-xs font-mono font-bold text-slate-900 truncate">
                            {rootPath || '点击打开文件管理器选择...'}
                          </span>
                        </div>
                      </div>

                      <span className="px-3 py-1.5 bg-brand-600 group-hover:bg-brand-700 text-white rounded-lg text-xs font-semibold shrink-0 shadow-xs transition ml-2">
                        {isBrowsing ? '正在唤起文件管理器...' : '打开文件管理器选择...'}
                      </span>
                    </button>
                  </div>
                </div>
              ) : (
                <div className="relative">
                  <input
                    type="text"
                    value={rootPath}
                    disabled={workspaceModalMode === 'edit'}
                    onChange={(e) => setRootPath(e.target.value)}
                    placeholder="/home/Skualeilu/Projects/Aegis"
                    required
                    className="w-full pl-8 pr-3 py-2 border border-slate-200 rounded-lg text-xs font-mono disabled:bg-slate-100 focus:ring-2 focus:ring-brand-500 focus:outline-hidden text-slate-900"
                  />
                  <HardDrive className="w-4 h-4 text-slate-400 absolute left-2.5 top-2.5" />
                </div>
              )}
            </div>

            <div className="space-y-1.5">
              <label className="block font-semibold text-slate-700">
                工作区名称 <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如: Aegis Core"
                required
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs focus:ring-2 focus:ring-brand-500 focus:outline-hidden text-slate-900"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block font-semibold text-slate-700">项目背景与架构说明</label>
              <textarea
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="简述该工作区的核心技术栈、职责分工与开发纪律..."
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs focus:ring-2 focus:ring-brand-500 focus:outline-hidden resize-none text-slate-900"
              />
            </div>

            {error && <div className="text-rose-600 text-[11px]">{error}</div>}

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              {workspaces.length > 0 && (
                <button
                  type="button"
                  onClick={() => openWorkspaceModal('manage')}
                  className="px-3.5 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100 transition"
                >
                  取消 / 查看列表
                </button>
              )}
              <button
                type="submit"
                disabled={isSubmitting}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium transition disabled:opacity-50 shadow-xs"
              >
                <Check className="w-3.5 h-3.5" />
                <span>{workspaceModalMode === 'edit' ? '保存修改' : '立即创建工作区'}</span>
              </button>
            </div>
          </form>
        )}

        {/* Visual Directory Picker Modal */}
        <DirectoryPickerModal
          isOpen={showDirPicker}
          initialPath={rootPath}
          onSelect={(selectedPath, suggestedName) => {
            setRootPath(selectedPath);
            if (!name || name.startsWith('工作区 #') || name === 'Aegis Core') {
              setName(suggestedName);
            }
            setShowDirPicker(false);
          }}
          onClose={() => setShowDirPicker(false)}
        />
      </div>
    </div>
  );
};
