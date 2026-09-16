# AegisAgent LangGraph 状态机与工作流编排功能与设计里程碑

> **对应设计规范**：`documents/agent_runtime/03_node_specification.md` & `04_routing_and_control_flow.md`  
> **责任模块**：`AegisAgent/src/agent_runtime/workflow.py`, `nodes/`, `edges/`  
> **核心原则**：双层模型分工（Reasoning vs Fast）、独立验收打回、并发工具派发、条件边自愈。

---

## 一、双层模型分工与节点架构 (`nodes/`)

- [x] **`Planner` 节点（宏观规划与自主分解 - Reasoning 层）**
  - [x] 不产生 `tool_calls`，专注高价值决策与下一步自然语言指令
  - [x] 首次规划产出完整 `milestones`，后续轮次增量更新状态
  - [x] 强制 JSON 结构化输出，解析失败时优雅降级为纯文本指令
- [x] **`Executor` 节点（动作翻译与并发派发 - Fast 层）**
  - [x] 采用快速廉价模型将 Planner 指令翻译为具体 `tool_calls`
  - [x] 并发工具调度：通过 `ToolDispatcher` 与 `asyncio.gather` 并发派发
  - [x] 指纹死循环拦截与瞬态连续错误计数
  - [x] 观察值蒸馏与超限落盘
- [x] **`Evaluator` 节点（独立验收与认知沉淀 - Reasoning 层）**
  - [x] 独立复核 Planner 自我声明的完工状态，不满足条件时打回重试
  - [x] 复核通过时推进里程碑完成状态
  - [x] 独立沉淀本轮已确认事实（`confirmed_facts`）与避坑记录（`failed_attempts`）
- [x] **`BudgetGuard` 节点（物理预算拦截网关）**
  - [x] 拦截并检查当前步数、Token 与挂钟时间物理指标
  - [x] 达到阈值时置位熔断终止

---

## 二、确定性条件路由边体系 (`edges/`)

- [x] **`route_after_planner`**
  - [x] 优先级 1：硬熔断（`should_terminate=True`）➔ 直接进入 `END`
  - [x] 优先级 2：全部里程碑自我声明完成 ➔ 导向 `evaluator` 独立复核
  - [x] 优先级 3：常规推进 ➔ 导向 `budget_guard` 进入主执行环
- [x] **`route_after_budget_guard`**
  - [x] 预算超限熔断 ➔ 直接进入 `END`
  - [x] 预算正常 ➔ 导向 `executor`
- [x] **`route_after_executor`**
  - [x] 硬熔断（如金丝雀泄露）➔ 直接进入 `END`
  - [x] 工具派发完毕（无论成功、连续失败或死循环）➔ 回流 `planner` 触发下一步或重规划
- [x] **`route_after_evaluator`**
  - [x] 硬熔断或全部里程碑复核通过 ➔ 导向 `END`
  - [x] 验收打回或仍有后续里程碑 ➔ 回流 `planner` 继续推进

---

## 三、图状态机编译与流式执行 (`workflow.py`)

- [x] **StateGraph 闭环状态图编译**
  - [x] 注册节点、配置 Reducer 与 Checkpointer
  - [x] 挂载全套条件边与终态收敛点
- [x] **双执行驱动模式**
  - [x] `run_agent`：标准异步执行，驱动至终态返回最终 `AgentState`
  - [x] `run_streaming`：异步生成器流式驱动，向 `event_sink` 实时派发节点步骤与状态增量
