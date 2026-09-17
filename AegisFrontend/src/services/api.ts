/**
 * REST API client for Aegis Backend
 */

export interface CreateTaskPayload {
  prompt: string;
  permission_level?: 'readonly' | 'workspace_write' | 'full_access';
  model?: string;
  context_files?: string[];
}

export const api = {
  async createTask(payload: CreateTaskPayload) {
    const res = await fetch('/api/v1/tasks', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Failed to create task: ${res.statusText}`);
    }
    return res.json();
  },

  async getTask(taskId: string) {
    const res = await fetch(`/api/v1/tasks/${taskId}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch task: ${res.statusText}`);
    }
    return res.json();
  },

  async approveAction(taskId: string, actionId: string, options?: { alwaysAllow?: boolean }) {
    const res = await fetch(`/api/v1/tasks/${taskId}/approve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ action_id: actionId, always_allow: options?.alwaysAllow }),
    });
    if (!res.ok) {
      throw new Error(`Failed to approve action: ${res.statusText}`);
    }
    return res.json();
  },

  async rejectAction(taskId: string, actionId: string, reason?: string) {
    const res = await fetch(`/api/v1/tasks/${taskId}/reject`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ action_id: actionId, reason }),
    });
    if (!res.ok) {
      throw new Error(`Failed to reject action: ${res.statusText}`);
    }
    return res.json();
  },

  async cancelTask(taskId: string) {
    const res = await fetch(`/api/v1/tasks/${taskId}/cancel`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Failed to cancel task: ${res.statusText}`);
    }
    return res.json();
  },
};
