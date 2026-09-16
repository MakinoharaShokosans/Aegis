# Aegis 实施里程碑全景总索引 (Milestone Master Index)

> **定位**：Aegis 各系统与子模块功能就绪度、架构设计特性与实施进度全景跟踪入口。  
> 
> **双勾状态图例规范**：
> - `[代码完成] [测试通过]`
> - `[x] [x]`：**代码开发已完成** 且 **自动化测试已验证通过**
> - `[x] [ ]`：**代码开发已完成** 但 **尚未补齐独立专测/测试待完善**
> - `[ ] [ ]`：**规划中**，代码尚未实现，测试未开始

---

## 📁 里程碑文档拓扑

```text
documents/里程碑/
├── README.md                                    # [当前文档] 里程碑全景主索引与双勾图例
│
├── AegisAgent/                                  # 👑 Agent 宿主主系统实施里程碑
│   ├── skills.md                                # 1. 专家领域技能 (Skills) 渐进式披露与安全隔离
│   ├── mcp.md                                   # 2. MCP 协议接入、静态审查与 stdio 配额治理
│   ├── research_subagent.md                     # 3. 外部不可信检索隔离与研究子智能体
│   ├── guardrails.md                            # 4. 确定性护栏、会话级金丝雀 Token 与防注入体系
│   │
│   ├── agent_runtime/                           # 🧠 Agent Runtime 核心引擎解耦子模块
│   │   ├── state_and_domain.md                  # • 状态契约、物理度量与共享领域模型
│   │   ├── global_context.md                    # • 全局多层上下文装配与 XML 沙箱协议
│   │   ├── execution_context.md                 # • 微观执行上下文、SQLite 记忆与水位线压缩
│   │   ├── graph_workflow.md                    # • LangGraph 状态机编排与确定性路由边
│   │   └── http_api.md                          # • FastAPI 网关、任务流式推送与系统自省端点
│   │
│   └── services/                                # 🛡️ Sidecar 微服务沙箱
│       ├── bash_shell.md                        # • 受控 Bash Shell 沙箱微服务 (:8002)
│       └── web_search.md                        # • 免 Key 网络检索与清洗微服务 (:8003)
│
└── AegisRAG/                                    # 📚 独立代码检索子系统 (:8001)
    └── rag_retrieval.md                         # • AST 语法切分、FastEmbed 向量化与 Qdrant 检索
```

---

## 📊 模块完成度与测试验收一览

| 模块名称 | 物理路径 | 代码状态 | 测试状态 | 对应里程碑文档 |
| :--- | :--- | :---: | :---: | :--- |
| **确定性护栏体系** | `AegisAgent/src/agent_runtime/guardrails/` | `[x]` | `[x]` | [`guardrails.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/guardrails.md) |
| **状态与领域模型** | `AegisAgent/src/agent_runtime/state.py` | `[x]` | `[x]` | [`agent_runtime/state_and_domain.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/agent_runtime/state_and_domain.md) |
| **全局上下文装配** | `AegisAgent/src/agent_runtime/context.py` | `[x]` | `[x]` | [`agent_runtime/global_context.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/agent_runtime/global_context.md) |
| **微观上下文与记忆** | `AegisAgent/src/agent_runtime/execution_context.py` | `[x]` | `[x]` | [`agent_runtime/execution_context.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/agent_runtime/execution_context.md) |
| **图状态机与工作流** | `AegisAgent/src/agent_runtime/workflow.py` | `[x]` | `[x]` | [`agent_runtime/graph_workflow.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/agent_runtime/graph_workflow.md) |
| **HTTP API 网关** | `AegisAgent/src/agent_runtime/api/` | `[x]` | `[x]` | [`agent_runtime/http_api.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/agent_runtime/http_api.md) |
| **受控 Bash 沙箱** | `AegisAgent/src/services/bash_shell/` | `[x]` | `[x]` | [`services/bash_shell.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/services/bash_shell.md) |
| **免 Key 检索服务** | `AegisAgent/src/services/web_search/` | `[x]` | `[x]` | [`services/web_search.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/services/web_search.md) |
| **Skills 技能系统** | `AegisAgent/src/agent_runtime/skills/` | `[x]` | `[x]` | [`skills.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/skills.md) |
| **MCP 接入治理** | `AegisAgent/src/mcps/` | `[x]` | `[ ]` | [`mcp.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/mcp.md) |
| **研究子智能体** | `AegisAgent/src/agent_runtime/research/` | `[x]` | `[ ]` | [`research_subagent.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisAgent/research_subagent.md) |
| **AegisRAG 代码检索** | `AegisRAG/` | `[ ]` | `[ ]` | [`AegisRAG/rag_retrieval.md`](file:///home/Skualeilu/Projects/Aegis/documents/里程碑/AegisRAG/rag_retrieval.md) |
