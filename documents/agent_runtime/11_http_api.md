# Agent Runtime HTTP API 规范

> **责任领域**：`AegisAgent/src/agent_runtime/api/`
> **契约基线**：`02_state_definition.md`（AgentState）、`04_routing_and_control_flow.md`（run/resume）、`10_directory_structure.md`（结构）
> **文档状态**：v1。本文件是 Agent 对外 HTTP 契约的**唯一权威来源**，Web 前端按此对接。

---

## 1. 定位与安全姿态

**定位**：Agent Runtime 对外暴露的**唯一用户入口**。前端（Web UI）通过它创建工作区/会话、提交任务、订阅执行流、检视上下文与产物。不提供 CLI。

| 项 | 约定 |
|:---|:---|
| 监听地址 | `127.0.0.1:8000`（**仅本地回环**，与 AegisRAG `:8001`、bash_shell `:8002`、web_search `:8003` 并列） |
| 基础路径 | `/api/v1` |
| 协议 | HTTP/1.1 + JSON；任务进度用 **SSE**（`text/event-stream`） |
| 认证 | **v1 无认证**（单机单用户） |
| 并发 | 进程内单实例；默认同时只跑 **1 个**任务，超出返回 `429` |

> ⚠️ **安全红线**：本 API 的工具链包含受控 Bash 执行能力，等价于对本机工程目录的读写与命令执行权限。**禁止**绑定 `0.0.0.0`、禁止置于反向代理后对外暴露；在引入认证与授权之前，任何非回环暴露都属于高危配置。

**其它安全约束**：

- **CORS 默认拒绝**：仅允许 `[server].cors_allow_origins` 白名单内的来源（前端开发服务器）。
- **密钥零外泄**：任何响应**不得**返回 API Key、`api_key_env` 的解析值或 `.env` 内容。`/models` 只返回端点别名、模型名与 `base_url`。
- **产物路径防穿越**：artifact 下载只接受 `artifact_id`（由服务端维护 `artifact_id → 绝对路径` 映射），**绝不**接受客户端传入的文件路径；解析后必须校验最终路径位于 `storage/artifacts/` 之内。
- **工作区越界防护**：涉及文件的操作以工作区 `root_path` 为边界（`10` 裁决项⑦）。

---

## 2. 数据契约分层

**`AgentState` 绝不直接作为响应体**。原因：它包含 LangChain `AnyMessage` 对象、`Milestone` 等内部结构，且体积随步数增长。

| 层 | 载体 | 用途 |
|:---|:---|:---|
| 内部执行契约 | `AgentState`（`state.py`） | LangGraph 节点间流转 + Checkpoint |
| 对外传输契约 | `api/schemas.py` 的 DTO | HTTP 请求/响应，字段稳定、可演进、JSON 安全 |
| 流式事件契约 | SSE 事件（§6） | 前端增量渲染执行过程 |

**投影规则**：`AgentState.messages` 不整体外发，而是投影为 `TimelineItem`（§5.3），只保留角色、类型、精炼摘要与产物句柄。

---

## 3. 通用约定

**请求**：`Content-Type: application/json`；所有时间戳为 Unix 秒（浮点）。

**调用链透传**：请求头 `X-Trace-ID`（可选）。若缺省，服务端生成 UUID 并回写同名字段，同时注入所有下游 sidecar 调用（`06`、`tools/core/http_client.py`）。

**分页**：查询参数 `limit`（默认 50，上限 200）与 `cursor`（不透明游标）。响应统一为：

```json
{ "items": [ ... ], "next_cursor": "string|null", "total": 123 }
```

**错误模型**（所有非 2xx 响应体一致）：

```json
{
  "error": {
    "code": "WORKSPACE_NOT_FOUND",
    "message": "工作区不存在: 3f2a...",
    "details": {},
    "trace_id": "8c1d..."
  }
}
```

| HTTP | code | 触发场景 |
|:--|:---|:---|
| 400 | `VALIDATION_ERROR` | 请求体字段缺失/非法 |
| 404 | `WORKSPACE_NOT_FOUND` / `SESSION_NOT_FOUND` / `TASK_NOT_FOUND` / `ARTIFACT_NOT_FOUND` | 资源不存在 |
| 409 | `WORKSPACE_PATH_CONFLICT` | `root_path` 已被另一个 `workspace_id` 占用（唯一索引） |
| 409 | `TASK_ALREADY_RUNNING` | 对同一 `session_id` 并发提交任务 |
| 422 | `PATH_ESCAPE_DETECTED` | 目标路径越出工作区 `root_path` |
| 429 | `TASK_QUEUE_FULL` | 超出 `max_concurrent_tasks` |
| 503 | `DEPENDENCY_UNAVAILABLE` | sidecar（RAG/shell/web）不可达 |
| 500 | `INTERNAL_ERROR` | 未预期异常（记录完整堆栈到日志，不外泄细节） |

