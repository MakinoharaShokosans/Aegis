# Modules Directory

> 状态标签: `[Current]`(实码校验) | `[Unverified]`(历史推断待印证) | `[Unknown]`(尚无证据) | `[Stale]`(待修正)

## 1. AegisAgent 核心模块
- `[Current]` **Agent Runtime (`AegisAgent/src/agent_runtime`)**:
  - 职责: LangGraph 状态机编排、节点决策、检查点持久化与运行上下文管理。
  - 核心文件: `workflow.py`, `state.py`, `checkpoint.py`, `nodes/`, `edges/`
- `[Current]` **Guardrails 治理防线 (`AegisAgent/src/agent_runtime/guardrails`)**:
  - 职责: 拦截死循环、观察截断、双轨预算账本与命令权限审计。
  - 核心文件: `loop_detector.py`, `observation_pruner.py`, `budget_ledger.py`, `canary.py`
- `[Current]` **Bash Shell 沙箱 (`AegisAgent/src/services/bash_shell`)**:
  - 职责: 独立 Linux PGID 进程组管理、setrlimit 物理资源约束、全量日志落盘与 Head/Tail 提取。
  - 核心文件: `sandbox.py`, `audit.py`, `memory_pool.py`, `app.py`
- `[Current]` **Web Search 外部检索 (`AegisAgent/src/services/web_search`)**:
  - 职责: 联网检索、网页正文提取与清洗、去重过滤。
  - 核心文件: `providers.py`, `extractor.py`, `dedup.py`

## 2. AegisRAG 独立检索子系统
- `[Current]` **AST & 文档切片 (`AegisRAG/src/indexer`)**:
  - 职责: 基于 Tree-Sitter 的代码语法树切分与 Markdown 标题面包屑层级切分。
  - 核心文件: `ast_splitter.py`, `markdown_splitter.py`, `dispatch.py`
- `[Current]` **向量与重排 (`AegisRAG/src/embeddings`, `src/rerank`)**:
  - 职责: FastEmbed 双路向量化（稠密+稀疏）与 Cross-Encoder 深度重排。
  - 核心文件: `embeddings/pipeline.py`, `rerank/reranker.py`
- `[Current]` **向量存储 (`AegisRAG/src/storage`)**:
  - 职责: Qdrant 客户端封装与 RRF 融合检索。
  - 核心文件: `storage/qdrant_store.py`

## 3. AegisFrontend 前端交互系统
- `[Current]` **状态与通信 (`AegisFrontend/src/stores`, `src/api`)**:
  - 职责: SSE 实时长连接驱动、Zustand 全局状态（任务、工作区、RAG、UI）与断线重连。
  - 核心文件: `api/sse.ts`, `stores/useTaskStore.ts`, `stores/useWorkspaceStore.ts`
- `[Current]` **UI 交互组件 (`AegisFrontend/src/components`)**:
  - 职责: 思考瀑布流渲染、Monaco Editor 差异对比与 HITL 审批弹窗。
