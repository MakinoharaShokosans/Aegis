# Aegis 架构设计与实施技术规范全景索引 (Master Documentation Index)

> **定位**：Aegis (Engineering Research Agent) 工业级落地实施的权威设计蓝图与开发规范总入口。  
> **核心原则**：确定性包裹非确定性、单一职责微服务化、物理配额硬约束、双轨可观测与证据闭环。

---

## 1. 文档全景拓扑与子系统导航

整个系统的文档划分为三大实施规范套件、一套 ADR 技术决策集与一份技术栈物料清单 (BOM)：

```text
documents/
├── README.md                      # [当前文档] 全景总入口与实施导航
├── 技术栈.md                      # 全景技术栈清单 (Tech Stack BOM, 库/模型/版本/环境)
│
├── 技术选型/                      # 架构决策记录 (ADRs) - 阐述"为什么选该技术"
│   ├── README.md                  # ADR 导航与设计哲学
│   ├── agent_runtime.md           # Agent Runtime 架构决策
│   ├── bash_shell.md              # 受控代码沙箱决策
│   ├── web_search.md              # 外部网络信息摄取决策
│   ├── rag_retrieval.md           # 独立 RAG 检索基础设施决策
│   └── evaluation.md              # 自动化双轨评测体系决策
│
├── agent_runtime/                 # 【实施技术规范】核心调度宿主 (AegisAgent/src/agent_runtime/)
│   ├── README.md                  # Agent 运行时实施规范索引与步骤指引
│   ├── 01_architecture_overview.md
│   ├── 02_state_definition.md
│   ├── 03_node_specification.md
│   ├── 04_routing_and_control_flow.md
│   ├── 05_guardrails_implementation.md
│   ├── 06_memory_and_context_management.md
│   ├── 07_execution_context_management.md
│   ├── 08_skills_management.md
│   ├── 09_mcp_integration_and_governance.md
│   ├── 10_directory_structure.md  # 权威目录结构与工程分层（裁决记录）
│   ├── 11_http_api.md             # HTTP API 契约与对外交付入口
│   └── 12_research_subagent.md    # 外部检索隔离：信任边界、强类型契约、有界研究循环
│
├── bash_shell/                    # 【实施技术规范】受控 Shell 沙箱 (AegisAgent/src/services/bash_shell/)
│   ├── README.md                  # 沙箱子系统实施规范索引与架构拓扑
│   ├── 01_process_lifecycle_and_isolation.md   # PGID 进程组隔离与两段式超时熔断 (SIGTERM->SIGKILL)
│   ├── 02_resource_quotas_and_memory_pool.md   # setrlimit 物理边界 (2GB/50MB) 与内存池并发排队
│   ├── 03_command_audit_and_path_sandbox.md    # 高危正则审计、工作区根目录绑定 (CWD) 与防逃逸
│   ├── 04_output_governance_and_artifacts.md   # 流式分块读取、全量离线落盘与 Head/Tail 提炼
│   └── 05_http_api_and_client_contract.md      # FastAPI 路由契约与 ToolLayer 客户端适配
│
└── web_search/                    # 【实施技术规范】网络检索与清洗 (AegisAgent/src/services/web_search/)
    ├── README.md                  # 检索子系统实施规范索引与数据流拓扑
    ├── 01_search_architecture_and_data_flow.md # 检索、抓取、清洗、去重、卸载全链路数据流
    ├── 02_duckduckgo_provider_and_resilience.md# DuckDuckGoProvider 零 Key 实现与异步化封装
    ├── 03_async_fetch_and_trafilatura_clean.md # httpx 并发池、WAF 快速降级与 trafilatura Markdown 清洗
    ├── 04_content_dedup_and_artifacts_offloading.md # MD5 内容指纹去重与超长正文落盘卸载
    └── 05_http_api_and_client_contract.md      # FastAPI 路由契约与 ToolLayer 客户端适配
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
     `ToolRegistry(allow_untrusted=False)` 会在**构造期**拒绝把不可信工具注册进特权表（见 `12_research_subagent.md`）；
   - 单轮内多个 `tool_calls` 由 `ToolDispatcher` 通过 `asyncio.gather` 并发派发，端到端耗时大幅缩减。
3. **提示层安全三道互补机制**（详见 `agent_runtime/05`、`12`）：
   - **XML 定界协议**：`<project_rules>` / `<user_task>` / `<tool_observation>` / `<external_content>`
     内的文本一律视为数据而非指令（`system.md` §一）；
   - **Canary Token**：会话级确定性派生的金丝雀注入系统提示词，检测外泄并熔断（`guardrails/canary.py`）；
   - **权限分离**：不可信来源与特权工具不共处同一上下文，注入无法直接转化为特权动作（`12_research_subagent.md`）。
4. **证据链离线闭环**：
   - 无论是 Shell 编译日志还是 Web 抓取的长篇技术文档，凡超过 Token 阈值，一律流式落盘写入 `storage/artifacts/{task_id}/`；
   - 仅向 Agent 上下文注入保留语法结构的精炼摘要与磁盘句柄，需要时按需精确查阅。
