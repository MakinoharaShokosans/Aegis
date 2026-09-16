"""路由契约聚合导出（**对外稳定入口**）。

本模块**不实现**任何路由逻辑——实现分散在 :mod:`agent_runtime.edges` 的四个对称模块中。
保留这一层的意义：

1. 文档（``04_routing_and_control_flow``）承诺的公开契约名 ``routing.py`` 保持有效；
2. ``workflow.py`` 只需 ``from agent_runtime import routing`` 即可拿到全部路由函数与目标表；
3. 外部扩展（如新增自定义边）有唯一注册点，不必到处改 import。
"""

from __future__ import annotations

from typing import Dict, Mapping, Tuple

from agent_runtime.edges import (
    after_budget_guard,
    after_evaluator,
    after_executor,
    after_planner,
    after_tool_runner,
)
from agent_runtime.edges.base import RouterFn

__all__ = [
    "EDGE_TABLE",
    "route_after_budget_guard",
    "route_after_evaluator",
    "route_after_executor",
    "route_after_planner",
    "route_after_tool_runner",
]

route_after_planner: RouterFn = after_planner.route_after_planner
route_after_budget_guard: RouterFn = after_budget_guard.route_after_budget_guard
route_after_executor: RouterFn = after_executor.route_after_executor
route_after_evaluator: RouterFn = after_evaluator.route_after_evaluator
route_after_tool_runner: RouterFn = after_tool_runner.route_after_tool_runner

#: 图装配表：``节点名 -> (路由函数, 目标映射)``。
#: ``workflow.build_agent_graph`` 直接遍历本表挂载条件边，新增边无需改图构建代码。
EDGE_TABLE: Dict[str, Tuple[RouterFn, Mapping[str, str]]] = {
    "planner": (route_after_planner, after_planner.TARGETS),
    "budget_guard": (route_after_budget_guard, after_budget_guard.TARGETS),
    "executor": (route_after_executor, after_executor.TARGETS),
    "tool_runner": (route_after_tool_runner, after_tool_runner.TARGETS),
    "evaluator": (route_after_evaluator, after_evaluator.TARGETS),
}
