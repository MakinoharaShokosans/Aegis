# AegisRAG 总体架构与数据流规范

> **责任领域**：`AegisRAG/` 整体拓扑、数据流与模块边界（**物理目录结构与依赖矩阵见 `07_directory_structure.md`，本文档不重复**）
> **状态**：📋 规划中，尚未实现
> **核心原则**：Ingest（索引写入）与 Retrieve（在线检索）双流水线物理解耦、独立子工程零反向依赖、双部署形态可切换、不持有 Chat LLM 客户端。

---

## 1. 为什么是物理独立子工程，而非 Agent 内 Sidecar

`AegisAgent/src/services/bash_shell/` 与 `services/web_search/` 是**同工程 Sidecar**——独立进程但共享一个 `uv` 虚拟环境与代码仓库。`AegisRAG/` 不是：它有自己的 `pyproject.toml`、自己的 `uv.lock`、自己的虚拟环境（`.venv`）。

**原因**（`技术选型/rag_retrieval.md` 命名说明 + `AegisAgent` 侧 `10_directory_structure.md` 裁决项③⑧）：

1. **重依赖隔离**：`tree-sitter`、`tree-sitter-c/cpp/go`、`fastembed`（内含 `onnxruntime`）都是携带 C 扩展的重依赖。混进 Agent 主工程会拖慢主工程的 `uv sync`，且 C 扩展段错误会直接杀死宿主进程；
2. **比 Sidecar 更强的隔离**：同工程 Sidecar 理论上仍可能被误 `import agent_runtime.*`（需要人工纪律约束）；独立子工程**物理上不可能**——不同虚拟环境里根本没有 `agent_runtime` 这个包可以导入。这是本子系统在依赖纪律上唯一比 `bash_shell`/`web_search` 更强的一点，值得在实现时保持，不要为了"图方便共享代码"而破坏它（例如误把两个工程的 `pyproject.toml` 合并、或用 `sys.path` hack 互相引用）。

## 2. 双流水线拓扑

AegisRAG 对外只有两类职责，对应两条独立触发、独立扩缩容的流水线：

### 2.1 Ingest 流水线（索引写入，批量/离线特征）

```text
目标仓库文件（工作区根目录下的源码/文档）
        │
        ▼
   语言/类型分发（按扩展名匹配 [indexer].supported_languages，见 02 §1）
        │
        ▼
   语法感知切分（tree-sitter AST / Markdown 标题 / 通用降级，见 02，模块见 07 §2 indexer/）
        │
        ▼
   Dense + Sparse 双路向量化（embeddings/pipeline.py，见 03 §1）
        │
        ▼
   Qdrant 幂等写入（确定性 Point ID，覆盖式 upsert，见 03 §3）
```

触发时机、增量再索引与失效清理是**当前 ADR 与里程碑文档完全没有覆盖的设计空白**，本规范在 `02` §1 中给出具体方案（不是既成事实，是本轮新增的设计决策，实现时需与用户确认）。

### 2.2 Retrieve 流水线（在线检索，低延迟特征）

即 `技术选型/rag_retrieval.md` §1 已定稿的检索链路：Query → Dense/Sparse 双路编码 → Qdrant 双路召回（`[retrieval].dense_top_k`/`sparse_top_k`） → 原生 RRF 融合（`[retrieval].fusion_top_k`） → Cross-Encoder 精排（`rerank/reranker.py`，`[retrieval].default_top_k`） → 结构化 JSON。详见 `04`；召回/融合/返回数量的具体默认值一律以 `rag_config.toml` 为准，本文档不重复。

**两条流水线必须能独立失败而不互相拖累**：Ingest 侧的长耗时批处理不应阻塞 Retrieve 侧的低延迟查询请求——这是 `[server].workers` 与 FastAPI 异步路由设计时需要考虑的约束（Ingest 走后台任务/独立 worker，不占用处理 `/retrieve` 请求的事件循环）。

## 3. 模块职责一览（物理目录见 `07`）

| 模块 | 承担的流水线阶段 | 一句话职责 |
| :--- | :--- | :--- |
| `api/` | 两条流水线的统一入口 | 请求校验 + 编排调用，不含业务逻辑 |
| `indexer/` | Ingest | 语言分发 + 语法感知切分，产出携带元数据的切片 |
| `embeddings/` | Ingest（切分后）+ Retrieve（查询编码） | Dense/Sparse 双路向量化，双流水线共用同一份编码逻辑 |
| `rerank/` | Retrieve（精排阶段） | Cross-Encoder 交叉编码打分，独立于 `indexer/`（详见 `07` 裁决记录，它不是 Ingest 侧模块） |
| `storage/` | 两条流水线的存储适配 | Qdrant 客户端：Collection 初始化、写入、查询、删除 |

依赖方向、每个目录下的具体文件清单、打包配置，一律见 `07_directory_structure.md`——本文档只负责说清楚"数据怎么流"，不重复"文件放哪"。

## 4. 部署形态：本地嵌入 vs 独立容器

由 `[qdrant].mode` 二选一，两者共享**完全相同**的 `storage/qdrant_store.py` 客户端代码（`qdrant-client` 同时支持 `:memory:`/本地路径与远程 gRPC/HTTP 连接，仅初始化参数不同）：

