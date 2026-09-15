"""AgentState 与共享领域模型契约（**唯一真源**）。

对齐 ``documents/agent_runtime/02_state_definition.md``，遵守四条纪律：

1. **物理指标替代外部计费**：只保留 ``total_tokens`` / ``step_count`` / 挂钟时间，
   坚决不含 ``cost_usd`` 之类不可控的费用字段；
2. **原子消息对**：``messages`` 依赖 ``add_messages`` Reducer，保证
   ``AIMessage(tool_calls)`` 与其配对的 ``ToolMessage`` 不被割裂（否则端点返回 400）；
3. **共享模型唯一真源**：:class:`Milestone` 与 :class:`FailedAttempt` 由本模块独家定义，
   ``memory/`` 等模块一律 **import 复用**，禁止自持第二份定义；
4. **纯契约层**：本模块零 I/O、零业务依赖。

``AgentState`` 与 ``ExecutionContext`` 的关系（见 ``07_execution_context_management.md``）：
前者是 LangGraph 的 Checkpoint 持久化单位；后者是单任务在内存中的运行时视图，
字段同名同义，任务终结即擦除，仅把结论回写 ``AgentState``。
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# ==============================================================================
# 字面量类型
# ==============================================================================

MilestoneStatus = Literal["pending", "in_progress", "completed", "failed"]
"""里程碑状态。"""

StepPhase = Literal["planning", "executing", "reflecting"]
"""执行步骤所处阶段。"""

TaskStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "terminated"]
"""任务对外可见的生命周期状态。

迁移关系::

    queued ──► running ──┬──► succeeded    (evaluator 判定里程碑全部达成)
                         ├──► terminated   (物理预算熔断)
                         ├──► failed       (不可恢复异常，如 LLM 全链路不可用)
                         └──► cancelled    (客户端主动取消)

    terminated / failed ──► running   (POST /resume)
"""


# ==============================================================================
# 共享领域模型（全工程唯一真源）
# ==============================================================================

class Milestone(BaseModel):
    """阶段里程碑定义。"""

    id: int = Field(description="里程碑序号（自增，从 1 开始）")
    title: str = Field(description="里程碑标题")
    description: str = Field(default="", description="达成标准与验收说明")
    status: MilestoneStatus = Field(default="pending", description="当前状态")


class FailedAttempt(BaseModel):
    """已证伪的错误尝试（负向记忆，防止 Agent 原地打转重复踏坑）。"""

    action: str = Field(description="曾尝试的具体操作（命令、参数或修改）")
    failure_reason: str = Field(description="失败的核心报错摘要")
    conclusion: str = Field(description="沉淀的禁区结论（严禁再犯）")


class StepRecord(BaseModel):
    """单步执行记录（内存态审计视图，不进入 Checkpoint 以避免 State 膨胀）。"""

    step_id: int = Field(description="步序号")
    phase: StepPhase = Field(description="所属阶段")
    thought: str = Field(default="", description="该步的推理摘要")
    tool_name: str = Field(default="", description="调用的工具名（无工具时为空）")
    tool_args: Dict[str, object] = Field(default_factory=dict, description="工具入参（已脱敏）")
    observation_summary: str = Field(default="", description="精炼后的观察值摘要")
    raw_artifact_path: str = Field(default="", description="全量原始输出的离线落盘句柄")


# ==============================================================================
# LangGraph 状态契约（Checkpoint 持久化单位）
# ==============================================================================

class AgentState(TypedDict):
    """Aegis Agent 全局执行状态。

    字段写入责任划分（防止多节点争抢同一字段）：

    * ``planner``      : ``milestones`` / ``current_milestone_idx`` / ``messages`` / ``total_tokens``
    * ``budget_guard`` : ``should_terminate`` / ``termination_reason``
    * ``executor``     : ``step_count`` / ``total_tokens`` / ``consecutive_errors`` /
      ``fingerprint_history`` / ``artifacts`` / ``messages``
    * ``evaluator``    : ``rolling_summary`` / ``confirmed_facts`` / ``failed_attempts`` /
      ``milestones`` / ``should_terminate``
    """

    # --------------------------------------------------------------------------
    # 0. 工作区与会话归属（全生命周期不变）
    # --------------------------------------------------------------------------
    workspace_id: str
    workspace_path: str
    session_id: str

    # --------------------------------------------------------------------------
    # 1. 任务元数据与里程碑规划
    # --------------------------------------------------------------------------
    task_id: str
    task_goal: str
    milestones: List[Milestone]
    current_milestone_idx: int

    # --------------------------------------------------------------------------
    # 2. 对话上下文与认知记忆
    # --------------------------------------------------------------------------
    messages: Annotated[List[AnyMessage], add_messages]
    rolling_summary: str
    confirmed_facts: List[str]
    failed_attempts: List[FailedAttempt]

    # --------------------------------------------------------------------------
    # 3. 产物句柄（artifact_id -> 磁盘绝对路径）
    # --------------------------------------------------------------------------
    artifacts: Dict[str, str]

    # --------------------------------------------------------------------------
    # 4. 物理预算与防御度量
    # --------------------------------------------------------------------------
    step_count: int
    total_tokens: int
    consecutive_errors: int
    fingerprint_history: List[str]

    # --------------------------------------------------------------------------
    # 5. 安全防御与执行控制标记
    # --------------------------------------------------------------------------
    canary_token: str
    should_terminate: bool
    termination_reason: str


# ==============================================================================
# 微观执行上下文契约（内存态运行时视图）
# ==============================================================================

class ExecutionContext(TypedDict):
    """单任务执行草稿纸视图（不进 Checkpoint）。

    详见 ``07_execution_context_management.md``。与 :class:`AgentState` 相比，
    额外持有 ``step_history``（本任务全量步骤留痕），该字段在 Teardown 阶段
    落盘到 ``storage/traces/{task_id}.jsonl`` 后即被丢弃。
    """

    task_id: str
    task_goal: str
    confirmed_facts: List[str]
    failed_attempts: List[FailedAttempt]
    messages: Annotated[List[AnyMessage], add_messages]
    step_history: List[StepRecord]
    artifacts: Dict[str, str]
    last_action_target: Dict[str, List[str]]
    step_count: int
    total_tokens: int
    consecutive_errors: int
    fingerprint_history: List[str]
    canary_token: str
    should_terminate: bool
    termination_reason: str


__all__ = [
    "AgentState",
    "ExecutionContext",
    "FailedAttempt",
    "Milestone",
    "MilestoneStatus",
    "StepPhase",
    "StepRecord",
    "TaskStatus",
]
