"""工具框架核心：与具体工具无关的通用机制。"""

from tools.core.dispatcher import DispatchedResult, ToolDispatcher
from tools.core.http_client import ServiceClient
from tools.core.protocol import AegisTool, ToolResult
from tools.core.registry import ToolRegistry
from tools.core.schema import to_openai_tool, to_openai_tools

__all__ = [
    "AegisTool",
    "DispatchedResult",
    "ServiceClient",
    "ToolDispatcher",
    "ToolRegistry",
    "ToolResult",
    "to_openai_tool",
    "to_openai_tools",
]
