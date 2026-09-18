import { create } from 'zustand';
import type { RagHealth, RagHit } from '@/types';
import { ragApi } from '@/api';

interface RagState {
  health: RagHealth | null;
  isLoadingHealth: boolean;

  isIngesting: boolean;
  ingestStatus: string | null;
  ingestProgress: { total_files: number; total_chunks: number } | null;

  // Retrieval Playground
  query: string;
  hits: RagHit[];
  isSearching: boolean;
  searchDurationMs: number;
  selectedHit: RagHit | null;

  // Actions
  fetchHealth: () => Promise<void>;
  triggerIngest: (options?: { incremental?: boolean; workspaceId?: string }) => Promise<void>;
  search: (query: string) => Promise<void>;
  setQuery: (q: string) => void;
  setSelectedHit: (hit: RagHit | null) => void;
  clearPlayground: () => void;
}

export const useRagStore = create<RagState>((set) => ({
  health: null,
  isLoadingHealth: false,

  isIngesting: false,
  ingestStatus: null,
  ingestProgress: null,

  query: '',
  hits: [],
  isSearching: false,
  searchDurationMs: 0,
  selectedHit: null,

  fetchHealth: async () => {
    set({ isLoadingHealth: true });
    try {
      const h = await ragApi.getHealth();
      set({ health: h, isLoadingHealth: false });
    } catch {
      set({ isLoadingHealth: false });
    }
  },

  triggerIngest: async (options) => {
    set({ isIngesting: true, ingestStatus: '正在扫描工作区并执行语法感知切分...' });
    try {
      const res: any = await ragApi.triggerIngest({
        incremental: options?.incremental ?? true,
        workspace_id: options?.workspaceId,
      });
      const indexedCount = res.indexed ?? res.total_files ?? 0;
      const skippedCount = res.skipped ?? 0;
      const totalCount = res.total_chunks ?? indexedCount;
      set({
        isIngesting: false,
        ingestStatus: `索引完成！已处理 ${indexedCount} 个切片，跳过 ${skippedCount} 个未修改文件`,
        ingestProgress: { total_files: indexedCount, total_chunks: totalCount },
      });
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : '索引失败';
      set({
        isIngesting: false,
        ingestStatus: `索引失败: ${errorMsg}`,
      });
    }
  },

  search: async (q: string) => {
    if (!q.trim()) return;
    set({ isSearching: true, query: q });
    const start = Date.now();
    try {
      const res: any = await ragApi.retrieve({ query: q, top_k: 5 });
      const rawHits = res.results || res.hits || [];
      const normalizedHits: RagHit[] = rawHits.map((r: any, idx: number) => ({
        score: r.score ?? 0,
        file_path: r.file_path || '',
        start_line: r.start_line ?? 1,
        end_line: r.end_line ?? 1,
        content: r.content || '',
        dense_rank: r.dense_rank ?? idx + 1,
        sparse_rank: r.sparse_rank,
        rrf_score: r.rrf_score,
      }));
      set({
        hits: normalizedHits,
        searchDurationMs: res.elapsed_ms || Date.now() - start,
        isSearching: false,
      });
    } catch {
      set({
        hits: [],
        searchDurationMs: Date.now() - start,
        isSearching: false,
      });
    }
  },

  setQuery: (q) => set({ query: q }),
  setSelectedHit: (hit) => set({ selectedHit: hit }),
  clearPlayground: () => set({ hits: [], query: '', selectedHit: null }),
}));
