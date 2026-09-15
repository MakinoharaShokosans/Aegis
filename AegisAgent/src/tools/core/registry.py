"""工具注册表。

职责边界：只做"名字 → 工具实例"的映射与查询，**不含任何执行逻辑**
（执行在 :mod:`tools.core.dispatcher`），也不感知状态机。
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Set

from loguru import logger

from agent_runtime.errors import ToolExecutionError
from tools.core.protocol import AegisTool
from tools.core.schema import to_openai_tools

__all__ = ["ToolRegistry"]


class ToolRegistry:
    """工具注册表（进程内单例由装配层持有）。

    Args:
        allow_untrusted: 是否允许注册 ``trust="untrusted"`` 的工具。
            **默认 False**：特权工具表（主 Agent）在构造期就会拒绝不可信工具，
            想犯错也犯不了。
        untrusted_allowlist: **逐名授权清单**。当 ``allow_untrusted=True`` 时：
            ``None`` 表示放行全部不可信工具（供隔离区使用，如研究子智能体）；
            提供集合时只放行列出的名字——这是"用户为该 MCP server 显式开启"
            这一人工动作在代码里的表达（见 `09` §3.5.2）。
    """

    __slots__ = ("_tools", "_allow_untrusted", "_untrusted_allowlist")

    def __init__(
        self,
        *,
        allow_untrusted: bool = False,
        untrusted_allowlist: Optional[Set[str]] = None,
    ) -> None:
        self._tools: Dict[str, AegisTool] = {}
        self._allow_untrusted = allow_untrusted
        self._untrusted_allowlist: Optional[Set[str]] = (
            set(untrusted_allowlist) if untrusted_allowlist is not None else None
        )

    @property
    def allow_untrusted(self) -> bool:
        """本注册表是否允许承载不可信工具。"""
        return self._allow_untrusted

    @property
    def untrusted_allowlist(self) -> Optional[Set[str]]:
        """逐名授权清单；``None`` 表示未设限（隔离区模式）。"""
        return set(self._untrusted_allowlist) if self._untrusted_allowlist is not None else None

    def register(self, tool: AegisTool) -> None:
        """注册（或覆盖）一个工具。

        Args:
            tool: 工具实例。

        Raises:
            ToolExecutionError: 工具名为空、与已有工具重名，
                或在**不允许不可信工具**的注册表中注册了 ``trust="untrusted"`` 的工具。
        """
        if not tool.name:
            raise ToolExecutionError(f"工具 {type(tool).__name__} 未声明 name")
        if tool.name in self._tools:
            # 重名通常意味着并发装配 bug，直接失败而不是静默覆盖
            raise ToolExecutionError(f"工具名重复注册: {tool.name}")
        trust = getattr(tool, "trust", "trusted")
        if trust != "trusted":
            # 这是权限边界的落点：不可信来源的工具不得进入特权上下文
            if not self._allow_untrusted:
                raise ToolExecutionError(
                    f"拒绝将不可信工具 {tool.name} 注册进特权工具表",
                    context={"tool": tool.name, "trust": trust},
                )
            if self._untrusted_allowlist is not None and tool.name not in self._untrusted_allowlist:
                raise ToolExecutionError(
                    f"不可信工具 {tool.name} 未获显式授权",
                    context={"tool": tool.name, "trust": trust, "allowlist": sorted(self._untrusted_allowlist)},
                )
        self._tools[tool.name] = tool
        logger.debug(f"[ToolRegistry] 注册工具 {tool.name}")

    def register_all(self, tools: Iterable[AegisTool]) -> None:
        """批量注册。

        Args:
            tools: 工具实例可迭代对象。
        """
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Optional[AegisTool]:
        """按名查询。

        Args:
            name: 工具名。

        Returns:
            工具实例；不存在时返回 ``None``（由调用方决定如何降级）。
        """
        return self._tools.get(name)

    def require(self, name: str) -> AegisTool:
        """按名查询，不存在即失败。

        Args:
            name: 工具名。

        Returns:
            工具实例。

        Raises:
            ToolExecutionError: 工具未注册。
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ToolExecutionError(f"未注册的工具: {name}")
        return tool

    def names(self) -> List[str]:
        """返回全部已注册工具名（有序）。"""
        return list(self._tools)

    def all(self) -> List[AegisTool]:
        """返回全部工具实例。"""
        return list(self._tools.values())

    def to_openai_tools(self) -> List[Dict[str, object]]:
        """导出为 OpenAI function calling 定义列表。"""
        return to_openai_tools(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self) -> Iterator[AegisTool]:
        return iter(self._tools.values())
