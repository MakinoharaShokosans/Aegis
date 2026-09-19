"""微观执行上下文的生命周期管理（Spawn / Evolution / Distillation / Teardown）。

对应 ``documents/agent_runtime/07_execution_context_management.md`` 的四阶段。

**边界纪律**（本模块最容易做错的地方）：

* 本模块**只**负责"把状态造出来"与"把状态收干净"，不参与任何推理决策；
* ``ExecutionContext`` 是内存视图，**不进 Checkpoint**；真正被 LangGraph 持久化的是
  ``AgentState``；
* Teardown 阶段必须完成两件事：① 全量链路落盘 ``storage/traces/{task_id}.jsonl``；
  ② 把本轮结论回写会话记忆并触发水位压缩——**内部执行细节绝不进入下一轮人机对话**。
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from loguru import logger

from agent_runtime.guardrails.canary import derive_session_canary, generate_canary_token, sanitize_canary
from agent_runtime.memory.manager import MemoryManager
from agent_runtime.observability.trajectory import TrajectoryRecorder
from agent_runtime.state import AgentState, FailedAttempt, Milestone

__all__ = ["ExecutionContextManager", "build_initial_state"]


def _turns_to_messages(turns: Sequence[Any]) -> List[BaseMessage]:
    """把会话流水轮次还原为 LangChain 消息。

    Args:
        turns: ``TurnRecord`` 序列（时间正序）。

    Returns:
        消息列表：``user`` → HumanMessage，``assistant`` → AIMessage。
    """
    messages: List[BaseMessage] = []
    for turn in turns:
        content = getattr(turn, "content", "")
        if getattr(turn, "role", "") == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    return messages


def build_initial_state(
    *,
    workspace_id: str,
    workspace_path: str,
    session_id: str,
    task_goal: str,
    task_id: Optional[str] = None,
    canary_token: Optional[str] = None,
    active_turns: Sequence[Any] = (),
    rolling_summary: str = "",
    confirmed_facts: Optional[Sequence[str]] = None,
    failed_attempts: Optional[Sequence[FailedAttempt]] = None,
    permission_level: str = "workspace_write",
) -> AgentState:
    """构造任务的初始 ``AgentState``（Spawn 阶段）。

    所有物理度量从零起步；认知记忆从会话层继承——这正是"新任务不重复踩坑"的来源。
    金丝雀 Token 默认与 ``session_id`` 绑定派生，确保同一会话内多轮对话的 Prompt 前缀缓存 100% 命中。

    Args:
        workspace_id: 工作区标识。
        workspace_path: 工作区物理根路径（工具执行 cwd）。
        session_id: 会话标识。
        task_goal: 任务目标（永久锚定，不被修剪）。
        task_id: 任务 ID；缺省自动生成 UUID。
        canary_token: 任务 Canary Token；缺省由 session_id 派生会话级唯一 Token。
        active_turns: 低水位线以上的活跃对话轮次。
        rolling_summary: 会话已压缩摘要。
        confirmed_facts: 会话已确认事实。
        failed_attempts: 会话踩坑记录。
        permission_level: 会话权限基线（三级分级管控）。

    Returns:
        全新的 :class:`AgentState`。
    """
    init_messages = _turns_to_messages(active_turns)
    # 标准会话时序模型：将当前轮次任务目标作为最新的 HumanMessage 注入消息序列尾部
    # 严格遵循主流 LLM 的 [Turn1_User, Turn1_AI, ..., Current_User] 预训练注意力分布
    if task_goal and (not init_messages or not (isinstance(init_messages[-1], HumanMessage) and init_messages[-1].content == task_goal)):
        init_messages.append(HumanMessage(content=task_goal))

    token = canary_token or derive_session_canary(session_id)

    return AgentState(
        workspace_id=workspace_id,
        workspace_path=workspace_path,
        session_id=session_id,
        task_id=task_id or str(uuid.uuid4()),
        task_goal=task_goal,
        milestones=[],
        current_milestone_idx=0,
        messages=init_messages,
        rolling_summary=rolling_summary,
        confirmed_facts=list(confirmed_facts or []),
        failed_attempts=list(failed_attempts or []),
        permission_level=permission_level,
        artifacts={},
        step_count=0,
        total_tokens=0,
        consecutive_errors=0,
        fingerprint_history=[],
        canary_token=token,
        should_terminate=False,
        termination_reason="",
    )


class ExecutionContextManager:
    """单任务执行上下文的收尾管理器。

    Args:
        memory: 记忆管理器（用于回写会话流水与触发水位压缩）。
        recorder: 轨迹记录器。
    """

    __slots__ = ("_memory", "_recorder")

    def __init__(self, memory: MemoryManager, recorder: TrajectoryRecorder) -> None:
        self._memory = memory
        self._recorder = recorder

    async def finalize(
        self,
        state: Mapping[str, Any],
        delivery: str,
        last_action_target: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        """任务终结（Teardown 阶段）：沉淀因果、回写记忆。

        Args:
            state: 终态 ``AgentState``。
            delivery: 面向用户的交付结论（不含内部执行细节）。
            last_action_target: 本轮核心修改实体（文件/符号句柄）。
        """
        task_id = str(state.get("task_id", ""))
        canary_token = str(state.get("canary_token") or "")
        safe_delivery = sanitize_canary(delivery, canary_token) if canary_token else delivery

        await self._recorder.record(
            record_type="final",
            node="workflow",
            phase="reflecting",
            thought=str(state.get("termination_reason") or ""),
            observation_summary=safe_delivery[:1000],
            ok=bool(state.get("should_terminate")),
            step_count=int(state.get("step_count", 0)),
            total_tokens=int(state.get("total_tokens", 0)),
            consecutive_errors=int(state.get("consecutive_errors", 0)),
        )

        try:
            await self._memory.record_turn_and_maybe_compact(
                session_id=str(state.get("session_id", "")),
                user_query=str(state.get("task_goal", "")),
                agent_delivery=safe_delivery,
                last_action_target=last_action_target,
                workspace_id=str(state.get("workspace_id", "default")),
            )
        except Exception as exc:  # noqa: BLE001 - 记忆回写失败不应让已完成的交付变成失败
            logger.error(f"[ExecutionContext] 会话记忆回写失败（任务结果仍然有效）: {exc}")

        logger.info(
            f"[ExecutionContext] 任务 {task_id} 已收敛: "
            f"步数={state.get('step_count')} Token={state.get('total_tokens')} "
            f"原因={state.get('termination_reason')}"
        )

    @staticmethod
    def extract_delivery(state: Mapping[str, Any]) -> str:
        """从终态中抽取最后一条面向用户的交付文本（自动脱敏 Canary Token）。

        Args:
            state: 终态 ``AgentState``。

        Returns:
            最后一条 AIMessage 的文本内容；不存在时回退为终止原因。
        """
        canary_token = str(state.get("canary_token") or "")
        delivery = ""
        for message in reversed(list(state.get("messages") or [])):
            if isinstance(message, AIMessage) and message.content:
                delivery = str(message.content)
                break
        if not delivery:
            delivery = str(state.get("termination_reason") or "任务结束")

        if canary_token:
            delivery = sanitize_canary(delivery, canary_token)
        return delivery

    @staticmethod
    def collect_failed_attempts(state: Mapping[str, Any]) -> List[FailedAttempt]:
        """导出本任务沉淀的踩坑记录（供工作区级上浮）。

        Args:
            state: 终态 ``AgentState``。

        Returns:
            本任务的踩坑记录列表。
        """
        return [attempt for attempt in (state.get("failed_attempts") or []) if isinstance(attempt, FailedAttempt)]

    @staticmethod
    def collect_milestones(state: Mapping[str, Any]) -> List[Milestone]:
        """导出里程碑列表（供报告渲染）。

        Args:
            state: 终态 ``AgentState``。

        Returns:
            里程碑列表。
        """
        return [milestone for milestone in (state.get("milestones") or []) if isinstance(milestone, Milestone)]
