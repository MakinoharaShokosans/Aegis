"""``executor`` 之后的路由（HITL 引入后指向 ``tool_runner`` 或 ``evaluator``）。

``executor`` 负责将 planner 指令翻译为 ``tool_calls``（或直接输出文本答复）。
- 若产生了工具调用：流转至 ``tool_runner`` 负责权限闸门与实际派发；
- 若本轮未产生工具调用（纯问答/自然语言回答/无工具需求）：直接流转至 ``evaluator`` 验收与收敛，避免无脑回跳 planner 造成死循环。
"""

from __future__ import annotations

from typing import Any, Mapping

from langgraph.graph import END
from loguru import logger

from agent_runtime.edges.base import RouterFn, is_hard_terminated, resolve_targets
from agent_runtime.nodes.base import latest_ai_message, to_tool_call_specs

__all__ = ["TARGETS", "route_after_executor"]

TARGETS = resolve_targets("tool_runner", "evaluator")


def route_after_executor(state: Mapping[str, Any]) -> str:
    """``executor`` 输出后的路由决策。

    Args:
        state: ``AgentState``（只读）。

    Returns:
        ``"tool_runner"``、``"evaluator"`` 或 ``END``。
    """
    if is_hard_terminated(state):
        logger.warning(f"[Router] executor 熔断: {state.get('termination_reason', '')}")
        return END

    assistant = latest_ai_message(list(state.get("messages") or []))
    specs = to_tool_call_specs(getattr(assistant, "tool_calls", None) or [])
    if not specs:
        logger.info("[Router] executor 本轮未产生工具调用，流转至 evaluator 验收/收敛")
        return "evaluator"

    return "tool_runner"


assert_router_type: RouterFn = route_after_executor

