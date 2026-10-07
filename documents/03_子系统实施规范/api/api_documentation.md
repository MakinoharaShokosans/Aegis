# AegisAgent & Sidecars 统一 HTTP/SSE API 契约参考手册 (Complete API Reference)

> **文档定位**：AegisAgent 系统对外暴露的**全量 RESTful 与 SSE 接口契约权威参考手册**。
> **服务基准地址**：`http://127.0.0.1:8000`（API 统一前缀 `/api/v1`）
> **适配版本**：Aegis Core Runtime v4.0 / AegisRAG v1.0.0 / AegisFrontend v4.0

---

## 1. 架构拓扑与接入层安全姿态 (Architecture & Security)

### 1.1 微服务端口拓扑

```
                                      +---------------------------------------------+
                                      |            AegisFrontend (React 19)         |
                                      +---------------------------------------------+
                                                             |
                                         (REST + SSE with X-API-Token / Bearer)
                                                             v
+-------------------------------------------------------------------------------------------------------------------------+
| AegisAgent 主智能体网关 (:8000)                                                                                          |
|                                                                                                                         |
|  [三道接入层安全闸门] ──> [Host 闸门] ──> [Origin 闸门] ──> [Token 闸门 (secrets.compare_digest)]                        |
|                                                                                                                         |
|  [路由模块集合]                                                                                                          |
|   ├─ /workspaces          : 工作区 CRUD、级联删除与长期共享记忆                                                         |
|   ├─ /sessions            : 1:N 级联任务会话、对话流水与四层上下文装配透视                                              |
|   ├─ /tasks               : 任务异步登记、状态查询、HITL 人机协同审批与 SSE 事件流                                      |
|   ├─ /workspaces/.../files: 工作区文件树递归扫描、受限读写与防路径穿越沙箱                                              |
|   ├─ /rag (代理网关)      : 代理转发到 AegisRAG (:8001)，双路召回 + Cross-Encoder 重排                                  |
|   ├─ /artifacts           : 离线产物与长日志句柄 (ObservationPruner)                                                    |
|   ├─ /introspection       : 工具清单、Skill 技能、MCP 服务器与脱敏配置透视                                              |
|   └─ /health              : 存活健康探针与任务池负载监控                                                                |
+-------------------------------------------------------------------------------------------------------------------------+
          |                                       |                                       |
  (ServiceClient IPC)                     (ServiceClient IPC)                     (ServiceClient IPC)
          v                                       v                                       v
+-----------------------+               +-----------------------+               +-----------------------+
| AegisRAG (:8001)      |               | bash_shell (:8002)    |               | web_search (:8003)    |
| Qdrant 向量库+AST切分 |               | 独立沙箱子进程+512MB  |               | DDG+Trafilatura 隔离  |
+-----------------------+               +-----------------------+               +-----------------------+
```

### 1.2 三道接入层安全闸门 (Security Gates)

所有进入 `:8000` 的请求（除豁免的存活探针 `/health`、`/`、`/docs` 外）必须通过三道安全拦截：
1. **Host 闸门**：`Host` 主机名强制限制为 `{127.0.0.1, localhost, ::1}` ∪ `allowed_hosts`，防御 DNS 重绑定攻击；
2. **Origin 闸门**：非安全 HTTP 请求（POST/PUT/PATCH/DELETE）若携带 `Origin`，必须属于 `cors_allow_origins` 白名单，防御 CSRF；
3. **令牌闸门**：支持从以下三种载体读取令牌，采用 `secrets.compare_digest` 恒定时间比较：
   - `Authorization: Bearer <token>`（推荐）
   - `X-API-Token: <token>`
   - `?token=<token>`（专供浏览器原生 `EventSource` SSE 长连接鉴权）

---

## 2. 全局错误响应与状态码契约 (Error Handling)

所有异常统一按以下 JSON 结构返回：

```json
{
  "detail": {
    "error_code": "WORKSPACE_NOT_FOUND",
    "message": "工作区不存在: ws-123456",
    "context": { "workspace_id": "ws-123456" }
  }
}
```

