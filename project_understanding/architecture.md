# Architecture Model

> 状态标签: `[Current]`(实码校验) | `[Unverified]`(历史推断待印证) | `[Unknown]`(尚无证据) | `[Stale]`(待修正)

## 1. 系统宏观拓扑
```text
[ 用户端浏览器 ]
      │ (HTTP / SSE :5173 / :8000)
      ▼
┌────────────────────────────────────────────────────────┐
│ AegisFrontend (React 19 + Zustand + Monaco Editor)      │
└──────────────────────────┬─────────────────────────────┘
                           │ (HTTP REST / SSE 事件流)
                           ▼
┌────────────────────────────────────────────────────────┐
│ AegisAgent (FastAPI :8000)                             │
│  ├─ Agent Runtime (LangGraph 状态机: Planner-Executor-Evaluator)
│  ├─ Context & Guardrails (三层上下文治理 / 循环检测 / 预算账本)
│  └─ Service & Tool Layer:                              │
│       ├─ Bash Shell 沙箱服务 (PGID 隔离 / 资源配额)    │
│       ├─ Web Search 服务 (DuckDuckGo + 正文提取)       │
│       ├─ Subagent / MCP 托管生态                       │
│       └─ Code Search Tool ──┐                          │
└─────────────────────────────┼──────────────────────────┘
                              │ (HTTP :8001)
                              ▼
┌────────────────────────────────────────────────────────┐
│ AegisRAG (FastAPI :8001)                               │
│  ├─ Indexer: Tree-Sitter (AST 切分) + Markdown Splitter │
│  ├─ Embeddings: FastEmbed (ONNX 双路: 语义稠密 + 词法稀疏)
│  ├─ Storage: Qdrant 向量引擎 (内核级 RRF 混合融合召回)   │
│  └─ Reranker: Cross-Encoder 深度重排 (Top-5 精排交付)   │
└────────────────────────────────────────────────────────┘
```

## 2. 分层架构规范
- `[Current]` **展示交互层 (Presentation)**: `AegisFrontend/` - 状态瀑布流、思考卡片、Monaco 代码 Diff 与人工介入 (HITL) 审批。
- `[Current]` **调度编排层 (Orchestration)**: `AegisAgent/src/agent_runtime/` - LangGraph 状态机，解耦 Planner、Executor、Evaluator 决策环。
- `[Current]` **安全与治理层 (Governance)**: `AegisAgent/src/agent_runtime/guardrails/` - 语法感知截断、双轨预算账本、XML 定界与 Canary 探针。
- `[Current]` **执行与沙箱层 (Execution)**: `AegisAgent/src/services/bash_shell/` - 物理隔离进程组与 Linux setrlimit 配额执行。
- `[Current]` **知识检索基础设施 (Retrieval)**: `AegisRAG/` - 独立微服务化代码与文档索引、AST 语法树块抽取与混合重排。
