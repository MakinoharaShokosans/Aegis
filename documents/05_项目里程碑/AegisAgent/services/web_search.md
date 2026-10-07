# AegisAgent 免 Key 网络检索与清洗服务功能与设计里程碑

> **对应设计规范**：`documents/web_search/01~05`
> **责任模块**：`AegisAgent/src/services/web_search/` & `AegisAgent/src/tools/builtin/web_search.py`
> **运行端口**：`:8003`（独立微服务进程）
> **核心原则**：纯免 Key 检索、异步网页抓取清洗、MD5 内容去重、受限沙箱工具集成。
>
> **图例规范**：`[代码实现] [测试通过]`

---

## 一、免 Key 检索与弹性重试 (`provider.py`)

- [x] [x] **DuckDuckGo 纯免 Key 异步检索实现**
  - [x] [x] 彻底移除任何付费/商业 Key 强依赖，降低部署与使用门槛
  - [x] [x] 异步封装与指数退避重试（Exponential Backoff），对抗偶发网络抖动与限流
- [x] [x] **搜索结果结构化标准化**
  - [x] [x] 统一输出包含 `title`、`url`、`snippet` 的标准化结果序列

---

## 二、网页并发抓取与正文清洗 (`fetcher.py`)

- [x] [x] **异步并发抓取引擎**
  - [x] [x] 基于 `httpx.AsyncClient` 连接池与超时保护
  - [x] [x] WAF 拦截与非法内容快速失败与降级处理
- [x] [x] **Markdown 干净正文提取**
  - [x] [x] 集成 `trafilatura` 库过滤 HTML 冗余标签、导航栏与广告噪音
  - [x] [x] 提取排版干净的技术正文与原生 Markdown 代码块

---

## 三、内容指纹去重与离线卸载 (`dedup.py`)

- [x] [x] **MD5 语义正规化去重**
  - [x] [x] 文本空白字符正规化与 MD5 哈希指纹计算
  - [x] [x] 自动剔除同批次中高度重复的段落切片与镜像网页
- [x] [x] **超长正文离线落盘与摘要提取**
  - [x] [x] 超过大小阈值的网页正文写入磁盘产物库
  - [x] [x] 保留头部结构与核心摘要返回给上层

---

## 四、FastAPI 微服务与受限工具接入 (`server.py` & `client.py`)

- [x] [x] **独立 HTTP 服务契约**
  - [x] [x] 暴露 `POST /search` 与 `POST /fetch` 端点
- [x] [x] **只读受限工具契约（`trust="untrusted"`）**
  - [x] [x] `WebSearchTool` 作为受限叶子工具，仅由 `ResearchSubagent` 消费
  - [x] [x] 物理阻断原始网页直接流入主 Agent 特权上下文
