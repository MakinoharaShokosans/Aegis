"""``web_search`` 基础工具：外部动态知识摄取。

**WAF Fail-Fast**：来源被 Cloudflare 之类阻断时不做逆向对抗，直接把该条标记为
``BLOCKED`` 并只保留搜索摘要——把"要不要换检索词"的决策交回给模型（条件边重规划），
这是比无限爬虫对抗更稳的工程选择（见 ``技术选型/web_search.md``）。
"""

from __future__ import annotations

from typing import Any, Mapping

from loguru import logger

from agent_runtime.errors import DependencyUnavailableError
from tools.core.http_client import ServiceClient
from tools.core.protocol import AegisTool, ToolResult

__all__ = ["WebSearchTool"]


class WebSearchTool(AegisTool):
    """外部 Web 检索与正文提炼工具。

    Args:
        client: 指向 ``web_search`` 子系统的 HTTP 客户端。
        task_id: 当前任务 ID（长正文落盘目录）。
        default_max_results: 默认候选条数。
    """

    name = "web_search"
    description = (
        "检索外部网络资料（官方文档、GitHub Issue、内核更新日志等），"
        "返回去噪后的 Markdown 正文。适合确认版本行为、查证已知缺陷与最新变更。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索关键词"},
            "max_results": {"type": "integer", "description": "可选，候选结果条数"},
            "fetch": {
                "type": "boolean",
                "description": "可选，是否抓取并清洗正文（默认 true；仅需摘要时设 false 更快）",
            },
        },
        "required": ["query"],
    }

    def __init__(self, client: ServiceClient, *, task_id: str = "", default_max_results: int = 8) -> None:
        self._client = client
        self._task_id = task_id
        self._default_max_results = default_max_results
        self.timeout_sec = 60.0

    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        """执行检索并汇总为可引用文本。

        Args:
            args: ``{"query": str, "max_results"?: int, "fetch"?: bool}``。

        Returns:
            :class:`ToolResult`。
        """
        query = str(args.get("query", "")).strip()
        if not query:
            return ToolResult.failure("缺少 query 参数")

        payload = {
            "query": query,
            "max_results": int(args.get("max_results") or self._default_max_results),
            "fetch": bool(args.get("fetch", True)),
            "task_id": self._task_id,
        }

        try:
            data = await self._client.request_json("POST", "/api/v1/search/query", payload=payload)
        except DependencyUnavailableError as exc:
            logger.error(f"[WebSearchTool] web 子系统不可用: {exc}")
            return ToolResult.failure(str(exc), tool=self.name)

        results = data.get("results") or []
        if not results:
            return ToolResult(ok=True, content="未检索到相关网络资料。", meta={"hits": 0})

        blocks = []
        blocked = 0
        for index, item in enumerate(results, start=1):
            status = str(item.get("status") or "OK")
            if status == "BLOCKED":
                blocked += 1
            title = item.get("title") or item.get("url") or "?"
            lines = [f"[{index}] {title}", f"    URL: {item.get('url', '')}", f"    状态: {status}"]
            if item.get("published_at"):
                lines.append(f"    发布时间: {item['published_at']}")
            body = item.get("markdown") or item.get("preview") or item.get("snippet") or ""
            if body:
                lines.append(body)
            if item.get("artifact_path"):
                lines.append(f"    [完整正文已落盘: artifact://{item['artifact_path']}]")
            blocks.append("\n".join(lines))

        summary = "\n\n---\n\n".join(blocks)
        if blocked:
            summary += f"\n\n[提示] 有 {blocked} 条来源被反爬阻断，已降级为摘要；如需全文请更换检索词或来源。"
        return ToolResult(ok=True, content=summary, meta={"hits": len(results), "blocked": blocked})
