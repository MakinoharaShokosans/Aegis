/**
 * Aegis RAG Gateway API Module
 */

import { httpClient } from '../client';
import type {
  RagHealth,
  RagIngestPayload,
  RagIngestResponse,
  RagRetrievePayload,
  RagRetrieveResult,
} from '@/types';

export const ragApi = {
  /**
   * Health probe for AegisRAG microservice and Qdrant
   */
  getHealth(): Promise<RagHealth> {
    return httpClient.get<RagHealth>('/api/v1/rag/health');
  },

  /**
   * Trigger AST-aware chunking and vector embedding ingestion
   */
  triggerIngest(payload: RagIngestPayload): Promise<RagIngestResponse> {
    return httpClient.post<RagIngestResponse>('/api/v1/rag/ingest', payload);
  },

  /**
   * Query dual-recall (dense + sparse BM25) and Cross-Encoder reranking
   */
  retrieve(payload: RagRetrievePayload): Promise<RagRetrieveResult> {
    return httpClient.post<RagRetrieveResult>('/api/v1/rag/retrieve', payload);
  },
};
