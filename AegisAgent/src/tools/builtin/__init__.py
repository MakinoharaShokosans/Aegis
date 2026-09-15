"""基础工具集合（Built-in Tools）。

**"基础工具单独存放"的含义**：本包只放**具体工具实现**；
工具协议、Schema 转译、注册表、并发派发、HTTP 客户端等**框架机制**
一律位于 :mod:`tools.core`。这样新增一个基础工具只需加一个文件，
永远不会碰到框架代码；反过来改派发策略也不会碰到任何工具。

统一的装配入口是 :func:`build_builtin_tools`——由 ``workflow`` 在任务 Spawn 时调用，
注入该任务的工作区上下文与服务客户端。
"""

from __future__ import annotations

from typing import List, Optional

from agent_runtime.skills.registry import SkillsRegistry
from tools.builtin.bash import BashTool
from tools.builtin.file_ops import FileWriteTool, ViewFileTool, build_file_tools
from tools.builtin.load_skill import LoadSkillTool
from tools.builtin.rag_search import RagSearchTool
from tools.builtin.web_search import WebSearchTool
from tools.core.http_client import ServiceClient
from tools.core.protocol import AegisTool

__all__ = [
    "BashTool",
    "FileWriteTool",
    "LoadSkillTool",
    "RagSearchTool",
    "ViewFileTool",
    "WebSearchTool",
    "build_builtin_tools",
    "build_file_tools",
]


def build_builtin_tools(
    *,
    workspace_id: str,
    workspace_root: str,
    task_id: str,
    rag_client: Optional[ServiceClient] = None,
    shell_client: Optional[ServiceClient] = None,
    web_client: Optional[ServiceClient] = None,
    skills: Optional[SkillsRegistry] = None,
    bash_timeout_sec: float = 60.0,
    rag_top_k: int = 5,
    web_max_results: int = 8,
) -> List[AegisTool]:
    """装配当前任务可用的全部基础工具。

    任何 sidecar 客户端为 ``None`` 时，对应工具**不注册**——这样在只做本地代码
    分析（不需要网络/检索）的场景下，模型看不到也不会误调用不存在的工具。

    Args:
        workspace_id: 工作区标识。
        workspace_root: 工作区物理根路径。
        task_id: 任务 ID。
        rag_client: AegisRAG 客户端。
        shell_client: bash_shell 客户端。
        web_client: web_search 客户端。
        skills: 技能注册表。
        bash_timeout_sec: bash 默认超时。
        rag_top_k: 检索默认返回条数。
        web_max_results: 网络检索默认条数。

    Returns:
        工具实例列表。
    """
    tools: List[AegisTool] = []

    if shell_client is not None:
        tools.append(
            BashTool(
                shell_client,
                workspace_id=workspace_id,
                workspace_root=workspace_root,
                task_id=task_id,
                default_timeout_sec=bash_timeout_sec,
            )
        )
    if rag_client is not None:
        tools.append(RagSearchTool(rag_client, default_top_k=rag_top_k))
    if web_client is not None:
        tools.append(WebSearchTool(web_client, task_id=task_id, default_max_results=web_max_results))

    tools.extend(build_file_tools(workspace_root))

    if skills is not None:
        tools.append(LoadSkillTool(skills))

    return tools
