/**
 * Aegis Workspace Virtual File System API Module
 */

import { httpClient } from '../client';
import type { FileNode, FileContentResponse, FileSaveResponse } from '@/types';

function normalizeFileItem(item: any): FileNode {
  const isDir = item.type === 'directory' || item.is_dir === true;
  return {
    name: item.name || '',
    path: item.path || '',
    type: isDir ? 'directory' : 'file',
    size: item.size || item.size_bytes,
    modified_at:
      typeof item.updated_at === 'number'
        ? item.updated_at
        : typeof item.modified_at === 'number'
        ? item.modified_at
        : undefined,
    language: item.language,
    children: item.children ? item.children.map(normalizeFileItem) : undefined,
  };
}

export const fileApi = {
  /**
   * Recursively retrieve workspace file tree
   */
  async getTree(workspaceId: string, maxDepth: number = 8): Promise<FileNode> {
    const raw = await httpClient.get<any>(
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/files/tree`,
      { max_depth: maxDepth }
    );
    const items = raw.items || (Array.isArray(raw) ? raw : [raw]);
    return {
      name: raw.root_path ? raw.root_path.split('/').filter(Boolean).pop() || 'workspace' : 'workspace',
      path: '',
      type: 'directory',
      children: items.map(normalizeFileItem),
    };
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
