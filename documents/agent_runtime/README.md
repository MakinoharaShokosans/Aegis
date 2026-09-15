# Aegis Agent Runtime - 实施技术规范索引

## 1. 文档拓扑结构

| 文档 | 领域分类 | 核心技术规范 |
| :--- | :--- | :--- |
| [01_architecture_overview.md](./01_architecture_overview.md) | 系统总架构 | 双子工程 Sidecar 拓扑、进程解耦、非确定性包围 |
| [02_state_definition.md](./02_state_definition.md) | 状态契约 | AgentState 强类型规范、原子消息对更新、物理指标 |
| [03_node_specification.md](./03_node_specification.md) | 节点规范 | Planner / Executor / Evaluator 等核心算子逻辑 |
| [04_routing_and_control_flow.md](./04_routing_and_control_flow.md) | 流程与路由 | 有向循环图构建、动态重规划回退、条件边决策 |
| [05_guardrails_implementation.md](./05_guardrails_implementation.md) | 护栏与容灾 | 双轨死循环防御、双模型 Fallback 链、观察值离线截断 |
| [06_memory_and_context_management.md](./06_memory_and_context_management.md) | **工作区、多会话与上下文治理** | **工作区一等公民(多工作区支持)、一工作区多会话(1:N级联从属)、跨会话长期记忆共享、单会话高低水位动态压缩(80%触发/40%对话对齐)** |
| [07_execution_context_management.md](./07_execution_context_management.md) | **微观执行上下文** | **任务草稿纸 (Scratchpad)、四阶段生命周期、绑定工作区根路径(cwd)、观察值截断下沉、瞬态护栏** |
| [08_skills_management.md](./08_skills_management.md) | **专家技能系统** | **两阶段渐进式披露、SOP 目录包规范、load_skill 按需动态挂载** |
| [09_mcp_integration_and_governance.md](./09_mcp_integration_and_governance.md) | **MCP 协议集成与治理** | **JSON-RPC 协议转译、stdio 进程托管与防僵尸、命名空间隔离、懒加载连接池** |
| [10_directory_structure.md](./10_directory_structure.md) | **目录结构与工程分层（权威）** | **内容/代码分离、依赖方向矩阵、统一裁决记录、打包与资源约定** |
| [11_http_api.md](./11_http_api.md) | **HTTP API 契约（唯一用户入口）** | **工作区/会话/任务 REST、SSE 事件流、DTO 分层、安全红线** |

---

## 2. 实施指南与模块对应

### 步骤一：配置与环境加载
- 参考：[`config/config.toml`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/config/config.toml)
- 实现：`AegisAgent/src/agent_runtime/config.py` (Pydantic Settings 加载 TOML 与 `.env`)

### 步骤二：工作区、状态契约与多层上下文
- 参考：`02_state_definition.md`、`06_memory_and_context_management.md`、`07_execution_context_management.md`
- 实现：
  - `AegisAgent/src/agent_runtime/memory/models.py` (Workspace, WorkspaceMemory, SessionMetadata)
  - `AegisAgent/src/agent_runtime/memory/sqlite_store.py` (workspaces 表、多工作区多会话 CRUD)
  - `AegisAgent/src/agent_runtime/memory/manager.py` (工作区生命周期与会话统筹)
  - `AegisAgent/src/agent_runtime/state.py` (ExecutionContext / AgentState 契约，绑定 workspace_id 与 workspace_path)
  - `AegisAgent/src/agent_runtime/context.py` (多层上下文装配器)

### 步骤三：技能系统与按需挂载
- 参考：`08_skills_management.md`
- 实现：
  - `AegisAgent/src/agent_runtime/skills/registry.py` (技能扫描与元数据提取)
  - `AegisAgent/src/tool_layer/tools/skill_tool.py` (`load_skill` 系统工具)

