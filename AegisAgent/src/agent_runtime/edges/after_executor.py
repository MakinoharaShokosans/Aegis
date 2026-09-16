"""``executor`` 之后的路由（HITL 引入后指向 ``tool_runner``）。

``executor`` 只生成 ``tool_calls`` 不执行，因此这里必然进入 ``tool_runner``
（后者负责权限闸门与实际派发）。若 ``executor`` 未产生工具调用，
``tool_runner`` 会直接返回空增量，图随即回到 ``planner``——
多一次空跳的代价远低于在边里做消息内容判断的复杂度。
"""

from __future__ import annotations

from typing import Any, Mapping

from langgraph.graph import END
from loguru import logger

from agent_runtime.edges.base import RouterFn, is_hard_terminated, resolve_targets

__all__ = ["TARGETS", "route_after_executor"]

TARGETS = resolve_targets("tool_runner")


def route_after_executor(state: Mapping[str, Any]) -> str:
    """``executor`` 输出后的路由决策。

    Args:
        state: ``AgentState``（只读）。

    Returns:
        ``"tool_runner"`` 或 ``END``。
    """
    if is_hard_terminated(state):
        logger.warning(f"[Router] executor 熔断: {state.get('termination_reason', '')}")
        return END
    return "tool_runner"


assert_router_type: RouterFn = route_after_executor
