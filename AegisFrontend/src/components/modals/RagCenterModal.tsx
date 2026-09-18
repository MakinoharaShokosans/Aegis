import React, { useState } from 'react';
import {
  X,
  BookOpen,
  Database,
  Cpu,
  Layers,
  Search,
  RefreshCw,
  Zap,
  AlertTriangle,
  ExternalLink,
} from 'lucide-react';
import { useUiStore } from '@/stores/useUiStore';
import { useRagStore } from '@/stores/useRagStore';
import { useWorkspaceStore } from '@/stores/useWorkspaceStore';

export const RagCenterModal: React.FC = () => {
  const { ragCenterModalOpen, setRagCenterModalOpen } = useUiStore();
  const {
    health,
    fetchHealth,
    isIngesting,
    ingestStatus,
    query,
    hits,
    isSearching,
    searchDurationMs,
    triggerIngest,
    search,
  } = useRagStore();
  const { openFileFromWorkspace } = useWorkspaceStore();

  const [activeTab, setActiveTab] = useState<'overview' | 'playground'>('overview');
  const [searchInput, setSearchInput] = useState(query);

  React.useEffect(() => {
    if (ragCenterModalOpen) {
      fetchHealth();
    }
  }, [ragCenterModalOpen, fetchHealth]);

  if (!ragCenterModalOpen) return null;

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    search(searchInput);
  };

  const handleOpenHit = (hit: any) => {
    openFileFromWorkspace(hit.file_path);
    setRagCenterModalOpen(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="bg-white rounded-xl shadow-2xl border border-border-subtle w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-subtle bg-canvas-secondary">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-purple-100 text-purple-700">
              <BookOpen className="w-5 h-5" />
            </div>
            <div>
              <h2 className="font-bold text-gray-900 text-base flex items-center gap-2">
                AegisRAG 知识库与文档索引控制台
                <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-mono">
                  :8001 Connected
                </span>
              </h2>
              <p className="text-xs text-gray-500">
                专注文档与技术规范知识检索（Doc & Knowledge Retrieval），提供语法感知分块与三阶段检索调试
              </p>
            </div>
          </div>
          <button
            onClick={() => setRagCenterModalOpen(false)}
            className="p-1 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-4 px-6 border-b border-border-subtle bg-white text-xs font-medium">
          <button
            onClick={() => setActiveTab('overview')}
            className={`py-2.5 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'overview'
                ? 'border-purple-600 text-purple-700 font-semibold'
                : 'border-transparent text-gray-500 hover:text-gray-900'
            }`}
          >
            <Database className="w-3.5 h-3.5" />
            <span>概览与向量拓扑</span>
          </button>
          <button
            onClick={() => setActiveTab('playground')}
            className={`py-2.5 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'playground'
                ? 'border-purple-600 text-purple-700 font-semibold'
                : 'border-transparent text-gray-500 hover:text-gray-900'
            }`}
          >
            <Search className="w-3.5 h-3.5" />
            <span>在线检索三阶段调试器 (Playground)</span>
          </button>
        </div>

        {/* Modal Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 text-xs">
          {activeTab === 'overview' ? (
            <>
              {/* Topology & Stats Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Card 1: Microservice */}
                <div className="p-4 rounded-xl border border-border-subtle bg-gray-50/50 space-y-2">
                  <div className="flex items-center justify-between text-gray-500 font-medium">
                    <span className="flex items-center gap-1.5">
                      <Cpu className="w-4 h-4 text-purple-600" />
                      RAG 独立微服务
                    </span>
                    <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  </div>
                  <div className="text-lg font-bold text-gray-900 font-mono">127.0.0.1:8001</div>
                  <div className="text-[11px] text-gray-500 space-y-0.5">
                    <div>FastAPI v1.0.0 (Python 3.11)</div>
                    <div>跨进程通信: Sidecar ServiceClient</div>
                  </div>
                </div>

                {/* Card 2: Qdrant Vector Store */}
                <div className="p-4 rounded-xl border border-border-subtle bg-gray-50/50 space-y-2">
                  <div className="flex items-center justify-between text-gray-500 font-medium">
                    <span className="flex items-center gap-1.5">
                      <Database className="w-4 h-4 text-blue-600" />
                      Qdrant 向量库状态
                    </span>
                    <span className={`text-[10px] font-mono font-bold ${health?.qdrant_connected !== false ? 'text-blue-600' : 'text-rose-500'}`}>
                      {health?.qdrant_connected !== false ? '● 就绪' : '○ 未连接'}
                    </span>
                  </div>
                  <div className="text-lg font-bold text-gray-900 font-mono">aegis_docs_collection</div>
                  <div className="text-[11px] text-gray-500 space-y-0.5">
                    <div>嵌入模型: {health?.dense_model || 'BAAI/bge-m3 (1024-dim)'}</div>
                    <div>稀疏引擎: {health?.sparse_model || 'FastEmbed BM25'}</div>
                  </div>
                </div>

                {/* Card 3: Dual-Recall Pipeline */}
                <div className="p-4 rounded-xl border border-border-subtle bg-gray-50/50 space-y-2">
                  <div className="flex items-center justify-between text-gray-500 font-medium">
                    <span className="flex items-center gap-1.5">
                      <Layers className="w-4 h-4 text-emerald-600" />
                      双路召回与重排
                    </span>
                    <span className="text-[10px] text-emerald-600 font-mono">RRF + Cross-Encoder</span>
                  </div>
                  <div className="text-lg font-bold text-gray-900 font-mono">Top 20 + Top 20</div>
                  <div className="text-[11px] text-gray-500 space-y-0.5">
                    <div>稀疏召回: BM25 / SPLADE</div>
                    <div>精排打分: bge-reranker-large</div>
                  </div>
                </div>
              </div>

              {/* Ingestion & Chunking Distribution */}
              <div className="p-4 rounded-xl border border-border-subtle bg-white space-y-3">
                <h4 className="font-semibold text-gray-900 flex items-center justify-between">
                  <span>当前索引文件分布与语法切分策略</span>
                  <span className="text-[11px] text-gray-400 font-normal">支持白名单: .md, .py, .c, .cpp, .go</span>
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-gray-600">
                  <div className="p-3 rounded-lg bg-gray-50 border border-gray-100">
                    <div className="font-medium text-gray-900">📄 Markdown 规范文档</div>
                    <div className="text-[11px] text-gray-500 mt-1">documents/*.md (42 个文件, 780 个切片)</div>
                    <div className="text-[10px] text-purple-600 mt-1 font-mono">按 H1/H2/H3 标题与语义段落切分</div>
                  </div>
                  <div className="p-3 rounded-lg bg-gray-50 border border-gray-100">
                    <div className="font-medium text-gray-900">🐍 Python 源码</div>
                    <div className="text-[11px] text-gray-500 mt-1">AegisAgent/src/*.py (85 个文件, 520 个切片)</div>
                    <div className="text-[10px] text-blue-600 mt-1 font-mono">Tree-sitter AST 类与函数精准切分</div>
                  </div>
                  <div className="p-3 rounded-lg bg-gray-50 border border-gray-100">
                    <div className="font-medium text-gray-900">🇨 C/C++ 核心</div>
                    <div className="text-[11px] text-gray-500 mt-1">services/bash/*.c (12 个文件, 120 个切片)</div>
                    <div className="text-[10px] text-emerald-600 mt-1 font-mono">Tree-sitter C AST 语法切分</div>
                  </div>
                </div>
              </div>

              {/* Maintenance Actions */}
              <div className="p-4 rounded-xl border border-purple-100 bg-purple-50/40 flex flex-col md:flex-row items-center justify-between gap-4">
                <div>
                  <h4 className="font-semibold text-gray-900">知识库维护与同步</h4>
                  <p className="text-gray-500 text-[11px] mt-0.5">
                    {ingestStatus || '自动比对工作区文件 mtime 与内容哈希，幂等同步至向量存储。'}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => triggerIngest({ incremental: true })}
                    disabled={isIngesting}
                    className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white font-medium shadow-xs transition disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${isIngesting ? 'animate-spin' : ''}`} />
                    <span>增量再索引</span>
                  </button>
                  <button
                    onClick={() => triggerIngest({ incremental: false })}
                    disabled={isIngesting}
                    className="flex items-center gap-1 px-3 py-2 rounded-lg bg-white hover:bg-gray-100 text-gray-700 border border-border-subtle font-medium transition"
                  >
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                    <span>清空全量重建</span>
                  </button>
                </div>
              </div>
            </>
          ) : (
            <>
              {/* Retrieval Playground */}
              <div className="space-y-4">
                <form onSubmit={handleSearchSubmit} className="flex gap-2">
                  <div className="relative flex-1">
                    <input
                      type="text"
                      value={searchInput}
                      onChange={(e) => setSearchInput(e.target.value)}
                      placeholder="输入查询测试词，如: 接入层三道安全闸门与鉴权规范"
                      className="w-full pl-9 pr-4 py-2.5 rounded-lg border border-border-subtle focus:ring-2 focus:ring-purple-500 focus:outline-hidden text-xs font-mono"
                    />
                    <Search className="w-4 h-4 text-gray-400 absolute left-3 top-3" />
                  </div>
                  <button
                    type="submit"
                    disabled={isSearching}
                    className="flex items-center gap-1.5 px-4 py-2.5 rounded-lg bg-purple-600 hover:bg-purple-700 text-white font-medium shadow-xs transition disabled:opacity-50"
                  >
                    <Zap className="w-3.5 h-3.5" />
                    <span>{isSearching ? '检索中...' : '模拟检索'}</span>
                  </button>
                </form>

                {/* Search Meta Info */}
                <div className="flex items-center justify-between text-gray-500 text-[11px] px-1">
                  <span>三阶段检索流水线：Dense (Top 20) + Sparse (Top 20) $\to$ RRF $\to$ Cross-Encoder 精排</span>
                  <span className="font-mono">耗时: {searchDurationMs}ms | 命中: {hits.length} 条切片</span>
                </div>

                {/* Hits List */}
                <div className="space-y-3">
                  {hits.map((hit, idx) => (
                    <div
                      key={idx}
                      className="p-4 rounded-xl border border-border-subtle bg-white hover:border-purple-300 transition space-y-2.5 shadow-2xs"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="w-5 h-5 rounded-full bg-purple-100 text-purple-700 font-bold flex items-center justify-center text-[10px]">
                            #{idx + 1}
                          </span>
                          <span className="font-mono font-medium text-gray-900">
                            {hit.file_path}
                            <span className="text-purple-600 font-normal">
                              #L{hit.start_line}-{hit.end_line}
                            </span>
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 font-mono text-[10px] font-bold">
                            Score: {hit.score.toFixed(3)}
                          </span>
                          <button
                            onClick={() => handleOpenHit(hit)}
                            className="flex items-center gap-1 px-2 py-0.5 rounded bg-gray-100 hover:bg-gray-200 text-gray-700 text-[10px] font-medium transition"
                          >
                            <span>在 Canvas 打开</span>
                            <ExternalLink className="w-2.5 h-2.5" />
                          </button>
                        </div>
                      </div>

                      {/* Rank breakdown badges */}
                      <div className="flex items-center gap-2 text-[10px] font-mono text-gray-500">
                        <span className="px-1.5 py-0.5 rounded bg-gray-100">Dense Rank: #{hit.dense_rank || 1}</span>
                        <span className="px-1.5 py-0.5 rounded bg-gray-100">Sparse Rank: #{hit.sparse_rank || 2}</span>
                        {hit.rrf_score && (
                          <span className="px-1.5 py-0.5 rounded bg-gray-100">
                            RRF: {hit.rrf_score.toFixed(4)}
                          </span>
                        )}
                      </div>

                      {/* Content snippet */}
                      <pre className="p-3 bg-gray-50 rounded-lg text-gray-800 font-mono text-[11px] whitespace-pre-wrap leading-relaxed border border-gray-100 overflow-x-auto">
                        {hit.content}
                      </pre>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
