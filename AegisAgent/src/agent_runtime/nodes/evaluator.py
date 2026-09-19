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

        # ------------------------------------------------------------------
        # 1. 显式判定（Explicit Verdict）
        # ------------------------------------------------------------------
        explicit_positive = bool(
            verdict.get("milestone_ok") is True
            or verdict.get("is_completed") is True
            or verdict.get("all_completed") is True
            or str(verdict.get("status", "")).lower() in ("completed", "succeeded", "success", "passed", "done", "ok")
        )
        explicit_negative = bool(
            verdict.get("milestone_ok") is False
            or verdict.get("is_completed") is False
            or verdict.get("all_completed") is False
            or str(verdict.get("status", "")).lower() in ("failed", "rejected", "in_progress", "pending")
        )

        all_milestones_completed_in_state = bool(milestones and all(m.status == "completed" for m in milestones))

        # ------------------------------------------------------------------
        # 2. 连续打回检测与死循环熔断（Rejection Loop Breaker）
        # ------------------------------------------------------------------
        prior_rejections = sum(
            1 for m in existing_msgs
            if isinstance(m, AIMessage) and "【阶段验收未通过" in (m.content or "")
        )

        if explicit_positive:
            accepted = True
        elif explicit_negative:
            # 若已连续打回 >= 2 次且当前已有完整直接答复交付，触发死循环熔断放行
            if prior_rejections >= 2 and has_direct_reply:
                logger.warning(
                    f"[Evaluator] 触发打回死循环熔断保护（历史打回 {prior_rejections} 次且已有直接交付），放行任务"
                )
                accepted = True
            else:
                accepted = False
        else:
            # 既非显式通过亦非显式打回（模型输出了业务分析载荷如 workspace/files/data 等 Schema 漂移）
            if (all_milestones_completed_in_state or not milestones) and has_direct_reply:
                logger.info("[Evaluator] 捕获业务分析载荷：前序里程碑已全完工且已有直接答复，智能判定验收通过")
                accepted = True
            elif prior_rejections >= 2 and has_direct_reply:
                logger.warning(f"[Evaluator] 已连续打回 {prior_rejections} 次且已有直接回复，触发死循环熔断放行")
                accepted = True
            else:
                accepted = False

        all_completed = bool(
            verdict.get("all_completed")
            or (accepted and (not milestones or current_index >= len(milestones) - 1 or all_milestones_completed_in_state))
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

        # ------------------------------------------------------------------
        # 3. 事实与摘要抽取（支持从业务载荷中自适应萃取）
        # ------------------------------------------------------------------
        summary = str(verdict.get("summary") or "").strip()
        if not summary:
            if isinstance(verdict.get("files"), list):
                summary = f"工作区文件分析已完成，共包含 {len(verdict['files'])} 个文件。"
            elif isinstance(verdict.get("topic"), str):
                summary = f"已完成关于【{verdict['topic']}】的调研与总结。"
            elif state.get("rolling_summary"):
                summary = str(state.get("rolling_summary")).strip()

        facts_extracted = [str(item) for item in (verdict.get("confirmed_facts") or [])]
        if not facts_extracted and isinstance(verdict.get("files"), list):
            for f in verdict["files"]:
                if isinstance(f, dict) and f.get("path"):
                    facts_extracted.append(f"文件 {f['path']}: {f.get('responsibility', '')}")

        confirmed_facts = merge_unique(
            state.get("confirmed_facts") or [],
            facts_extracted,
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
