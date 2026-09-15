"""工具注册表。

职责边界：只做"名字 → 工具实例"的映射与查询，**不含任何执行逻辑**
（执行在 :mod:`tools.core.dispatcher`），也不感知状态机。
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from loguru import logger

from agent_runtime.errors import ToolExecutionError
from tools.core.protocol import AegisTool
from tools.core.schema import to_openai_tools

__all__ = ["ToolRegistry"]


class ToolRegistry:
    """工具注册表（进程内单例由装配层持有）。"""

    __slots__ = ("_tools",)

    def __init__(self) -> None:
        self._tools: Dict[str, AegisTool] = {}

    def register(self, tool: AegisTool) -> None:
        """注册（或覆盖）一个工具。

        Args:
            tool: 工具实例。

        Raises:
            ToolExecutionError: 工具名为空或与已有工具重名时抛出。
        """
        if not tool.name:
            raise ToolExecutionError(f"工具 {type(tool).__name__} 未声明 name")
        if tool.name in self._tools:
            # 重名通常意味着并发装配 bug，直接失败而不是静默覆盖
            raise ToolExecutionError(f"工具名重复注册: {tool.name}")
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
