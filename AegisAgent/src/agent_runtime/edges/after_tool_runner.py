"""``tool_runner`` 之后的路由。

工具执行完毕（含被人工拒绝、被死循环拦截两种情况）统一回到 ``planner``：
* 执行成功 → planner 依据新观察值推进下一步；
* 被拒绝 → 观察值中已说明拒绝原因，planner 需给出合规的替代方案；
* 被拦截 → 已注入强制重规划通知。

硬熔断（预算耗尽 / 安全熔断）直达 ``END``。
"""

from __future__ import annotations

from typing import Any, Mapping

from langgraph.graph import END
from loguru import logger

from agent_runtime.edges.base import RouterFn, is_hard_terminated, resolve_targets

__all__ = ["TARGETS", "route_after_tool_runner"]

TARGETS = resolve_targets("planner")


def route_after_tool_runner(state: Mapping[str, Any]) -> str:
    """``tool_runner`` 输出后的路由决策。

    Args:
        state: ``AgentState``（只读）。

    Returns:
        ``"planner"`` 或 ``END``。
    """
    if is_hard_terminated(state):
        logger.warning(f"[Router] tool_runner 熔断: {state.get('termination_reason', '')}")
        return END
    return "planner"


assert_router_type: RouterFn = route_after_tool_runner
