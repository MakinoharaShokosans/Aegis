"""代码检索子智能体（Code Search Subagent）。

将多轮 RAG 检索、切片判别、自适应改词重试与证据提炼封装进独立的子智能体生命周期：
- :mod:`~agent_runtime.code_search.contracts` —— Pydantic 强类型契约与真实切片位置白名单过滤；
- :mod:`~agent_runtime.code_search.runner`    —— 最多 3 轮检索-判别-换词-提炼的有界状态机；
- :mod:`~agent_runtime.code_search.tool`      —— 主 Agent 调用的 ``delegate_code_search`` 适配器。
"""

from agent_runtime.code_search.contracts import (
    CodeChunkEvidence,
    CodeFinding,
    CodeSearchReport,
    CodeSearchRequest,
    CodeSnippet,
    StructuredCodeSearchTool,
    build_code_report,
)
from agent_runtime.code_search.runner import CodeSearchRunner
from agent_runtime.code_search.tool import DelegateCodeSearchTool, build_code_search_tool

__all__ = [
    "CodeChunkEvidence",
    "CodeFinding",
    "CodeSearchReport",
    "CodeSearchRequest",
    "CodeSearchRunner",
    "CodeSnippet",
    "DelegateCodeSearchTool",
    "StructuredCodeSearchTool",
    "build_code_report",
    "build_code_search_tool",
]
