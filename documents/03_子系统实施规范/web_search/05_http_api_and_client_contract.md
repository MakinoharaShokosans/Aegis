# Web Search - 服务契约与客户端适配规范

> **责任领域**：`AegisAgent/src/services/web_search/app.py` 与 `AegisAgent/src/tools/builtin/web_search.py`  
> **核心原则**：HTTP REST 契约化通信、强类型 DTO 约束、解耦红线（禁止反向依赖 Agent 内部模块）。

---

## 1. 服务接口定义 (FastAPI 端点)

Web Search 作为独立微服务（默认运行于 `127.0.0.1:8003`），向 Agent 工具层暴露以下接口：

### 1.1 端到端综合检索：`POST /api/v1/search`
执行“检索 + 抓取 + 清洗 + 去重 + 卸载”的全流程一体化接口。

#### 请求体 Schema (`SearchRequest`)
```json
{
  "query": "linux kernel 6.6 io_uring security patch",
  "max_results": 5,
  "task_id": "9b1e7c54-46c5-4428-a408-dbcbcf123456",
  "fetch_full_content": true
}
```

#### 响应体 Schema (`SearchResponse`)
```json
{
  "query": "linux kernel 6.6 io_uring security patch",
  "total_hits": 4,
  "articles": [
    {
      "title": "Security fixes in io_uring for Linux 6.6",
      "url": "https://lore.kernel.org/all/20231102.../",
      "snippet": "This patch series addresses a race condition in io_uring...",
      "content_markdown": "## Vulnerability Details\n...",
      "is_offloaded": false,
      "artifact_path": null,
      "status": "SUCCESS"
    },
    {
      "title": "Linux Kernel Git Log: io_uring buffer ring",
      "url": "https://git.kernel.org/pub/scm/linux/kernel/git/...",
      "snippet": "commit 8f3a9e12... io_uring: check credentials...",
      "content_markdown": "commit 8f3a9e128912...\n[已落盘，前 200 字预览]...",
      "is_offloaded": true,
      "artifact_path": "storage/artifacts/9b1e.../web_8f3a.md",
      "status": "OFFLOADED"
    }
  ],
  "duration_ms": 1850
}
```

### 1.2 单 URL 针对性抓取：`POST /api/v1/search/fetch`
供 Agent 针对某一特定 URL 进行全文抓取与提取。

### 1.3 健康检查与自省：`GET /health`
```json
{
  "status": "healthy",
  "service": "web_search",
  "version": "0.1.0",
  "provider": "ddg",
  "concurrency_limit": 5
}
```

---

## 2. Agent ToolLayer 客户端适配器 (`tools/builtin/web_search.py`)

在 Agent 调度主进程中，通过统一的 `AegisTool` 规范对接 Web 搜索服务：

```python
from tools.core.protocol import AegisTool, ToolResult
from tools.core.http_client import ServiceClient

class WebSearchTool(AegisTool):
    name = "web_search"
    description = "执行外部网络技术资料检索，自动拉取网页正文、过滤噪音广告并提供精炼 Markdown 格式的技术证据。"

    def __init__(self, client: ServiceClient, task_id: str):
        self.client = client
        self.task_id = task_id

    async def execute(self, query: str, max_results: int = 5) -> ToolResult:
        payload = {
            "query": query,
            "max_results": max_results,
            "task_id": self.task_id,
            "fetch_full_content": True,
        }
        resp = await self.client.post("/api/v1/search", json=payload)
        data = resp.json()
        
        articles = data.get("articles") or []
        if not articles:
            return ToolResult(
                success=True,
                content=f"未检索到与 '{query}' 相关的有效网页结果。",
                metadata={"hits": 0}
            )

        # 组装高信息密度的 Markdown 引用格式
        lines = [f"### 网络检索结果 ({len(articles)} 条):"]
        for idx, item in enumerate(articles, 1):
            lines.append(f"#### [{idx}] {item['title']}")
            lines.append(f"- **来源**: {item['url']}")
            if item.get("is_offloaded"):
                lines.append(f"- **摘要**: {item['content_markdown']}")
                lines.append(f"- **完整正文已落盘**: `{item['artifact_path']}`")
            else:
                lines.append(f"- **正文**:\n{item['content_markdown']}")
            lines.append("")

        return ToolResult(
            success=True,
            content="\n".join(lines),
            metadata={"hits": len(articles), "duration_ms": data.get("duration_ms")}
        )
```
