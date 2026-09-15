"""``executor`` 之后的路由。

**为什么这里几乎只有两个分支**：连续错误熔断与指纹死循环的**目的节点相同**
（都回 ``planner`` 强制重规划），差异只在 executor 追加了什么纠正消息。
把这种"看似有分支实则等价"的差异塞进返回值，只会制造伪复杂度。

因此本边只判断一件事：**是否已被硬熔断**。
"""

from __future__ import annotations

from typing import Any, Mapping

from langgraph.graph import END
from loguru import logger

from agent_runtime.edges.base import RouterFn, is_hard_terminated, resolve_targets

__all__ = ["TARGETS", "route_after_executor"]

TARGETS = resolve_targets("planner")


def route_after_executor(state: Mapping[str, Any]) -> str:
    """``executor`` 输出后的路由决策。

    Args:
        state: ``AgentState``（只读）。

    Returns:
        ``"planner"`` 或 ``END``。
    """
    if is_hard_terminated(state):
        logger.warning(f"[Router] executor 熔断: {state.get('termination_reason', '')}")
        return END
    return "planner"


assert_router_type: RouterFn = route_after_executor