| HTTP 状态码 | 错误码 (`error_code`) | 说明与处置建议 |
| :--- | :--- | :--- |
| **401** | `UNAUTHORIZED` | 缺失、无效或格式错误的接入令牌 |
| **403** | `HOST_NOT_ALLOWED` / `ORIGIN_NOT_ALLOWED` | 违反 Host 或 Origin 安全闸门白名单 |
| **404** | `WORKSPACE_NOT_FOUND` / `SESSION_NOT_FOUND` / `TASK_NOT_FOUND` / `FILE_NOT_FOUND` | 指定实体不存在 |
| **409** | `WORKSPACE_PATH_CONFLICT` | 本地物理路径已被其他工作区占用 |
| **422** | `PATH_ESCAPE_DETECTED` | 文件操作目标路径试图逃逸出工作区 `root_path` 边界 |
| **422** | `HITL_APPROVAL_REQUIRED` | 尝试执行超出当前权限基线的操作，需通过审批端点放行 |
| **429** | `RATE_LIMITED_TASK_RUNNING` | 并发任务数已达上限（默认单进程 1 个任务） |
| **500** | `INTERNAL_SERVER_ERROR` | 内部状态机崩溃或未捕获异常 |

---

## 3. 工作区管理与共享记忆 API (Workspaces API)

### 3.1 创建工作区（按 root_path 幂等）
- **路由**：`POST /api/v1/workspaces`
- **请求头**：`Content-Type: application/json`, `X-API-Token: <token>`
- **请求体 (JSON)**：
  ```json
  {
    "name": "Aegis Core Runtime",
    "root_path": "/home/user/projects/aegis",
    "description": "智能体核心调度系统与工作区管理",
    "workspace_id": "ws-optional-custom-id"
  }
  ```
- **响应 (201 Created / 200 OK)**：
  ```json
  {
    "workspace_id": "ws-1710680000-a1b2",
    "name": "Aegis Core Runtime",
    "root_path": "/home/user/projects/aegis",
    "description": "智能体核心调度系统与工作区管理",
    "created_at": 1710680000.0,
    "updated_at": 1710680000.0
  }
  ```

### 3.2 列出全部工作区
- **路由**：`GET /api/v1/workspaces`
- **响应 (200 OK)**：`WorkspaceOut[]`

### 3.3 查询单工作区
- **路由**：`GET /api/v1/workspaces/{workspace_id}`
- **响应 (200 OK)**：`WorkspaceOut`

### 3.4 更新工作区属性
- **路由**：`PATCH /api/v1/workspaces/{workspace_id}`
- **请求体 (JSON)**：
  ```json
  {
    "name": "Aegis Core (Renamed)",
    "description": "更新后的项目工程背景说明"
  }
  ```
- **响应 (200 OK)**：`WorkspaceOut`

### 3.5 级联删除工作区
- **路由**：`DELETE /api/v1/workspaces/{workspace_id}`
- **说明**：级联物理清理其名下的所有会话、历史流水、情境记忆与工作区定论（本地磁盘工程源码不删除）。
- **响应**：`204 No Content`

### 3.6 读取工作区长期共享记忆
- **路由**：`GET /api/v1/workspaces/{workspace_id}/memory`
- **响应 (200 OK)**：
  ```json
  {
    "scope": "workspace",
    "updated_at": 1710681000.0,
    "project_conventions": [
      "所有新增模块必须提供单元测试，保持 100% Green 状态",
      "规划反思使用 Reasoning 模型 (temp=0.0)，动作执行使用 Fast 模型 (temp=0.2)"
    ],
    "confirmed_architecture": [
      "接入层三道安全闸门前置拓扑：Host -> Origin -> Token",
      "Sidecar 微服务端口分配：RAG :8001 / Shell :8002 / Web :8003"
    ],
    "failed_attempts": [
      {
        "action": "在沙箱外直接执行 rm -rf",
        "failure_reason": "命中危险命令拦截正则",
        "conclusion": "必须通过工作区受限 FileOps 读写"
      }
    ]
  }
  ```

### 3.7 上浮事实到工作区共享记忆
- **路由**：`POST /api/v1/workspaces/{workspace_id}/memory/facts`
- **请求体 (JSON)**：
  ```json
  {
    "fact": "接入层三道安全闸门必须按 Host -> Origin -> Token 顺序执行",
    "category": "confirmed_architecture"
  }
  ```
- **响应 (201 Created)**：`{ "status": "ok", "category": "confirmed_architecture" }`

