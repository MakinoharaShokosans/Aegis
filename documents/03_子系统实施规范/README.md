# 03_子系统实施规范 (Subsystem Implementation Specifications)

> **定位**：Aegis 各子系统工程落地的权威实施与接口规范集群。所有模块均遵循强契约、物理配额硬约束与不可信输入隔离准则。

---

## 目录索引与子系统导航

```text
03_子系统实施规范/
├── README.md                  # [当前文档] 子系统实施规范导航
├── agent_runtime/             # 🧠 调度内核与运行时实施规范 (AegisAgent/src/agent_runtime/)
│   ├── README.md              # • Agent 运行时规范总览
│   ├── 01_architecture_overview.md          # 架构概览与分层设计
│   ├── 02_state_definition.md               # 状态模型与强类型契约
│   ├── 03_node_specification.md             # 节点规范与纯函数计算闭包
│   ├── 04_routing_and_control_flow.md       # 路由与条件流转
│   ├── 05_guardrails_implementation.md      # 确定性安全护栏与 Canary 熔断
│   ├── 06_memory_and_context_management.md  # 记忆与上下文治理
│   ├── 07_execution_context_management.md   # 执行环境依赖与隔离上下文
│   ├── 08_skills_management.md              # 动态技能发现与加载机制
│   ├── 09_mcp_integration_and_governance.md # MCP 工具集成与特权管控
│   ├── 10_directory_structure.md            # 工程代码目录权威规约
│   ├── 11_http_api.md                       # FastAPI 网关与 SSE 流式接口
│   ├── 12_research_subagent.md              # 研究子智能体与信息净化
│   ├── 13_subagent_delegation.md            # 动态子智能体委派与权限收窄
│   └── 14_code_search_subagent.md           # 代码检索子智能体实施规范
│
├── bash_shell/                # 💻 受控代码沙箱实施规范 (AegisAgent/src/services/bash_shell/)
│   ├── README.md              # • 沙箱执行子系统总览
│   ├── 01_process_lifecycle_and_isolation.md   # PGID 进程组隔离与两段式硬超时熔断 (SIGTERM->SIGKILL)
│   ├── 02_resource_quotas_and_memory_pool.md   # setrlimit 内核物理资源硬约束 (2GB/50MB) 与并发排队
│   ├── 03_command_audit_and_path_sandbox.md    # 高危正则审计、CWD 路径边界绑定与防逃逸
│   ├── 04_output_governance_and_artifacts.md   # 流式日志截断治理与超长输出落盘卸载
│   └── 05_http_api_and_client_contract.md      # 沙箱独立进程 HTTP 服务契约与客户端适配
│
├── rag_retrieval/             # 🔍 代码语义检索子系统实施规范 (AegisRAG/)
│   ├── README.md              # • RAG 检索子系统总览与双流水线
│   ├── 01_architecture_overview.md            # Ingest / Retrieve 双流水线隔离
│   ├── 02_chunking_and_parsing.md             # 基于 Tree-sitter 的 AST 代码语法切分
│   ├── 03_embedding_and_storage.md            # FastEmbed 双路向量化与 Qdrant 存储
│   ├── 04_hybrid_retrieval_and_rerank.md      # Dense+Sparse 混合检索与 Cross-Encoder 重排
│   ├── 05_http_api_and_client_contract.md     # RAG Sidecar 服务 HTTP API 契约
│   ├── 06_evaluation_and_benchmarking.md      # RAGBench 评测框架与召回率量化
│   └── 07_directory_structure.md              # AegisRAG 独立工程目录规范
│
├── web_search/                # 🌐 外部网络检索子系统实施规范 (AegisAgent/src/services/web_search/)
│   ├── README.md              # • 网络检索子系统总览
│   ├── 01_search_architecture_and_data_flow.md # 检索、抓取、清洗、去重与卸载全链路
│   ├── 02_duckduckgo_provider_and_resilience.md# DuckDuckGo 免 Key 驱动与容错设计
│   ├── 03_async_fetch_and_trafilatura_clean.md # 异步高并发抓取与 Trafilatura 正文提取
│   ├── 04_content_dedup_and_artifacts_offloading.md # MD5 页面去重与 Artifacts 离线落盘
│   └── 05_http_api_and_client_contract.md      # 检索服务独立进程 HTTP 契约
│
├── frontend/                  # 🖥️ Web 前端架构与交互实施规范 (AegisWeb/)
│   ├── frontend_design.md     # 前端视觉层次、组件体系、Monaco Diff 与 HITL 审批卡片设计规范
│   └── frontend_workflow.md   # 前端生命周期、会话流转、快捷键映射与 SSE 实时渲染时序图
│
└── api/                       # 📡 服务间通信与外部网关契约
    └── api_documentation.md   # 全系统统一 HTTP RESTful API、SSE 事件规范与请求响应 Schema
```