### 步骤四：MCP 外部协议与进程托管
- 参考：`09_mcp_integration_and_governance.md`
- 实现：
  - `AegisAgent/src/mcps/manager.py` (stdio 子进程托管与生命周期清理)
  - `AegisAgent/src/tool_layer/mcp_adapter.py` (命名空间防冲突与 Schema 转译)

### 步骤五：双模型 Fallback 网关
- 参考：`05_guardrails_implementation.md`
- 实现：`AegisAgent/src/agent_runtime/llm/client.py` (tenacity 指数退避与跨端点降级)

### 步骤六：安全护栏机制
- 参考：`05_guardrails_implementation.md`
- 实现：
  - `AegisAgent/src/agent_runtime/guardrails/loop_detector.py` (指纹哈希)
  - `AegisAgent/src/agent_runtime/guardrails/budget_guard.py` (步数与 Token 熔断)
  - `AegisAgent/src/agent_runtime/guardrails/pruner.py` (长输出离线落盘)

### 步骤七：状态图节点与条件边
- 参考：`03_node_specification.md` & `04_routing_and_control_flow.md`
- 实现：
  - `AegisAgent/src/agent_runtime/nodes/` (planner, executor 等)
  - `AegisAgent/src/agent_runtime/routing.py` (条件边与重规划路由)
  - `AegisAgent/src/agent_runtime/workflow.py` (LangGraph 图构建与编译)

### 步骤八：HTTP API 接入层（唯一用户入口）
- 参考：[`11_http_api.md`](./11_http_api.md)
- 实现：
  - `AegisAgent/src/agent_runtime/api/` (`app.py` / `deps.py` / `schemas.py` / `task_registry.py` / `routes/`)
- 前置依赖变更：`fastapi`、`uvicorn[standard]`；`config.toml` 补 `[server]` 段（含 CORS 白名单）

