import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  workspaceApi,
  sessionApi,
  taskApi,
  fileApi,
  ragApi,
  systemApi,
} from '../index';

describe('Domain API Modules', () => {
  let mockFetch: any;

  beforeEach(() => {
    mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true }),
    });
    global.fetch = mockFetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('workspaceApi calls proper endpoints', async () => {
    await workspaceApi.list();
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/workspaces', expect.objectContaining({ method: 'GET' }));

    await workspaceApi.get('ws-123');
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/workspaces/ws-123', expect.objectContaining({ method: 'GET' }));

    await workspaceApi.create({ name: 'Aegis', root_path: '/path' });
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/workspaces', expect.objectContaining({ method: 'POST' }));

    await workspaceApi.delete('ws-123');
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/workspaces/ws-123', expect.objectContaining({ method: 'DELETE' }));

    await workspaceApi.getMemory('ws-123');
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/workspaces/ws-123/memory', expect.objectContaining({ method: 'GET' }));
  });

  it('sessionApi calls proper endpoints', async () => {
    await sessionApi.list('ws-123');
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/workspaces/ws-123/sessions', expect.objectContaining({ method: 'GET' }));

    await sessionApi.create('ws-123', 'Task Session');
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/workspaces/ws-123/sessions', expect.objectContaining({ method: 'POST' }));

    await sessionApi.getTurns('sess-456', 30);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/sessions/sess-456/turns?limit=30'),
      expect.objectContaining({ method: 'GET' })
    );

    await sessionApi.getContext('sess-456');
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/sessions/sess-456/context', expect.objectContaining({ method: 'GET' }));
  });

  it('taskApi calls proper endpoints for execution and HITL approvals', async () => {
    await taskApi.create('sess-1', { prompt: 'Do task' });
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/sessions/sess-1/tasks', expect.objectContaining({ method: 'POST' }));

    await taskApi.approve('task-99', { approval_id: 'appr-1', decision: 'once' });
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/tasks/task-99/approve', expect.objectContaining({ method: 'POST' }));

    await taskApi.reject('task-99', { approval_id: 'appr-1', reason: 'Forbidden command' });
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/tasks/task-99/reject', expect.objectContaining({ method: 'POST' }));

    await taskApi.cancel('task-99');
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/tasks/task-99/cancel', expect.objectContaining({ method: 'POST' }));
  });

  it('fileApi calls proper endpoints for tree, read and save (PUT)', async () => {
    await fileApi.getTree('ws-1', 4);
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/workspaces/ws-1/files/tree?max_depth=4', expect.objectContaining({ method: 'GET' }));

    await fileApi.getContent('ws-1', 'src/app.py');
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/workspaces/ws-1/files/content?path=src%2Fapp.py', expect.objectContaining({ method: 'GET' }));

    await fileApi.saveContent('ws-1', 'src/app.py', 'print("hello")');
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/workspaces/ws-1/files/content', expect.objectContaining({ method: 'PUT' }));
  });

  it('ragApi calls proper endpoints for health, ingest and retrieval', async () => {
    await ragApi.getHealth();
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/rag/health', expect.objectContaining({ method: 'GET' }));

    await ragApi.triggerIngest({ incremental: true, workspace_id: 'ws-1' });
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/rag/ingest', expect.objectContaining({ method: 'POST' }));

    await ragApi.retrieve({ query: '鉴权规范', top_k: 5 });
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/rag/retrieve', expect.objectContaining({ method: 'POST' }));
  });

  it('systemApi calls introspection endpoints', async () => {
    await systemApi.getHealth();
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/health', expect.objectContaining({ method: 'GET' }));

    await systemApi.getIntrospection();
    expect(mockFetch).toHaveBeenCalledWith('/api/v1/introspection', expect.objectContaining({ method: 'GET' }));
  });
});
