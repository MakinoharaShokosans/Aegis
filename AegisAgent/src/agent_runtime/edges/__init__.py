"""条件边（Edges）—— 与 :mod:`agent_runtime.nodes` 一一对称。

**为什么把边单独成层**：节点负责"做事"，边负责"决定下一步去哪"。
二者混在一个文件里会导致新增一条迁移必须修改公共文件，且难以单独测试路由逻辑。

每个 ``after_*.py`` 内聚两件东西：

* ``route_after_xxx(state) -> str`` —— **纯函数**决策（零 I/O、零 LLM）；
* ``TARGETS`` —— 供 ``add_conditional_edges`` 使用的目标映射表。

:mod:`agent_runtime.routing` 只是本包的**聚合导出**，保持文档承诺的对外契约名不变。
"""

from agent_runtime.edges import (
    after_budget_guard,
    after_evaluator,
    after_executor,
    after_planner,
)

__all__ = ["after_budget_guard", "after_evaluator", "after_executor", "after_planner"]
