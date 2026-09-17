/**
 * Aegis Unified API Layer
 * Exports HTTP Client, SSE Stream Engine, and Domain API Modules.
 */

export * from './client';
export * from './sse';
export * from './modules/workspace.api';
export * from './modules/session.api';
export * from './modules/task.api';
export * from './modules/file.api';
export * from './modules/rag.api';
export * from './modules/system.api';
export * from './modules/artifact.api';

// Backwards-compatible legacy facade (if needed)
import { httpClient } from './client';
import { workspaceApi } from './modules/workspace.api';
import { sessionApi } from './modules/session.api';
import { taskApi } from './modules/task.api';
import { fileApi } from './modules/file.api';
import { ragApi } from './modules/rag.api';
import { systemApi } from './modules/system.api';
import { artifactApi } from './modules/artifact.api';

export const api = {
  // Token methods
  setToken: (token: string) => httpClient.setToken(token),
  getToken: () => httpClient.getToken(),

  // Workspaces
  listWorkspaces: workspaceApi.list,
  createWorkspace: workspaceApi.create,
  getWorkspace: workspaceApi.get,
  updateWorkspace: workspaceApi.update,
  deleteWorkspace: workspaceApi.delete,
  getWorkspaceMemory: workspaceApi.getMemory,
  promoteWorkspaceFact: workspaceApi.promoteFact,
  recordWorkspaceFailure: workspaceApi.recordFailure,

  // Sessions
  listSessions: sessionApi.list,
  createSession: sessionApi.create,
  getSession: sessionApi.get,
  deleteSession: sessionApi.delete,
  getSessionContext: sessionApi.getContext,

  // Tasks & HITL
  createTask: taskApi.create,
  getTask: taskApi.get,
  approveAction: taskApi.approve,
  rejectAction: taskApi.reject,
  cancelTask: taskApi.cancel,

  // Files
  getFileTree: fileApi.getTree,
  getFileContent: fileApi.getContent,
  saveFileContent: fileApi.saveContent,

  // RAG
  getRagHealth: ragApi.getHealth,
  triggerRagIngest: ragApi.triggerIngest,
  queryRagRetrieve: ragApi.retrieve,

  // System
  getHealth: systemApi.getHealth,
  getIntrospection: systemApi.getIntrospection,

  // Artifacts
  getArtifact: artifactApi.getArtifact,
};
