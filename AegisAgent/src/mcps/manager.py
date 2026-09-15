"""MCP 服务器生命周期管理（stdin/stdout 子进程 + SSE 远程会话）。

对应 ``documents/agent_runtime/09_mcp_integration_and_governance.md`` §3。

**四项治理机制**：

1. **懒加载（Lazy Initialization）**：进程启动只加载静态配置，**不拉起任何子进程**；
   第一次真正需要工具时才握手并缓存会话，保证 Agent 冷启动不被 MCP 拖慢；
2. **故障隔离**：单个 MCP 服务器连不上只标记该服务器不可用并告警，
   **绝不影响**其余工具与主执行流程；
3. **防僵尸**：所有连接通过 :class:`contextlib.AsyncExitStack` 纳管，
   ``shutdown_all`` 统一逆序释放，由 SDK 负责终止子进程；
4. **命名空间隔离**：远端工具一律以 ``mcp__{server}__{tool}`` 暴露（见 :mod:`mcps.models`）。

.. warning::
   **事件循环任务约束**：``anyio`` 的取消作用域与创建它的 asyncio Task 绑定，
   因此连接的建立与释放**必须在同一个 Task 内完成**。实践上请由应用 lifespan
   统一负责启动与关闭；不要在临时 Task 里 ``list_tools`` 然后指望别处能关掉它。
"""

from __future__ import annotations

import asyncio
import atexit
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from loguru import logger

from agent_runtime.errors import ToolExecutionError
from mcps.models import MCPToolDefinition, parse_namespaced_tool

__all__ = ["MCPManager"]


def _resolve_env(env: Mapping[str, str]) -> Dict[str, str]:
    """解析 ``"env:VAR"`` 形式的凭据引用。

    Args:
        env: 配置中的环境变量映射。

    Returns:
        真实环境变量字典；``"env:XXX"`` 会被替换为 ``os.environ["XXX"]``，
        未设置时替换为空串并告警（不阻断启动，由服务端自行报鉴权失败）。
    """
    resolved: Dict[str, str] = {}
    for key, value in env.items():
        if isinstance(value, str) and value.startswith("env:"):
            source_name = value[4:]
            actual = os.getenv(source_name, "")
            if not actual:
                logger.warning(f"[MCP] 环境变量 {source_name} 未设置（供 {key} 使用）")
            resolved[key] = actual
        else:
            resolved[key] = str(value)
    return resolved


@dataclass
class _Connection:
    """一条已建立的 MCP 连接。"""

    server_name: str
    session: Any
    stack: AsyncExitStack
    tools: List[MCPToolDefinition] = field(default_factory=list)


