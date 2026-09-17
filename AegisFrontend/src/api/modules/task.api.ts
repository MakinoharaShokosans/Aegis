/**
 * Aegis Task, Execution & HITL Approval API Module
 */

import { httpClient } from '../client';
import { subscribeTaskEvents, type SSEOptions } from '../sse';
import type {
  TaskCreatePayload,
  TaskCreateResponse,
  HitlApprovalPayload,
  HitlRejectPayload,
} from '@/types';

export const taskApi = {
  /**
   * Submit and launch a new agent task under a session
   */
  create(sessionId: string, payload: TaskCreatePayload): Promise<TaskCreateResponse> {
    return httpClient.post<TaskCreateResponse>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/tasks`,
      payload
    );
  },

  /**
   * Get task execution status, messages and traces
   */
  get(taskId: string): Promise<unknown> {
    return httpClient.get<unknown>(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
  },

  /**
   * Approve a blocked HITL privilege/network action
   */
  approve(
    taskId: string,
    payload: HitlApprovalPayload
  ): Promise<{ success: boolean; task_status: string }> {
    return httpClient.post<{ success: boolean; task_status: string }>(
      `/api/v1/tasks/${encodeURIComponent(taskId)}/approve`,
      payload
    );
  },

  /**
   * Reject a blocked HITL action with reason
   */
  reject(
    taskId: string,
    payload: HitlRejectPayload
  ): Promise<{ success: boolean; task_status: string }> {
    return httpClient.post<{ success: boolean; task_status: string }>(
      `/api/v1/tasks/${encodeURIComponent(taskId)}/reject`,
      payload
    );
  },

  /**
   * Emergency physical cancel/breaker for a running task
   */
  cancel(taskId: string): Promise<{ success: boolean; task_status: string }> {
    return httpClient.post<{ success: boolean; task_status: string }>(
      `/api/v1/tasks/${encodeURIComponent(taskId)}/cancel`
    );
  },

  /**
   * Subscribe to task SSE stream events
   */
  subscribe(taskId: string, options?: SSEOptions): () => void {
    return subscribeTaskEvents(taskId, options);
  },
};
