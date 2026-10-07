# Web Search - 全景架构与数据流规范

> **责任领域**：`AegisAgent/src/services/web_search/` 全系统  
> **核心原则**：单一职责微服务、管道化数据流转、轻量零成本。

---

## 1. 架构定位与业务场景

在工程研究中，Agent 经常需要摄取外部最新的技术资料，例如：
* 检索最新开源库的 API 变更或弃用说明；
* 查阅特定编译器或内核模块在特定架构下的编译报错排查方案；
* 获取特定技术规范的官方 RFC 手册。

传统大模型接入搜索时存在三大缺陷：
1. **网络爬虫无休止对抗**：遇到 Cloudflare / WAF 验证码时死循环重试，卡死 Agent；
2. **HTML 噪声巨大**：直接将原始网页 HTML 塞入上下文，包含上万字符的导航菜单、页脚版权、Cookie 弹窗与广告脚本；
3. **镜像站大量冗余**：同一个技术问题往往被数十个爬虫技术博客镜像转载，内容完全重复，白白消耗检索配额。

`web_search` 作为 Aegis 的独立伴生服务，构建了一条确定性的“检索 $\to$ 抓取 $\to$ 提炼 $\to$ 去重 $\to$ 卸载”流水线。

---

## 2. 端到端数据流转模型

```text
[ 输入: 关键词 "gcc 13 -Werror=address 解决方案" ]
                       │
                       ▼
             [ DuckDuckGoProvider ]
                       │ (调用 duckduckgo_search API)
                       ▼
             [ 获得 5 个候选链接 ]
             ├── Hit 1: https://gcc.gnu.org/bugzilla/show_bug.cgi?id=...
             ├── Hit 2: https://stackoverflow.com/questions/...
             ├── Hit 3: https://blog.csdn.net/xxx (镜像转载)
             ├── Hit 4: https://www.cnblogs.com/xxx (镜像转载)
             └── Hit 5: https://github.com/torvalds/linux/commit/...
                       │
                       ▼
         [ httpx 并发连接池 (Top-5 并行拉取) ]
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
  [ 遭遇 403 拦截 (如 StackOverflow) ]    [ 正常拉回 HTML (200 OK) ]
         │                           │
         ▼                           ▼
  [ Fail-Fast 降级 ]          [ trafilatura 启发式清洗 ]
  保留搜索 Snippet 摘要        剔除 JS/CSS/Nav/Ads，提炼 Markdown
         │                           │
         └─────────────┬─────────────┘
                       ▼
             [ MD5 内容指纹去重 ]
             Hit 3 与 Hit 4 正文计算出相同 MD5，剔除冗余项
                       │
                       ▼
             [ 超长内容离线卸载 ]
             Hit 1 正文 4,800 Token > 1,500 Token 阈值:
             - 全量落盘 storage/artifacts/{task_id}/web_c8e9...md
             - 上下文注入 200 字摘要 + 磁盘句柄
                       │
                       ▼
[ 输出: 干净、去重、带证据引用的结构化结果列表 ]
```

---

## 3. 独立进程解耦红线

* **独立性**：`web_search` 仅作为 HTTP 服务的提供者，不 import 任何 `agent_runtime` 模块；
* **配置自持**：通过 `services.web_search.settings.WebSearchSettings` 直接读取 `config.toml` 中的 `[web_search]` 配置段；
* **环境安全**：默认仅监听 `127.0.0.1:8003`，只服务本地 Agent 进程。