class MCPManager:
    """MCP 服务器连接管理器。

    Args:
        config: ``agent_runtime.config.MCPConfig``。
    """

    __slots__ = ("_config", "_connections", "_failed", "_lock", "_atexit_registered")

    def __init__(self, config: Any) -> None:
        self._config = config
        self._connections: Dict[str, _Connection] = {}
        #: 连接失败的服务器（记录原因，避免每次调用都重试拖慢主循环）
        self._failed: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._atexit_registered = False

    # ==========================================================================
    # 对外只读状态（供 /api/v1/mcp/servers 自省端点使用）
    # ==========================================================================

    @property
    def enabled(self) -> bool:
        """MCP 总开关是否打开。"""
        return bool(getattr(self._config, "enabled", False))

    def server_states(self) -> Dict[str, Dict[str, Any]]:
        """返回各服务器的连接状态快照。"""
        states: Dict[str, Dict[str, Any]] = {}
        for name, server in (getattr(self._config, "servers", {}) or {}).items():
            states[name] = {
                "enabled": bool(getattr(server, "enabled", False)),
                "transport": getattr(server, "transport", "stdio"),
                "connected": name in self._connections,
                "tool_count": len(self._connections[name].tools) if name in self._connections else 0,
                "error": self._failed.get(name),
            }
        return states

    # ==========================================================================
    # 工具发现
    # ==========================================================================

    async def list_tools(self) -> List[MCPToolDefinition]:
        """列出全部**已启用且可连接**服务器的工具。

        Returns:
            命名空间化的工具定义列表；无 MCP 或全部失败时返回空列表。
        """
        if not self.enabled:
            logger.debug("[MCP] 总开关已关闭，跳过工具发现")
            return []

        definitions: List[MCPToolDefinition] = []
        for name, server in (getattr(self._config, "servers", {}) or {}).items():
            if not getattr(server, "enabled", False):
                continue
            connection = await self._ensure_connected(name, server)
            if connection is not None:
                definitions.extend(connection.tools)
        logger.info(f"[MCP] 工具发现完成，可用 MCP 工具 {len(definitions)} 个")
        return definitions

    # ==========================================================================
    # 调用
    # ==========================================================================

    async def call_tool(
        self,
        namespaced_name: str,
        arguments: Mapping[str, Any],
        task_id: str = "",
    ) -> Tuple[str, bool]:
        """调用远端 MCP 工具。

        Args:
            namespaced_name: 命名空间化工具名。
            arguments: 工具入参。
            task_id: 任务 ID（仅用于日志）。

        Returns:
            ``(文本结果, 是否错误)``。

        Raises:
            ToolExecutionError: 命名非法、服务器未启用或调用失败。
        """
        try:
            server_name, tool_name = parse_namespaced_tool(namespaced_name)
        except ValueError as exc:
            raise ToolExecutionError(str(exc), context={"tool": namespaced_name}) from exc

        server = (getattr(self._config, "servers", {}) or {}).get(server_name)
        if server is None:
            raise ToolExecutionError(
                f"MCP 服务器未在配置中声明: {server_name}", context={"tool": namespaced_name}
            )

        connection = await self._ensure_connected(server_name, server)
        if connection is None:
            raise ToolExecutionError(
                f"MCP 服务器不可用: {server_name}",
                context={"reason": self._failed.get(server_name, "连接失败")},
            )

        try:
            result = await asyncio.wait_for(
                connection.session.call_tool(tool_name, dict(arguments)),
                timeout=float(getattr(self._config, "call_timeout_sec", 60.0)),
            )
        except asyncio.TimeoutError as exc:
            raise ToolExecutionError(
                f"MCP 工具调用超时: {namespaced_name}",
                context={"task_id": task_id},
            ) from exc
        except Exception as exc:  # noqa: BLE001 - 远端异常统一转为可重规划的错误结果
            # 会话可能已失效：标记该连接作废，下一轮重新握手
            await self._drop_connection(server_name, reason=str(exc))
            raise ToolExecutionError(
                f"MCP 工具调用失败: {namespaced_name}", context={"reason": str(exc)}
            ) from exc

        return _flatten_content(result), bool(getattr(result, "isError", False))

    # ==========================================================================
    # 连接管理
    # ==========================================================================

    async def _ensure_connected(self, server_name: str, server: Any) -> Optional[_Connection]:
        """确保指定服务器已连接（懒加载 + 失败短路）。"""
        if server_name in self._connections:
            return self._connections[server_name]
        if server_name in self._failed:
            return None

        async with self._lock:
            # 双重检查：持锁期间可能已被其它协程建立
            if server_name in self._connections:
                return self._connections[server_name]
            try:
                connection = await self._connect(server_name, server)
            except Exception as exc:  # noqa: BLE001 - 单服务器故障必须被隔离
                self._failed[server_name] = str(exc)
                logger.error(f"[MCP] 服务器 {server_name} 连接失败，已标记不可用: {exc}")
                return None

            self._connections[server_name] = connection
            self._register_atexit_guard()
            return connection

    async def _connect(self, server_name: str, server: Any) -> _Connection:
        """建立单条 MCP 连接并完成握手。"""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.sse import sse_client
        from mcp.client.stdio import stdio_client

        transport = getattr(server, "transport", "stdio")
        timeout = float(getattr(self._config, "connection_timeout_sec", 30.0))
        stack = AsyncExitStack()

        try:
            if transport == "stdio":
                command = getattr(server, "command", "")
                if not command:
                    raise ValueError(f"stdio 模式服务器 {server_name} 未配置 command")
                params = StdioServerParameters(
                    command=command,
                    args=list(getattr(server, "args", []) or []),
                    env=_resolve_env(getattr(server, "env", {}) or {}),
                )
                read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
            elif transport == "sse":
                url = getattr(server, "url", "")
                if not url:
                    raise ValueError(f"sse 模式服务器 {server_name} 未配置 url")
                read_stream, write_stream = await stack.enter_async_context(sse_client(url))
            else:
                raise ValueError(f"不支持的传输模式: {transport}")

            session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream, read_timeout_seconds=timeout)
            )
            await session.initialize()
            raw_tools = await session.list_tools()
        except BaseException:
            # 任何失败都要把已进入的上下文栈清理掉，避免留下半开子进程
            await stack.aclose()
            raise

        tools = [
            MCPToolDefinition.from_remote(
                server_name,
                {"name": tool.name, "description": tool.description, "inputSchema": _schema_of(tool)},
            )
            for tool in getattr(raw_tools, "tools", [])
        ]
        logger.info(f"[MCP] 服务器 {server_name} 握手完成（{transport}），暴露 {len(tools)} 个工具")
        return _Connection(server_name=server_name, session=session, stack=stack, tools=tools)

    async def _drop_connection(self, server_name: str, *, reason: str) -> None:
        """丢弃并释放一条失效连接。"""
        connection = self._connections.pop(server_name, None)
        if connection is None:
            return
        try:
            await connection.stack.aclose()
        except Exception as exc:  # noqa: BLE001 - 释放失败只告警
            logger.warning(f"[MCP] 释放服务器 {server_name} 连接时异常: {exc}")
        logger.warning(f"[MCP] 已断开服务器 {server_name}: {reason}")

    async def shutdown_all(self) -> None:
        """逆序释放全部连接（应由应用 lifespan 在关闭阶段调用）。"""
        if not self._connections:
            return
        logger.info(f"[MCP] 开始关闭 {len(self._connections)} 条 MCP 连接")
        for server_name in list(self._connections):
            await self._drop_connection(server_name, reason="应用关闭")
        self._connections.clear()

    def _register_atexit_guard(self) -> None:
        """注册进程退出守卫：提醒未正常关闭的连接（防僵尸的最后一道告警）。"""
        if self._atexit_registered:
            return
        self._atexit_registered = True

        def _guard() -> None:  # pragma: no cover - 仅在异常退出路径触发
            if self._connections:
                logger.error(
                    f"[MCP] 进程退出时仍有 {len(self._connections)} 条 MCP 连接未关闭，"
                    "可能存在残留子进程；请确保 lifespan 调用了 shutdown_all()"
                )

        atexit.register(_guard)


def _schema_of(tool: Any) -> Dict[str, Any]:
    """从 MCP Tool 对象提取 JSON Schema（兼容字段命名差异）。"""
    for attr in ("inputSchema", "input_schema"):
        schema = getattr(tool, attr, None)
        if isinstance(schema, Mapping):
            return dict(schema)
    return {"type": "object", "properties": {}}


def _flatten_content(result: Any) -> str:
    """把 MCP ``CallToolResult`` 的内容块压平为纯文本。"""
    blocks = getattr(result, "content", None) or []
    parts: List[str] = []
    for block in blocks:
        text = getattr(block, "text", None)
        if text:
            parts.append(str(text))
            continue
        # 非文本块（图片、资源引用等）保留类型提示，避免信息完全丢失
        parts.append(f"<{getattr(block, 'type', 'unknown')} content>")
    return "\n".join(parts) if parts else ""
