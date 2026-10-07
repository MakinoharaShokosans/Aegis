# Aegis 架构设计与实施技术规范全景索引 (Master Documentation Index)

> **定位**：Aegis (Engineering Research Agent) 工业级落地实施的权威设计蓝图与开发规范总入口。
> **核心原则**：确定性包裹非确定性、单一职责微服务化、物理配额硬约束、双轨可观测与证据闭环。

---

## 1. 文档全景拓扑与子系统导航

文档库整体划分为清晰的 7 大分层目录，遵循高内聚、低耦合与从宏观到微观的认知流线：

```text
documents/
├── README.md                      # [当前文档] 全景总入口与导航
│
├── 01_项目架构/                   # 【架构总览中枢】系统宏观拓扑、分层架构模型与核心子系统设计
│   ├── README.md                  # • 架构总纲：系统宏观拓扑、五层分层模型、四大物理进程协同矩阵
│   ├── 01_Agent编排与状态机架构.md # • 调度内核：LangGraph 状态机推演、五大计算节点闭包注入、上下文治理
│   ├── 02_代码语义检索RAG架构.md   # • 知识检索：Tree-sitter AST切分、Dense+Sparse双路召回、Qdrant与Cross-Encoder
│   ├── 03_受控Linux沙箱与隔离架构.md # • 安全沙箱：PGID会话防孤儿、setrlimit内核物理配额、两段式硬超时熔断
│   ├── 04_Web前端与人机协同交互架构.md # • 前端控制台：React 19 + Zustand状态机、Monaco Diff比对、HITL卡片审批流
│   └── 05_服务通信与网关契约架构.md # • 接入网关：三道安全闸门（Host/Origin/Token）、SSE长连接事件总线
│
├── 02_技术选型/                   # 【架构决策记录 (ADRs)】阐述核心组件技术权衡与"为什么选该技术"
│   ├── README.md                  # • ADR 导航与设计哲学
│   ├── agent_runtime.md           # • Agent 编排框架选型 (LangGraph vs 传统自主循环)
│   ├── bash_shell.md              # • 代码执行沙箱选型 (原生进程受控沙箱 vs Docker / microVM)
│   ├── web_search.md              # • 外部网络检索选型 (DuckDuckGo 免 Key + Trafilatura)
│   ├── rag_retrieval.md           # • 代码语义检索基础设施选型 (Qdrant + FastEmbed + BGE-Reranker)
│   └── evaluation.md              # • 自动化双轨评测体系决策 (单元基准 + 真实 LLM 评测)
│
├── 03_子系统实施规范/             # 【各子系统详细落地规范】强类型契约、生命周期与边界硬约束
│   ├── README.md                  # • 子系统实施规范导航
│   ├── agent_runtime/             # • 核心调度宿主实施规范 (01~14 文档集群，含状态机、节点、子智能体委派)
│   ├── bash_shell/                # • 受控 Shell 沙箱实施规范 (01~05 文档集群，含进程组隔离、配额与审计)
│   ├── rag_retrieval/             # • 代码语义检索实施规范 (01~07 文档集群，含 AST 切分、混合检索与重排)
│   ├── web_search/                # • 外部网络检索实施规范 (01~05 文档集群，含异步抓取、去重与卸载)
│   ├── frontend/                  # • Web 前端交互规范 (UI/UX 视觉体系与状态机时序工作流)
│   └── api/                       # • 全系统 HTTP RESTful 与 SSE 流式事件契约
│
├── 04_测试与质量保障/             # 【测试路线与测试报告质量大盘】
│   ├── README.md                  # • 质量保障体系总览与执行门禁
│   ├── 测试报告/                  # • 自动化测试执行报告产物集群 (453 项测试通过率 100%)
│   │   ├── 00_全系统测试执行总纲与质量门禁报告.md
│   │   ├── 01_单元测试报告/       # Agent(263)、RAG(61)、Frontend(55) 单元测试报告
│   │   ├── 02_集成测试报告/       # LangGraph 状态机流转、FastAPI 安全闸门、前端流式通信
│   │   ├── 03_端到端与安全对抗报告/ # 权限越级对抗(24)、Canary 熔断(28)、崩溃断电续跑
│   │   └── 04_深度评测报告/       # 真实 LLM 评测矩阵、RAGBench 4组消融基准
│   └── 测试路线/                  # • 结构化全景测试路线体系
│       ├── 00_总测试路线.md        # • 质量门禁与金字塔分层总纲
│       ├── 01_单元测试/            # 纯函数算法、AST语法切分、Zustand状态机单测
│       ├── 02_集成测试/            # LangGraph节点流转、FastAPI微服务契约、SSE流式通信
│       ├── 03_端到端测试/          # 4大物理进程全链路业务闭环、kill -9崩溃断电续跑容灾
│       ├── 04_深度评测/            # 真实LLM前沿模型驱动评测、RAGBench消融基准与规范报告
│       └── 05_安全对抗测试/        # 权限正则黑名单绕过对抗、Prompt注入沙箱与Canary硬熔断
│
├── 05_项目里程碑/                 # 【功能就绪与实施全景】核心特性交付跟踪与双勾验收
│   ├── README.md                  # • 里程碑总览与进度板
│   ├── AegisAgent/                # • 调度核心、沙箱、搜索各阶段交付物记录
│   └── AegisRAG/                  # • 独立检索服务交付物记录
│
├── 06_技术栈与知识库/             # 【物料清单与知识库】全景依赖清单与核心三方库底层深度剖析
│   ├── README.md                  # • 知识库导航
│   ├── 技术栈.md                  # • 全景技术栈清单 (Tech Stack BOM: 库/模型/版本/环境)
│   └── tech-stack/                # • 单库深入原理文档集群 (Obsidian Search-First: Tree-sitter, Qdrant 等)
│
└── 07_面试与求职复盘/             # 【个人发展与面试备战】(已纳入 .gitignore 物理防泄露)
    ├── README.md                  # • 面试备战全景导航与题库索引
    ├── 简历Skills.md              # • 核心技术点与项目亮点精炼
    ├── 00_面试高频必杀总结与总览.md # • 电梯演讲与核心问答总纲
    └── 01~12 各专项题库文档       # • Agent、后端、数据库、前端、网络、RAG、源码深水区、八股与大厂真题
```

