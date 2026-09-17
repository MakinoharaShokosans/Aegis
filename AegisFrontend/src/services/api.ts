/**
 * Aegis Unified REST API Client
 * Supports Workspaces, Sessions, Tasks, Files, and RAG endpoints with X-API-Token injection.
 */

import type {
  Workspace,
  WorkspaceCreatePayload,
  WorkspaceUpdatePayload,
  Session,
  SessionContextResponse,
  FileNode,
  RagHealth,
  RagRetrieveResult,
  PermissionLevel,
} from '@/types';

export interface MemoryViewDto {
  scope: string;
  updated_at?: number;
  project_conventions: string[];
  confirmed_architecture: string[];
  failed_attempts: Array<{ action: string; failure_reason: string; conclusion?: string }>;
}

class ApiClient {
  private token: string = '';

  constructor() {
    this.token = localStorage.getItem('aegis_api_token') || '';
  }

  public setToken(token: string) {
    this.token = token;
    localStorage.setItem('aegis_api_token', token);
  }

  public getToken(): string {
    return this.token;
  }

  private getHeaders(extraHeaders: Record<string, string> = {}): HeadersInit {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...extraHeaders,
    };
    if (this.token) {
      headers['X-API-Token'] = this.token;
    }
    return headers;
  }

  private async request<T>(url: string, options: RequestInit = {}): Promise<T> {
    const res = await fetch(url, {
      ...options,
      headers: this.getHeaders(options.headers as Record<string, string>),
    });

    if (!res.ok) {
      let errorMsg = res.statusText;
      try {
        const errorJson = await res.json();
        errorMsg = errorJson.detail || errorJson.message || JSON.stringify(errorJson);
      } catch {
        // use statusText
      }
      throw new Error(`API Request Error [${res.status}]: ${errorMsg}`);
    }

    if (res.status === 204) {
      return {} as T;
    }

    return res.json();
  }

  // ==========================================
  // Workspaces API
  // ==========================================
  async listWorkspaces(): Promise<Workspace[]> {
    return this.request<Workspace[]>('/api/v1/workspaces');
  }

  async createWorkspace(payload: WorkspaceCreatePayload): Promise<Workspace> {
    return this.request<Workspace>('/api/v1/workspaces', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getWorkspace(workspaceId: string): Promise<Workspace> {
    return this.request<Workspace>(`/api/v1/workspaces/${workspaceId}`);
  }

  async updateWorkspace(workspaceId: string, payload: WorkspaceUpdatePayload): Promise<Workspace> {
    return this.request<Workspace>(`/api/v1/workspaces/${workspaceId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  }

  async deleteWorkspace(workspaceId: string): Promise<{ success: boolean; deleted_id: string }> {
    return this.request<{ success: boolean; deleted_id: string }>(`/api/v1/workspaces/${workspaceId}`, {
      method: 'DELETE',
    });
  }

  async getWorkspaceMemory(workspaceId: string): Promise<MemoryViewDto> {
    return this.request<MemoryViewDto>(`/api/v1/workspaces/${workspaceId}/memory`);
  }

  async promoteWorkspaceFact(
    workspaceId: string,
    payload: { fact: string; category?: string }
  ): Promise<{ status: string; category?: string }> {
    return this.request<{ status: string; category?: string }>(`/api/v1/workspaces/${workspaceId}/memory/facts`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async recordWorkspaceFailure(
    workspaceId: string,
    payload: { action: string; failure_reason: string; conclusion?: string }
  ): Promise<{ status: string }> {
    return this.request<{ status: string }>(`/api/v1/workspaces/${workspaceId}/memory/failures`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // ==========================================
  // Sessions API
  // ==========================================
  async listSessions(workspaceId: string): Promise<Session[]> {
    return this.request<Session[]>(`/api/v1/workspaces/${workspaceId}/sessions`);
  }

  async createSession(workspaceId: string, title?: string): Promise<Session> {
    return this.request<Session>(`/api/v1/workspaces/${workspaceId}/sessions`, {
      method: 'POST',
      body: JSON.stringify({ title: title || '新会话' }),
    });
  }

  async getSession(sessionId: string): Promise<Session> {
    return this.request<Session>(`/api/v1/sessions/${sessionId}`);
  }

  async deleteSession(sessionId: string): Promise<{ success: boolean }> {
    return this.request<{ success: boolean }>(`/api/v1/sessions/${sessionId}`, {
      method: 'DELETE',
    });
  }

  async getSessionContext(sessionId: string): Promise<SessionContextResponse> {
    return this.request<SessionContextResponse>(`/api/v1/sessions/${sessionId}/context`);
  }

  // ==========================================
  // Tasks API
  // ==========================================
  async createTask(
    sessionId: string,
    payload: {
      prompt: string;
      permission_level?: PermissionLevel;
      model?: string;
    }
  ): Promise<{ task_id: string; status: string; stream_url: string }> {
    return this.request<{ task_id: string; status: string; stream_url: string }>(
      `/api/v1/sessions/${sessionId}/tasks`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }

  async getTask(taskId: string): Promise<unknown> {
    return this.request<unknown>(`/api/v1/tasks/${taskId}`);
  }

  async approveAction(
    taskId: string,
    payload: {
      approval_id: string;
      decision: 'once' | 'always';
      feedback?: string;
    }
  ): Promise<{ success: boolean; task_status: string }> {
    return this.request<{ success: boolean; task_status: string }>(`/api/v1/tasks/${taskId}/approve`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async rejectAction(
    taskId: string,
    payload: {
      approval_id: string;
      reason: string;
    }
  ): Promise<{ success: boolean; task_status: string }> {
    return this.request<{ success: boolean; task_status: string }>(`/api/v1/tasks/${taskId}/reject`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async cancelTask(taskId: string): Promise<{ success: boolean; task_status: string }> {
    return this.request<{ success: boolean; task_status: string }>(`/api/v1/tasks/${taskId}/cancel`, {
      method: 'POST',
    });
  }

  // ==========================================
  // Files API
  // ==========================================
  async getFileTree(workspaceId: string, maxDepth: number = 5): Promise<FileNode> {
    return this.request<FileNode>(`/api/v1/workspaces/${workspaceId}/files/tree?max_depth=${maxDepth}`);
  }

  async getFileContent(workspaceId: string, relativePath: string): Promise<{ path: string; content: string; language: string }> {
    const encoded = encodeURIComponent(relativePath);
    return this.request<{ path: string; content: string; language: string }>(
      `/api/v1/workspaces/${workspaceId}/files/content?path=${encoded}`
    );
  }

  async saveFileContent(
    workspaceId: string,
    relativePath: string,
    content: string
  ): Promise<{ path: string; status: string; size: number }> {
    return this.request<{ path: string; status: string; size: number }>(
      `/api/v1/workspaces/${workspaceId}/files/content`,
      {
        method: 'PUT',
        body: JSON.stringify({ path: relativePath, content }),
      }
    );
  }

  // ==========================================
  // RAG Gateway API
  // ==========================================
  async getRagHealth(): Promise<RagHealth> {
    return this.request<RagHealth>('/api/v1/rag/health');
  }

  async triggerRagIngest(payload: {
    workspace_id?: string;
    incremental?: boolean;
    file_extensions?: string[];
  }): Promise<{ task_id: string; status: string; total_files: number; total_chunks: number }> {
    return this.request<{ task_id: string; status: string; total_files: number; total_chunks: number }>(
      '/api/v1/rag/ingest',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }

  async queryRagRetrieve(payload: {
    query: string;
    top_k?: number;
    dense_top_k?: number;
    sparse_top_k?: number;
  }): Promise<RagRetrieveResult> {
    return this.request<RagRetrieveResult>('/api/v1/rag/retrieve', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }
}

export const api = new ApiClient();
