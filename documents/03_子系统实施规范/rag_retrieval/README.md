# AegisRAG 独立代码检索子系统 - 实施技术规范索引

> **责任领域**：`AegisRAG/`（**物理独立子工程**，独立 `uv` 虚拟环境，默认监听 `127.0.0.1:8001`）
> **核心原则**：代码语法感知切分（拒绝暴力定长切片）、ONNX 本地 CPU 推理（零 GPU/PyTorch 依赖）、Qdrant 单库双模（Dense + Sparse）混合检索、内置 RRF 融合 + Cross-Encoder 精排。
>
> ### 实现状态图例（**阅读前必看**）
>
> | 标记 | 含义 |
> | :--- | :--- |
> | ✅ | **已实现**，且与本节描述一致（可在对应源码文件核对） |
> | 📋 | **规划中，尚未实现**。仅记录设计意图，**不得**据此认为系统具备该能力 |
>
> **当前全局状态**：`AegisRAG/src/` 下 `api/`、`embeddings/`、`indexer/`、`rerank/`、`storage/` 五个包的核心模块已按本套规范落地（详见 `07_directory_structure.md` §9 落地状态台账），已用真实本地 Qdrant + 真实 tree-sitter 解析跑通端到端冒烟验证；**尚未补齐测试**（`tests/` 仍是空白），RSE/MMR 等 §6 未来增强也仍未实现。本规范套件（01~07）的正文仍按 📋 标注"设计意图"，不逐条改写成实现细节说明书——具体"哪些文件已经真的存在"以 `07` §9 的台账为准，请勿混淆"规范记录的设计意图"与"当前代码真实状态"这两件事。
>
> 本批规范的原则：**配置值一律不在文档中硬编码**，均以 `AegisRAG/config/rag_config.toml` 为唯一真源；文档只说明语义与默认值。

---

## 1. 文档拓扑结构与技术规范

| 文档序号 | 技术领域 | 状态 | 核心规范与设计重点 |
| :--- | :--- | :--: | :--- |
| [01_architecture_overview.md](./01_architecture_overview.md) | **总体架构与数据流** | 📋 | Ingest（索引写入）与 Retrieve（在线检索）双流水线拓扑、模块划分（`indexer/` `embeddings/` `storage/` `api/`）、独立子工程物理隔离纪律、双部署形态（本地嵌入 / Docker） |
| [02_chunking_and_parsing.md](./02_chunking_and_parsing.md) | **语法感知切分与索引触发** | 📋 | Tree-sitter AST 切分（C/C++/Go）、非 AST 语言的降级切分策略、Markdown 标题分块、证据元数据 Schema、索引触发时机与增量再索引 |
| [03_embedding_and_storage.md](./03_embedding_and_storage.md) | **向量化与 Qdrant 存储** | 📋 | FastEmbed Dense/Sparse 双路生成、Qdrant Collection Schema（命名向量 + Payload）、维度一致性校验、幂等写入（确定性 Point ID）、失效数据清理 |
| [04_hybrid_retrieval_and_rerank.md](./04_hybrid_retrieval_and_rerank.md) | **混合检索与精排** | 📋 | Dense/Sparse 双路召回、Qdrant 原生 RRF 融合、Payload 预过滤、Cross-Encoder 精排（**核心范围，非可选项**）、低置信度与空结果治理、职责边界（查询改写类增强不属于 RAG） |
| [05_http_api_and_client_contract.md](./05_http_api_and_client_contract.md) | **服务契约与客户端适配** | 📋 / ✅ | 📋 `POST /api/v1/retrieve`、`POST /api/v1/documents/ingest`、`GET /api/v1/health` 服务端契约；✅ Agent 侧 `tools/builtin/rag_search.py` 客户端适配器**已实现**，本规范是其对端契约的补全 |
| [06_evaluation_and_benchmarking.md](./06_evaluation_and_benchmarking.md) | **检索质量评测与基准** | 📋 | 接入**已实现**的零 LLM 评测 harness（`src/evaluation/rag_bench/`）、金标数据集构建方法、Dense/Sparse/Hybrid/Rerank 四组消融矩阵——`02`/`03`/`04` 各处"未来增强"项能否落地的量化依据 |
| [07_directory_structure.md](./07_directory_structure.md) | **目录结构与工程分层** | 📋 | `src/` 权威目录树（含 `rerank/` 独立成包等裁决记录）、依赖方向矩阵、打包约定——**本规范其余各篇的物理路径唯一真源** |

---

## 2. 核心架构拓扑（概览，详见 `01`）

