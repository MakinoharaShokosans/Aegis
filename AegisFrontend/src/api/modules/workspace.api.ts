/**
 * Aegis Workspace & Memory API Module
 */

import { httpClient } from '../client';
import type {
  Workspace,
  WorkspaceCreatePayload,
  WorkspaceUpdatePayload,
  MemoryViewDto,
  PromoteFactPayload,
  RecordFailurePayload,
} from '@/types';

export const workspaceApi = {
  /**
   * List all registered workspaces
   */
  list(): Promise<Workspace[]> {
    return httpClient.get<Workspace[]>('/api/v1/workspaces');
  },

  /**
   * Get single workspace by ID
   */
  get(workspaceId: string): Promise<Workspace> {
    return httpClient.get<Workspace>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}`);
  },

  /**
   * Create a new workspace (idempotent by root_path)
   */
  create(payload: WorkspaceCreatePayload): Promise<Workspace> {
    return httpClient.post<Workspace>('/api/v1/workspaces', payload);
  },

  /**
   * Update workspace metadata (name, description)
   */
  update(workspaceId: string, payload: WorkspaceUpdatePayload): Promise<Workspace> {
    return httpClient.patch<Workspace>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}`, payload);
  },

  /**
   * Delete a workspace and its sessions/memories
   */
  delete(workspaceId: string): Promise<{ success: boolean; deleted_id: string }> {
    return httpClient.delete<{ success: boolean; deleted_id: string }>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}`);
  },

  /**
   * Get long-term workspace memory pool (confirmed architecture, conventions, failed attempts)
   */
  getMemory(workspaceId: string): Promise<MemoryViewDto> {
    return httpClient.get<MemoryViewDto>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/memory`);
  },

  /**
   * Promote a confirmed architectural fact or convention
   */
  promoteFact(workspaceId: string, payload: PromoteFactPayload): Promise<{ status: string; category?: string }> {
    return httpClient.post<{ status: string; category?: string }>(
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/memory/facts`,
      payload
    );
  },

  /**
   * Record a failed attempt to prevent circular trial-and-error
   */
  recordFailure(workspaceId: string, payload: RecordFailurePayload): Promise<{ status: string }> {
    return httpClient.post<{ status: string }>(
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/memory/failures`,
      payload
    );
  },
};