### 步骤九：双轨可观测
- 参考：`01` §4、[`技术栈.md`](file:///home/Skualeilu/Projects/Aegis/documents/技术栈.md)
- 实现：
  - `AegisAgent/src/agent_runtime/observability/logging.py` (Loguru 结构化 JSONL)
  - `AegisAgent/src/agent_runtime/observability/trajectory.py` (`storage/traces/{task_id}.jsonl`)
  - `AegisAgent/src/agent_runtime/observability/langfuse_tracer.py` (Langfuse 回调)

---

## 3. 文档版本与依赖基线（v2 统一修订）

### 3.1 规范冲突裁决记录

早期 `03_node_specification.md` 与 `04_routing_and_control_flow.md` 残留了一套通用模板（`cost_usd` 费用模型、`supervisor` 节点、`trajectory` 状态字段），与 `02`/`05` 的定稿规范直接冲突。现已统一裁决并改写为 **v2**：

| 冲突点 | 裁决结果 | 权威依据 |
| :--- | :--- | :--- |
| `cost_usd` / `max_cost_usd` | 删除，改用 `total_tokens` / `step_count` / 挂钟时间 | `02` §1、`05` §2 |
| `supervisor` 节点 | 删除，改由连续错误熔断回退 `planner` 重规划 | `05` §1.2 |
| 第三类节点命名 | 统一为 `evaluator`（里程碑验收 + 事实沉淀） | `01` §4.1、本 README 索引 |
| `planner` 是否产出 `tool_calls` | 不产出。`planner`(reasoning) 出决策指令，`executor`(fast) 生成并派发工具 | `01` §4.1/§4.2、`05` §3 |

**最终节点集合**：`planner` / `budget_guard` / `executor` / `evaluator`。

> **结构与契约裁决的完整清单**（pruner 归属、技能内容/代码分离、子系统部署形态、`FailedAttempt` 唯一真源、`run_id`→`task_id`、Bash cwd 语义、评测入口、HTTP API 入口、可观测性落点，共 11 项）统一记录在 [`10_directory_structure.md`](./10_directory_structure.md) §4。**该表是关于目录与归属的唯一权威来源**，本节仅保留状态机契约层面的裁决。

### 3.2 依赖基线

- 依赖唯一真源为 `AegisAgent/pyproject.toml` + `AegisAgent/uv.lock`（RAG 侧同理），**文档中的版本号仅为视图**，不得作为安装依据。
- 断点续跑所依赖的 `AsyncSqliteSaver` 位于独立包 **`langgraph-checkpoint-sqlite`** —— **已声明并锁定**（`>=3.1.1,<4.0.0`），详见 `04` §4.1。
- HTTP API 接入层（步骤八）所需的 `fastapi`、`uvicorn[standard]`，与 MCP 集成（步骤四）所需的 `mcp` —— **均已声明并锁定**。以上四项在同一次变更中刷新了 `uv.lock`，`uv lock --check` 通过（114 包）。

### 3.3 实施进度对照

`02` 提出的工作区/状态契约中，记忆子系统（`memory/`）**已实现并通过单测**；`state.py` 与 `context.py` 尚未落地。`03`–`09`、`11` 规范的实现文件目前均为空占位，详见各步骤的"实现"路径与 `10` §2–§3 的 `＋` 标记。

### 3.4 架构定位（补充确认）

- **同工程子系统**：`bash_shell`、`web_search` 保留在 `AegisAgent/src/services/` 内，各自作为独立进程经 HTTP 暴露（`:8002` / `:8003`），不拆分独立子工程。
- **独立子工程**：仅 `AegisRAG`（因 `onnxruntime` / `tree-sitter` 重依赖与 C 扩展而物理隔离，`:8001`）。
- **用户入口**：仅 HTTP API（`127.0.0.1:8000`），不提供 CLI；后续由 Web 前端消费。

## 4. 代码目录映射 (`AegisAgent/`)

> 下列为**速览版**。目录结构、依赖方向矩阵、打包约定与占位规则的**权威定义**见 [`10_directory_structure.md`](./10_directory_structure.md)。

```text
AegisAgent/
├── config/
│   └── config.toml               # 物理配额、多模型降级列表、服务寻址、[server]、[mcp]
├── src/
│   ├── agent_runtime/
│   │   ├── __init__.py
│   │   ├── config.py             # Pydantic 强类型配置
│   │   ├── state.py              # AgentState / Milestone / FailedAttempt 契约
│   │   ├── execution_context.py  # 单任务草稿纸与 Teardown 落盘
│   │   ├── context.py            # 多层上下文装配器
│   │   ├── workflow.py           # LangGraph 状态图编译入口
│   │   ├── routing.py            # 条件边与熔断跳转
│   │   ├── memory/               # 已实现：工作区/会话双层记忆 + 水位压缩
│   │   ├── prompts/              # system.md / planner.md / compactor.md ...
│   │   ├── nodes/                # planner / budget_guard / executor / evaluator
│   │   ├── guardrails/           # loop_detector / budget_guard / pruner
│   │   ├── llm/                  # 双模型 Fallback 网关
│   │   ├── skills/               # 技能注册表（代码）
│   │   ├── observability/        # Loguru / Trajectory / Langfuse
│   │   └── api/                  # HTTP API：app / deps / schemas / routes（见 11）
│   ├── skills/                   # 内置技能内容包（SKILL.md 等，数据）
│   ├── tool_layer/               # 工具适配器、并发派发、HTTP Client、MCP 适配
│   ├── mcps/                     # MCP 服务器托管
│   ├── services/                 # bash_shell / web_search（同工程子系统）
│   └── evaluation/               # rag_bench / agent_bench
├── tests/                        # 与 src 镜像的测试树（pytest 入口）
└── storage/
    ├── checkpoints/              # SQLite 状态快照
    ├── artifacts/{task_id}/      # 离线截断日志与产物
    ├── traces/{task_id}.jsonl    # JSONL 因果轨迹
    └── logs/                     # Loguru JSONL
```
