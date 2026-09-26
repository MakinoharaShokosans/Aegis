---
aliases:
  - LangGraph
  - 智能体状态图框架
  - 任务状态机编排引擎
tags:
  - tech-stack
  - python
  - agent
  - workflow
  - state-machine
package: "langgraph"
version: ">=1.2.11,<2.0.0"
project_role: "系统核心编排调度中枢，基于有向循环状态图实现 Planner-Executor-Evaluator 双层规划、自愈自适应与人机审批流转"
entrypoints:
  - "AegisAgent/src/agent_runtime/workflow.py"
  - "AegisAgent/src/agent_runtime/state.py"
  - "AegisAgent/src/agent_runtime/routing.py"
---

# LangGraph 辅助检索与理解指南

> [!info] 什么是 LangGraph
> **生活化比喻**：如果把大语言模型（LLM）比作一个“聪明但记性短暂、容易跑偏的专家”，那么 LangGraph 就是他的**“精密生产流水线指挥中心”**。它用一张清晰的“状态流程图”（StateGraph），规定好：第一步做什么（Planner 制定计划）、第二步做什么（Executor 调度工具）、第三步谁来核验质量（Evaluator 反思验收）；如果做错了该回退到哪一步重新来过，做对了从哪里交卷。它让不可控的 AI 对话变成了可预测、可暂停、可分支重试的工业级状态机。

---

## 1. 小白心智模型（1分钟看懂）

- **解决的核心痛点**：如果不使用 LangGraph，手写大模型 Agent 往往只能写成简单的 `while True` 循环。一旦任务步数变长（10~30 步），模型极其容易发生注意力漂移、原地死循环、工具重复调用、甚至在中途报错时彻底崩盘无法自愈。
- **一句话本质**：LangGraph 是一个**带状态持久化与条件分支的有向循环图（Stateful Cyclical Graph）框架**。
- **三大核心物理机制**：
  1. **State（全局状态黑板）**：所有节点共享的数据结构（在本项目中为 `AgentState`）。每个节点就像黑板前的值班员，读取黑板上的当前状态，擦写或追加自己的工作成果。
  2. **Nodes（执行节点）**：纯逻辑执行函数或异步协程（如 Planner、Executor、ToolRunner、Evaluator），输入当前 State，输出待合并的增量补丁（Patch）。
  3. **Edges（条件导流边）**：根据当前 State 中的度量指标（如连续报错数、里程碑完成度、预算水位），通过判断函数动态决定下一跳该流向哪一个节点，或是直接流向终点 `END`。

---

## 2. 本项目中的角色与调用链路

- **在本项目的位置**：智能体运行时编排核心（Agent Runtime Orchestration Layer）。
- **核心入口文件**：
  - 状态契约定义：[`AegisAgent/src/agent_runtime/state.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/state.py)
  - 状态图装配与编译：[`AegisAgent/src/agent_runtime/workflow.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/workflow.py)
  - 条件边路由表：[`AegisAgent/src/agent_runtime/routing.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/routing.py)
  - 检查点持久化：[`AegisAgent/src/agent_runtime/checkpoint.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/checkpoint.py)
- **典型执行流转链路**：
  ```text
  [Entry] ──► planner (宏观计划分解)
                 │
                 ▼
              budget_guard (物理配额与熔断守卫)
                 │
                 ▼
              executor (微观决策与工具参数生成)
                 │
                 ▼
              tool_runner (安全鉴权/HITL审批/并发工具执行)
                 │
                 ▼
              evaluator (反思自检与成果验收)
                 │
        ┌────────┴────────────────────────┐
        ▼                                 ▼
  [未达成/报错重试]                  [全部里程碑完成]
  流回 planner 或 executor           流向 END (任务交付)
  ```

---

## 3. 核心 Symbol 速查字典（类 / 函数 / 属性 / 装饰器）

### `StateGraph`（核心类）

