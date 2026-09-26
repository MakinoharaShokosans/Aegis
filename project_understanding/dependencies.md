# Dependencies & Interactions

> 状态标签: `[Current]`(实码校验) | `[Unverified]`(历史推断待印证) | `[Unknown]`(尚无证据) | `[Stale]`(待修正)

## 1. 跨服务通信链路
- `[Current]` **Frontend → Agent**:
  - 协议: HTTP REST (任务发起/控制) + SSE (Server-Sent Events 实时事件流)
  - 默认端口: `http://localhost:8000`
- `[Current]` **Agent → RAG 微服务**:
  - 协议: HTTP REST
  - 默认端口: `http://localhost:8001`
  - 交互场景: Agent 工具调用 `code_search` 向 RAG 服务请求 AST 切片检索与重排结果
- `[Current]` **Agent → 沙箱与网络工具**:
  - 交互模式: 支持独立进程服务化调用或内部模块直接加载 (`services/bash_shell`, `services/web_search`)

## 2. 外部依赖与数据流交互
- `[Current]` **LLM Provider**: OpenAI 兼容协议接口接入，负责 Planner / Executor / Evaluator 驱动。
- `[Current]` **Qdrant**: 本地嵌入式或网络向量数据库，承载双路向量检索与 RRF 融合。
- `[Current]` **SQLite**: `aiosqlite` 驱动的 WAL 模式本地数据库，用于 LangGraph 状态快照与断点续跑。