### 3.8 追加全局避坑黑名单
- **路由**：`POST /api/v1/workspaces/{workspace_id}/memory/failures`
- **请求体 (JSON)**：
  ```json
  {
    "action": "git push --force origin main",
    "failure_reason": "超出工作区只读基线且未获 HITL 授权",
    "conclusion": "必须由用户在前端审批卡片显式放行"
  }
  ```
- **响应 (201 Created)**：`{ "status": "ok" }`

---

## 4. 会话与四层上下文装配透视 API (Sessions API)

### 4.1 在工作区下创建会话
- **路由**：`POST /api/v1/workspaces/{workspace_id}/sessions`
- **请求体 (JSON)**：
  ```json
  {
    "title": "接入层三道安全闸门设计与落地"
  }
  ```
- **响应 (201 Created)**：
  ```json
  {
    "session_id": "sess-1710682000-xyz",
    "workspace_id": "ws-1710680000-a1b2",
    "title": "接入层三道安全闸门设计与落地",
    "created_at": 1710682000.0,
    "updated_at": 1710682000.0
  }
  ```

### 4.2 列出工作区下的全部会话
- **路由**：`GET /api/v1/workspaces/{workspace_id}/sessions`
- **响应 (200 OK)**：`SessionOut[]`

### 4.3 删除单会话
- **路由**：`DELETE /api/v1/sessions/{session_id}`
- **响应**：`204 No Content`

### 4.4 分页读取会话历史对话流水
- **路由**：`GET /api/v1/sessions/{session_id}/turns?limit=50&before_id=100`
- **响应 (200 OK)**：
  ```json
  [
    {
      "id": 1,
      "role": "user",
      "content": "请在 AegisAgent 中设计并实现接入层安全闸门",
      "token_count": 32,
      "timestamp": 1710682100.0
    },
    {
      "id": 2,
      "role": "assistant",
      "content": "### 阶段目标与里程碑...",
      "token_count": 480,
      "timestamp": 1710682105.0
    }
  ]
  ```

### 4.5 四层装配上下文透视器 (Context Inspector)
- **路由**：`GET /api/v1/sessions/{session_id}/context`
- **说明**：实时透视送入大模型的第一视界快照（系统提示词 + 工作区共享记忆 + 会话压缩摘要 + 活跃滑窗对话轮次与 Token 水位）。
- **响应 (200 OK)**：
  ```json
  {
    "workspace": {
      "workspace_id": "ws-1710680000-a1b2",
      "name": "Aegis Core Runtime",
      "root_path": "/home/user/projects/aegis"
    },
    "workspace_memory": {
      "confirmed_architecture": ["..."],
      "project_conventions": ["..."],
      "global_failed_attempts": ["..."]
    },
    "session_memory": {
      "summary": "阶段 1: 契约确认；阶段 2: 中间件落地",
      "confirmed_facts": ["..."],
      "compacted_until_turn_id": 8
    },
    "active_turns": [ ... ],
    "token_budget": {
      "active_tokens": 14200,
      "max_context_tokens": 80000,
      "water_level_pct": 17.75,
      "high_watermark_pct": 80.0,
      "low_watermark_pct": 40.0
    }
  }
  ```

---

## 5. 任务异步编排、SSE 流与 HITL 审批 API (Tasks API)

### 5.1 提交任务（只登记不阻塞）
- **路由**：`POST /api/v1/sessions/{session_id}/tasks`
- **请求体 (JSON)**：
  ```json
  {
    "prompt": "实现接入层三道安全闸门并编写单测",
    "permission_level": "workspace_write",
    "model": "deepseek-reasoner",
    "context_files": ["documents/agent_runtime/11_http_api.md"]
  }
  ```
- **响应 (202 Accepted)**：
  ```json
  {
    "task_id": "task-1710683000-9988",
    "session_id": "sess-1710682000-xyz",
    "status": "queued",
    "stream_url": "/api/v1/tasks/task-1710683000-9988/stream",
    "created_at": 1710683000.0,
    "updated_at": 1710683000.0
  }
  ```

### 5.2 查询任务状态快照
- **路由**：`GET /api/v1/tasks/{task_id}`
- **响应 (200 OK)**：`TaskOut`（含当前 status、耗时、Token 水位、错误原因等）

