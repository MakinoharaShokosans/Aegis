"""``planner`` 节点：宏观规划与反思重规划（reasoning 层）。

对应 ``documents/agent_runtime/03_node_specification.md`` §4.1。

**关键设计**：planner **不产出 ``tool_calls``**。它只输出"要做什么"的自然语言决策指令
与里程碑状态变更；"具体调用哪个工具的哪些参数"下沉给 fast 层的 ``executor``。
这样 reasoning 模型专注高价值判断，便宜快速的模型承担格式化的动作翻译。

**结构化输出**：为了能确定性更新里程碑，本节点强制 JSON 输出::

    {"thought": "...", "milestone_updates": [{"id": 1, "status": "completed"}], "next_step": "..."}

解析失败时**优雅降级**：把原始文本当作决策指令，不改动里程碑（不因格式问题中断任务）。
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from langchain_core.messages import AIMessage
from loguru import logger

from agent_runtime.context import ContextManager
from agent_runtime.errors import LLMUnavailableError
from agent_runtime.llm.client import LLMGateway
from agent_runtime.nodes.base import (
    NodeFn,
    apply_milestone_updates,
    coerce_milestones,
    extract_json_object,
)
from agent_runtime.observability.trajectory import TrajectoryRecorder
from agent_runtime.prompt_loader import PromptLibrary

__all__ = ["build_planner_node"]


def build_planner_node(
    gateway: LLMGateway,
    context: ContextManager,
    prompts: PromptLibrary,
    recorder: Optional[TrajectoryRecorder] = None,
) -> NodeFn:
    """构造 ``planner`` 节点。

    Args:
        gateway: 双模型网关。
        context: 上下文装配器。
        prompts: 提示词库。
        recorder: 轨迹记录器（可选旁路）。

    Returns:
        节点函数。
    """

    async def planner(state: Mapping[str, Any]) -> Dict[str, Any]:
        """产出下一步决策指令并更新里程碑状态。

        Args:
            state: ``AgentState``（只读）。

        Returns:
            消息、里程碑与 Token 计数增量；LLM 全链路不可用时置位熔断。
        """
        messages = context.assemble(state, node_instruction=prompts.load("planner"))

        try:
            response = await gateway.invoke("reasoning", messages, force_json=True)
        except LLMUnavailableError as exc:
            logger.error(f"[Planner] LLM 全链路不可用: {exc}")
            return {"should_terminate": True, "termination_reason": f"LLM 不可用: {exc}"}

        verdict = extract_json_object(response.content) or {}
        if not verdict and response.content:
            logger.warning("[Planner] 未能解析结构化输出，降级为纯文本指令")

        thought = str(verdict.get("thought") or response.content or "").strip()
        directive = str(verdict.get("next_step") or thought).strip()

        # 首次规划：由 planner 产出完整里程碑计划；后续轮次只做状态增量更新。
        # 这样"里程碑"是模型自主分解的产物，而不是硬编码的固定流程。
        existing = list(state.get("milestones") or [])
        if not existing and verdict.get("milestones"):
            milestones = coerce_milestones(verdict["milestones"])
        else:
            milestones = apply_milestone_updates(existing, verdict.get("milestone_updates"))

        logger.info(f"[Planner] 决策指令已生成（tokens={response.total_tokens}）")

        if recorder is not None:
            await recorder.record(
                record_type="node",
                node="planner",
                phase="planning",
                thought=thought[:1000],
                step_count=int(state.get("step_count", 0)),
                total_tokens=int(state.get("total_tokens", 0)) + response.total_tokens,
                consecutive_errors=int(state.get("consecutive_errors", 0)),
            )

        return {
            "messages": [AIMessage(content=directive or "继续推进当前里程碑。")],
            "milestones": milestones,
            "total_tokens": int(state.get("total_tokens", 0)) + response.total_tokens,
        }

    return planner