| 模式 | 适用场景 | 特点 |
| :--- | :--- | :--- |
| `local`（`storage_path` 指向 `storage/qdrant_data/`） | 单机本地开发、演示、CI | 零额外部署，进程内嵌入式存储；**不支持多进程并发写入**（`[server].workers` 必须为 `1`，否则多进程同时打开同一本地存储文件会报错或数据损坏） |
| `server`（连接 `host:port`，默认 `:6333`） | 需要多进程/多副本、需要 Qdrant Dashboard 可视化排查 | 需要额外起 Docker 容器；支持并发写入，`[server].workers` 可 `>1` |

> **实现时的强制校验点**：`local` 模式下若 `[server].workers > 1`，服务启动时应直接拒绝（fail-fast）而不是留给用户在生产环境踩坑——这条约束目前不存在于任何既有文档，是本规范新增的正确性要求。

## 5. 故障隔离契约（与 Agent 侧的关系）

AegisRAG 不可达时，Agent 侧 `tools/builtin/rag_search.py` 通过 `ServiceClient` 捕获 `DependencyUnavailableError` 并转为 `ToolResult.failure(...)`（已实现，✅）——与 `bash`/`web_search` 工具的降级策略完全一致：**RAG 服务挂了不应该让整个 Agent 任务崩溃**，而是作为一次可反思的工具失败反馈给模型（触发 `consecutive_errors` 计数与重规划路径，而非硬熔断）。

服务端实现时需保证：

* 启动期 Qdrant 连接失败 / Collection 维度不匹配 → 服务本身可以正常起来并响应 `GET /api/v1/health`（返回降级状态），但 `/api/v1/retrieve` 应返回明确的 `503 COLLECTION_NOT_READY`（见 `05` §2），而不是让请求 500 崩溃或无限挂起；
* Embedding 模型加载失败（ONNX 文件缺失/损坏）同理，需要在 `/api/v1/health` 中可观测。

## 6. 职责边界：AegisRAG 不持有 Chat LLM 客户端

**这是一条硬边界，不是留白**：AegisRAG 全程只调用 FastEmbed（Dense/Sparse 编码 + Cross-Encoder 精排，均为 ONNX 本地推理）与 Qdrant，**不依赖、不调用任何 Chat Completions 接口**——`AegisRAG/pyproject.toml` 不应该出现 `openai` 一类的 LLM SDK 依赖（`07` §5 的打包/依赖清单同样受此约束）。这与它"物理独立子工程"的定位（§1）是同一件事的两面：拉进一个 Chat LLM 客户端，就意味着要处理 API Key、端点降级、重试退避这整套 `AegisAgent/src/agent_runtime/llm/` 已经在做的事情，纯粹是重复建设，而且会让这个本该"输入 query 字符串、输出结构化切片"的纯函数式检索服务背上不必要的外部依赖和故障面。

**具体后果**：任何需要"先用 LLM 生成/改写一段文本，再拿这段文本去检索"的技术（例如查询扩写、假设性文档生成一类的查询增强手法），**都不属于 AegisRAG 的职责范围**，因为那一步的本质是"推理"而不是"检索"。这类需求如果确实有价值，做法应该是：**Agent 在调用 `rag_search` 工具之前，自己用已有的 LLM 调用能力把 query 文本改写好，再把改写后的文本作为普通的 `query` 参数传给 `/api/v1/retrieve`**——AegisRAG 拿到什么文本就编码检索什么文本，不关心也不需要知道这段文本是用户原话还是模型改写过的产物，接口契约（`05` §1.1）完全不需要为此新增任何字段。这条边界原则在 `04` §4/§6 各有一处具体应用（CRAG 式低置信度回退、查询语义改写类增强的排除），同一原则也是 `06` 的评测脚本必须放在 `AegisAgent` 侧而非 `AegisRAG` 侧的依据之一（见 `07` 裁决记录）——评测脚本要读取 `src/evaluation/rag_bench/` 的数据集与指标代码，那是 `AegisAgent` 虚拟环境里的包，AegisRAG 的独立虚拟环境（§1）里天然导入不到，只能通过 HTTP 调用 AegisRAG，而不是把评测逻辑搬进 AegisRAG。

> **与 `[embedding]`/`[rerank]` 的 `mode="remote"` 不冲突的原因**：`03`/`04` 引入的远端 Embedding/Rerank 调用（默认网关 `https://api.openlux.ai/v1`）看起来"AegisRAG 在对外发请求"，但它调用的是**结构化、单一职责的接口**——"给一段文本，返回一个定长向量"或"给 query+documents，返回相关性分数数组"，输入输出形状固定、无对话历史、无工具调用、无开放式生成，本质上和调用一个远程函数没有区别。这与"Chat LLM 客户端"（开放式对话、可被诱导偏离既定任务、需要处理多轮上下文与工具调用协议）是两类完全不同的依赖，本节的边界约束针对的是后者。判断标准很简单：AegisRAG 允许调用的远端接口，其请求/响应形状必须是**确定性契约化**的（正是本文档反复强调的"接口契约"精神），不允许出现"模型可以自由决定说什么"的开放式生成通道。