```text
                        ┌──────────────────────────────────────────┐
                        │      AegisRAG 独立子工程 (:8001)           │
                        │      独立 uv 虚拟环境，物理隔离于 Agent     │
                        └──────────────────────────────────────────┘
   [ Ingest 流水线 ]  📋                          [ Retrieve 流水线 ]  📋
   仓库文件 → 语言分发                              Query
      │                                              │
      ▼                                      ┌───────┴───────┐
   语法感知切分                                ▼               ▼
   (tree-sitter / Markdown /                Dense 编码      Sparse 编码
    通用降级切分)                          (bge-small)      (bm25)
      │                                        │               │
      ▼                                        ▼               ▼
   Dense + Sparse 双路向量化          Qdrant dense_top_k  Qdrant sparse_top_k
      │                                        └───────┬───────┘
      ▼                                                ▼
   Qdrant 幂等写入                              Qdrant 原生 RRF 融合
   (确定性 Point ID，                              │ fusion_top_k
    file_path+content_hash)                        ▼
                                       Cross-Encoder 精排 (rerank.model_name)
                                                  │ default_top_k
                                                  ▼
                                          结构化 JSON（含 file_path/行号/git_commit）
```

候选数量（`dense_top_k`/`sparse_top_k`/`fusion_top_k`/`default_top_k`）均为 `[retrieval]` 配置项，具体数值见 §4，图中不重复标注字面数字。Agent 侧只经由 `tools/builtin/rag_search.py`（`AegisTool` 契约，✅ 已实现）通过 `httpx` 调用 Retrieve 流水线；Ingest 流水线的触发时机与调用方见 `02` §1。

---

## 3. 代码映射一览（规划路径，📋 待创建）