- **通俗职责**：状态图构造器。用于定义状态模式、注册所有执行节点、设置图的初始入口点以及绑定节点之间的转移边。
- **签名/参数速查**：
  - `state_schema: Type[AgentState]`：全局状态的类型定义（在本项目中为 TypedDict）。
  - **返回值**：未编译的 `StateGraph` 实例。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/workflow.py:L432`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/workflow.py#L432)
- **最小实战代码**：
  ```python
  from langgraph.graph import StateGraph
  from agent_runtime.state import AgentState

  # 1. 实例化状态图
  graph = StateGraph(AgentState)
  # 2. 注册节点
  graph.add_node("planner", planner_node_fn)
  graph.add_node("executor", executor_node_fn)
  # 3. 设置入口点
  graph.set_entry_point("planner")
  # 4. 绑定条件边并编译
  app = graph.compile(checkpointer=checkpointer)
  ```
- **关键注意点**：`StateGraph` 注册节点与边之后必须调用 `.compile()` 生成可运行的 `CompiledGraph`。

---

### `add_messages`（Reducer 增量合并函数）

- **通俗职责**：消息列表的“智能追加器”。在多个节点更新消息时，自动根据消息 `id` 进行更新，或以成对原子追加的形式扩展消息链，防止全量覆盖。
- **签名/参数速查**：
  - `left: List[AnyMessage]`：现有历史消息列表。
  - `right: List[AnyMessage] | AnyMessage`：本次节点产出的新消息。
  - **返回值**：合并后的新消息列表。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/state.py:L133`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/state.py#L133)
- **最小实战代码**：
  ```python
  from typing import Annotated, List
  from langchain_core.messages import AnyMessage
  from langgraph.graph.message import add_messages

  class AgentState(TypedDict):
      # 声明该字段采用 add_messages 规则追加，而不是整数组替换覆盖
      messages: Annotated[List[AnyMessage], add_messages]
  ```
- **关键注意点**：如果不使用 `Annotated[..., add_messages]`，LangGraph 默认会将节点返回的 `messages` 直接全量覆盖旧状态，造成历史对话彻底丢失。

---

### `END`（哨兵终止常量）

- **通俗职责**：状态图流转的“终点站”。当条件边路由函数返回 `END` 时，状态图运行结束并进入终态。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/edges/base.py:L11`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/edges/base.py#L11)、[`AegisAgent/src/agent_runtime/edges/after_evaluator.py:L11`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/edges/after_evaluator.py#L11)
- **最小实战代码**：
  ```python
  from langgraph.graph import END

  def route_after_evaluator(state: AgentState) -> str:
      if state.get("should_terminate", False):
          return END  # 任务达成或熔断，直接终结
      return "executor"
  ```
- **关键注意点**：`END` 是一个特殊的内部字符串常量 `"__end__"`，在条件分支字典的目标集合映射中必须显式声明包含。

---

### `interrupt`（人机交互中断函数）

- **通俗职责**：主动“暂停”当前图的执行并将控制权交还给外部调用方（如等待人类管理员进行高危命令审批）。
- **签名/参数速查**：
  - `value: Any`：携带给外部的中断负载（如审批 ID、拟执行的高危 Shell 命令参数）。
  - **返回值**：外部使用 `Command(resume=...)` 恢复时传入的审批决策结果（如 `{"approved": True}`）。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/nodes/tool_runner.py:L41`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/nodes/tool_runner.py#L41)
- **最小实战代码**：
  ```python
  from langgraph.types import interrupt

  # 遇到越级高危操作时挂起状态机，等待前端 HITL 审批
  approval_payload = {"approval_id": "appr-123", "command": "rm -rf build/"}
  resume_decision = interrupt(approval_payload)

  if not resume_decision.get("approved"):
      raise PermissionError("管理员拒绝了本次高危执行！")
  ```
- **关键注意点**：调用 `interrupt()` 的图必须挂载持久化 Checkpointer（如 `AsyncSqliteSaver`），否则中断后内存状态丢失无法恢复。

---

### `Command`（控制指令包装类）

