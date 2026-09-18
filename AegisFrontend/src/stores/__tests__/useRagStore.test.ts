import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useRagStore } from '../useRagStore';
import { ragApi } from '@/api';

describe('useRagStore', () => {
  beforeEach(() => {
    useRagStore.setState({
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
    });
    vi.restoreAllMocks();
  });

  it('should fetch RAG microservice health probe', async () => {
    vi.spyOn(ragApi, 'getHealth').mockResolvedValue({
      status: 'healthy',
      version: '1.0.0',
      service: 'AegisRAG',
      qdrant_connected: true,
      dense_model: 'bge-small-en-v1.5',
      sparse_model: 'BM25',
    });

    const store = useRagStore.getState();
    await store.fetchHealth();

    const state = useRagStore.getState();
    expect(state.health?.status).toBe('healthy');
    expect(state.health?.qdrant_connected).toBe(true);
  });

  it('should trigger RAG chunk ingestion and update progress status', async () => {
    vi.spyOn(ragApi, 'triggerIngest').mockResolvedValue({
      task_id: 'ingest-1',
      status: 'completed',
      total_files: 42,
      total_chunks: 380,
    });

    const store = useRagStore.getState();
    await store.triggerIngest({ incremental: true });

    const state = useRagStore.getState();
    expect(state.isIngesting).toBe(false);
    expect(state.ingestProgress).toEqual({ total_files: 42, total_chunks: 380 });
    expect(state.ingestStatus).toContain('42');
  });

  it('should execute hybrid retrieval query in playground', async () => {
    vi.spyOn(ragApi, 'retrieve').mockResolvedValue({
      query: '安全闸门',
      hits: [
        {
          score: 0.95,
          file_path: 'documents/11_http_api.md',
          start_line: 25,
          end_line: 60,
          content: '三道闸门契约',
        },
      ],
      elapsed_ms: 18,
    });

    const store = useRagStore.getState();
    await store.search('安全闸门');

    const state = useRagStore.getState();
    expect(state.isSearching).toBe(false);
    expect(state.hits.length).toBe(1);
    expect(state.hits[0].file_path).toBe('documents/11_http_api.md');
    expect(state.searchDurationMs).toBe(18);
  });
});
