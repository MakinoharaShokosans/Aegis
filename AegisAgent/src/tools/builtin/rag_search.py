"""``rag_search`` 基础工具：源码语义检索（委托 AegisRAG 独立子工程）。

**为什么检索必须走独立进程**：AST 解析与向量化是 CPU 密集型且携带 C 扩展，
放在 Agent 进程内会阻塞事件循环、并让段错误直接杀死宿主（见 ``01`` §3）。
"""

from __future__ import annotations

from typing import Any, Mapping

from loguru import logger

from agent_runtime.errors import DependencyUnavailableError
from tools.core.http_client import ServiceClient
from tools.core.protocol import AegisTool, ToolResult

__all__ = ["RagSearchTool"]


class RagSearchTool(AegisTool):
    """在工作区代码库中做混合检索（Dense + Sparse + RRF + Rerank）。

    Args:
        client: 指向 ``AegisRAG`` 的 HTTP 客户端。
        default_top_k: 默认返回切片数。
    """

    name = "rag_search"
    description = (
        "在目标工程代码库中检索相关源码片段。适合定位函数实现、结构体定义、"
        "调用点与配置项。返回结果带文件路径与行号，可直接作为证据引用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索意图，建议包含关键符号名"},
            "top_k": {"type": "integer", "description": "可选，返回切片数量上限"},
            "language": {"type": "string", "description": "可选，限定语言（c/cpp/go/python）"},
        },
        "required": ["query"],
    }

    def __init__(self, client: ServiceClient, default_top_k: int = 5) -> None:
        self._client = client
        self._default_top_k = default_top_k
        self.timeout_sec = 60.0

    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        """调用检索服务并格式化为带行号的证据文本。

        Args:
            args: ``{"query": str, "top_k"?: int, "language"?: str}``。

        Returns:
            :class:`ToolResult`。
        """
        query = str(args.get("query", "")).strip()
        if not query:
            return ToolResult.failure("缺少 query 参数")

        payload: dict[str, Any] = {"query": query, "top_k": int(args.get("top_k") or self._default_top_k)}
        if args.get("language"):
            payload["filters"] = {"language": str(args["language"])}

        try:
            data = await self._client.request_json("POST", "/api/v1/retrieve", payload=payload)
        except DependencyUnavailableError as exc:
            logger.error(f"[RagSearchTool] RAG 子系统不可用: {exc}")
            return ToolResult.failure(str(exc), tool=self.name)

        chunks = data.get("results") or data.get("chunks") or []
        if not chunks:
            return ToolResult(ok=True, content="未检索到相关代码片段。", meta={"hits": 0})

        blocks = []
        for index, chunk in enumerate(chunks, start=1):
            location = f"{chunk.get('file_path', '?')}:{chunk.get('start_line', '?')}-{chunk.get('end_line', '?')}"
            header = f"[{index}] {location}"
            if chunk.get("git_commit"):
                header += f" @{chunk['git_commit']}"
            blocks.append(f"{header}\n{chunk.get('content', '')}")

        return ToolResult(
            ok=True,
            content="\n\n---\n\n".join(blocks),
            meta={"hits": len(chunks)},
        )
