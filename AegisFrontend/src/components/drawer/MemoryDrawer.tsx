import React, { useState } from 'react';
import {
  X,
  BrainCircuit,
  Pin,
  Plus,
  Trash2,
  Bookmark,
  AlertOctagon,
  Code2,
} from 'lucide-react';
import { useUiStore } from '@/stores/useUiStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import type { MemoryCategory } from '@/types';

export const MemoryDrawer: React.FC = () => {
  const { memoryDrawerOpen, setMemoryDrawerOpen } = useUiStore();
  const { memories, createMemory, deleteMemory } = useWorkspaceStore();

  const [activeCategory, setActiveCategory] = useState<MemoryCategory>('confirmed_architecture');
  const [showAddForm, setShowAddForm] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newContent, setNewContent] = useState('');
  const [newPinned, setNewPinned] = useState(true);

  if (!memoryDrawerOpen) return null;

  const filteredMemories = memories.filter((m) => m.category === activeCategory);

  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim() || !newContent.trim()) return;
    await createMemory({
      category: activeCategory,
      title: newTitle,
      content: newContent,
      pinned: newPinned,
    });
    setNewTitle('');
    setNewContent('');
    setShowAddForm(false);
  };

  const getCategoryInfo = (cat: MemoryCategory) => {
    switch (cat) {
      case 'confirmed_architecture':
        return {
          label: '项目架构定论',
          icon: <Bookmark className="w-3.5 h-3.5 text-purple-600" />,
          desc: '核心模块分层、服务端口分配与依赖拓扑定论，跨所有会话持久生效',
        };
      case 'project_conventions':
        return {
          label: '编码与工程规范',
          icon: <Code2 className="w-3.5 h-3.5 text-blue-600" />,
          desc: '严格代码风格、单测覆盖要求（100% Green）与纯函数设计纪律',
        };
      case 'global_failed_attempts':
        return {
          label: '全局避坑黑名单',
          icon: <AlertOctagon className="w-3.5 h-3.5 text-amber-600" />,
          desc: '历史尝试失败的方案与不可行指令清单，防止任何会话重蹈覆辙',
        };
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="w-full max-w-md h-full bg-white shadow-2xl flex flex-col border-l border-border-subtle animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle bg-canvas-secondary">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-purple-100 text-purple-700">
              <BrainCircuit className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 text-sm">工作区长期共享记忆</h3>
              <p className="text-[11px] text-gray-500">Workspace Shared Memory (跨会话共享)</p>
            </div>
          </div>
          <button
            onClick={() => setMemoryDrawerOpen(false)}
            className="p-1 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-200 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Category Selector Tabs */}
        <div className="flex border-b border-border-subtle bg-gray-50 text-xs">
          {(['confirmed_architecture', 'project_conventions', 'global_failed_attempts'] as MemoryCategory[]).map(
            (cat) => {
              const info = getCategoryInfo(cat);
              const count = memories.filter((m) => m.category === cat).length;
              return (
                <button
                  key={cat}
                  onClick={() => {
                    setActiveCategory(cat);
                    setShowAddForm(false);
                  }}
                  className={`flex-1 py-2 px-1.5 text-center transition border-b-2 flex items-center justify-center gap-1 ${
                    activeCategory === cat
                      ? 'border-purple-600 bg-white text-purple-700 font-semibold'
                      : 'border-transparent text-gray-500 hover:text-gray-900'
                  }`}
                >
                  <span className="truncate">{info.label}</span>
                  <span className="text-[10px] px-1 py-0.2 rounded-full bg-gray-200 text-gray-700 font-mono">
                    {count}
                  </span>
                </button>
              );
            }
          )}
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3 text-xs">
          <p className="text-[11px] text-gray-500 px-1">{getCategoryInfo(activeCategory).desc}</p>

          {/* New memory button or form */}
          {!showAddForm ? (
            <button
              onClick={() => setShowAddForm(true)}
              className="w-full flex items-center justify-center gap-1.5 py-2 border border-dashed border-gray-300 hover:border-purple-500 rounded-lg text-gray-600 hover:text-purple-600 transition"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>新增此类别定论 / 纪律</span>
            </button>
          ) : (
            <form onSubmit={handleAddSubmit} className="p-3.5 bg-purple-50/40 border border-purple-200 rounded-xl space-y-3">
              <div className="font-semibold text-gray-900">新增记忆定论</div>
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="定论标题（例如: 接入层三道闸门执行次序）"
                required
                className="w-full px-2.5 py-1.5 border border-border-subtle rounded-lg text-xs bg-white"
              />
              <textarea
                rows={3}
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder="详细定论规范内容..."
                required
                className="w-full px-2.5 py-1.5 border border-border-subtle rounded-lg text-xs bg-white resize-none"
              />
              <div className="flex items-center justify-between pt-1">
                <label className="flex items-center gap-1.5 text-[11px] text-gray-600 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={newPinned}
                    onChange={(e) => setNewPinned(e.target.checked)}
                    className="rounded text-purple-600"
                  />
                  <span>置顶常驻 Prompt 视界</span>
                </label>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setShowAddForm(false)}
                    className="px-2.5 py-1 rounded text-gray-500 hover:bg-gray-200"
                  >
                    取消
                  </button>
                  <button
                    type="submit"
                    className="px-3 py-1 rounded bg-purple-600 hover:bg-purple-700 text-white font-medium"
                  >
                    保存
                  </button>
                </div>
              </div>
            </form>
          )}

          {/* Memories List */}
          <div className="space-y-2.5">
            {filteredMemories.length === 0 ? (
              <div className="text-center py-8 text-gray-400 italic">该类别暂无记忆定论</div>
            ) : (
              filteredMemories.map((mem) => (
                <div
                  key={mem.id}
                  className="p-3.5 rounded-xl border border-border-subtle bg-white hover:border-purple-200 transition space-y-1.5 shadow-2xs group relative"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 font-semibold text-gray-900">
                      {mem.pinned && <Pin className="w-3 h-3 text-purple-600 shrink-0 fill-purple-600" />}
                      <span>{mem.title}</span>
                    </div>
                    <button
                      onClick={() => deleteMemory(mem.id)}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 transition"
                      title="删除此条记忆"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <p className="text-gray-600 text-[11px] leading-relaxed whitespace-pre-wrap">{mem.content}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
