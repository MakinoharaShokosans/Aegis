"""工具 → OpenAI function calling Schema 转译。

独立成模块的原因：Schema 转译是"格式适配"而非"业务"，与工具实现、注册表
都不相干；把它单独放一处，可以让 MCP 转译工具、基础工具共用同一套规则。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from tools.core.protocol import AegisTool

__all__ = ["to_openai_tool", "to_openai_tools"]


def to_openai_tool(tool: AegisTool) -> Dict[str, Any]:
    """把工具转译为 OpenAI 兼容的 function 定义。

    Args:
        tool: 工具实例。

    Returns:
        形如 ``{"type": "function", "function": {...}}`` 的字典。

    Raises:
        ValueError: 工具未声明 ``name`` 时抛出（早失败优于静默生成非法 Schema）。
    """
    if not tool.name:
        raise ValueError(f"工具 {type(tool).__name__} 未声明 name，无法生成 Schema")
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def to_openai_tools(tools: Iterable[AegisTool]) -> List[Dict[str, Any]]:
    """批量转译。

    Args:
        tools: 工具实例可迭代对象。

    Returns:
        function 定义列表。
    """
    return [to_openai_tool(tool) for tool in tools]
