# AegisAgent HTTP API 网关与自省端点功能与设计里程碑

> **对应设计规范**：`documents/agent_runtime/11_http_api.md`
> **责任模块**：`AegisAgent/src/agent_runtime/api/`
> **核心原则**：RESTful 契约、SSE 流式实时交互、全生命周期管理、多维自省可观测。
>
> **图例规范**：`[代码实现] [测试通过]`

---

## 一、工作区与会话资源全生命周期管理

- [x] [x] **工作区（Workspaces）端点**
  - [x] [x] `POST /api/v1/workspaces`：创建或获取工作区实体
  - [x] [x] `GET /api/v1/workspaces`：列出当前所有已注册工作区
  - [x] [x] `GET /api/v1/workspaces/{id}`：查询特定工作区详情
  - [x] [x] `DELETE /api/v1/workspaces/{id}`：工作区级联物理删除（同步清空会话与记忆）
- [x] [x] **会话（Sessions）端点**
  - [x] [x] `POST /api/v1/workspaces/{ws_id}/sessions`：在指定工作区下创建新会话
  - [x] [x] `GET /api/v1/workspaces/{ws_id}/sessions`：列出会话清单
  - [x] [x] `GET /api/v1/sessions/{id}/turns`：分页查询历史对话轮次流
  - [x] [x] `GET /api/v1/sessions/{id}/context`：实时检视当前会话装配后的多层上下文快照

---

## 二、任务调度、人机审核与流式响应交互

- [x] [x] **同步/异步任务提交与轮询**
  - [x] [x] `POST /api/v1/workspaces/{ws_id}/sessions/{sess_id}/tasks`：异步提交任务并返回 `task_id`
  - [x] [x] `GET /api/v1/tasks/{id}`：查询任务执行状态、步数、Token 消耗与终态结论
- [x] [x] **人机协同审核（HITL）交互端点**
  - [x] [x] `POST /api/v1/tasks/{id}/approve`：批准待审核越级操作（单次放行 / 会话永久放行）
  - [x] [x] `POST /api/v1/tasks/{id}/reject`：拒绝越级操作并向模型回传理由重新规划
- [x] [x] **Server-Sent Events (SSE) 实时流式交互**
  - [x] [x] `GET /api/v1/tasks/{id}/stream`：订阅任务实时执行事件流
  - [x] [x] 实时推送 `task.started`、`node.started`、`tool.call`、`tool.result`、`milestone.updated`、`task.finished` 等核心事件流
  - [x] [x] 实时推送 `task.waiting_for_approval`、`task.approved`、`task.rejected` 审核事件流
- [x] [x] **子智能体中间步骤可见（事件总线旁路）**
  - [x] [x] 任务级事件总线 `observability/event_bus.py`：叶子工具内部事件 → `TaskRegistry.emit` → SSE（自动获得序号与断线重连）
  - [x] [x] `subagent.started` / `subagent.step` / `subagent.tool` / `subagent.blocked` / `subagent.finished`
  - [x] [x] `research.started` / `research.round` / `research.finished`
  - [x] [x] 摘要强制限长 300 字符；原始正文仍不进入主状态、主 Checkpoint 与事件流；`emit` 永不抛异常
  - 注：已在 `tests/observability/test_event_bus.py` 建立 9 项专项测试，全量覆盖状态机、限长截断、异常隔离与事件模型。


---

## 三、系统自省与状态监控端点 (`api/routes/introspection.py`)

- [x] [x] **健康检查与就绪探针**
  - [x] [x] `GET /health` / `GET /api/v1/health`：返回服务运行状态与组件就绪度
- [x] [x] **工具与沙箱自省**
  - [x] [x] `GET /api/v1/tools`：列出当前已注册特权工具清单
  - [x] [x] 支持 `include_sandboxed=true` 查询受限沙箱工具（如内部 web_search）
- [x] [x] **技能与协议自省**
  - [x] [x] `GET /api/v1/skills`：查询已扫描可用专家技能与安全告警标记
  - [x] [x] `GET /api/v1/mcps`：查询已挂载 MCP 服务状态与工具审查结论

---

## 四、接入层安全闸门 (`api/auth.py`)

> 动机：**只监听回环不等于安全**。用户浏览器里的任意页面都能向 `127.0.0.1:8000` 发请求，
> `POST /tasks/{id}/approve` 一旦被诱导调用，等于让攻击者替用户批准一次高危操作。

- [x] [x] **纯 ASGI 安全闸门中间件 `SecurityGateMiddleware`**
  - [x] [x] 中间件而非路由依赖：**无法被漏挂**，新增路由自动受保护
  - [x] [x] 纯 ASGI（不碰 body），对 SSE 长连接透明
  - [x] [x] 闸门① **Host 校验**：挡 DNS rebinding（回环名 ∪ `[server].allowed_hosts`）
  - [x] [x] 闸门② **Origin 校验**：非安全方法若带 `Origin` 必须在 CORS 白名单内（挡跨站替用户提交）
  - [x] [x] 闸门③ **令牌校验**：`hmac.compare_digest` 恒定时间比较；`auth_enabled=false` 时关闭
- [x] [x] **令牌准备与存放 `provision_api_token()`**
  - [x] [x] 环境变量（`[server].api_token_env`）→ 令牌文件 → 自动生成，三级优先级
  - [x] [x] 已存在令牌文件则**复用**（重启不让前端掉线）
  - [x] [x] `0600` 落盘（`os.open` + 显式 `chmod`，避免 umask 削减）；`.gitignore` 排除
  - [x] [x] **日志只打印文件路径，绝不打印令牌本身**
  - [x] [x] fail-closed：要求令牌但取不到令牌时**全部请求 401**（`AUTH_MISCONFIGURED`）
- [x] [x] **凭据载体与豁免**
  - [x] [x] `Authorization: Bearer` / `X-API-Token` / `?token=`（`EventSource` 不能自定义请求头，这是 SSE 唯一可行通道）
  - [x] [x] 豁免：`/`、`/health`、`/api/v1/health`、`/docs`、`/redoc`、`/openapi.json`、全部 `OPTIONS` 预检
  - [x] [x] 统一错误体（与 `api/errors.py` 同构）+ `WWW-Authenticate: Bearer`
  - [x] [x] 失败语义：`401 UNAUTHORIZED` / `403 HOST_NOT_ALLOWED` / `403 ORIGIN_NOT_ALLOWED`
- [x] [x] **中间件嵌套顺序**：`CORS（外）→ SecurityGate（内）→ 路由`
  - [x] [x] CORS 在外层，401/403 才带得上 CORS 头（否则浏览器只看到语焉不详的网络错误）
- [x] [x] **`/docs` 联调体验**：OpenAPI 广告 `ApiTokenHeader` / `BearerToken` 两种 SecurityScheme（`auto_error=False`，只作文档用途）
- 注：已在 `tests/api/test_security_gates.py` 建立 18 项专项测试，全量覆盖 Host、Origin、Token 校验与文件权限。

### 明确不提供（避免过度承诺）

- **不防同用户的其它本地进程**：它能直接读令牌文件。本层防的是浏览器跨站与远程访问。
- **不是多用户体系**：没有身份、没有 RBAC、没有按用户隔离的工作区；令牌是"持有即可用"的单一凭据。
