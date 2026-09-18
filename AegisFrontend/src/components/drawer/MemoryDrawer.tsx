import React, { useState } from 'react';
import {
  X,
  BrainCircuit,
  Pin,
  Plus,
  Trash2,
  Bookmark,
  AlertOctagon,
  Sliders,
  User,
} from 'lucide-react';
import { useUiStore } from '@/stores/useUiStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';
import type { MemoryCategory } from '@/types';

export const MemoryDrawer: React.FC = () => {
  const { memoryDrawerOpen, setMemoryDrawerOpen } = useUiStore();
  const { memories, createMemory, deleteMemory } = useWorkspaceStore();

  const [activeCategory, setActiveCategory] = useState<MemoryCategory>('user_profile');
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
      case 'user_profile':
        return {
          label: '用户画像与偏好',
          shortLabel: '用户画像',
          icon: <User className="w-3.5 h-3.5 text-indigo-600" />,
          desc: '记录您的身份角色、工作习惯、输出风格与个性化指令，跨所有会话全局个性化生效',
          placeholderTitle: '偏好标题（例如: 交互风格与角色设定）',
          placeholderContent: '详细画像与偏好（例如: 资深架构师背景，偏好极简严谨推演与工程化落地，无需客套寒暄）',
        };
      case 'confirmed_architecture':
        return {
          label: '知识库与领域定论',
          shortLabel: '知识库定论',
          icon: <Bookmark className="w-3.5 h-3.5 text-purple-600" />,
          desc: '知识库业务事实、核心领域定论、服务拓扑与工程背景，跨所有会话持久沉淀',
          placeholderTitle: '知识定论（例如: 微服务物理隔离与 RAG 向量切片规范）',
          placeholderContent: '详细定论事实（例如: 知识库以 512 tokens 粒度切片并建立语义索引，主服务与 Sidecar 物理独立）',
        };
      case 'project_conventions':
        return {
          label: '工程准则与规范',
          shortLabel: '工程准则',
          icon: <Sliders className="w-3.5 h-3.5 text-blue-600" />,
          desc: '工程交付标准、质量纪律、开发与操作流程准则',
          placeholderTitle: '工程准则（例如: 变更单测 100% 覆盖与纯函数纪律）',
          placeholderContent: '详细准则要求（例如: 所有变更必须执行双端自动化测试并通过，严禁引入未声明依赖）',
        };
      case 'global_failed_attempts':
        return {
          label: '全局避坑黑名单',
          shortLabel: '避坑清单',
          icon: <AlertOctagon className="w-3.5 h-3.5 text-amber-600" />,
          desc: '历史尝试失败的方案、不可行操作与安全禁忌清单，防止任何会话重蹈覆辙',
          placeholderTitle: '避坑条目（例如: 禁止在主进程执行未沙箱化命令）',
          placeholderContent: '详细失败原因与避坑结论（例如: 曾直接执行导致权限溢出，结论是一律通过 Sidecar 8002 受限沙箱隔离运行）',
        };
    }
  };

  const categories: MemoryCategory[] = [
    'user_profile',
    'confirmed_architecture',
    'project_conventions',
    'global_failed_attempts',
  ];

  const currentInfo = getCategoryInfo(activeCategory);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="w-full max-w-lg h-full bg-white shadow-2xl flex flex-col border-l border-border-subtle animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle bg-canvas-secondary">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600">
              <BrainCircuit className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 text-sm">工作区长效记忆池</h3>
              <p className="text-[11px] text-gray-500">知识库事实 · 用户画像偏好 · 工程准则沉淀 (跨会话共享)</p>
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
        <div className="grid grid-cols-4 border-b border-border-subtle bg-gray-50 text-xs">
          {categories.map((cat) => {
            const info = getCategoryInfo(cat);
            const count = memories.filter((m) => m.category === cat).length;
            return (
              <button
                key={cat}
                onClick={() => {
                  setActiveCategory(cat);
                  setShowAddForm(false);
                }}
                className={`py-2.5 px-1 text-center transition border-b-2 flex flex-col sm:flex-row items-center justify-center gap-1 ${
                  activeCategory === cat
                    ? 'border-indigo-600 bg-white text-indigo-700 font-semibold'
                    : 'border-transparent text-gray-500 hover:text-gray-900'
                }`}
              >
                <span className="truncate">{info.shortLabel}</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-gray-200 text-gray-700 font-mono">
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3 text-xs">
          <div className="p-2.5 bg-slate-50 border border-slate-200/80 rounded-lg flex items-start gap-2 text-[11px] text-slate-600">
            <div className="mt-0.5">{currentInfo.icon}</div>
            <p className="leading-relaxed">{currentInfo.desc}</p>
          </div>

          {/* New memory button or form */}
          {!showAddForm ? (
            <button
              onClick={() => setShowAddForm(true)}
              className="w-full flex items-center justify-center gap-1.5 py-2 border border-dashed border-gray-300 hover:border-indigo-500 rounded-lg text-gray-600 hover:text-indigo-600 transition"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>新增此类别沉淀 / 设定</span>
            </button>
          ) : (
            <form onSubmit={handleAddSubmit} className="p-3.5 bg-indigo-50/40 border border-indigo-200 rounded-xl space-y-3">
              <div className="font-semibold text-gray-900 flex items-center gap-1.5">
                {currentInfo.icon}
                <span>新增: {currentInfo.label}</span>
              </div>
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder={currentInfo.placeholderTitle}
                required
                className="w-full px-2.5 py-1.5 border border-border-subtle rounded-lg text-xs bg-white"
              />
              <textarea
                rows={3}
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder={currentInfo.placeholderContent}
                required
                className="w-full px-2.5 py-1.5 border border-border-subtle rounded-lg text-xs bg-white resize-none"
              />
              <div className="flex items-center justify-between pt-1">
                <label className="flex items-center gap-1.5 text-[11px] text-gray-600 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={newPinned}
                    onChange={(e) => setNewPinned(e.target.checked)}
                    className="rounded text-indigo-600"
                  />
                  <span>置顶常驻 System Prompt 视界</span>
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
                    className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-700 text-white font-medium"
                  >
                    保存并沉淀
                  </button>
                </div>
              </div>
            </form>
          )}

          {/* Memories List */}
          <div className="space-y-2.5">
            {filteredMemories.length === 0 ? (
              <div className="text-center py-10 text-gray-400 italic space-y-1">
                <div>该类别暂无沉淀记录</div>
                <div className="text-[11px] text-gray-400 font-normal">点击上方按钮可主动新增，或在任务中由智能体自动提炼上浮</div>
              </div>
            ) : (
              filteredMemories.map((mem) => (
                <div
                  key={mem.id}
                  className="p-3.5 rounded-xl border border-border-subtle bg-white hover:border-indigo-200 transition space-y-1.5 shadow-2xs group relative"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 font-semibold text-gray-900">
                      {mem.pinned && <Pin className="w-3 h-3 text-indigo-600 shrink-0 fill-indigo-600" />}
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
