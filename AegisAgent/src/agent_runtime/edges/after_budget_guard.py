"""``budget_guard`` 之后的路由。

预算守卫只有两种结局：熔断（``END``）或放行（``executor``）。
"""

from __future__ import annotations

from typing import Any, Mapping

from langgraph.graph import END
from loguru import logger

from agent_runtime.edges.base import RouterFn, is_hard_terminated, resolve_targets

__all__ = ["TARGETS", "route_after_budget_guard"]

TARGETS = resolve_targets("executor")


def route_after_budget_guard(state: Mapping[str, Any]) -> str:
    """``budget_guard`` 输出后的路由决策。

    Args:
        state: ``AgentState``（只读）。

    Returns:
        ``"executor"`` 或 ``END``。
    """
    if is_hard_terminated(state):
        logger.warning(f"[Router] 预算守卫熔断: {state.get('termination_reason', '')}")
        return END
    return "executor"


assert_router_type: RouterFn = route_after_budget_guard
