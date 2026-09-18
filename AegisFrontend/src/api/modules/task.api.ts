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
    const body: Record<string, unknown> = {
      task_goal: payload.task_goal || payload.prompt || '',
    };
    if (payload.permission_level) {
      body.permission_level = payload.permission_level;
    }
    if (payload.parent_task_id) {
      body.parent_task_id = payload.parent_task_id;
    }
    return httpClient.post<TaskCreateResponse>(
      `/api/v1/sessions/${encodeURIComponent(sessionId)}/tasks`,
      body
    );
  },

  /**
   * Get task execution status, messages and traces
   */
  get(taskId: string): Promise<unknown> {
    return httpClient.get<unknown>(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
  },

  /**
   * Get recorded LLM request and response snapshots for a task
   */
  getLlmCalls(taskId: string): Promise<any[]> {
    return httpClient.get<any[]>(`/api/v1/tasks/${encodeURIComponent(taskId)}/llm_calls`);
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
