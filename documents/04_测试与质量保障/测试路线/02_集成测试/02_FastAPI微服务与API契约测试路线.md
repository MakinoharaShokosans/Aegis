# FastAPI 微服务与 API 契约集成测试路线图 (API Integration Test)

> **定位**：`AegisAgent`（端口 `:8000`）与 `AegisRAG`（端口 `:8001`）两大独立微服务对外暴露的 HTTP/SSE 端点、接入层安全闸门、代理路由与异常转译体系的契约测试路线。
> **原则**：使用 `httpx.AsyncClient` 绑定 ASGI Lifespan 上下文，严格验证 HTTP 状态码、请求头鉴权与 OpenAPI Schema 快照。

---

## 1. 现状盘点：微服务 API 契约覆盖矩阵

| 目标端点 / 闸门 | 对应测试文件 | 状态 | 核心验证重点 |
| :--- | :--- | :---: | :--- |
| **接入层三道安全闸门** | `AegisAgent/tests/api/test_security_gates.py` | `[x] [x]` | 闸门① Host 白名单 / DNS Rebinding 拦截；闸门② Origin 跨站校验；闸门③ Token 严格鉴权 |
| **任务全生命周期与审批路由** | `AegisAgent/tests/integration/test_api_lifecycle.py` | `[x] [x]` | `POST /tasks` 提交、`/tasks/{id}/approve` 恢复、`/tasks/{id}/reject` 拒绝、404/409 语义 |
| **RAG 代理网关路由** | `AegisAgent/tests/api/test_rag_routes.py` | `[x] [x]` | `/api/v1/rag/health`、`/api/v1/rag/ingest`、`/api/v1/rag/retrieve` 跨服务反向代理契约 |
| **沙箱 Sidecar 客户端契约** | `AegisAgent/tests/integration/test_sidecar_clients.py` | `[x] [x]` | BashTool、WebSearchTool 与独立 Sidecar 微服务的 Mock 通信与结果蒸馏 |
| **RAG 索引端点** | `AegisRAG/tests/api/test_route_ingest.py` | `[x] [x]` | `POST /api/v1/documents/ingest` 正常索引、二次幂等跳过（`skipped > 0`）、路径越界拒绝 |
| **RAG 检索端点** | `AegisRAG/tests/api/test_route_retrieve.py` | `[x] [x]` | `POST /api/v1/retrieve` 切片召回、Cross-Encoder 排序打分输出、空库安全返回 |
| **领域异常统一转译** | `AegisRAG/tests/api/test_error_handlers.py` | `[x] [x]` | 领域异常转 HTTP 状态码：`DimensionMismatch`→500、`CollectionNotReady`→503、`RepoNotIndexed`→404 |
| **同步路由非阻塞并发** | `AegisRAG/tests/api/test_concurrency_nonblocking.py` | `[x] [x]` | `def` 路由运行于线程池，重度 CPU 计算不阻塞 FastAPI 主事件循环 |

---

## 2. 细分测试用例规范

### 2.1 AegisAgent 接入层三道安全闸门 (`test_security_gates.py`)
- **闸门① Host 检查**：
  - 本地回环（`127.0.0.1`、`localhost`、`[::1]`）放行；
  - 外部未经授权 Host（如恶意伪造 `evil.com`）返回 `403 Forbidden` (`HOST_NOT_ALLOWED`)。
- **闸门② Origin 跨站检查**：
  - GET/HEAD 安全方法与无 Origin 桌面客户端放行；
  - 非白名单跨站 Origin 发起 POST/DELETE 请求返回 `403 Forbidden` (`ORIGIN_NOT_ALLOWED`)。
- **闸门③ 令牌鉴权与 Fail-Closed**：
  - 支持 `Authorization: Bearer <token>`、`X-API-Token: <token>` 及 SSE Query 参数 `?token=<token>`；
  - 令牌错误返回 `401 Unauthorized`；未配置服务端令牌时全部严格拒绝（`fail-closed`）。

### 2.2 任务审批与状态机 HTTP 契约 (`test_api_lifecycle.py`)
- **审批恢复端点契约**：
  - `POST /tasks/{id}/approve`：正常审批返回 200/202，任务重回 `running`；
  - `POST /tasks/{id}/reject`：拒绝审批返回 200，模型接收拒绝观察值；
  - 任务非挂起状态调用审批返回 `409 Conflict`；不存在的 `task_id` 返回 `404 Not Found`。

### 2.3 AegisRAG 独立微服务契约 (`AegisRAG/tests/api/`)
- **增量 Ingest 幂等性**：对同一代码目录连续请求 Ingest，第二次请求断言 `indexed == 0` 且 `skipped == 100%`；
- **异常转译状态码**：Collection 维度配置冲突时必须返回 HTTP 500 并携带具体维度差信息，上游网关捕获后转译为可读降级提示。

---

## 3. 验收标准与执行

- 接口状态码与 Pydantic 响应模型 100% 吻合；
- 并发请求无死锁与事件循环阻塞；
- 执行命令：
  ```bash
  cd /home/Skualeilu/Projects/Aegis/AegisAgent
  uv run pytest tests/api/ tests/integration/test_api_lifecycle.py -v
  cd /home/Skualeilu/Projects/Aegis/AegisRAG
  uv run pytest tests/api/ -v
  ```
