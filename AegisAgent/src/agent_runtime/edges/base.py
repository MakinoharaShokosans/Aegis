"""边的公共契约与判定原语。

把"什么样的状态算终止""里程碑是否全部完成"这类判定抽成纯函数，
让四个边模块只剩"分支意图"，也便于围栏测试。
"""

from __future__ import annotations

from typing import Any, Callable, List, Mapping

from langgraph.graph import END

__all__ = [
    "RouterFn",
    "all_milestones_completed",
    "is_hard_terminated",
    "resolve_targets",
]

#: 路由函数签名：只读状态，返回下一个节点名（或 ``END``）
RouterFn = Callable[[Mapping[str, Any]], str]


def is_hard_terminated(state: Mapping[str, Any]) -> bool:
    """判断是否已被硬熔断。

    Args:
        state: ``AgentState``（只读）。

    Returns:
        ``should_terminate`` 为真时返回 ``True``。
    """
    return bool(state.get("should_terminate", False))


def all_milestones_completed(state: Mapping[str, Any]) -> bool:
    """判断是否"存在里程碑且全部已完成"。

    空里程碑列表视为**未完成**：单步任务不应因为"没有计划"就跳过执行阶段。

    Args:
        state: ``AgentState``（只读）。

    Returns:
        存在至少一个里程碑且其状态全部为 ``completed`` 时返回 ``True``。
    """
    from agent_runtime.nodes.base import coerce_milestones

    raw_milestones: List[Any] = list(state.get("milestones") or [])
    if not raw_milestones:
        return False
    milestones = coerce_milestones(raw_milestones)
    if not milestones:
        return False
    return all(milestone.status == "completed" for milestone in milestones)


def resolve_targets(*node_names: str) -> dict[str, str]:
    """构造 ``add_conditional_edges`` 需要的目标映射表。

    Args:
        *node_names: 目标节点名（不含 ``END``，会自动附加）。

    Returns:
        形如 ``{"planner": "planner", END: END}`` 的映射。
    """
    targets = {name: name for name in node_names}
    targets[END] = END
    return targets