---

## 4. 端点总览

### 4.1 健康检查

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | `/api/v1/health` | 进程存活 + 元数据库/checkpoint 可用性 |
| GET | `/api/v1/health/dependencies` | 三个 sidecar 的连通性与版本（失败不返回 5xx，只在体内标记） |

### 4.2 工作区 Workspaces

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| POST | `/api/v1/workspaces` | **幂等**创建：以 `root_path` 规范化后反查，已存在则返回既有工作区（200） |
| GET | `/api/v1/workspaces` | 按 `updated_at` 倒序列表 |
| GET | `/api/v1/workspaces/{workspace_id}` | 详情 |
| PATCH | `/api/v1/workspaces/{workspace_id}` | 改 `name` / `description` |
| DELETE | `/api/v1/workspaces/{workspace_id}` | 级联删除其下全部会话、流水与记忆（`06` §2.2） |
| GET | `/api/v1/workspaces/{workspace_id}/memory` | 工作区共享记忆（架构定论 / 规范 / 全局避坑） |
| POST | `/api/v1/workspaces/{workspace_id}/memory/facts` | 事实上浮（`category` ∈ `convention` \| `architecture`） |
| POST | `/api/v1/workspaces/{workspace_id}/memory/failures` | 追加全局避坑禁区 |

`POST /workspaces` 请求体：

```json
{ "name": "Aegis Core", "root_path": "/home/user/projects/aegis", "description": "可选", "workspace_id": "可选 UUID" }
```

响应（`Workspace`）：`{ workspace_id, name, root_path, description, created_at, updated_at }`

### 4.3 会话 Sessions

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| POST | `/api/v1/workspaces/{workspace_id}/sessions` | 新建会话（`title` 可选） |
| GET | `/api/v1/workspaces/{workspace_id}/sessions` | 该工作区会话列表（`updated_at` 倒序） |
| GET | `/api/v1/sessions/{session_id}` | 会话元数据（含 `workspace_id`） |
| DELETE | `/api/v1/sessions/{session_id}` | 级联删除其流水与情境记忆 |
| GET | `/api/v1/sessions/{session_id}/turns` | 人机对话流水（分页，`id` 升序） |
| GET | `/api/v1/sessions/{session_id}/memory` | 会话已压缩情境记忆（含 `compacted_until_turn_id` 水位） |
| GET | `/api/v1/sessions/{session_id}/context` | **上下文检视器**：返回四层装配结果，供前端展示"模型此刻看到了什么" |

`GET /context` 响应（对齐 `06` §4 的装配公式）：

```json
{
  "workspace": { "workspace_id": "...", "name": "...", "root_path": "..." },
  "workspace_memory": { "confirmed_architecture": [], "project_conventions": [], "global_failed_attempts": [] },
  "session_memory": { "compacted_until_turn_id": 12, "summary": "...", "confirmed_facts": [], "failed_attempts": [], "last_action_target": {} },
  "active_turns": [ { "id": 13, "role": "user", "content": "...", "token_count": 42, "timestamp": 0.0 } ],
  "budget": { "session_token_limit": 32000, "active_tokens": 12000, "high_watermark": 0.8, "compaction_ratio": 0.4 }
}
```

### 4.4 任务 Tasks

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| POST | `/api/v1/sessions/{session_id}/tasks` | 提交任务，立即返回 `202`，后台执行 |
| GET | `/api/v1/tasks/{task_id}` | 任务状态快照（DTO，非 AgentState） |
| GET | `/api/v1/tasks/{task_id}/stream` | **SSE** 实时事件流（§6） |
| POST | `/api/v1/tasks/{task_id}/resume` | 从最近 Checkpoint 续跑（`04` §4.4） |
| POST | `/api/v1/tasks/{task_id}/cancel` | 请求终止（置位 `should_terminate`，节点边界生效） |
| GET | `/api/v1/tasks/{task_id}/timeline` | 执行时间线（分页，`TimelineItem`） |
| GET | `/api/v1/tasks/{task_id}/trace` | 全量因果轨迹下载（`application/x-ndjson`，对应 `storage/traces/{task_id}.jsonl`） |
| GET | `/api/v1/tasks/{task_id}/artifacts` | 产物句柄列表 |
| GET | `/api/v1/tasks/{task_id}/artifacts/{artifact_id}` | 产物原文（`text/plain; charset=utf-8`） |

