/**
 * Aegis Session API Module
 */

import { httpClient } from '../client';
import type { Session, SessionContextResponse } from '@/types';

export const sessionApi = {
  /**
   * List all sessions within a workspace
   */
  list(workspaceId: string): Promise<Session[]> {
    return httpClient.get<Session[]>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sessions`);
  },

  /**
   * Create a new session in workspace
   */
  create(workspaceId: string, title?: string): Promise<Session> {
    return httpClient.post<Session>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sessions`, {
      title: title || '新会话任务',
    });
  },

  /**
   * Get single session by ID
   */
  get(sessionId: string): Promise<Session> {
    return httpClient.get<Session>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`);
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
