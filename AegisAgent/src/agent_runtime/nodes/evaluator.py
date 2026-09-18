"""``evaluator`` 节点：里程碑验收与认知事实沉淀（reasoning 层）。

对应 ``documents/agent_runtime/03_node_specification.md`` §4.4。

**为什么必须由独立节点验收**：让"干活的"自己宣布完工，等于没有验收。
planner 主张里程碑完成，evaluator 独立复核并可以**打回**（不标记完成），
同时把本轮暴露出的事实与踩坑沉淀为跨轮次记忆。

**与 :class:`~agent_runtime.memory.compactor.MemoryCompactor` 的分工**：
本节点处理**任务级**里程碑验收（reasoning 层，重判断质量）；
压缩器处理**会话级**历史轮次压缩（fast 层，重成本）。二者层级不同，禁止混用。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Mapping, Optional

from langchain_core.messages import AIMessage
from loguru import logger

from agent_runtime.context import ContextManager
from agent_runtime.errors import LLMUnavailableError
from agent_runtime.guardrails.canary import detect_canary_leak
from agent_runtime.llm.client import LLMGateway, to_openai_messages
from agent_runtime.nodes.base import (
    NodeFn,
    coerce_failed_attempts,
    coerce_milestones,
    extract_json_object,
    merge_unique,
)
from agent_runtime.observability.event_bus import TaskEventBus
from agent_runtime.observability.trajectory import TrajectoryRecorder
from agent_runtime.prompt_loader import PromptLibrary
from agent_runtime.state import Milestone

__all__ = ["build_evaluator_node"]


def _mark_milestone_completed(milestones: List[Milestone], index: int) -> List[Milestone]:
    """把指定下标的里程碑标记为已完成。

    Args:
        milestones: 里程碑列表。
        index: 目标下标。

    Returns:
        新的里程碑列表（不修改入参）。
    """
    if not (0 <= index < len(milestones)):
        return list(milestones)
    target_id = milestones[index].id
    return [
        milestone.model_copy(update={"status": "completed"}) if milestone.id == target_id else milestone
        for milestone in milestones
    ]


def build_evaluator_node(
    gateway: LLMGateway,
    context: ContextManager,
    prompts: PromptLibrary,
    recorder: Optional[TrajectoryRecorder] = None,
    event_bus: Optional[TaskEventBus] = None,
) -> NodeFn:
    """构造 ``evaluator`` 节点。

    Args:
        gateway: 双模型网关。
        context: 上下文装配器。
        prompts: 提示词库。
        recorder: 轨迹记录器（可选旁路）。
        event_bus: 事件总线（可选旁路）。

    Returns:
        节点函数。
    """

    async def evaluator(state: Mapping[str, Any]) -> Dict[str, Any]:
        """复核里程碑达成情况并沉淀认知记忆。

        Args:
            state: ``AgentState``（只读）。

        Returns:
            里程碑、摘要、事实、踩坑与终止标记的增量。
        """
        messages = context.assemble(state, node_instruction=prompts.load("evaluator"))
        step_num = int(state.get("step_count", 0))

        t0 = time.time()
        try:
            response = await gateway.invoke("reasoning", messages, force_json=True)
        except LLMUnavailableError as exc:
            logger.error(f"[Evaluator] LLM 全链路不可用: {exc}")
            if event_bus is not None:
                await event_bus.emit({
                    "event": "llm.call",
                    "id": f"llm-evaluator-{step_num}-{time.time()}",
                    "node": "evaluator",
                    "step": step_num,
                    "tier": "reasoning",
                    "model": "reasoning-model",
                    "messages": to_openai_messages(messages),
                    "tools": None,
                    "response": {"content": "", "tool_calls": [], "finish_reason": "error"},
                    "tokens": 0,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "error": str(exc),
                })
            return {"should_terminate": True, "termination_reason": f"LLM 不可用: {exc}"}

        duration_ms = int((time.time() - t0) * 1000)
        if event_bus is not None:
            await event_bus.emit({
                "event": "llm.call",
                "id": f"llm-evaluator-{step_num}-{time.time()}",
                "node": "evaluator",
                "step": step_num,
                "tier": "reasoning",
                "model": response.endpoint_name or "gpt-5.6-terra",
                "messages": to_openai_messages(messages),
                "tools": None,
                "response": {
                    "content": response.content,
                    "tool_calls": response.tool_calls,
                    "finish_reason": response.finish_reason or "stop",
                },
                "tokens": response.total_tokens,
                "duration_ms": duration_ms,
            })

        tokens_after = int(state.get("total_tokens", 0)) + response.total_tokens

        # ------------------------------------------------------------------
        # 安全防御：Canary Token 泄露检测
        # ------------------------------------------------------------------
        canary_token = str(state.get("canary_token") or "")
        if canary_token and detect_canary_leak(response.content, canary_token):
            logger.critical("[Evaluator] 安全熔断：检测到 Canary Token 泄露！")
            if recorder is not None:
                await recorder.record(
                    record_type="guard",
                    node="evaluator",
                    phase="reflecting",
                    thought="[SECURITY] Canary Token leak detected in evaluator response",
                    ok=False,
                    step_count=int(state.get("step_count", 0)),
                    total_tokens=tokens_after,
                )
            return {
                "should_terminate": True,
                "termination_reason": "[SECURITY] Prompt leak detected via canary token",
                "total_tokens": tokens_after,
            }

        verdict = extract_json_object(response.content) or {}
        if not verdict:
            logger.warning("[Evaluator] 未能解析结构化验收结论，按未达成处理")

        milestones: List[Milestone] = coerce_milestones(list(state.get("milestones") or []))
        current_index = int(state.get("current_milestone_idx", 0))

        existing_msgs = list(state.get("messages") or [])
        latest_msg = existing_msgs[-1] if existing_msgs else None
        has_direct_reply = isinstance(latest_msg, AIMessage) and bool(latest_msg.content) and not getattr(latest_msg, "tool_calls", None)

        accepted = bool(
            verdict.get("milestone_ok")
            or verdict.get("is_completed")
            or verdict.get("all_completed")
            or str(verdict.get("status", "")).lower() == "completed"
        )

        all_completed = bool(
            verdict.get("all_completed")
            or (accepted and (not milestones or current_index >= len(milestones) - 1))
        )

        if accepted and milestones:
            if all_completed:
                milestones = [m.model_copy(update={"status": "completed"}) for m in milestones]
            else:
                milestones = _mark_milestone_completed(milestones, current_index)
        elif accepted and not milestones:
            all_completed = True

        all_done = (
            all(milestone.status == "completed" for milestone in milestones)
            if milestones
            else all_completed
        )

        # 验收通过且仍有后续里程碑时，推进指针；全部完成则保持在末尾
        next_index = min(current_index + 1, len(milestones) - 1) if (accepted and milestones) else current_index

        summary = str(verdict.get("summary") or state.get("rolling_summary") or "").strip()
        confirmed_facts = merge_unique(
            state.get("confirmed_facts") or [],
            [str(item) for item in (verdict.get("confirmed_facts") or [])],
        )
        failed_attempts = list(state.get("failed_attempts") or []) + coerce_failed_attempts(
            verdict.get("failed_attempts")
        )

        logger.info(
            f"[Evaluator] 验收结果={'通过' if accepted else '未通过'}，"
            f"里程碑完成 {sum(1 for m in milestones if m.status == 'completed')}/{len(milestones)}"
        )

        if recorder is not None:
            await recorder.record(
                record_type="node",
                node="evaluator",
                phase="reflecting",
                thought=summary[:1000],
                ok=accepted,
                step_count=int(state.get("step_count", 0)),
                total_tokens=int(state.get("total_tokens", 0)) + response.total_tokens,
                consecutive_errors=int(state.get("consecutive_errors", 0)),
            )

        if not accepted:
            msg_updates = [
                AIMessage(
                    content=f"【阶段验收未通过，需要继续推进】{summary or '当前目标尚未达成，请调度相应工具完成实际操作。'}"
                )
            ]
        elif has_direct_reply:
            msg_updates = []
        else:
            msg_updates = [AIMessage(content=summary or response.content or "验收完成。")]

        return {
            "messages": msg_updates,
            "milestones": milestones,
            "current_milestone_idx": next_index,
            "rolling_summary": summary,
            "confirmed_facts": confirmed_facts,
            "failed_attempts": failed_attempts,
            "should_terminate": all_done,
            "termination_reason": "task_goal achieved" if all_done else "",
            "total_tokens": int(state.get("total_tokens", 0)) + response.total_tokens,
        }

    return evaluator
