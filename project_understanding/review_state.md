# Review State

> 当前会话交互状态机

## 1. 焦点与范围
- **当前 Scope 层级**: Level 3: Module / Level 2: Component (`agent_runtime.nodes`)
- **当前 Target**: `AegisAgent/src/agent_runtime/nodes` (5 核心决策与执行节点及 base 契约)
- **当前 Module**: `AegisAgent/src/agent_runtime/nodes`
- **当前探索深度 (Depth)**: 3 (源码级深度剖析)

## 2. 认知与讨论进展
- **用户真实意图**: 深入理解 `agent_runtime/nodes` 模块结构、公共基类契约、各节点职责、实现机理、设计初衷与解耦机制。
- **已理解内容清单**:
  - 系统宏观三层拓扑与启动入口。
  - Agent 调度循环状态机（5 节点闭环）。
  - `llm/` 模块的双模型网关与两级弹性容灾流水线。
  - `guardrails/` 模块的 8 项纯策略确定性防线。
  - `nodes/` 采用工厂闭包依赖注入模式（`build_xxx_node -> NodeFn`）。
  - `planner`（不发工具）与 `executor`（只发工具不执行）解耦；`executor` 与 `tool_runner`（纯判定+HITL）解耦；`evaluator`（独立复核+记忆蒸馏）与执行解耦。
- **正在探讨内容**: `nodes` 模块各节点的输入输出契约、HITL 中断防重跑、死循环防线及反思自愈机制。
- **待决悬念**: 节点产出与前端 SSE 事件推送 (`TaskEventBus`) 的流式映射。
- **用户忽略项**: 暂无。
- **已发现认知偏差**: 暂无。
