/**
 * Core type definitions for AegisAgent & Workspace Frontend Architecture v4.0
 */

// ==========================================
// 1. Workspace & Memory Types
// ==========================================

export type MemoryCategory =
  | 'user_profile'
  | 'confirmed_architecture'
  | 'project_conventions'
  | 'global_failed_attempts';

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

export interface ContextLayersBreakdown {
  system_tokens: number;
  workspace_memory_tokens: number;
  session_memory_tokens: number;
  active_turns_tokens: number;
  total_context_tokens: number;
}

export interface ContextBudget {
  session_token_limit: number; // 32,000
  active_tokens: number;
  total_context_tokens: number;
  water_level_pct: number;
  high_watermark: number; // 0.8
  compaction_ratio: number; // 0.4
  max_task_budget_tokens: number; // 200,000
}

export interface SessionContextResponse {
  workspace?: {
    workspace_id: string;
    name: string;
    root_path: string;
  };
  workspace_memory?: {
    user_profile: string[];
    confirmed_architecture: string[];
    project_conventions: string[];
    global_failed_attempts: any[];
  };
  session_memory?: {
    compacted_until_turn_id: number;
    summary: string;
    confirmed_facts: string[];
    failed_attempts: any[];
    last_action_target: Record<string, string[]>;
  };
  active_turns: SessionTurn[];
  budget: ContextBudget;
  layers_breakdown?: ContextLayersBreakdown;
  session_id?: string;
  system_prompt?: string;
  workspace_memories?: WorkspaceMemory[];
  total_tokens?: number;
  water_level_pct?: number;
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

export type PermissionLevel = 'read_only' | 'workspace_write' | 'full_permissions';

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
  decision?: string;
  tool?: string;
  toolArgs?: Record<string, unknown> | string;
  toolResult?: string;
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
  totalTokens: number; // 本任务思考与工具物理累计消耗 (Cumulative Physical Execution Tokens, 对标 200k 预算)
  contextTokens?: number; // 当前会话活跃上下文窗口占用 (Active Context Window Tokens, 对标 32k 窗口)
  maxContextTokens?: number; // 会话上下文上限 (32,000)
  maxBudgetTokens?: number; // 任务物理预算上限 (200,000)
  cacheHitRate: number; // e.g. 0.998 for 99.8%
  waterLevelPct: number; // 上下文水位百分比 (contextTokens / maxContextTokens * 100)
  maxWaterLevelPct: number; // e.g. 80 for 80% (高水位压缩触发线)
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

export interface DirectoryEntry {
  name: string;
  path: string;
  is_directory: boolean;
  has_subdirectories?: boolean;
}

export interface QuickLocation {
  label: string;
  path: string;
}

export interface DirectoryBrowseResponse {
  current_path: string;
  parent_path?: string | null;
  is_root: boolean;
  directories: DirectoryEntry[];
  quick_locations: QuickLocation[];
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
  status: 'ok' | 'healthy' | 'degraded' | 'unhealthy' | string;
  version: string;
  service?: string;
  qdrant?: {
    mode?: string;
    collection_ready?: boolean;
    point_count?: number;
    vector_size?: number;
  };
  qdrant_connected?: boolean;
  dense_model?: string;
  sparse_model?: string;
  embedding_model_loaded?: boolean;
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

// ==========================================
// 7. API DTOs & Payloads
// ==========================================

export interface MemoryViewDto {
  scope: string;
  updated_at?: number;
  user_profile?: string[];
  project_conventions: string[];
  confirmed_architecture: string[];
  failed_attempts: Array<{ action: string; failure_reason: string; conclusion?: string }>;
}

export interface PromoteFactPayload {
  fact: string;
  category?: string;
}

export interface RecordFailurePayload {
  action: string;
  failure_reason: string;
  conclusion?: string;
}

export interface TaskCreatePayload {
  task_goal?: string;
  prompt?: string;
  permission_level?: PermissionLevel;
  parent_task_id?: string;
  model?: string;
}

export interface TaskCreateResponse {
  task_id: string;
  session_id?: string;
  workspace_id?: string;
  task_goal?: string;
  status: string;
  stream_url?: string;
}


export interface HitlApprovalPayload {
  approval_id: string;
  decision: 'once' | 'always';
  feedback?: string;
}

export interface HitlRejectPayload {
  approval_id: string;
  reason: string;
}

export interface FileContentResponse {
  path: string;
  content: string;
  language: string;
}

export interface FileSaveResponse {
  path: string;
  status: string;
  size: number;
}

export interface RagIngestPayload {
  workspace_id?: string;
  incremental?: boolean;
  file_extensions?: string[];
}

export interface RagIngestResponse {
  task_id: string;
  status: string;
  total_files: number;
  total_chunks: number;
}

export interface RagRetrievePayload {
  query: string;
  top_k?: number;
  dense_top_k?: number;
  sparse_top_k?: number;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  uptime_sec?: number;
  active_tasks?: number;
}

export interface ToolMetadata {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  is_dangerous: boolean;
  permission_level: PermissionLevel;
}

export interface SystemIntrospection {
  service: string;
  version: string;
  tools: ToolMetadata[];
  skills: Array<{ name: string; description: string }>;
  mcps: Array<{ name: string; status: string; tools_count: number }>;
  config: Record<string, unknown>;
}

export interface ArtifactHandleResponse {
  handle_id: string;
  task_id: string;
  file_path: string;
  content: string;
  size_bytes: number;
  token_count: number;
  created_at: string;
}

export interface McpServerInfo {
  name: string;
  enabled: boolean;
  transport: 'stdio' | 'sse' | string;
  connected: boolean;
  tool_count: number;
  error?: string | null;
  rejected_tools?: Array<{ name: string; reasons: string[] }>;
}

