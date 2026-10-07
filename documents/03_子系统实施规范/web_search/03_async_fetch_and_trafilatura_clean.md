# Web Search - 异步抓取与正文清洗规范

> **责任领域**：`AegisAgent/src/services/web_search/extractor.py`
> **核心原则**：`httpx` 全异步连接池并发、UA 伪装轮换、WAF 阻断 Fail-Fast 快速降级、`trafilatura` 启发式提炼精炼 Markdown。

---

## 1. 异步网络抓取底座 (`httpx.AsyncClient`)

在获得搜索引擎返回的候选 URL 列表后，服务通过 `httpx` 并发拉取前 $N$ 个（默认 5 个）候选网页的原始 HTML。

### 1.1 核心配置与并发池

```python
# settings.py 中的关键配额
fetch_concurrency = 5            # 最大并发抓取连接数
request_timeout_sec = 10         # 单网页请求硬超时 (秒)
total_timeout_sec = 30           # 单轮搜索抓取全流程总超时 (秒)
```

* **并发控制**：基于 `asyncio.Semaphore(fetch_concurrency)` 进行抓取并发限流，保护本地网络套接字不被耗尽；
* **连接复用**：维护长连接池，支持 HTTP/1.1 与 HTTP/2；
* **跟从重定向**：开启 `follow_redirects=True`，但限制最大跳数（防止重定向死循环）。

### 1.2 User-Agent 伪装与轮换池
从 `config.toml` 中加载 `user_agents` 候选池，随机选取合规的现代浏览器标头，降低被对端站点无差别拦截的概率。

---

## 2. WAF / Cloudflare 阻断治理：Fail-Fast 快速降级

### 2.1 传统缺陷
传统爬虫在遭遇 Cloudflare 5秒盾、人机验证（CAPTCHA）或 HTTP 403 时，往往尝试反复重试或换用代理，耗费上分钟甚至死循环挂死。

### 2.2 Aegis 确定性降级策略
Aegis 坚决放弃无意义的爬虫对抗：
1. **状态码检测**：若对端响应状态码为 `403 Forbidden`、`429 Too Many Requests`、`503 Service Unavailable`，立即判定为 `BLOCKED`；
2. **挑战页面特征识别**：若 HTML 标题包含 `Just a moment...`、`Cloudflare`、`Attention Required!`，同样判定为阻断；
3. **安全降级**：
   * 立即放弃该页面的正文抓取，耗时控制在 1 秒以内；
   * **自动降级回退至搜索引擎提供的该页 Snippet 摘要**；
   * 在元数据中显式标记 `status: "BLOCKED_FALLBACK_TO_SNIPPET"`，告知 Agent 该页面存在防护，可优先依赖摘要或选择备用链接。

---

## 3. 启发式正文清洗提炼 (`trafilatura`)

原始 HTML 充斥着海量的 DOM 树噪声（导航条、页眉页脚、侧边栏推荐、版权声明、广告与脚本）。若直接转成纯文本，信噪比低于 10%。

### 3.1 为什么选用 `trafilatura`？
* **学术级正文提取算法**：采用基于树结构与文本密度的启发式评估，精准锁定 `<article>`、`<main>` 或主体正文容器；
* **技术文档原生友好**：**100% 完整保留代码块（`<pre><code>`）与 Markdown 表格语法**，对技术资料提取质量极高；
* **极速 CPU 处理**：纯 C 绑定的底层解析，毫秒级完成单个网页正文清洗。

### 3.2 提炼实现契约

```python
import trafilatura

def extract_markdown_content(html: str) -> str:
    """
    使用 trafilatura 提取网页核心正文并转为标准 Markdown
    """
    if not html:
        return ""

    extracted = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=True,
        include_images=False,
        include_tables=True,
        include_formatting=True,
        favor_recall=False, # 优先保证高精度，宁缺毋滥
    )
    return (extracted or "").strip()
```
