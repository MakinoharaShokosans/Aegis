/**
 * Aegis System Health, Introspection & Settings API Module
 */

import { httpClient } from '../client';
import type {
  HealthResponse,
  SystemIntrospection,
  ToolMetadata,
  McpServerInfo,
} from '@/types';

export const systemApi = {
  /**
   * Health probe and active task load monitor
   */
  getHealth(): Promise<HealthResponse> {
    return httpClient.get<HealthResponse>('/api/v1/health');
  },

  /**
   * Complete runtime introspection (tools, skills, mcps, config)
   */
  getIntrospection(): Promise<SystemIntrospection> {
    return httpClient.get<SystemIntrospection>('/api/v1/introspection');
  },

  /**
   * List all registered tools and their security levels
   */
  getTools(): Promise<ToolMetadata[]> {
    return httpClient.get<ToolMetadata[]>('/api/v1/tools');
  },

  /**
   * List available skills
   */
  getSkills(): Promise<Array<{ name: string; description: string; triggers?: string[]; trust?: string; source?: string }>> {
    return httpClient.get<Array<{ name: string; description: string; triggers?: string[]; trust?: string; source?: string }>>('/api/v1/skills');
  },

  /**
   * List MCP servers and their statuses
   */
  getMcps(): Promise<McpServerInfo[]> {
    return httpClient.get<McpServerInfo[]>('/api/v1/mcp/servers');
  },

  /**
   * Masked system configuration
   */
  getConfig(): Promise<{ config: Record<string, unknown> }> {
    return httpClient.get<{ config: Record<string, unknown> }>('/api/v1/config');
  },

  /**
   * Introspect Dual-Tier reasoning and fast model endpoints topology
   */
  getModels(): Promise<{
    reasoning?: {
      temperature: number;
      endpoints: Array<{
        name: string;
        model: string;
        base_url: string;
        timeout_sec: number;
        available: boolean;
      }>;
    };
    fast?: {
      temperature: number;
      endpoints: Array<{
        name: string;
        model: string;
        base_url: string;
        timeout_sec: number;
        available: boolean;
      }>;
    };
  }> {
    return httpClient.get('/api/v1/models');
  },
};
