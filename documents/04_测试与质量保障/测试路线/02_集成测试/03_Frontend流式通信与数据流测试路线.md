# Frontend 流式通信与数据流测试路线图 (Frontend Network & SSE Integration)

> **定位**：`AegisFrontend` 接入层通信协议、HTTP 模块契约与 Server-Sent Events (SSE) 流式传输的集成测试路线。
> **原则**：全量 Mock 原生 `fetch` 与 `EventSource`，严格校验请求头、Token 鉴权穿透与断网自动重连机制。

---

## 1. 现状盘点：前端通信与网络层覆盖矩阵

| 目标源码模块 | 对应测试文件 | 状态 | 核心验证重点 |
| :--- | :--- | :---: | :--- |
| `src/api/client.ts` | `src/api/__tests__/client.test.ts` | `[x] [x]` | Token 内存与 LocalStorage 双向同步、`X-API-Token` 与 `Authorization` 头注入、异常转译 |
| `src/api/index.ts` | `src/api/__tests__/modules.test.ts` | `[x] [x]` | Workspace / Session / Task / File / RAG / System 领域 API 端点映射与参数构建 |
| `taskApi.subscribe` | `src/stores/__tests__/useTaskStore.test.ts` | `[x] [x]` | SSE 流式报文聚合、`token` 增量拼接、`waiting_for_approval` 挂起事件捕获 |
| 断网重连与状态恢复 | 规划验证中 | `[x] [ ]` | 基于 `Last-Event-ID` 的断点续传、网络抖动指数退避重连（Exponential Backoff） |

---

## 2. 细分测试用例规范

### 2.1 HttpClient 核心机制与鉴权头注入 (`client.test.ts`)
- **Token 生命周期管理**：
  - 调用 `client.setToken("secret-123")`，验证客户端内部属性与浏览器的 `localStorage`（键 `aegis_api_token`）同步更新；
  - 调用 `client.getToken()` 正常读取。
- **安全请求头注入**：
  - 发送任意 API 请求（如 `GET /api/v1/health`），断言发送的 Request Headers 自动包含：
    - `X-API-Token: secret-123`
    - `Authorization: Bearer secret-123`
    - `Content-Type: application/json`
- **Query 参数序列化**：
  - 调用 `client.get('/tree', { max_depth: 3, include_hidden: false })`，准确编码为 `/tree?max_depth=3&include_hidden=false`。
- **204 No Content 安全处理**：服务端返回空内容时，安全反序列化为空对象 `{}`，不抛 JSON 解析异常。

### 2.2 领域 API 模块契约 (`modules.test.ts`)
- **`taskApi` 端点流转**：
  - `taskApi.create(sessionId, prompt)` 校验 POST payload；
  - `taskApi.approve(taskId, { approval_id, scope })` 正确调用 `/api/v1/tasks/{id}/approve`；
  - `taskApi.reject(taskId, { approval_id, reason })` 正确调用 `/api/v1/tasks/{id}/reject`。
- **`workspaceApi` & `sessionApi`**：
  - 校验工作区创建、列表拉取、Session 历史轮次分页（`turns?limit=30`）等请求路径与 HTTP 方法。

### 2.3 SSE 事件流解析与消息聚合
- 验证连续接收到后端分块推送的文本片段时，前端 Store 能够维持正确字符序列，中文多字节字符（UTF-8）不发生切分乱码。

---

## 3. 验收标准与执行

- 全部网络层单测通过，Mock 拦截率 100%；
- 执行命令：
  ```bash
  cd /home/Skualeilu/Projects/Aegis/AegisFrontend
  npm run test src/api/__tests__/
  ```
