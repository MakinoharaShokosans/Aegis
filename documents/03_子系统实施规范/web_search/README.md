# Aegis Web Search 外部网络信息摄取 - 实施技术规范索引

> **责任领域**：`AegisAgent/src/services/web_search/`（同工程独立微服务，默认监听 `127.0.0.1:8003`）  
> **核心原则**：开箱即用零成本检索 (DuckDuckGo)、全异步高并发抓取 (`httpx`)、智能正文清洗提炼 (`trafilatura`)、内容指纹精准去重 (MD5)、超长正文离线卸载 (Artifacts Offloading)。

---

## 1. 文档拓扑结构与技术规范

| 文档序号 | 技术领域 | 核心规范与实现重点 |
| :--- | :--- | :--- |
| [01_search_architecture_and_data_flow.md](./01_search_architecture_and_data_flow.md) | **全景架构与数据流** | Query 检索、httpx 异步并发抓取、WAF 阻断检测、trafilatura 正文提取、MD5 去重与离线卸载全链路拓扑 |
| [02_duckduckgo_provider_and_resilience.md](./02_duckduckgo_provider_and_resilience.md) | **搜索引擎源与容灾** | `SearchProvider` 适配器、`DuckDuckGoProvider` 零 Key 开箱即用实现、同步库 `to_thread` 异步化、频控与错误自愈 |
| [03_async_fetch_and_trafilatura_clean.md](./03_async_fetch_and_trafilatura_clean.md) | **异步抓取与正文清洗** | `httpx.AsyncClient` 连接池与超时管理、User-Agent 轮换反爬、WAF/Cloudflare 挑战快速降级、`trafilatura` 保留代码块输出精炼 Markdown |
| [04_content_dedup_and_artifacts_offloading.md](./04_content_dedup_and_artifacts_offloading.md) | **内容去重与离线卸载** | MD5 8位指纹过滤镜像站与转载重复、超长正文（>1500 Token）流式落盘 `storage/artifacts/`、上下文注入摘要与证据闭环 |
| [05_http_api_and_client_contract.md](./05_http_api_and_client_contract.md) | **服务契约与客户端适配** | FastAPI 路由契约 (`POST /api/v1/search/*`)、请求/响应 DTO 规范、自省端点与 Agent ToolLayer (`tools/builtin/web_search.py`) 适配 |

---

## 2. 数据流转拓扑

```text
 Agent Runtime (通过 tools/builtin/web_search.py 经 HTTP 调用)
                          │
                          ▼
            [ 1. DuckDuckGoProvider 检索 ]
              - 0 Key、开箱即用、无商业 API 绑定
              - 同步 SDK 经 asyncio.to_thread 异步化投递
              - 返回 Top-N SearchHit 候选列表 (URL + Snippet)
                          │
                          ▼
            [ 2. httpx 全异步并发抓取池 ]
              - fetch_concurrency 并发拉取 (默认 5 个)
              - User-Agent 随机轮换防封禁
              - 单页超时 10s，总超时 30s
                          │
         ┌────────────────┴────────────────┐
         ▼ (WAF / 403 / 503 拦截)           ▼ (正常拉回 HTML)
     Fail-Fast 快速降级            [ 3. trafilatura 启发式清洗 ]
     回退使用搜索引擎 Snippet      - 剔除导航、页脚、广告
     标识 status: BLOCKED          - 提取技术正文，保留代码块
                                   - 直接转换为 Markdown 格式
                                                   │
                                                   ▼
                                  [ 4. MD5 内容指纹去重 ]
                                  - 计算清洗后文本 MD5 前 8 位
                                  - 过滤完全一致的镜像站与转载
                                                   │
                                                   ▼
                                  [ 5. 超长正文离线落盘卸载 ]
                                  - Token > 1500: 全量存入 storage/artifacts/
                                  - 仅向 Agent 返回 200 字摘要 + 证据句柄
                                                   │
                                                   ▼
                          返回精炼 Web 证据列表供 Agent 引用推理
```

---

## 3. 代码映射一览

* **配置与设置**：[`src/services/web_search/settings.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/services/web_search/settings.py)（读取 `config.toml` 中 `[web_search]` 段）
* **搜索引擎适配器**：[`src/services/web_search/providers.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/services/web_search/providers.py)
* **正文抓取与清洗**：[`src/services/web_search/extractor.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/services/web_search/extractor.py)
* **内容指纹去重**：[`src/services/web_search/dedup.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/services/web_search/dedup.py)
* **FastAPI 接入层**：[`src/services/web_search/app.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/services/web_search/app.py)
* **服务启动入口**：[`src/services/web_search/__main__.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/services/web_search/__main__.py)
* **客户端调用端点**：[`src/tools/builtin/web_search.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/tools/builtin/web_search.py)
