# 架构决策记录：外部 Web 搜索与网页降噪清洗服务

> **状态**：已定稿 (Accepted)  
> **责任领域**：`AegisAgent/src/services/web_search/`（**同工程子系统**，独立进程，默认监听 `127.0.0.1:8003`）  
> **核心目标**：为 Agent 提供开源前沿动态调研、GitHub Issues 查错、内核更新日志检索等外部动态知识摄取能力。
>
> **暴露面变更（重要）**：本子系统**不再被主 Agent 直接调用**。
> 抓取能力只对**研究子智能体**（`agent_runtime/research/`）开放，
> 主工具表中没有 `web_search`，主 Agent 只能通过 `delegate_research` 请求研究
> （见 `agent_runtime/12_research_subagent.md`）。

---

## 1. 架构总览与清洗流水线

```text
 Agent Runtime (通过 httpx 调用 /api/v1/search/*)
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
[ 1. 搜索引擎检索 (Query) ]        [ 2. 网页全文异步抓取 (Fetch) ]
  - 默认: duckduckgo-search (无Key)  - httpx (全异步并发 / 超时治理)
        │                                 │
        │                                 ▼
        │                      [ WAF / Cloudflare 拦截检测 ]
        │                       ├── 触发 403 / 503 挑战
        │                       │    │
        │                       │    ▼ (Fail-Fast 降级策略)
        │                       │   - 降级为搜索引擎 Snippet 摘要
        │                       │   - 结构化返回 status: BLOCKED
        │                       │   - 触发 Agent 条件边动态切换备用 URL
        │                       │
        │                       └── 正常抓取 HTML (通过校验)
        │                                 │
        ▼                                 ▼
[ 搜索结果列表 (含 Snippets) ]       [ 3. trafilatura 智能正文清洗 ]
                                 - 启发式判定正文主干，剔除导航/广告/页脚
                                 - 直接提炼输出精炼 Markdown (保留代码块)
                                                  │
                                                  ▼
                                 [ 4. 网页内容离线卸载 (Offloading) ]
                                 - 全量存盘 storage/artifacts/{task_id}/web_xxx.md
                                 - 超长内容截取前 1500 Token + 证据句柄
                                                  │
                                                  ▼
                                 返回给 Agent 进行阅读、归纳与证据引用
```

---

## 2. 核心技术决策与权衡依据

### 2.1 搜索引擎源选型：开箱即用零成本检索（DuckDuckGo）

* **决策理由**：
  1. **零成本与开箱即用：`duckduckgo-search`**：
     - 100% 免费、完全无需注册或配置任何商业 API Key；
     - 任何人在任何机器上 clone 项目均可即刻跑通 Web 搜索功能，杜绝外部收费服务绑定；
     - 系统采用接口适配器模式（Adapter Pattern），调用方仅依赖 `SearchProvider` 抽象基类。
  2. **结果去重与时效性保障**：
     - **去重策略（Deduplication）**：基于标题+摘要的内容指纹（MD5 哈希前 8 位）过滤镜像站与转载重复内容；
     - **时效性过滤（Freshness Filter，可选）**：对时间敏感查询（如"2025 年 Linux 6.x 新特性"）优先返回最近 6-12 个月内容，避免过期文档混入。

### 2.2 异步网络抓取底座：选用 `httpx`

* **决策理由**：
  1. **全异步高并发**：并发抓取 5 个搜索候选页时，基于 `asyncio.gather` 并行拉取，总耗时取决于最慢单页而非串行累加；
  2. **安全防封治理**：内置合理的 `User-Agent` 标头轮换、重定向跟踪（`follow_redirects=True`）以及严格的单请求超时（`timeout=10s`），杜绝因个别死链挂起整个服务。

### 2.3 智能正文提取与降噪：选用 `trafilatura`（而非 BeautifulSoup4）

* **为什么不选 BeautifulSoup4 或简单的 html2text？**
  - **`BeautifulSoup4`**：需要手工维护大量繁杂的标签过滤规则（如 `<nav>`, `<footer>`, `<aside>`），极易漏掉有效正文或残留大量无用菜单链接；
  - **`html2text`**：纯暴力转码，不做任何内容主体判定，转换出的 Markdown 充满页脚版权声明和导航链接，极易撑爆 Context。
* **`trafilatura` 的优势**：
  - 业界用于 LLM 预训练语料清洗的事实标准，基于 Cython/lxml 编写，速度极快；
  - 内置启发式正文主干识别算法，自动剔除侧边栏、Cookie 弹窗与广告；
  - 原生直接提取输出规范的 Markdown（完美保留代码块 `pre/code`、标题与列表），有效降低 80% 以上的无用网页噪声。

### 2.4 面向阻断的设计哲学（Design for WAF Failure & Replanning）

* **严禁无休止的逆向破盾**：避免在单机项目中耗费大量精力与 Cloudflare 等 WAF 进行脆弱的爬虫攻防；
* **Fail-Fast 结构化反馈**：抓取遇到 403 / 503 阻断时快速返回 `status: BLOCKED`；
* **双重容错自愈链路**：
  1. **局部降级（Snippet Fallback）**：优先降级提取搜索引擎随附的 Snippet 摘要喂给模型，满足绝大部分技术报错查询需求；
  2. **全局自愈（Replanning）**：由 LangGraph 条件边捕获阻断观察，驱动 Agent 自动选择下一个候选 URL 或重构检索词，完美转化为一次有据可查的**自愈重试轨迹（Self-Correction Trace）**。

### 2.5 海量网页内容治理

清洗后的 Markdown 正文若超过 1,500 Token，全量异步落盘至 `storage/artifacts/{task_id}/`，仅向 Context 注入头部精炼摘要与文件句柄，保证多轮长任务的 Token 预算安全。
