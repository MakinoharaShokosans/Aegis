"""自省端点：向 Web 前端暴露"当前 Agent 具备哪些能力"。

**安全约束**：本组端点**绝不**返回任何密钥。``/models`` 只暴露端点别名、
模型名与 ``base_url``——足以让前端展示"主模型 / 备用模型"拓扑，
但不泄露 ``api_key_env`` 的解析结果。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter

from agent_runtime.api.deps import RuntimeDep
from agent_runtime.skills.registry import SkillsRegistry
from tools.builtin import build_builtin_tools
from tools.core.http_client import ServiceClient
from tools.core.registry import ToolRegistry

__all__ = ["router"]

router = APIRouter(tags=["introspection"])


@router.get("/skills", summary="列出可用专家技能")
async def list_skills(runtime: RuntimeDep) -> List[Dict[str, Any]]:
    """返回内置技能清单（不含正文，正文由 ``load_skill`` 按需载入）。

    Args:
        runtime: 进程级运行时。

    Returns:
        技能元数据列表。
    """
    registry = SkillsRegistry.from_workspace(
        workspace_root=Path.cwd(),
        builtin_dir=runtime.builtin_skills_dir,
    )
    return [
        {
            "name": skill.name,
            "description": skill.description,
            "triggers": list(skill.triggers),
            "required_tools": list(skill.required_tools),
            "source": skill.source,
        }
        for skill in registry.list_skills()
    ]


@router.get("/tools", summary="列出已注册工具及其 Schema")
async def list_tools(runtime: RuntimeDep) -> List[Dict[str, Any]]:
    """返回一个"标准任务"会拿到的工具集合（含 MCP 远端工具）。

    Args:
        runtime: 进程级运行时。

    Returns:
        OpenAI function calling 定义列表。
    """
    config = runtime.config
    skills = SkillsRegistry.from_workspace(
        workspace_root=Path.cwd(), builtin_dir=runtime.builtin_skills_dir
    )

    # 自省端点即用即弃：显式持有客户端并在 finally 中关闭，避免连接泄漏
    clients = [
        ServiceClient(config.services.rag_url, config.services.timeout_sec),
        ServiceClient(config.services.shell_url, config.services.timeout_sec),
        ServiceClient(config.services.web_url, config.services.timeout_sec),
    ]
    try:
        tools = build_builtin_tools(
            workspace_id="introspection",
            workspace_root=str(Path.cwd()),
            task_id="introspection",
            rag_client=clients[0],
            shell_client=clients[1],
            web_client=clients[2],
            skills=skills,
        )
        registry = ToolRegistry()
        registry.register_all(tools)
        definitions: List[Dict[str, Any]] = list(registry.to_openai_tools())
        for definition in definitions:
            definition["source"] = "builtin"
    finally:
        for client in clients:
            await client.aclose()

    for mcp_tool in await runtime.mcp_manager.list_tools():
        definitions.append(
            {
                "type": "function",
                "source": "mcp",
                "server": mcp_tool.server_name,
                "function": {
                    "name": mcp_tool.namespaced_name,
                    "description": mcp_tool.description,
                    "parameters": mcp_tool.input_schema,
                },
            }
        )
    return definitions


@router.get("/mcp/servers", summary="列出 MCP 服务器状态")
async def list_mcp_servers(runtime: RuntimeDep) -> List[Dict[str, Any]]:
    """返回已声明 MCP 服务器的启用与连接状态。

    Args:
        runtime: 进程级运行时。

    Returns:
        服务器状态列表。
    """
    states = runtime.mcp_manager.server_states()
    return [{"name": name, **state} for name, state in states.items()]


@router.get("/models", summary="列出双模型分层端点（不含密钥）")
async def list_models(runtime: RuntimeDep) -> Dict[str, Any]:
    """返回 reasoning / fast 两层的端点拓扑。

    Args:
        runtime: 进程级运行时。

    Returns:
        分层端点信息；``available`` 表示该端点是否已具备可用凭据。
    """
    config = runtime.config
    payload: Dict[str, Any] = {}
    for tier_name in ("reasoning", "fast"):
        tier = getattr(config.models, tier_name)
        payload[tier_name] = {
            "temperature": tier.temperature,
            "endpoints": [
                {
                    "name": endpoint.name,
                    "model": endpoint.model,
                    "base_url": endpoint.base_url,
                    "timeout_sec": endpoint.timeout_sec,
                    # 只暴露"凭据是否就绪"，绝不暴露凭据本身
                    "available": bool(runtime.gateway.has_endpoints(tier_name)),
                }
                for endpoint in tier.endpoints
            ],
        }
    return payload
