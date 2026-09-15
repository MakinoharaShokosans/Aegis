"""``budget_guard`` 节点：物理预算守卫的薄包装。

**为什么是薄节点**：全部熔断逻辑属于确定性策略，已在
:class:`agent_runtime.guardrails.physical_budget.PhysicalBudgetGuard` 中实现并可独立单测。
节点只负责"把策略结论翻译成状态增量"，不含任何判断逻辑。
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from langchain_core.messages import SystemMessage
from loguru import logger

from agent_runtime.guardrails.physical_budget import PhysicalBudgetGuard
from agent_runtime.nodes.base import NodeFn

__all__ = ["build_budget_guard_node"]


def build_budget_guard_node(guard: PhysicalBudgetGuard) -> NodeFn:
    """构造 ``budget_guard`` 节点。

    Args:
        guard: 任务级预算守卫实例（持有挂钟起点）。

    Returns:
        节点函数。
    """

    async def budget_guard(state: Mapping[str, Any]) -> Dict[str, Any]:
        """执行硬熔断检查与软告警注入。

        Args:
            state: ``AgentState``（只读）。

        Returns:
            ``should_terminate`` / ``termination_reason`` 或告警消息增量。
        """
        terminated, reason = guard.check(state)
        if terminated:
            logger.error(f"[BudgetGuard] 触发物理熔断: {reason}")
            return {"should_terminate": True, "termination_reason": reason or "预算熔断"}

        alerts = guard.warnings(state)
        if alerts:
            alert_text = "\n".join(alerts) + "\n\n请收敛方案并尽快交付结论。"
            return {"messages": [SystemMessage(content=alert_text)]}

        return {}

    return budget_guard