- **通俗职责**：用于在外部向已中断的状态图注入恢复数据，或者在节点内部同时更新状态并指示下一跳跳转。
- **签名/参数速查**：
  - `resume: Any`：恢复中断时传递的数据。
  - `update: Dict[str, Any]`：可选的状态补丁更新。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/workflow.py:L24`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/workflow.py#L24)
- **最小实战代码**：
  ```python
  from langgraph.types import Command

  # 恢复被 interrupt 挂起的任务并喂入管理员的审批决策
  await app.ainvoke(
      Command(resume={"approved": True, "decision": "once"}),
      config={"configurable": {"thread_id": task_id}},
  )
  ```
- **关键注意点**：`thread_id` 必须与挂起时的线程标识一致，否则无法正确定位 Checkpoint 快照。

---

## 4. 本项目典型用法与实操范式

### 范式 1：状态图声明式组装与编译
```python
# 路径：AegisAgent/src/agent_runtime/workflow.py
from langgraph.graph import StateGraph
from agent_runtime import routing
from agent_runtime.state import AgentState

def build_agent_graph(nodes: Mapping[str, NodeFn]) -> StateGraph:
    # 1. 绑定强类型 AgentState
    graph = StateGraph(AgentState)

    # 2. 批量注册节点函数
    for name, node_fn in nodes.items():
        graph.add_node(name, node_fn)

    # 3. 指定默认起点为 planner
    graph.set_entry_point("planner")

    # 4. 根据全局 routing.EDGE_TABLE 解耦注册所有条件跳转边
    for source, (router, targets) in routing.EDGE_TABLE.items():
        graph.add_conditional_edges(source, router, dict(targets))

    return graph
```

### 范式 2：流式事件驱动与权威终态回收
```python
# 路径：AegisAgent/src/agent_runtime/workflow.py
run_config = {"configurable": {"thread_id": task.state["task_id"]}}

# 1. stream_mode="updates" 逐节点捕获增量事件，通过 SSE 实时推送到前端
async for node_name, node_update in app.astream(
    graph_input, config=run_config, stream_mode="updates"
):
    await emit_sse_event(node_name, node_update)

# 2. 执行结束后，严禁手工合并增量！必须使用 aget_state 获取经由 Reducer 裁决的最终权威状态
snapshot = await app.aget_state(run_config)
final_state = snapshot.values
```

---

## 5. 新手易错陷阱与排坑指南

> [!warning] 陷阱 1：AIMessage 带有 tool_calls 但未成对返回 ToolMessage
> **现象**：大模型接口抛出 HTTP 400 错误：`Invalid parameter: messages with tool_calls must be followed by tool messages`。
> **原因**：当 Executor 节点的 `AIMessage` 触发了工具调用后，如果后续节点或裁剪逻辑截断了对话，导致没有对应的 `ToolMessage` 紧随其后，OpenAI 协议会直接拒绝请求。
> **正解**：本项目在 [`state.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/state.py) 与 [`context.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/context.py) 中严格落地了**“Atomic Pair（原子成对）”**保证：`AIMessage(tool_calls)` 与 `ToolMessage` 必须成对保留或成对移除，绝不可割裂。

> [!warning] 陷阱 2：异步图节点中忘记返回 Dict 增量补丁
> **现象**：节点明明执行成功了，但下一个节点拿到的 State 字段完全没有变化。
> **原因**：LangGraph 的节点函数必须返回一个 `Dict[str, Any]` 作为状态补丁。如果节点函数结尾遗漏了 `return {"step_count": count}`（或者返回了 None），LangGraph 会认为本步对黑板没有任何改动。
> **正解**：每个节点必须明确返回自己有权写入的字段字典（参考 [`AgentState`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/state.py#L102) 头部注明的字段责任划分）。

> [!warning] 陷阱 3：中断恢复时漏配 checkpointer
> **现象**：调用 `interrupt()` 时抛出 `ValueError: Checkpointer required for interrupts`。
> **正解**：任何支持挂起和恢复的状态图，在 `.compile()` 时必须显式传入 `checkpointer=AsyncSqliteSaver(...)`。
