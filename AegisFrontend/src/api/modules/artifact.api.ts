/**
 * Aegis Artifact & Observation Pruner API Module
 */

import { httpClient } from '../client';
import type { ArtifactHandleResponse } from '@/types';

export const artifactApi = {
  /**
   * Retrieve observation pruned content or task offline artifact by handle ID
   */
  getArtifact(handleId: string): Promise<ArtifactHandleResponse> {
    return httpClient.get<ArtifactHandleResponse>(
      `/api/v1/artifacts/${encodeURIComponent(handleId)}`
    );
  },
};
