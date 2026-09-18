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

function normalizeWorkspace(raw: any): Workspace {
  if (!raw) return raw;
  return {
    id: raw.workspace_id || raw.id || '',
    name: raw.name || '',
    root_path: raw.root_path || '',
    description: raw.description || '',
    created_at:
      typeof raw.created_at === 'number'
        ? new Date(raw.created_at * 1000).toISOString()
        : raw.created_at || new Date().toISOString(),
    updated_at:
      typeof raw.updated_at === 'number'
        ? new Date(raw.updated_at * 1000).toISOString()
        : raw.updated_at || new Date().toISOString(),
    session_count: raw.session_count,
    memory_count: raw.memory_count,
  };
}

export const workspaceApi = {
  /**
   * List all registered workspaces
   */
  async list(): Promise<Workspace[]> {
    const data = await httpClient.get<any[]>('/api/v1/workspaces');
    return Array.isArray(data) ? data.map(normalizeWorkspace) : [];
  },

  /**
   * Get single workspace by ID
   */
  async get(workspaceId: string): Promise<Workspace> {
    const data = await httpClient.get<any>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}`);
    return normalizeWorkspace(data);
  },

  /**
   * Create a new workspace (idempotent by root_path)
   */
  async create(payload: WorkspaceCreatePayload): Promise<Workspace> {
    const data = await httpClient.post<any>('/api/v1/workspaces', payload);
    return normalizeWorkspace(data);
  },

  /**
   * Update workspace metadata (name, description)
   */
  async update(workspaceId: string, payload: WorkspaceUpdatePayload): Promise<Workspace> {
    const data = await httpClient.patch<any>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}`, payload);
    return normalizeWorkspace(data);
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
