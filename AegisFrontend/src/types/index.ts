/**
 * Core type definitions for AegisAgent & Workspace Frontend Architecture v4.0
 */

// ==========================================
// 1. Workspace & Memory Types
// ==========================================

export type MemoryCategory = 'confirmed_architecture' | 'project_conventions' | 'global_failed_attempts';

export interface WorkspaceMemory {
  id: string;
  workspace_id: string;
  category: MemoryCategory;
  title: string;
  content: string;
  pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  root_path: string;
  description?: string;
  created_at: string;
  updated_at: string;
  session_count?: number;
  memory_count?: number;
}

export interface WorkspaceCreatePayload {
  name: string;
  root_path: string;
  description?: string;
}

export interface WorkspaceUpdatePayload {
  name?: string;
  description?: string;
}

// ==========================================
// 2. Session & Turn Types
// ==========================================

export interface SessionTurn {
  id: string;
  session_id: string;
  turn_index: number;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  token_count?: number;
  created_at: string;
}

export interface SessionMemory {
  id: string;
  session_id: string;
  summary: string;
  fact_list: string[];
  last_compressed_turn: number;
  created_at: string;
}

export interface Session {
  id: string;
  workspace_id: string;
  title: string;
  status: 'active' | 'archived';
  created_at: string;
  updated_at: string;
  turns?: SessionTurn[];
}

export interface SessionContextResponse {
  session_id: string;
  system_prompt: string;
  workspace_memories: WorkspaceMemory[];
  session_memory?: SessionMemory;
  active_turns: SessionTurn[];
  total_tokens: number;
  water_level_pct: number;
}

// ==========================================
// 3. Task, Message & HITL Types
// ==========================================

export type TaskStatus =
  | 'created'
  | 'running'
  | 'paused'
  | 'waiting_for_approval'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type PermissionLevel = 'readonly' | 'workspace_write' | 'full_access';

export type ModelTier = 'reasoning' | 'fast';

export interface FileMutation {
  path: string;
  action: 'create' | 'modify' | 'delete';
  summary?: string;
  diff?: string;
}

export interface HITLApprovalRequest {
  approval_id: string;
  task_id: string;
  action_type: 'network_egress' | 'privileged_exec' | 'workspace_out_of_bounds';
  command: string;
  reason: string;
  cwd?: string;
  created_at: string;
}

export interface MilestoneItem {
  id: string;
  title: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  round?: number;
}

export interface SubagentInfo {
  id: string;
  name: string;
  role: string;
  status: 'idle' | 'running' | 'completed' | 'failed';
  stepCount: number;
  lastQuery?: string;
  summary?: string;
}

export interface TaskMessage {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp: string;
  durationMs?: number;
  tokensUsed?: number;
  milestones?: MilestoneItem[];
  fileMutations?: FileMutation[];
  subagentReports?: {
    type: 'doc_search' | 'research';
    title: string;
    queries?: string[];
    citations?: string[];
    summary: string;
    isExternal?: boolean;
  }[];
  observationPrunerHandles?: {
    id: string;
    path: string;
    sizeBytes: number;
    tokens: number;
  }[];
  approvalRequest?: HITLApprovalRequest;
}

export interface TraceStep {
  id: string;
  node: 'planner' | 'executor' | 'tool_runner' | 'evaluator' | 'subagent' | 'budget_guard';
  step: number;
  inputSummary?: string;
  outputSummary?: string;
  durationMs: number;
  tokenUsage?: number;
  timestamp: string;
  error?: string;
  eventType?: string;
}

export interface TelemetryStats {
  rounds: number;
  steps: number;
  tokenSpeed: number; // tokens/sec
  totalTokens: number;
  cacheHitRate: number; // e.g. 0.998 for 99.8%
  waterLevelPct: number; // e.g. 32 for 32%
  maxWaterLevelPct: number; // e.g. 80 for 80%
}

export interface Task {
  id: string;
  session_id?: string;
  title: string;
  prompt: string;
  status: TaskStatus;
  permissionLevel: PermissionLevel;
  model: string;
  createdAt: string;
  updatedAt: string;
  messages: TaskMessage[];
  traceSteps: TraceStep[];
  subagents: SubagentInfo[];
  telemetry: TelemetryStats;
  pendingApproval?: HITLApprovalRequest;
}

// ==========================================
// 4. File Tree & Canvas Types
// ==========================================

export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  modified_at?: number;
  language?: string;
  children?: FileNode[];
}

export interface OpenTab {
  id: string;
  filePath: string;
  title: string;
  language: string;
  content: string;
  isStale?: boolean;
  isModified?: boolean;
  readOnly?: boolean;
}

// ==========================================
// 5. RAG & Knowledge Base Types
// ==========================================

export interface RagHealth {
  status: 'healthy' | 'degraded' | 'unhealthy';
  version: string;
  service: string;
  qdrant_connected: boolean;
  dense_model: string;
  sparse_model: string;
}

export interface RagChunk {
  id: string;
  file_path: string;
  start_line: number;
  end_line: number;
  ast_scope?: string;
  content: string;
  token_count: number;
}

export interface RagHit {
  score: number;
  file_path: string;
  start_line: number;
  end_line: number;
  content: string;
  dense_rank?: number;
  sparse_rank?: number;
  rrf_score?: number;
}

export interface RagRetrieveResult {
  query: string;
  hits: RagHit[];
  elapsed_ms: number;
}

// ==========================================
// 6. Settings & Security Gate Types
// ==========================================

export interface SecurityGatesConfig {
  allowedHosts: string[];
  corsAllowOrigins: string[];
  apiToken: string;
  tokenPath: string;
}

export interface DualTierModelConfig {
  reasoningModel: {
    alias: string;
    model: string;
    baseUrl: string;
    temperature: number;
  };
  fastModel: {
    alias: string;
    model: string;
    baseUrl: string;
    temperature: number;
  };
}

export interface SidecarConfig {
  ragUrl: string;
  bashUrl: string;
  webUrl: string;
  bashMemoryPoolMb: number;
  bashTimeoutSec: number;
}
