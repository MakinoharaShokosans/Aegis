# AgentState 定义与状态管理规范

> **责任领域**：`AegisAgent/src/agent_runtime/state.py`  
> **核心原则**：强类型契约保障、原子消息对裁剪安全、物理预算确定性度量。

---

## 1. 核心状态架构设计

在 Aegis 中，`AgentState` 既是 LangGraph 状态图各节点之间流转的唯一数据介质，也是 SQLite Checkpoint 的持久化单位。

遵循三大设计纪律：
1. **物理指标替代外部计费**：坚决弃用不可控的 `cost_usd` 字段，以确定性的物理指标 `total_tokens` 与 `step_count` 实行硬熔断。
2. **原子消息对（Atomic Message Pair）契约**：依托 `langgraph.graph.message.add_messages` Reducer 纳管消息更新，确保 `AIMessage(tool_calls)` 与 `ToolMessage` 不被意外割裂。
3. **内聚结构化认知记忆**：在 State 中显式纳管 `confirmed_facts`、`failed_attempts` 与 `artifacts` 句柄，杜绝上下文失忆与重复踏坑。
4. **共享领域模型唯一真源**：`FailedAttempt` 与 `Milestone` 由本文件对应的 `state.py` **独家定义**；`memory/models.py` 等其它模块一律 **import 复用**，严禁重复声明同名结构（历史上 `memory/models.py` 曾自持一份 `FailedAttempt`，已裁决收敛到 `state.py`，见 `10_directory_structure.md` 裁决项⑤）。

---

## 2. 完整类型定义规范

```python
from typing import Annotated, List, Dict, Optional, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

# ==============================================================================
# 1. 结构化子模型定义
# ==============================================================================

class Milestone(BaseModel):
    """阶段里程碑定义"""
    id: int
    title: str
    description: str
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"

class FailedAttempt(BaseModel):
    """已证伪的错误尝试（负向踩坑记忆，防止原地打转）"""
    action: str              # 尝试的操作（如执行了某个命令或修改）
    failure_reason: str      # 报错核心摘要
    conclusion: str          # 沉淀的禁区结论（严禁重复使用）

# ==============================================================================
# 2. 全局 AgentState 强类型状态契约
# ==============================================================================

class AgentState(TypedDict):
    """
    Aegis Agent 全局执行状态
    """
    # --------------------------------------------------------------------------
    # 0. 工作区与会话归属元数据 (Workspace & Session Scopes)
    # --------------------------------------------------------------------------
    workspace_id: str                                    # 所属工作区唯一标识 (UUID 或路径哈希)
    workspace_path: str                                  # 所属工作区物理工程根目录绝对路径 (工具执行 CWD 基准)
    session_id: str                                      # 所属会话唯一标识 (UUID)

    # --------------------------------------------------------------------------
    # 1. 任务元数据与里程碑规划 (Task & Milestones)
    # --------------------------------------------------------------------------
    task_id: str                                         # 全局唯一任务 ID (UUID)
    task_goal: str                                       # 终极任务目标 (永久锚定，不被修剪)
    milestones: List[Milestone]                          # 阶段计划列表
    current_milestone_idx: int                           # 当前正在推进的里程碑索引
    
    # --------------------------------------------------------------------------
    # 2. 对话上下文与认知记忆 (Memory & Active Messages)
    # --------------------------------------------------------------------------
    messages: Annotated[List[AnyMessage], add_messages]  # 活跃对话消息列表 (遵循 Atomic Pair 裁剪)
    rolling_summary: str                                 # 阶段跃迁时沉淀的历史全局摘要
    confirmed_facts: List[str]                           # 已确认的客观技术事实
    failed_attempts: List[FailedAttempt]                 # 踩坑禁区记录
    
    # --------------------------------------------------------------------------
    # 3. 产物指针与离线大日志句柄 (Artifacts)
    # --------------------------------------------------------------------------
    artifacts: Dict[str, str]                            # 句柄映射 (artifact_id -> 磁盘绝对路径)
    
    # --------------------------------------------------------------------------
    # 4. 物理预算与防御度量 (Physical Budgets & Guardrails)
    # --------------------------------------------------------------------------
    step_count: int                                      # 当前累计执行总步数
    total_tokens: int                                    # 累计消耗 Token 总数 (确定性指标)
    consecutive_errors: int                              # 连续错误计数器 (达阈值强行回退重规划)
    fingerprint_history: List[str]                       # 最近 N 次工具参数 MD5 哈希历史 (防死循环)
    
    # --------------------------------------------------------------------------
    # 5. 执行控制标记 (Flow Control)
    # --------------------------------------------------------------------------
    should_terminate: bool                               # 终止熔断开关
    termination_reason: str                              # 终止原因描述
```

---

## 3. 状态更新与 Reducer 运行规则

### 3.1 消息列表：`add_messages` Reducer
* **自动追加与替换**：返回新的 `[AIMessage(...)]` 时，LangGraph 自动追加至 `state["messages"]`；
* **原子删除支持**：如需裁剪陈旧轮次，可下发 `RemoveMessage(id=...)`，`add_messages` 能够安全执行精确剔除；
* **成对剔除原则**：执行剪枝时，必须同时下发一组 `tool_calls` 的 `AIMessage` 及其对应的所有 `ToolMessage`，严防产生孤立消息。

### 3.2 连续错误计数器：`consecutive_errors`
* **重置与累加逻辑**：
  - 工具返回 `exit_code == 0` 且无异常：`consecutive_errors = 0`；
  - 工具返回非零退出码或网络报错：`consecutive_errors += 1`；
  - **熔断判定**：当 `consecutive_errors >= 3` 时，条件边拦截微观试错循环，强制拉出并流转至 `planner` 进行全局方案重审。

### 3.3 物理 Token 累加与监控
* 每轮 LLM 调用结束后，解析响应中的 `usage.total_tokens`：
  ```python
  new_total_tokens = state["total_tokens"] + response.usage.total_tokens
  ```
* 一旦 `new_total_tokens >= config.guardrails.max_total_tokens`，立即置位 `should_terminate = True` 并标记 `termination_reason = "Token budget exceeded"`。
