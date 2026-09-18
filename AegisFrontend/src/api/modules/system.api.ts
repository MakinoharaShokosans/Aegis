/**
 * Aegis System Health, Introspection & Settings API Module
 */

import { httpClient } from '../client';
import type {
  HealthResponse,
  SystemIntrospection,
  ToolMetadata,
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
  getTools(): Promise<{ tools: ToolMetadata[] }> {
    return httpClient.get<{ tools: ToolMetadata[] }>('/api/v1/introspection/tools');
  },

  /**
   * List available skills
   */
  getSkills(): Promise<{ skills: Array<{ name: string; description: string }> }> {
    return httpClient.get<{ skills: Array<{ name: string; description: string }> }>('/api/v1/introspection/skills');
  },

  /**
   * List MCP servers and their statuses
   */
  getMcps(): Promise<{ mcps: Array<{ name: string; status: string; tools_count: number }> }> {
    return httpClient.get<{ mcps: Array<{ name: string; status: string; tools_count: number }> }>('/api/v1/introspection/mcps');
  },

  /**
   * Masked system configuration
   */
  getConfig(): Promise<{ config: Record<string, unknown> }> {
    return httpClient.get<{ config: Record<string, unknown> }>('/api/v1/introspection/config');
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
    return httpClient.get('/api/v1/introspection/models');
  },
};
