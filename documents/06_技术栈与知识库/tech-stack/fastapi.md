---
aliases:
  - FastAPI
  - Web微服务框架
  - HTTP与SSE接入层
tags:
  - tech-stack
  - python
  - web-framework
  - api
  - sse
package: "fastapi"
version: ">=0.141.1,<1.0.0"
project_role: "系统统一网络接入层与微服务底座，提供任务提交控制 REST API、实时 SSE 事件流推送以及安全中间件拦截"
entrypoints:
  - "AegisAgent/src/agent_runtime/api/app.py"
  - "AegisAgent/src/agent_runtime/api/routes/tasks.py"
  - "AegisRAG/src/api/app.py"
---

# FastAPI 辅助检索与理解指南

> [!info] 什么是 FastAPI
> **生活化比喻**：如果把整个 Aegis 系统比作一个“只认内部指令的高速科研实验室”，那么 FastAPI 就是实验室面向外部世界的**“现代化全功能接待大厅”**。它不仅能够高效分发各种来访者的业务请求（REST API），还能拉起一条直连的单向广播线（SSE 流），将实验室里面 AI 每一步的思考、敲击的每一句 Shell 命令实时传达给外面的观察者，同时牢牢守住三道安全闸门，防止可疑人员越权入侵。

---

## 1. 小白心智模型（1分钟看懂）

- **解决的核心痛点**：如果不使用 FastAPI，手写传统异步 Web 框架不仅需要手动解析请求 JSON、编写大量参数校验逻辑、手搓 OpenAPI/Swagger 接口文档，在实现带有断线重连的 Server-Sent Events（SSE）长连接流式推送时还容易发生内存泄漏或协程死锁。
- **一句话本质**：FastAPI 是一个**基于 Starlette 和 Pydantic 的超高性能、原生支持异步协程的现代 Python Web 框架**。
- **三大核心物理机制**：
  1. **Routing & Endpoints（路由与端点）**：将 HTTP 动词与 URL 路径绑定到具体的 Python 异步函数（`async def`）。
  2. **Dependency Injection（依赖注入系统，`Depends`）**：在路由函数执行前，自动解析、装配并注入所需的运行时上下文（如配置、数据库连接、任务注册表），实现业务逻辑与底层基础设施的彻底解耦。
  3. **Middleware & Exception Handlers（中间件与异常拦截器）**：在请求到达路由之前和响应离开之后执行全局拦截（如 Host/Origin 安全闸门、CORS 跨域头添加、未捕获异常统一格式化）。

---

## 2. 本项目中的角色与调用链路

- **在本项目的位置**：微服务网络接入与通信底座（Network Gateway & Microservice Layer）。
- **核心入口文件**：
  - Agent 主服务装配：[`AegisAgent/src/agent_runtime/api/app.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/api/app.py)
  - 任务与 SSE 流路由：[`AegisAgent/src/agent_runtime/api/routes/tasks.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/api/routes/tasks.py)
  - 依赖注入声明：[`AegisAgent/src/agent_runtime/api/deps.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/api/deps.py)
  - 安全闸门中间件：[`AegisAgent/src/agent_runtime/api/auth.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/api/auth.py)
  - RAG 检索微服务：[`AegisRAG/src/api/app.py`](file:///home/Skualeilu/Projects/Aegis/AegisRAG/src/api/app.py)
- **典型执行流转链路**：
  ```text
  Web 前端发起 HTTP 请求 (如 POST /api/v1/tasks)
                 │
                 ▼
  Starlette CORS 中间件 (跨域标头处理)
                 │
                 ▼
  SecurityGateMiddleware (Host防DNS重绑定 / Origin跨站校验 / Token比对)
                 │
                 ▼
  FastAPI Depends (自动注入 RuntimeDeps / TaskRegistry)
                 │
                 ▼
  路由函数处理 ──► 返回 JSON 或挂接 EventSourceResponse (SSE 持续推送事件)
  ```

---

## 3. 核心 Symbol 速查字典（类 / 函数 / 属性 / 装饰器）

### `FastAPI`（核心应用类）

- **通俗职责**：整个 Web 服务的总容器，负责应用初始化、中间件装配、全局生命周期（`lifespan`）托管与路由挂载。
- **常用参数**：
  - `title`: API 标题（显示在 `/docs` Swagger 文档中）。
  - `lifespan`: 异步上下文管理器，负责在服务启动时初始化数据库与微服务连接，在退出时逆序释放。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/api/app.py:L70`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/api/app.py#L70)
- **最小实战代码**：
  ```python
  from fastapi import FastAPI

  app = FastAPI(
      title="Aegis Agent Runtime",
      lifespan=lifespan_handler,
  )
  app.include_router(tasks_router, prefix="/api/v1")
  ```

---

### `APIRouter`（模块化路由类）

- **通俗职责**：路由分组器。将不同业务模块（workspaces, sessions, tasks, rag, artifacts）拆分到不同文件中独立维护。
- **常用方法**：`@router.get(...)`、`@router.post(...)`、`@router.delete(...)`。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/api/routes/tasks.py:L33`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/api/routes/tasks.py#L33)
- **最小实战代码**：
  ```python
  from fastapi import APIRouter

  router = APIRouter(tags=["tasks"])

  @router.post("/tasks/{task_id}/approve")
  async def approve_task(task_id: str):
      return {"status": "resumed"}
  ```

---

### `Depends`（依赖注入声明）

- **通俗职责**：“把依赖交给框架来给”。让路由函数声明自己需要什么组件，而不用关心组件如何被实例化。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/api/deps.py:L11`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/api/deps.py#L11)、[`AegisAgent/src/agent_runtime/api/routes/tasks.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/api/routes/tasks.py)
- **最小实战代码**：
  ```python
  from typing import Annotated
  from fastapi import Depends, Request
  from agent_runtime.workflow import RuntimeDeps

  def get_runtime(request: Request) -> RuntimeDeps:
      return request.app.state.runtime

  # 在路由中通过类型别名简洁引用
  RuntimeDep = Annotated[RuntimeDeps, Depends(get_runtime)]

  @router.get("/status")
  async def get_status(deps: RuntimeDep):
      return {"ready": True}
  ```

