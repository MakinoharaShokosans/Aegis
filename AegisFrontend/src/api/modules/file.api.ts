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

  /**
   * Browse host directories for workspace creation / connection
   */
  browseDirectories(path?: string): Promise<{
    current_path: string;
    parent_path?: string | null;
    is_root: boolean;
    directories: Array<{
      name: string;
      path: string;
      is_directory: boolean;
      has_subdirectories?: boolean;
    }>;
    quick_locations: Array<{
      label: string;
      path: string;
    }>;
  }> {
    const params = path ? { path } : undefined;
    return httpClient.get(`/api/v1/system/fs/directories`, params);
  },

  /**
   * Invoke native OS file manager directory chooser
   */
  pickNativeDirectory(initialPath?: string): Promise<{
    success: boolean;
    path: string | null;
    name: string | null;
    cancelled: boolean;
  }> {
    const params = initialPath ? { path: initialPath } : undefined;
    return httpClient.post(`/api/v1/system/fs/pick-directory`, undefined, { params });
  },
};
