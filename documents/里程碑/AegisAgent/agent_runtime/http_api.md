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
- [x] [ ] **人机协同审核（HITL）交互端点**
  - [x] [ ] `POST /api/v1/tasks/{id}/approve`：批准待审核越级操作（单次放行 / 会话永久放行）
  - [x] [ ] `POST /api/v1/tasks/{id}/reject`：拒绝越级操作并向模型回传理由重新规划
- [x] [x] **Server-Sent Events (SSE) 实时流式交互**
  - [x] [x] `GET /api/v1/tasks/{id}/stream`：订阅任务实时执行事件流
  - [x] [x] 实时推送 `task.started`、`node.started`、`tool.call`、`tool.result`、`milestone.updated`、`task.finished` 等核心事件流
  - [x] [ ] 实时推送 `task.waiting_for_approval`、`task.approved`、`task.rejected` 审核事件流


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
