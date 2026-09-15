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

### 3.2 依赖基线

- 依赖唯一真源为 `AegisAgent/pyproject.toml` + `AegisAgent/uv.lock`（RAG 侧同理），**文档中的版本号仅为视图**，不得作为安装依据。
- 断点续跑所依赖的 `AsyncSqliteSaver` 位于独立包 **`langgraph-checkpoint-sqlite`**，当前**未声明、未锁定**；实现 `workflow.py` 前须执行 `uv add "langgraph-checkpoint-sqlite"`（详见 `04` §4.1）。

### 3.3 实施进度对照

`02` 提出的工作区/状态契约中，记忆子系统（`memory/`）**已实现并通过单测**；`state.py` 与 `context.py` 尚未落地。`03`–`09` 规范的实现文件目前均为空占位，详见各步骤的"实现"路径。

## 4. 代码目录映射 (`AegisAgent/`)

```text
AegisAgent/
├── config/
│   └── config.toml               # 物理配额、多模型降级列表、服务寻址
├── src/
│   ├── agent_runtime/
│   │   ├── __init__.py
│   │   ├── config.py             # Pydantic 强类型配置
│   │   ├── state.py              # AgentState 契约
│   │   ├── context.py            # 上下文装配器与已压缩记忆
│   │   ├── workflow.py           # LangGraph 状态图编译入口
│   │   ├── routing.py            # 条件边与熔断跳转
│   │   ├── prompts/
│   │   │   └── system.md         # 内置系统提示词
│   │   ├── nodes/                # 算子实现
│   │   ├── guardrails/           # 护栏与 Pruner
│   │   └── llm/                  # 双模型 Fallback 网关
│   ├── tool_layer/               # 工具适配器、HTTP Client
│   ├── services/                 # bash_shell, web_search
│   └── evaluation/
└── storage/
    ├── checkpoints/              # SQLite 状态快照
    ├── artifacts/                # 离线截断日志
    └── traces/                   # JSONL 因果轨迹
```
