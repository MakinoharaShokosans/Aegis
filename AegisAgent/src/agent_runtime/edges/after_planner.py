"""``planner`` 之后的路由。

决策优先级（严格自上而下，命中即返回）：

1. **硬熔断** → ``END``（如 LLM 全链路不可用）；
2. **存在里程碑且全部完成** → ``evaluator``：任务的"自我声明完成"必须经过
   独立复核，不能由 planner 一句话就结束；
3. 其余 → ``budget_guard``：继续执行主循环（``budget_guard → executor → tool_runner → planner``）。
"""

from __future__ import annotations

from typing import Any, Mapping

from langgraph.graph import END
from loguru import logger

from agent_runtime.edges.base import RouterFn, all_milestones_completed, is_hard_terminated, resolve_targets

__all__ = ["TARGETS", "route_after_planner"]

#: 供 ``add_conditional_edges`` 使用的目标映射表
TARGETS = resolve_targets("evaluator", "budget_guard")


def route_after_planner(state: Mapping[str, Any]) -> str:
    """``planner`` 输出后的路由决策。

    Args:
        state: ``AgentState``（只读）。

    Returns:
        ``"evaluator"``、``"budget_guard"`` 或 ``END``。
    """
    if is_hard_terminated(state):
        logger.info(f"[Router] planner 置位终止信号: {state.get('termination_reason', '')}")
        return END

    if all_milestones_completed(state):
        step_count = int(state.get("step_count", 0))
        if step_count == 0:
            logger.info("[Router] 纯直接答复/无工具执行，直接交付结束")
            return END
        logger.info("[Router] 全部里程碑标记完成，进入 evaluator 复核")
        return "evaluator"

    return "budget_guard"


#: 显式类型标注，确保与图装配处的契约一致
assert_router_type: RouterFn = route_after_planner
