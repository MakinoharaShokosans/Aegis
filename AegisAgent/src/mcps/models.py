"""MCP 数据契约与命名空间规则。

**命名空间防冲突**：不同 MCP 服务器可能暴露同名工具（如都有 ``read_file``）。
统一加前缀 ``mcp__{server}__{tool}``，既避免与内置工具撞名，
也让 Executor 只看工具名就能路由到正确的服务器。

**单一真源说明**：服务器**配置**模型（含 host/env 等）由
``agent_runtime.config.MCPServerConfig`` 独家定义；本模块只定义**运行时**模型
（工具定义、连接状态），避免同一个 Schema 维护两份。
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple

from pydantic import BaseModel, Field

__all__ = [
    "NAMESPACE_PREFIX",
    "MCPToolDefinition",
    "parse_namespaced_tool",
    "to_namespaced_name",
]

#: 命名空间前缀（双下划线是刻意选择：MCP 工具名通常不含双下划线，冲突概率最低）
NAMESPACE_PREFIX = "mcp__"

#: 分隔符
_SEPARATOR = "__"


def to_namespaced_name(server_name: str, tool_name: str) -> str:
    """拼接命名空间化的工具名。

    Args:
        server_name: MCP 服务器标识。
        tool_name: 服务器原始工具名。

    Returns:
        形如 ``mcp__github__create_issue`` 的全局唯一工具名。
    """
    return f"{NAMESPACE_PREFIX}{server_name}{_SEPARATOR}{tool_name}"


def parse_namespaced_tool(namespaced_name: str) -> Tuple[str, str]:
    """拆分命名空间化工具名。

    Args:
        namespaced_name: 形如 ``mcp__github__create_issue`` 的工具名。

    Returns:
        ``(服务器名, 原始工具名)``。

    Raises:
        ValueError: 名称不符合命名空间规范时抛出（早失败优于静默路由错服务器）。
    """
    if not namespaced_name.startswith(NAMESPACE_PREFIX):
        raise ValueError(f"工具名缺少 {NAMESPACE_PREFIX!r} 前缀: {namespaced_name}")

    body = namespaced_name[len(NAMESPACE_PREFIX) :]
    server_name, separator, tool_name = body.partition(_SEPARATOR)
    if not separator or not server_name or not tool_name:
        raise ValueError(f"非法的 MCP 工具命名空间: {namespaced_name}")
    return server_name, tool_name


class MCPToolDefinition(BaseModel):
    """远端 MCP 工具的本地投影。"""

    server_name: str = Field(description="所属 MCP 服务器")
    original_name: str = Field(description="服务器侧原始工具名")
    namespaced_name: str = Field(description="本地全局唯一工具名")
    description: str = Field(default="", description="工具能力描述")
    input_schema: Dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}},
        description="JSON Schema 形式的入参定义（来自 MCP inputSchema）",
    )
    schema_ok: bool = Field(
        default=True,
        description=(
            "原始 inputSchema 是否为合法对象。"
            "为了让 mcps/vetting 能**看见并拒绝**畸形 Schema，"
            "这里保留原始判定结果而不是静默替换成默认值——"
            "否则一个畸形/恶意的工具定义会被悄悄洗白。"
        ),
    )

    @classmethod
    def from_remote(
        cls,
        server_name: str,
        raw_tool: Mapping[str, Any],
    ) -> "MCPToolDefinition":
        """从 MCP ``list_tools`` 的原始条目构造。

        Args:
            server_name: 服务器标识。
            raw_tool: MCP 返回的工具描述（含 ``name`` / ``description`` / ``inputSchema``）。

        Returns:
            本地工具定义。
        """
        original_name = str(raw_tool.get("name", ""))
        raw_schema = raw_tool.get("inputSchema")
        if raw_schema is None:
            raw_schema = raw_tool.get("input_schema")
        # 关键：不静默洗白畸形 Schema，只做兜底赋值并如实记录原始判定
        schema_ok = raw_schema is None or isinstance(raw_schema, Mapping)
        schema: Dict[str, Any] = (
            dict(raw_schema) if isinstance(raw_schema, Mapping) else {"type": "object", "properties": {}}
        )
        return cls(
            server_name=server_name,
            original_name=original_name,
            namespaced_name=to_namespaced_name(server_name, original_name),
            description=str(raw_tool.get("description") or ""),
            input_schema=schema,
            schema_ok=schema_ok,
        )