* **服务配置**：[`AegisRAG/config/rag_config.toml`](file:///home/Skualeilu/Projects/Aegis/AegisRAG/config/rag_config.toml)（已存在，`[server]` `[qdrant]` `[embedding]` `[indexer]` 四段）
* **AST 语法切分器**：`AegisRAG/src/indexer/ast_splitter.py` 📋
* **Markdown 标题切分器**：`AegisRAG/src/indexer/markdown_splitter.py` 📋
* **通用降级切分器**：`AegisRAG/src/indexer/fallback_splitter.py` 📋（见 `02` §3，本规范新引入，milestone 尚未列出）
* **向量化管道**：`AegisRAG/src/embeddings/pipeline.py` 📋
* **Qdrant 存储适配器**：`AegisRAG/src/storage/qdrant_store.py` 📋
* **Cross-Encoder 精排器**：`AegisRAG/src/rerank/reranker.py` 📋（核心范围，非可选项，见 `04` §3；独立成包而非挂在 `indexer/` 下，裁决见 `07`）
* **FastAPI 接入层**：`AegisRAG/src/api/` 📋
* **Agent 侧客户端**：[`AegisAgent/src/tools/builtin/rag_search.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/tools/builtin/rag_search.py) ✅ **已实现**（服务端契约需与其字段对齐，见 `05`）
* **评测基线脚本**：`AegisAgent/src/evaluation/rag_bench/rag_service_client.py` 📋（**放在 AegisAgent 侧**，见 `06` §4 / `01` §6 的跨虚拟环境边界说明；通过 HTTP 调用 AegisRAG，接入**已实现**的 [`AegisAgent/src/evaluation/rag_bench/`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/evaluation/rag_bench)）

---

## 4. 配置项唯一真源

所有可调参数位于 `AegisRAG/config/rag_config.toml`，**文档不重复其数值**：

| 段落 | 配置键 | 语义 |
| :--- | :--- | :--- |
| `[server]` | `host` / `port` / `workers` / `timeout_sec` | FastAPI 监听地址与请求超时 |
| `[qdrant]` | `mode` | `"local"`（本地嵌入式存储）或 `"server"`（独立 Docker 容器） |
| `[qdrant]` | `storage_path` | 本地模式的持久化目录（`storage/qdrant_data/`） |
| `[qdrant]` | `host` / `port` | 独立容器模式的连接地址（默认 `:6333`） |
| `[qdrant]` | `collection_name` | Collection 名称（`aegis_code_chunks`） |
| `[qdrant]` | `vector_size` | Dense 向量维度，**必须**与当前生效 Embedding 模型的真实输出维度一致——`api/app.py` 启动期用 `probe_dense_dimension()` 真实探测校验，不一致直接 fail-fast（见 `03` §1） |
| `[qdrant]` | `distance` | 向量距离度量（`Cosine`） |
| `[embedding]` | `mode` | Dense 向量来源：`"remote"`（**默认**，走 `[embedding.remote]`）或 `"local"`（走 `[embedding.local]`），仿照 `[qdrant].mode` 的双模式设计 |
| `[embedding]` | `cache_dir` | FastEmbed ONNX 模型缓存目录——**Sparse (BM25) 恒本地，本项无论何种 `mode` 都生效** |
| `[embedding]` | `batch_size` / `max_length` | 批处理大小与单切片截断上限 |
| `[embedding.local]` | `model_name` | 本地 Dense 嵌入模型（默认 `BAAI/bge-small-en-v1.5`） |
| `[embedding.remote]` | `base_url` / `model` / `api_key_env` / `timeout_sec` | OpenAI 兼容 `/embeddings` 接口（默认网关 `https://api.openlux.ai/v1`；`model` 当前是占位值 `CHANGE_ME_EMBEDDING_MODEL`，待真实模型 ID 填入，见 `07` §9 台账） |
| `[indexer]` | `chunk_size` / `chunk_overlap` | **仅对降级/通用切分器生效**（AST 与 Markdown 切分以语法边界为准，见 `02` §2 对本项适用范围的说明） |
| `[indexer]` | `supported_languages` | 当前为 `["c", "cpp", "go", "python"]`——**注意**：`python` 目前无对应 `tree-sitter` 语法包依赖锁定，走的是降级切分而非真 AST（见 `02` §3，属既有配置与 milestone 草案的纠偏） |
| `[retrieval]` | `dense_top_k` / `sparse_top_k` | 双路召回各自的 prefetch 候选数量（`04` §1） |
| `[retrieval]` | `fusion_top_k` | RRF 融合后进入精排的候选数量（`04` §1/§3） |
| `[retrieval]` | `default_top_k` | 请求未显式传 `top_k` 时的最终返回数量（`04` §3，`05` §1.1） |
| `[retrieval]` | `rse_max_gap` / `mmr_lambda` | **预留、当前不生效**——`04` §6 未来增强（RSE/MMR）启用时才消费，见 `rag_config.toml` 内联注释 |
| `[rerank]` | `mode` | 精排模型来源：`"remote"`（**默认**，走 `[rerank.remote]`）或 `"local"`（走 `[rerank.local]`），核心范围非可选项——不管哪种 `mode`，精排本身都必须做 |
| `[rerank]` | `cache_dir` | 精排模型 ONNX 缓存目录（仅 `mode="local"` 时生效） |
| `[rerank]` | `min_score` | 触发响应体 `low_confidence=true` 的阈值（`04` §4）——**占位值，需实现后用 `06` 的评测基线校准，不是已验证的默认值** |
| `[rerank.local]` | `model_name` | 本地 Cross-Encoder 精排模型（默认 `BAAI/bge-reranker-base`） |
| `[rerank.remote]` | `base_url` / `model` / `api_key_env` / `timeout_sec` | OpenAI 兼容风格 `/rerank` 接口（默认网关 `https://api.openlux.ai/v1`；`model` 当前是占位值 `CHANGE_ME_RERANK_MODEL`，待真实模型 ID 填入，见 `07` §9 台账；协议约定非 OpenAI 官方规范，见 `04` §3 的免责提醒） |

> **一致性纪律**（沿用 ADR `技术选型/rag_retrieval.md` §2.2，v2 补充）：`[qdrant].vector_size` 必须与当前生效 Embedding 模型（`[embedding].mode` 指向的 `local`/`remote` 那一个）的真实输出维度一致；`mode="local"` 时人工核对，`mode="remote"` 时由启动期 `probe_dense_dimension()` 自动核对并 fail-fast，不再是纯人工纪律。

---

## 5. 环境变量唯一真源

来源 `AegisRAG/.env.example`（已存在）。**v2 修订**：`[embedding]`/`[rerank]` 默认 `mode="remote"` 后，`EMBEDDING_API_KEY`/`RERANK_API_KEY` 从"架构预留、当前不消费"变成了**默认路径下的必填项**：

| 变量 | 用途 | 何时必填 |
| :--- | :--- | :--- |
| `QDRANT_API_KEY` | `[qdrant].mode="server"` 时连接独立 Qdrant 容器的鉴权密钥 | 仅当目标 Qdrant 容器**启用了鉴权**时才需要；`mode="local"` 恒不消费此变量 |
| `EMBEDDING_API_KEY` | `[embedding.remote]` 的鉴权密钥（默认网关 `https://api.openlux.ai/v1`） | `[embedding].mode="remote"`（**默认值**）时必填；缺失会在服务启动期被 `EmbeddingPipeline` 拒绝（`UpstreamModelError`）。`mode="local"` 时不消费 |
| `RERANK_API_KEY` | `[rerank.remote]` 的鉴权密钥（同一默认网关） | `[rerank].mode="remote"`（**默认值**）时必填，语义与 `EMBEDDING_API_KEY` 相同但**是独立的密钥**，不要共用同一个值。`mode="local"` 时不消费 |

**已知问题（截至本次修订，需要人工修复）**：当前 `AegisRAG/.env` 里 `EMBEDDING_API_KEY` 的值被误填成了 `https://api.openlux.ai/v1`（这是 `base_url`，应该填在 `rag_config.toml` 里，不是密钥）——这不是一个能用的真实密钥，会导致远端请求以一个明显不是 Token 的字符串去做 Bearer 鉴权。需要替换成真实的 API Key。

**缺省行为**：`mode="server"` 且目标容器要求鉴权但 `QDRANT_API_KEY` 未设置时，连接应在启动期就失败并在 `GET /api/v1/health` 中体现（见 `01` §5），不应该静默重试或把错误延迟到第一次真实查询才暴露；`EMBEDDING_API_KEY`/`RERANK_API_KEY` 缺失时的 fail-fast 行为参见 `01` §5 与 `05` 的 `UPSTREAM_MODEL_ERROR`（502）错误码。