### 5.3 订阅任务 SSE 执行事件流
- **路由**：`GET /api/v1/tasks/{task_id}/stream?token=<token>`
- **请求头**：`Accept: text/event-stream`
- **支持事件类型清单**：
  - `event: task.started`：任务开始执行；
  - `event: node.started`：节点状态机跃迁（`planner`, `budget_guard`, `executor`, `tool_runner`, `evaluator`）；
  - `event: node.finished`：节点执行完毕；
  - `event: plan`：Planner 输出阶段规划与里程碑清单；
  - `event: milestone.updated`：里程碑状态动态勾选变更；
  - `event: subagent.started` / `subagent.step` / `subagent.finished`：专用子智能体（文档检索/外部研究）中间汇报；
  - `event: tool.call` / `tool.result`：原子工具调用与回传结果；
  - `event: task.waiting_for_approval`：**HITL 权限越级挂起**（携带 `approval_id`、命令与拦截理由）；
  - `event: task.approved` / `task.rejected`：审批决议广播；
  - `event: task.finished`：任务圆满交付；
  - `event: task.error`：任务异常中止。

### 5.4 人机协同 (HITL) 权限审批通过
- **路由**：`POST /api/v1/tasks/{task_id}/approve`
- **请求体 (JSON)**：
  ```json
  {
    "approval_id": "appr-1710683500-abc",
    "decision": "once",
    "feedback": "同意单次执行 git push"
  }
  ```
- **响应 (200 OK)**：`{ "success": true, "task_status": "running" }`

### 5.5 人机协同 (HITL) 权限审批拒绝并指示改道
- **路由**：`POST /api/v1/tasks/{task_id}/reject`
- **请求体 (JSON)**：
  ```json
  {
    "approval_id": "appr-1710683500-abc",
    "reason": "禁止向远程仓库直接 push，改为在本地生成 patch 文件"
  }
  ```
- **响应 (200 OK)**：`{ "success": true, "task_status": "running" }`

### 5.6 任务取消、暂停与恢复
- **取消任务**：`POST /api/v1/tasks/{task_id}/cancel`
- **暂停任务**：`POST /api/v1/tasks/{task_id}/pause`
- **续跑断点**：`POST /api/v1/tasks/{task_id}/resume`

---

## 6. 工作区文件树与受限读写 API (Files API)

### 6.1 递归扫描工作区文件树
- **路由**：`GET /api/v1/workspaces/{workspace_id}/files/tree?max_depth=5`
- **响应 (200 OK)**：
  ```json
  {
    "name": "aegis",
    "path": "",
    "type": "directory",
    "children": [
      {
        "name": "documents",
        "path": "documents",
        "type": "directory",
        "children": [
          {
            "name": "11_http_api.md",
            "path": "documents/agent_runtime/11_http_api.md",
            "type": "file",
            "size": 24580,
            "modified_at": 1710680000.0,
            "language": "markdown"
          }
        ]
      }
    ]
  }
  ```

### 6.2 安全读取工作区文本文件
- **路由**：`GET /api/v1/workspaces/{workspace_id}/files/content?path=documents%2F11_http_api.md`
- **响应 (200 OK)**：
  ```json
  {
    "path": "documents/agent_runtime/11_http_api.md",
    "content": "# Agent Runtime HTTP API 规范\n...",
    "language": "markdown",
    "size": 24580
  }
  ```

### 6.3 保存/修改工作区文本文件 (带防路径穿越)
- **路由**：`PUT /api/v1/workspaces/{workspace_id}/files/content`
- **请求体 (JSON)**：
  ```json
  {
    "path": "AegisAgent/src/agent_runtime/api/auth.py",
    "content": "class SecurityGateMiddleware(BaseHTTPMiddleware):..."
  }
  ```
- **响应 (200 OK)**：
  ```json
  {
    "path": "AegisAgent/src/agent_runtime/api/auth.py",
    "status": "saved",
    "size": 3420
  }
  ```

---

## 7. RAG 知识库统一网关代理 API (RAG Gateway API)

### 7.1 检查 RAG 微服务存活与向量拓扑
- **路由**：`GET /api/v1/rag/health`
- **响应 (200 OK)**：
  ```json
  {
    "status": "healthy",
    "version": "1.0.0",
    "service": "AegisRAG Microservice",
    "qdrant_connected": true,
    "dense_model": "BAAI/bge-small-en-v1.5",
    "sparse_model": "BM25 / SPLADE Dual-Recall"
  }
  ```