---

## 2. 子系统端口与进程边界

| 服务子系统 | 物理承载位置 | 运行方式 | 默认端口 | 核心通信协议 | 核心职责 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Agent API 网关** | `AegisAgent/src/agent_runtime/api/` | 宿主主进程 | `:8000` | HTTP REST + SSE | 外部交互唯一入口，驱动 LangGraph 状态机 |
| **AegisRAG 服务** | `AegisRAG/src/` | 独立 Sidecar | `:8001` | HTTP REST | 代码 AST 解析、FastEmbed (ONNX) 向量化与 Qdrant 检索 |
| **Bash Shell 沙箱**| `AegisAgent/src/services/bash_shell/`| 同工程独立进程 | `:8002` | HTTP REST | 受控命令行执行、物理资源熔断、日志离线卸载 |
| **Web Search 服务**| `AegisAgent/src/services/web_search/`| 同工程独立进程 | `:8003` | HTTP REST | DuckDuckGo 免 Key 检索、网页清洗、MD5 去重 |

---

## 3. 跨系统调用与依赖纪律

1. **Sidecar 契约不可穿透**：
   - `services/bash_shell` 与 `services/web_search` 作为独立进程运行，**严禁 import `agent_runtime` 下的任何模块**；
   - 两大服务各自通过轻量 `settings.py` 直接读取 `config/config.toml` 的对应段落。
2. **工具层统一接入与不可信数据隔离**：
   - `agent_runtime` 通过 `tools/builtin/bash.py`（等可信叶子工具）作为适配器，经由 `ServiceClient` 走 HTTP 与各微服务交互；
   - **`tools/builtin/web_search.py` 标记为 `trust="untrusted"`，不在主 Agent 工具表中**——它只由研究子智能体
     （`agent_runtime/research/`）在受限工具表内调用；主 Agent 的外部信息入口是 `delegate_research`，
     收到的是经强类型校验（URL 白名单 / 版本正则 / 长度上限）净化后的报告。
     `ToolRegistry(allow_untrusted=False)` 会在**构造期**拒绝把不可信工具注册进特权表（详见 `03_子系统实施规范/agent_runtime/12_research_subagent.md`）；
   - 单轮内多个 `tool_calls` 由 `ToolDispatcher` 通过 `asyncio.gather` 并发派发，端到端耗时大幅缩减。
3. **提示层与不可信面安全：六道互补机制**（详见 `03_子系统实施规范/agent_runtime/` 05、08、09、12、13）：
   - **XML 定界协议**：`<project_rules>` / `<user_task>` / `<tool_observation>` / `<external_content>` /
     `<available_skills>` / `<skill_sop>` 内的文本一律视为数据而非指令；
   - **Canary Token**：会话级确定性派生的金丝雀注入系统提示词，检测外泄并熔断（`guardrails/canary.py`）；
   - **权限分离（只读信息源）**：网络检索隔离在研究子智能体内，主 Agent 结构性地拿不到原始网页；
   - **能力衰减委派**：主 Agent 可动态组建受限子劳动力（`spawn_subagent`），
     但子级工具集 / 权限级别 / 递归深度均在**派发前一次性收窄**，且子级
     **不能请求人工审批**（防审批洗白 + 防副作用重复执行）、回流内容一律按不可信处理
     并由**引用白名单**核对；
   - **技能信任分级**：内置/全局技能可信、**工作区技能默认拒绝**，元数据做注入标注与截断，
     内容纳入 XML 定界信封；
   - **MCP 数据面/控制面分离**：工具描述消毒硬拒、结果标注；server 默认关闭、
     `trust="untrusted"` 且经**逐名授权**进入主工具表，stdio 子进程施加 setrlimit；
   - **接入层三道闸门**：`Host → Origin → 令牌`（纯 ASGI 中间件，不可被漏挂）。
     回环监听挡不住"用户浏览器里的恶意页面直接向 `127.0.0.1:8000` 提交审批"，
     因此 `POST /approve|/reject` 这类端点必须有独立于"端口隐私"的保护。
4. **可观测性旁路（不牺牲隔离）**：
   - 子智能体运行在 `tool_runner` 内部的**一个工具**里，节点级流式看不见它；
     `observability/event_bus.py` 提供任务级事件总线，把 `subagent.*` / `research.*`
     事件接进既有 SSE 管道（自动获得序号与断线重连）；
   - 事件只带元数据与**已裁剪摘要**（强制限长 300 字符），原始正文仍不进入
     主状态、主 Checkpoint 与事件流；`emit` 永不抛异常（旁路失败不影响任务）。
5. **证据链离线闭环**：
   - 无论是 Shell 编译日志还是 Web 抓取的长篇技术文档，凡超过 Token 阈值，一律流式落盘写入 `storage/artifacts/{task_id}/`；
   - 仅向 Agent 上下文注入保留语法结构的精炼摘要与磁盘句柄，需要时按需精确查阅。
