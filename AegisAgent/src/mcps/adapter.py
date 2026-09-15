"""MCP 工具适配器：把远端工具伪装成本地 :class:`AegisTool`。

**契约透明转译**：Executor 节点对所有工具一视同仁，不应该出现
"如果是 MCP 工具就换个调用方式"这种分支。适配器负责把命名空间化的调用
还原为 MCP 的 ``call_tool(server, tool, args)``，并把返回内容压平成
统一的 :class:`ToolResult`。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Mapping

from loguru import logger

from agent_runtime.errors import ToolExecutionError
from tools.core.protocol import AegisTool, ToolResult

if TYPE_CHECKING:  # 仅类型检查期导入，避免运行时循环依赖
    from mcps.manager import MCPManager

__all__ = ["MCPToolAdapter"]


class MCPToolAdapter(AegisTool):
    """单个远端 MCP 工具的本地代理。

    Args:
        definition: 远端工具定义。
        manager: MCP 连接管理器。
        task_id: 当前任务 ID（用于产物命名与观测）。
    """

    def __init__(self, definition: Any, manager: "MCPManager", task_id: str = "") -> None:
        self.name = definition.namespaced_name
        self.description = definition.description or f"MCP 工具（来自 {definition.server_name}）"
        self.parameters = definition.input_schema
        self.timeout_sec = 60.0
        self._manager = manager
        self._task_id = task_id

    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        """转发调用到远端服务器。

        Args:
            args: 模型给出的入参。

        Returns:
            :class:`ToolResult`；远端异常会被包装为失败结果而非抛出。
        """
        try:
            content, is_error = await self._manager.call_tool(
                namespaced_name=self.name,
                arguments=dict(args),
                task_id=self._task_id,
            )
        except ToolExecutionError as exc:
            logger.error(f"[MCPAdapter] 调用 {self.name} 失败: {exc}")
            return ToolResult.failure(str(exc), server=self.name)

        return ToolResult(
            ok=not is_error,
            content=content,
            error=content if is_error else None,
            meta={"source": "mcp"},
        )