### 7.2 触发知识库切分与向量索引
- **路由**：`POST /api/v1/rag/ingest`
- **请求体 (JSON)**：
  ```json
  {
    "workspace_id": "ws-1710680000-a1b2",
    "incremental": true,
    "file_extensions": [".md", ".py", ".c", ".cpp", ".go"]
  }
  ```
- **响应 (200 OK)**：
  ```json
  {
    "task_id": "rag-ingest-1710684000",
    "status": "completed",
    "total_files": 127,
    "total_chunks": 1420
  }
  ```

### 7.3 在线三阶段检索与重排调试
- **路由**：`POST /api/v1/rag/retrieve`
- **请求体 (JSON)**：
  ```json
  {
    "query": "接入层三道安全闸门规范与令牌鉴权",
    "top_k": 5,
    "dense_top_k": 20,
    "sparse_top_k": 20
  }
  ```
- **响应 (200 OK)**：
  ```json
  {
    "query": "接入层三道安全闸门规范与令牌鉴权",
    "elapsed_ms": 38,
    "hits": [
      {
        "score": 0.942,
        "file_path": "documents/agent_runtime/11_http_api.md",
        "start_line": 25,
        "end_line": 60,
        "dense_rank": 1,
        "sparse_rank": 2,
        "rrf_score": 0.0328,
        "content": "## 1.1 三道闸门机制\n\n1. Host 闸门..."
      }
    ]
  }
  ```

---

## 8. 离线产物与长日志句柄 API (Artifacts API)

### 8.1 读取长日志产物元数据
- **路由**：`GET /api/v1/artifacts/{artifact_id}`
- **响应 (200 OK)**：
  ```json
  {
    "artifact_id": "obs_step_7_bash",
    "filename": "obs_step_7_bash.log",
    "size_bytes": 52428,
    "token_count": 1820,
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "created_at": 1710683200.0
  }
  ```

### 8.2 下载/读取长日志文本正文
- **路由**：`GET /api/v1/artifacts/{artifact_id}/content`
- **响应 (200 OK)**：`text/plain` 纯文本流

---

## 9. 智能体自省与系统健康探针 API (Introspection & Health)

### 9.1 工具自省
- **路由**：`GET /api/v1/introspection/tools`
- **响应 (200 OK)**：列出全部内置受控原子工具（`file_read`, `file_write`, `delegate_doc_search`, `delegate_research`, `bash_exec` 等）及其 JSON Schema 参数说明。

### 9.2 技能清单自省
- **路由**：`GET /api/v1/introspection/skills`
- **响应 (200 OK)**：已加载的技能名称、触发场景与路径列表。

### 9.3 MCP 服务器自省
- **路由**：`GET /api/v1/introspection/mcps`
- **响应 (200 OK)**：已挂载的外部 MCP 协议端点列表及连通状态。

### 9.4 系统基础健康探针（免令牌豁免）
- **路由**：`GET /health` 或 `GET /api/v1/health`
- **响应 (200 OK)**：
  ```json
  {
    "status": "healthy",
    "service": "aegis-agent",
    "uptime_seconds": 1845.2,
    "active_tasks": 0,
    "max_concurrent_tasks": 1
  }
  ```

---

## 10. 快速调用示例 (cURL Quickstart)

### 10.1 完整人机交互调用流水线

```bash
# 1. 取得 API 接入令牌
export TOKEN=$(cat storage/api_token)

# 2. 检查服务健康度
curl -s -H "X-API-Token: $TOKEN" http://127.0.0.1:8000/api/v1/health

# 3. 创建项目工作区
curl -s -X POST http://127.0.0.1:8000/api/v1/workspaces \
  -H "X-API-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Aegis Core","root_path":"/home/user/projects/aegis"}'

# 4. 在工作区下创建会话
curl -s -X POST http://127.0.0.1:8000/api/v1/workspaces/ws-1710680000-a1b2/sessions \
  -H "X-API-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"API 契约验证会话"}'

# 5. 提交任务目标
curl -s -X POST http://127.0.0.1:8000/api/v1/sessions/sess-1710682000-xyz/tasks \
  -H "X-API-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"检索 11_http_api.md 并实现工作区文件读写路由","permission_level":"workspace_write"}'

# 6. 监听任务实时 SSE 执行事件流
curl -N -H "Accept: text/event-stream" \
  "http://127.0.0.1:8000/api/v1/tasks/task-1710683000-9988/stream?token=$TOKEN"
```
