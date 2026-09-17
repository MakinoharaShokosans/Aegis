/**
 * Core type definitions for Aegis Harness Frontend
 */

export type TaskStatus = 'created' | 'running' | 'paused' | 'waiting_for_approval' | 'completed' | 'failed' | 'cancelled';

export type PermissionLevel = 'readonly' | 'workspace_write' | 'full_access';

export type ModelOption = 'deepseek-chat' | 'deepseek-reasoner' | 'deepseek-v4-flash';

export interface FileMutation {
  path: string;
  action: 'create' | 'modify' | 'delete';
  summary?: string;
  diff?: string;
}

export interface TaskMessage {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp: string;
  durationMs?: number;
  tokensUsed?: number;
  fileMutations?: FileMutation[];
}

export interface SubagentInfo {
  id: string;
  name: string;
  role: string;
  status: 'idle' | 'running' | 'completed' | 'failed';
  stepCount: number;
}

export interface TraceStep {
  id: string;
  node: 'planner' | 'executor' | 'tool_runner' | 'evaluator' | 'subagent';
  step: number;
  input?: unknown;
  output?: unknown;
  durationMs: number;
  tokenUsage?: number;
  timestamp: string;
  error?: string;
}

export interface TelemetryStats {
  rounds: number;
  steps: number;
  tokenSpeed: number; // tokens/sec
  totalTokens: number;
  cacheHitRate: number; // e.g. 0.998 for 99.8%
}

export interface Task {
  id: string;
  title: string;
  prompt: string;
  status: TaskStatus;
  permissionLevel: PermissionLevel;
  model: ModelOption;
  createdAt: string;
  updatedAt: string;
  messages: TaskMessage[];
  traceSteps: TraceStep[];
  subagents: SubagentInfo[];
  telemetry: TelemetryStats;
}

export interface OpenTab {
  id: string;
  filePath: string;
  title: string;
  language: string;
  content: string;
  isStale?: boolean;
  isModified?: boolean;
}
