# Web Search - 搜索引擎源与容灾规范

> **责任领域**：`AegisAgent/src/services/web_search/providers.py`
> **核心原则**：适配器模式 (Adapter Pattern)、零 Key 开箱即用、同步库安全异步化、统一领域异常转译。

---

## 1. 搜索引擎源选型决策：DuckDuckGo

* **零成本门槛**：完全免去任何商业 API Key 注册与付费绑卡流程，任何开发者 clone 代码库后即刻可用；
* **隐私与防追踪**：不记录检索历史与指纹；
* **轻量级依赖**：基于 `duckduckgo-search` Python 库直接访问检索接口。

---

## 2. 核心类结构与适配器设计

```text
┌────────────────────────────────────────────────────────┐
│                   SearchProvider (抽象基类)            │
├────────────────────────────────────────────────────────┤
│ + name: str                                            │
│ + default_max_results: int                             │
│ + search(query: str, max_results: int) -> [SearchHit]  │
└────────────────────────────────────────────────────────┘
                           ▲
                           │ 实现
┌──────────────────────────┴─────────────────────────────┐
│                 DuckDuckGoProvider                     │
├────────────────────────────────────────────────────────┤
│ - _search_sync(query: str, max_results: int) -> dict   │
│ + search(query: str, max_results: int) -> [SearchHit]  │
└────────────────────────────────────────────────────────┘
```

### 2.1 强类型数据契约 (`SearchHit`)

```python
class SearchHit(BaseModel):
    title: str = Field(default="", description="网页标题")
    url: str = Field(min_length=1, description="目标网页绝对 URL")
    snippet: str = Field(default="", description="搜索引擎附带的摘要片段")
    published_at: Optional[str] = Field(default=None, description="网页发布时间戳")
```

---

## 3. 同步库异步化投递原则 (`asyncio.to_thread`)

`duckduckgo_search` 的底包实现（如 `DDGS.text()`）是**同步阻塞型网络 I/O**。若在 FastAPI 主线程中直接调用，会直接阻塞整个 Python 异步事件循环，导致其他并行的任务、健康检查和客户端连接挂起。

### 3.1 纪律与实现
**严禁在主协程中直接调用同步网络库**，必须使用 `asyncio.to_thread` 投递到底层的工作线程池中执行：

```python
class DuckDuckGoProvider(SearchProvider):
    name = PROVIDER_DDG

    def _search_sync(self, query: str, max_results: int) -> list[dict]:
        """工作线程内同步执行"""
        try:
            from duckduckgo_search import DDGS
        except ImportError as exc:
            raise ProviderConfigError("未安装 duckduckgo_search，请安装依赖") from exc

        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results) or [])
        except Exception as exc:
            raise SearchProviderError(f"DuckDuckGo 检索失败: {exc}") from exc

    async def search(self, query: str, max_results: Optional[int] = None) -> list[SearchHit]:
        """异步统一对外接口"""
        cleaned = (query or "").strip()
        if not cleaned:
            raise SearchProviderError("检索词不能为空")

        limit = self._resolve_limit(max_results)
        # 核心：投递到独立工作线程
        raw_items = await asyncio.to_thread(self._search_sync, cleaned, limit)

        hits: list[SearchHit] = []
        for item in raw_items:
            url = str(item.get("href") or item.get("url") or "").strip()
            if not url:
                continue  # 无效链接直接丢弃
            hits.append(SearchHit(
                title=str(item.get("title") or "").strip(),
                url=url,
                snippet=str(item.get("body") or item.get("snippet") or "").strip(),
                published_at=item.get("published") or item.get("published_at")
            ))
        return hits
```

---

## 4. 异常转译与韧性保障

* **统一异常谱系**：底层第三方库因版本迭代抛出的异常种类不可控，适配器统一捕获并封装为 `SearchProviderError` 或 `ProviderConfigError`；
* **降级与重试**：当遭遇网络瞬时抖动时，上层通过 `tenacity` 自动以指数退避策略重试（最多 3 次）；若最终依然失败，以友好结构体返回，由 Agent 状态机自主决定换用备选关键词。