---

### `EventSourceResponse`（SSE 流响应类，来自 `sse_starlette`）

- **通俗职责**：维持一个长连接，以 `text/event-stream` 格式持续向客户端单向推送事件（如 Agent 的思考、工具调用结果、状态转移通知）。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/api/routes/tasks.py:L20`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/api/routes/tasks.py#L20)
- **最小实战代码**：
  ```python
  from sse_starlette.sse import EventSourceResponse

  @router.get("/tasks/{task_id}/stream")
  async def stream_task_events(task_id: str):
      async def event_generator():
          while not finished:
              event = await queue.get()
              yield {"event": "node.finished", "data": json.dumps(event)}

      return EventSourceResponse(event_generator())
  ```

---

## 4. 本项目典型用法与实操范式

### 范式 1：Lifespan 严格保证启动与关闭依赖顺序
```python
# 路径：AegisAgent/src/agent_runtime/api/app.py
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 1. 启动顺序：基础设施初始化 -> 注册表挂载 -> 存入 app.state
    runtime = await build_runtime(cfg)
    app.state.runtime = runtime
    app.state.task_registry = TaskRegistry(runtime)
    logger.info("Aegis 服务启动就绪")

    yield  # 服务运行中，持续处理请求

    # 2. 关闭顺序（逆序释放）：先终止所有后台运行的任务，再释放数据库连接
    await app.state.task_registry.cancel_all()
    await close_runtime(runtime)
    logger.info("Aegis 服务优雅停止完毕")
```

### 范式 2：非阻塞异步任务投递与状态流推送
```python
# 路径：AegisAgent/src/agent_runtime/api/routes/tasks.py
@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_task(
    body: TaskSubmit,
    registry: RegistryDep,
):
    # 只登记不阻塞：快速生成并持久化 task_id，真正执行转交后台协程
    task_id = await registry.spawn_task(body)
    return TaskOut(task_id=task_id, status="queued")
```

---

## 5. 新手易错陷阱与排坑指南

> [!warning] 陷阱 1：中间件注册顺序颠倒导致 CORS 头丢失
> **现象**：浏览器跨域请求被拦截报 401/403 时，前端控制台看不到详细的 JSON 错误信息，只报错 `CORS missing Allow-Origin header`。
> **原因**：在 Starlette 体系中，后注册的中间件位于外层。如果先注册 CORS 再注册安全闸门，安全闸门直接抛错返回的响应将无法走入 CORS 中间件，导致响应头中缺少跨域放行头。
> **正解**：本项目在 [`app.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/api/app.py#L7) 中严格遵循先添加 `SecurityGateMiddleware`，后添加 `CORSMiddleware`。

> [!warning] 陷阱 2：在异步路由中调用耗时同步阻塞代码
> **现象**：某个端点（如大文件哈希计算或高耗时 CPU 算法）执行时，整个服务的所有 SSE 推送和 HTTP 响应全部卡死。
> **正解**：FastAPI 的 `async def` 路由运行在主事件循环中，绝不可出现 `time.sleep()` 或耗时同步读写。必须使用 `asyncio.sleep()` 或将计算移入线程池 `run_in_threadpool`。

> [!warning] 陷阱 3：SSE 生成器中出现未捕获异常导致连接静默断开
> **现象**：前端 EventSource 持续报连接断开重连，但后台找不到明确日志。
> **正解**：在 `event_generator()` 内必须使用 `try...except` 块包裹，捕获异常后主动推送一个包含错误信息的 `task.error` 事件再退出，避免连接非预期截断。
