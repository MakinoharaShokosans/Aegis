/**
 * Aegis Workspace Virtual File System API Module
 */

import { httpClient } from '../client';
import type { FileNode, FileContentResponse, FileSaveResponse } from '@/types';

export const fileApi = {
  /**
   * Recursively retrieve workspace file tree
   */
  getTree(workspaceId: string, maxDepth: number = 5): Promise<FileNode> {
    return httpClient.get<FileNode>(
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/files/tree`,
      { max_depth: maxDepth }
    );
  },

  /**
   * Get content of a workspace file
   */
  getContent(workspaceId: string, relativePath: string): Promise<FileContentResponse> {
    return httpClient.get<FileContentResponse>(
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/files/content`,
      { path: relativePath }
    );
  },

  /**
   * Save / overwrite workspace file content (PUT)
   */
  saveContent(
    workspaceId: string,
    relativePath: string,
    content: string
  ): Promise<FileSaveResponse> {
    return httpClient.put<FileSaveResponse>(
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/files/content`,
      { path: relativePath, content }
    );
  },
};
