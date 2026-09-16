# Aegis 实施里程碑全景总索引 (Milestone Master Index)

> **定位**：Aegis 各系统与子模块功能就绪度、架构设计特性与实施进度全景跟踪入口。  
> **更新纪律**：各里程碑文档采用 `- [x]` / `- [ ]` 格式，严格聚焦已具备的**系统功能与设计特性**。

---

## 📁 里程碑文档拓扑

```text
documents/里程碑/
├── README.md                                    # [当前文档] 里程碑全景主索引
│
├── AegisAgent/                                  # Agent 宿主主系统实施里程碑
│   ├── skills.md                                # 专家领域技能 (Skills) 系统
│   ├── mcp.md                                   # MCP 协议接入与静态审查安全治理
│   ├── research_subagent.md                     # 外部检索隔离与研究子智能体
│   ├── guardrails.md                            # 确定性护栏、金丝雀 Token 与防注入体系
│   │
│   ├── agent_runtime/                           # 核心运行时解耦模块
│   │   ├── state_and_domain.md                  # 状态契约与共享领域模型
│   │   ├── global_context.md                    # 全局多层上下文装配与 XML 沙箱
│   │   ├── execution_context.md                 # 微观执行上下文与记忆生命周期
│   │   ├── graph_workflow.md                    # LangGraph 状态机编排与路由边
│   │   └── http_api.md                          # HTTP API 网关与自省端点
│   │
│   └── services/                                # Sidecar 微服务沙箱
│       ├── bash_shell.md                        # 受控 Bash Shell 沙箱微服务 (:8002)
│       └── web_search.md                        # 免 Key 网络检索与清洗微服务 (:8003)
│
└── AegisRAG/                                    # 独立代码检索子系统 (:8001)
    └── rag_retrieval.md                         # 源码 AST 切分、向量化与混合检索
```

---

## 📊 模块完成度一览

| 模块名称 | 物理路径 | 状态 | 对应里程碑文档 |
| :--- | :--- | :---: | :--- |
| **Skills 技能系统** | `AegisAgent/src/agent_runtime/skills/` | **已完成** | [`skills.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/skills.md) |
| **MCP 接入治理** | `AegisAgent/src/mcps/` | **已完成** | [`mcp.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/mcp.md) |
| **研究子智能体** | `AegisAgent/src/agent_runtime/research/` | **已完成** | [`research_subagent.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/research_subagent.md) |
| **确定性护栏体系** | `AegisAgent/src/agent_runtime/guardrails/` | **已完成** | [`guardrails.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/guardrails.md) |
| **状态与领域模型** | `AegisAgent/src/agent_runtime/state.py` | **已完成** | [`agent_runtime/state_and_domain.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/agent_runtime/state_and_domain.md) |
| **全局上下文装配** | `AegisAgent/src/agent_runtime/context.py` | **已完成** | [`agent_runtime/global_context.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/agent_runtime/global_context.md) |
| **微观上下文与记忆** | `AegisAgent/src/agent_runtime/execution_context.py` | **已完成** | [`agent_runtime/execution_context.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/agent_runtime/execution_context.md) |
| **图状态机与工作流** | `AegisAgent/src/agent_runtime/workflow.py` | **已完成** | [`agent_runtime/graph_workflow.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/agent_runtime/graph_workflow.md) |
| **HTTP API 网关** | `AegisAgent/src/agent_runtime/api/` | **已完成** | [`agent_runtime/http_api.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/agent_runtime/http_api.md) |
| **受控 Bash 沙箱** | `AegisAgent/src/services/bash_shell/` | **已完成** | [`services/bash_shell.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/services/bash_shell.md) |
| **免 Key 检索服务** | `AegisAgent/src/services/web_search/` | **已完成** | [`services/web_search.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/services/web_search.md) |
| **AegisRAG 代码检索** | `AegisRAG/` | **待推进** | [`AegisRAG/rag_retrieval.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisRAG/rag_retrieval.md) |