`POST /tasks` 请求体与响应：

```json
// 请求
{ "task_goal": "定位并修复 connection.c 的内存泄漏", "parent_task_id": null }

// 202 响应
{ "task_id": "9b1e...", "status": "queued", "stream_url": "/api/v1/tasks/9b1e.../stream" }
```

**提交语义**：`POST /tasks` 只登记并在事件循环中调度（`asyncio.create_task`），**不阻塞**等待完成。任务完成后由 `MemoryManager.record_turn_and_maybe_compact()` 回写会话流水并驱动水位压缩（`06` §5）。

### 4.5 自省 Introspection（供前端渲染能力清单）

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | `/api/v1/skills` | 已发现的专家技能清单（`name` / `description` / `triggers` / `required_tools` / 来源层级） |
| GET | `/api/v1/tools` | 已注册工具及 JSON Schema |
| GET | `/api/v1/mcp/servers` | MCP 服务器列表、连接状态与各自暴露的工具 |
| GET | `/api/v1/models` | 双模型分层配置（端点别名、模型名、`base_url`）——**不含任何密钥** |

---

## 5. 核心 DTO

### 5.1 `TaskStatus`

```json
{
  "task_id": "9b1e...",
  "session_id": "4c7a...",
  "workspace_id": "ws_...",
  "task_goal": "定位并修复 connection.c 的内存泄漏",
  "status": "running",
  "milestones": [ { "id": 1, "title": "复现崩溃", "description": "...", "status": "completed" } ],
  "current_milestone_idx": 1,
  "step_count": 7,
  "total_tokens": 41820,
  "consecutive_errors": 0,
  "fingerprint_loop": false,
  "should_terminate": false,
  "termination_reason": "",
  "created_at": 0.0,
  "started_at": 0.0,
  "finished_at": null,
  "artifact_count": 2
}
```

`status` 取值与迁移：

```text
queued ──► running ──┬──► succeeded    (evaluator 判定里程碑全部达成)
                     ├──► terminated   (物理预算熔断：步数/Token/挂钟时间)
                     ├──► failed       (LLM 全链路不可用等不可恢复异常)
                     └──► cancelled    (客户端主动取消)

terminated / failed ──► running   (POST /resume)
```

### 5.2 `TimelineItem`

```json
{
  "seq": 12,
  "type": "tool_call",
  "role": "assistant",
  "summary": "bash: gcc -fsanitize=address -g connection.c",
  "artifact_id": null,
  "timestamp": 0.0
}
```

`type` ∈ `plan` | `thought` | `tool_call` | `tool_result` | `system_notice` | `milestone` | `guard_warning`。

**约束**：单条 `summary` 上限 2000 字符；被 Pruner 截断的完整内容只以 `artifact_id` 引用（`05` §4），前端按需调用 artifact 端点拉取。

### 5.3 `ArtifactDescriptor`

```json
{ "artifact_id": "obs_step_7_bash", "task_id": "9b1e...", "size_bytes": 51234, "tokens": 1820, "created_at": 0.0, "preview": "前 200 字符…" }
```

---

## 6. SSE 事件契约

`GET /api/v1/tasks/{task_id}/stream`

**帧格式**：标准 SSE，`event` 为事件类型，`id` 为单调递增序号，`data` 为单行 JSON。

```text
event: tool.result
id: 42
data: {"task_id":"9b1e...","seq":42,"ts":0.0,"tool_call_id":"c1","tool_name":"bash","ok":false,"exit_code":1,"summary":"...","artifact_id":"obs_step_7_bash"}

```

**事件类型**：

