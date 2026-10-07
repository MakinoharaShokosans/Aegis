# Core Symbols Index

> 状态标签: `[Current]`(实码校验) | `[Unverified]`(历史推断待印证) | `[Unknown]`(尚无证据) | `[Stale]`(待修正)

## 1. 核心状态与契约
- `[Current]` **`AgentState`** (`AegisAgent/src/agent_runtime/state.py`):
  - 类型: `TypedDict`
  - 职责: LangGraph Checkpoint 持久化唯一真源，维护消息队列、里程碑、物理指标与任务状态。
- `[Current]` **`Milestone`** (`AegisAgent/src/agent_runtime/state.py`):
  - 类型: `BaseModel`
  - 职责: 任务阶段性目标领域模型，供 Planner 规划与 Evaluator 验收。

## 2. 调度与图构建
- `[Current]` **`build_runtime`** (`AegisAgent/src/agent_runtime/workflow.py`):
  - 类型: 函数
  - 职责: 进程级单例装配（配置、检查点、模型网关、技能库、MCP 管理器）。
- `[Current]` **`prepare_task`** (`AegisAgent/src/agent_runtime/workflow.py`):
  - 类型: 函数
  - 职责: 任务级生命周期对象初始化（预算守卫、观察裁剪器、闭包编译 StateGraph）。
- `[Current]` **`build_planner_node`** / **`build_executor_node`** / **`build_evaluator_node`** (`AegisAgent/src/agent_runtime/nodes/`):
  - 类型: 工厂函数
  - 职责: 状态机核心决策节点装配。

## 3. RAG 检索关键 Symbol
- `[Current]` **`split_ast`** (`AegisRAG/src/indexer/ast_splitter.py`):
  - 类型: 函数
  - 职责: 基于 Tree-sitter (C/C++/Go) 沿语法树节点边界切分完整函数与结构体。
- `[Current]` **`QdrantStore`** (`AegisRAG/src/storage/qdrant_store.py`):
  - 类型: 类
  - 职责: Qdrant 客户端交互，承载双路向量写入与 RRF 融合检索。
- `[Current]` **`Reranker`** (`AegisRAG/src/rerank/reranker.py`):
  - 类型: 类
  - 职责: Cross-Encoder 深度重排打分。
