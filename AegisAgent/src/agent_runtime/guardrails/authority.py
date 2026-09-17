"""任务授权窗口：父任务权限级别的**单一可变真源**（叶子工具只读视图）。

## 为什么需要这个对象

权限级别存放在 ``AgentState`` 里，而**叶子工具看不到 State**（工具的 ``invoke``
只拿 ``args``）。两种朴素做法都错：

* **构造期捕获**：让 ``spawn_subagent`` 在构造时记下级别。但任务恢复时
  ``prepare_task`` 会重新构造工具，而 Checkpoint 里的级别才是权威值——
  两者可能不一致，就会出现"子级级别 ≠ 父级实际级别"的错配，
  而能力衰减的正确性**完全依赖这个等式**。
* **把 State 传进工具**：破坏工具契约（工具不该知道自己被谁调用），
  并让工具获得读取整个执行状态的能力，与最小权限相反。

因此采用"**推送式绑定**"：``tool_runner`` 在每个节点入口把 State 中的权威级别
推进本对象，工具只读这一个来源。这与 ``BudgetLedger.sync_parent_usage`` 是同一手法
——父任务运行期事实由父级推送给叶子，叶子不回读 State。
"""

from __future__ import annotations

from typing import Any

__all__ = ["TaskAuthority"]


class TaskAuthority:
    """当前任务的授权级别持有者（每任务一个实例）。

    Args:
        permission_level: 初始级别；缺省取保守的 ``workspace_write``，
            真正的值由 ``tool_runner`` 在首次派发前绑定。
    """

    __slots__ = ("_permission_level",)

    def __init__(self, permission_level: str = "workspace_write") -> None:
        self._permission_level = str(permission_level or "workspace_write")

    @property
    def permission_level(self) -> str:
        """当前任务的权威权限级别。"""
        return self._permission_level

    def bind(self, permission_level: Any) -> None:
        """绑定 State 中的权威级别（由 ``tool_runner`` 调用）。

        Args:
            permission_level: ``state["permission_level"]``；为空时保持不变。
        """
        level = str(permission_level or "").strip()
        if level:
            self._permission_level = level

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<TaskAuthority level={self._permission_level!r}>"
