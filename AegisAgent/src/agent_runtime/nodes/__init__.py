"""图节点（Nodes）—— 与 :mod:`agent_runtime.edges` 一一对称。

**统一的依赖注入模式**：每个节点都是一个 ``build_xxx_node(deps) -> NodeFn`` 工厂。
原因：LangGraph 的节点签名固定为 ``(state) -> dict``，而节点真正需要的依赖
（模型网关、工具注册表、预算守卫实例、裁剪器、轨迹记录器）无法从 state 取得。
用工厂闭包注入依赖，既满足图契约，又让节点可在单测中整体替换依赖。

**为什么每个任务重新编译图**：预算守卫持有 ``start_time``、裁剪器与轨迹记录器
绑定 ``task_id``，都是**任务级**生命周期对象。按任务编译一次图（毫秒级开销）
比把它们塞进 Checkpoint 状态干净得多。
"""

from agent_runtime.nodes.budget_guard import build_budget_guard_node
from agent_runtime.nodes.evaluator import build_evaluator_node
from agent_runtime.nodes.executor import build_executor_node
from agent_runtime.nodes.planner import build_planner_node

__all__ = [
    "build_budget_guard_node",
    "build_evaluator_node",
    "build_executor_node",
    "build_planner_node",
]