| event | 触发时机 | 关键字段 |
|:---|:---|:---|
| `task.started` | 图开始执行 | `task_id`, `task_goal` |
| `node.started` | 节点进入 | `node` ∈ `planner`\|`budget_guard`\|`executor`\|`evaluator` |
| `node.finished` | 节点返回 | `node`, `step_count`, `total_tokens` |
| `plan` | planner 产出决策指令 | `summary` |
| `tool.call` | 工具派发（并发时逐个推送） | `tool_call_id`, `tool_name`, `args_digest` |
| `tool.result` | 工具返回 | `tool_call_id`, `ok`, `exit_code`, `summary`, `artifact_id` |
| `milestone.updated` | 里程碑状态变化 | `milestone_id`, `status` |
| `guard.warning` | 90% 预算告警 / 指纹死循环拦截 | `kind`, `detail` |
| `task.finished` | 正常结束 | `status`, `termination_reason`, `step_count`, `total_tokens` |
| `task.error` | 不可恢复异常 | `code`, `message` |
| `heartbeat` | 每 `sse_heartbeat_sec`（默认 15s） | 无业务字段 |

**断线重连**：客户端重连时携带 `Last-Event-ID`，服务端从进程内**环形缓冲区**（默认 1000 条，`[server].sse_buffer_events`）重放其后事件。若游标已滑出缓冲区，服务端立即推送 `task.error`（`code = STREAM_GAP`），客户端须改用 `GET /tasks/{task_id}` 与 `/timeline` 做全量重新同步。

**终态保证**：每个流**必定**以 `task.finished` 或 `task.error` 收尾，随后服务端关闭连接。

---

## 7. 运行时装配与并发模型

**lifespan 启动顺序**：

1. 加载 `AegisConfig`（`config.py`）
2. 初始化 `observability/logging.py`（Loguru JSONL）
3. `SqliteMemoryStore.initialize()`（建表 + WAL）
4. 装配 `PhysicalBudgetGuard` 工厂与 `TaskRegistry`
5. `MCPManager` 仅加载静态配置与工具元数据缓存，**不拉起子进程**（懒加载，`09` §3.3）

**并发模型**：

- 单进程单事件循环。`TaskRegistry` 维护 `task_id → TaskHandle`（含 `asyncio.Task`、事件环形缓冲、订阅者集合）。
- `[server].max_concurrent_tasks`（默认 1）限制同时在跑的任务数；超限 `429 TASK_QUEUE_FULL`。这与会话级水位压缩、Bash 全局内存池（`技术选型/bash_shell.md`）共同构成串行化的资源治理。
- **已知语义边界**：事件环形缓冲与订阅者**仅在内存**，进程重启后丢失；但 Checkpoint（SQLite）保证任务可 `resume`。前端需能容忍"流中断 → 重新拉取快照"。

---

## 8. 配置项（`config.toml`，已落地）

> `[server]` 段已写入 `AegisAgent/config/config.toml`，并由 `config.py::ServerConfig` 强类型加载。
> 其中 `host` 设有 **fail-closed 护栏**：非回环地址在配置加载阶段即抛错，防止误将本服务对外暴露。

```toml
[server]
host = "127.0.0.1"                                  # 严禁改为 0.0.0.0
port = 8000
max_concurrent_tasks = 1
cors_allow_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
sse_heartbeat_sec = 15
sse_buffer_events = 1000
artifact_preview_chars = 200
```

---

## 9. API 层需要 `MemoryManager` 补齐的能力

现有 `MemoryManager`（已实现）已覆盖大部分需求，以下为 API 层新增诉求，需在实现阶段补齐：

| 能力 | 现状 |
|:---|:---|
| `list_workspaces` / `get_workspace` / `get_workspace_by_path` / `create_workspace` / `delete_workspace` | ✅ 已有 |
| `update_workspace(name, description)` | ⚠️ `SqliteMemoryStore` 已有，`MemoryManager` 未暴露 |
| `create_session` / `list_sessions` / `delete_session` | ✅ 已有 |
| `get_session(session_id)`（按 ID 单查，且需返回其 `workspace_id`） | ⚠️ 需新增（现仅有 `create_or_get_session` 副作用式获取） |
| `get_workspace_memory` / `promote_fact_to_workspace` / `record_global_failure` | ✅ 已有 |
| 分页查询 `turns`（`cursor`/`limit`） | ⚠️ 需新增（现有 `get_recent_turns` 不支持游标） |
| 上下文装配预览（`/context`） | ⚠️ 需新增，可复用 `load_session_context` + 配置阈值 |

---

## 10. v1 明确不做

- 多用户、认证、RBAC、API Key 管理
- WebSocket（统一用 SSE + 轮询补拉）
- RAG 文档入库端点（归 `AegisRAG`）
- 评测触发端点（归 `src/evaluation/`，离线命令行驱动）
- 任务跨进程调度（单机单实例；多实例需先解决 SQLite 并发与 Checkpoint 归属）
