/**
 * Aegis Session API Module
 */

import { httpClient } from '../client';
import type { Session, SessionContextResponse } from '@/types';

function normalizeSession(raw: any): Session {
  if (!raw) return raw;
  return {
    id: raw.session_id || raw.id || '',
    workspace_id: raw.workspace_id || '',
    title: raw.title || '新会话任务',
    status: raw.status || 'active',
    created_at:
      typeof raw.created_at === 'number'
        ? new Date(raw.created_at * 1000).toISOString()
        : raw.created_at || new Date().toISOString(),
    updated_at:
      typeof raw.updated_at === 'number'
        ? new Date(raw.updated_at * 1000).toISOString()
        : raw.updated_at || new Date().toISOString(),
  };
}

export const sessionApi = {
  /**
   * List all sessions within a workspace
   */
  async list(workspaceId: string): Promise<Session[]> {
    const data = await httpClient.get<any[]>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sessions`);
    return Array.isArray(data) ? data.map(normalizeSession) : [];
  },

  /**
   * Create a new session in workspace
   */
  async create(workspaceId: string, title?: string): Promise<Session> {
    const data = await httpClient.post<any>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sessions`, {
      title: title || '新会话任务',
    });
    return normalizeSession(data);
  },

  /**
   * Get single session by ID
   */
  async get(sessionId: string): Promise<Session> {
    const data = await httpClient.get<any>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`);
    return normalizeSession(data);
  },

  /**
   * Delete a session and its turns/memories
   */
  delete(sessionId: string): Promise<{ success: boolean; session_id: string }> {
    return httpClient.delete<{ success: boolean; session_id: string }>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`);
  },

  /**
   * Get assembled prompt context and token water level
   */
  getContext(sessionId: string): Promise<SessionContextResponse> {
    return httpClient.get<SessionContextResponse>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/context`);
  },
};
