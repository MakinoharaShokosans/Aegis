"""``evaluator`` 之后的路由。

验收通过（``should_terminate`` 为真）即交付结束；否则回到 ``planner``
继续推进尚未达成的里程碑。
"""

from __future__ import annotations

from typing import Any, Mapping

from langgraph.graph import END
from loguru import logger

from agent_runtime.edges.base import RouterFn, is_hard_terminated, resolve_targets

__all__ = ["TARGETS", "route_after_evaluator"]

TARGETS = resolve_targets("planner")


def route_after_evaluator(state: Mapping[str, Any]) -> str:
    """``evaluator`` 输出后的路由决策。

    Args:
        state: ``AgentState``（只读）。

    Returns:
        ``"planner"`` 或 ``END``。
    """
    if is_hard_terminated(state):
        logger.info("[Router] 验收通过，任务交付")
        return END
    return "planner"


assert_router_type: RouterFn = route_after_evaluator
