# 目录结构与工程分层规范

> **责任领域**：`AegisRAG/` 全工程目录布局
> **契约基线**：`01`–`06` 规范 + `documents/技术选型/rag_retrieval.md`（ADR）
> **文档状态**：v1（首版，📋 规划中，代码尚未落地）。本文件是 AegisRAG 目录结构的**唯一权威来源**；`01`~`06` 中出现的模块路径以本文为准，冲突以本文裁决。
> **体例对照**：结构与栏目对齐 `AegisAgent` 侧的 `documents/agent_runtime/10_directory_structure.md`（同一套治理纪律，规模按 AegisRAG 实际复杂度裁剪）。

---

## 1. 设计原则

1. **Ingest 与 Retrieve 共用底座，不共用编排**
   `embeddings/`（向量化）与 `storage/`（Qdrant 适配）同时服务两条流水线，是两者的共用底座；但 `indexer/`（切分，Ingest 专属）与 `rerank/`（精排，Retrieve 专属）不得互相依赖——两条流水线各自的编排逻辑留在 `api/`，不下沉进底座包。

2. **精排是 Retrieve 阶段模块，不是 Ingest 阶段模块**
   `reranker.py` 在最早的草稿里曾经挂在 `indexer/` 下（因为二者都涉及"模型推理"），但 `indexer/` 的语义是"Ingest 侧切分"，精排发生在查询时的 Retrieve 路径——两者生命周期、触发时机完全不同。裁决为独立的 `rerank/` 包，与 `embeddings/` 同级、同构（两者都是"加载一个 ONNX 模型 + 批处理推理"，理应用同一种目录形状）。

3. **配置分段对应目录分包**
   `rag_config.toml` 的 `[embedding]`/`[rerank]`/`[indexer]`/`[retrieval]` 四段与 `embeddings/`/`rerank/`/`indexer/`/`api/`（检索编排参数）四个目录一一对应，改配置结构时同步检查目录结构是否也该跟着调整，两者不允许长期漂移。

4. **纯函数与 I/O 分层**
   `indexer/` 的切分算法本身（给定文本返回切片列表）与"从磁盘读文件"应分离到不同函数/模块，保持切分逻辑可离线单测，不需要真实文件系统或 Qdrant 连接。

5. **零 Chat LLM 依赖是打包层面的硬约束**
   呼应 `01` §6：`pyproject.toml` 的 `dependencies` 列表里不得出现任何 Chat Completions SDK（如 `openai`）。这条不只是"运行时不调用"的行为约定，也是"依赖清单里物理上不存在"的打包约定，两层都要守住。

6. **评测脚本不进 AegisRAG**
   `AegisRAG` 是独立虚拟环境（`01` §1），无法 import `AegisAgent/src/evaluation/rag_bench/` 的数据集与指标代码；评测适配脚本因此归属 `AegisAgent` 一侧，通过 HTTP 调用 AegisRAG，与 `rag_search.py` 走同一条客户端路径，不在 AegisRAG 内部另开一条特殊通道。

---

## 2. `AegisRAG/src/` 详细结构

```text
AegisRAG/src/
├── __init__.py                             对外能力边界占位
│
├── api/                          ✅         交付层：FastAPI 路由 + 编排调用（不含业务逻辑）
│   ├── __init__.py
│   ├── app.py                    ✅         FastAPI 装配 + lifespan（Qdrant 连接 + 维度自动探测校验 + 远端/本地模型装配）
│   ├── settings.py               ✅         rag_config.toml 强类型装配（含 embedding/rerank 的 local/remote 嵌套配置）
│   ├── schemas.py                ✅         RetrieveRequest/Response、IngestRequest/Response DTO（05 §1）
│   ├── errors.py                 ✅         领域异常 → HTTP 状态码映射（05 §2，含 v2 新增 UpstreamModelError→502）
│   ├── __main__.py               ✅         uvicorn 入口（127.0.0.1:8001）
│   └── routes/
│       ├── __init__.py
│       ├── retrieve.py           ✅         POST /api/v1/retrieve（04 §1~§3 编排：召回→融合→过滤→精排）
│       ├── ingest.py             ✅         POST /api/v1/documents/ingest（02 §1 触发语义 + 03 §3/§4 幂等写入与清理）
│       └── health.py             ✅         GET /api/v1/health（01 §5 故障隔离契约）
│
├── indexer/                      ✅         Ingest 侧：语言分发 + 语法感知切分（02）
│   ├── __init__.py
│   ├── dispatch.py               ✅         按扩展名路由到具体切分器 + 文件级降级（02 §2/§4）
│   ├── ast_splitter.py           ✅         tree-sitter C/C++/Go 语法树切分（02 §4）
│   ├── markdown_splitter.py      ✅         MarkdownHeaderTextSplitter 标题层级切分（02 §5）
│   ├── fallback_splitter.py      ✅         Python 及未匹配语言的降级切分（02 §3，纠偏后新增）
│   └── metadata.py               ✅         统一组装证据元数据 Schema（02 §6：file_path/content_hash/chunk_index 等）
│
├── embeddings/                   ✅         Dense/Sparse 双路向量化，Ingest 与 Retrieve 共用（03 §1）
│   ├── __init__.py
│   └── pipeline.py               ✅         Dense 双模式（远端 OpenAI 兼容 /embeddings 默认 / 本地 FastEmbed 兜底）+ Sparse 恒本地
│
├── rerank/                       ✅         Cross-Encoder 精排，Retrieve 专属（04 §3；不属于 indexer/，见裁决①）
│   ├── __init__.py
│   └── reranker.py               ✅         双模式：远端 OpenAI 兼容风格 /rerank 默认 / 本地 TextCrossEncoder 兜底
│
└── storage/                      ✅         Qdrant 客户端适配，Ingest 与 Retrieve 共用（03 §2~§4）
    ├── __init__.py
    ├── qdrant_store.py           ✅         Collection 初始化 + 维度校验 + 命名向量/Payload 读写 + RRF 混合检索
    └── ids.py                    ✅         确定性 Point ID 计算（03 §3：uuid5(repo_name:file_path:start_line:content_hash)）
```

**RSE/MMR（04 §6）未实现**：`[retrieval].rse_max_gap`/`mmr_lambda` 两项配置能被正确读取但不接线生效，符合"非本轮核心范围"的既定裁决。评测脚本 `AegisAgent/src/evaluation/rag_bench/rag_service_client.py`（06 §4，裁决②）本轮同样未写——它属于 `AegisAgent` 一侧，不在本次 `AegisRAG/` 编码范围内。

---

## 3. `AegisRAG/` 全景结构

```text
AegisRAG/
├── config/
│   └── rag_config.toml           ✅         已存在。[server]/[qdrant]/[embedding]/[indexer]/[retrieval]/[rerank] 六段
├── pyproject.toml  uv.lock  .env  .env.example  .python-version   ✅         已存在（wheel packages 已同步 `src/rerank`）
├── README.md                     ⬜         仍为空文件，待补（见 §4 裁决⑤）
│
├── src/                                      ← 见 §2（本轮代码已落地，详见落地状态台账 §9）
│
├── tests/                        📋         与 src 镜像的测试树（当前**完全不存在**，连空目录骨架都没有）
│   ├── conftest.py               📋         共享 fixtures（mock Qdrant client、临时 ONNX 缓存目录等）
│   ├── indexer/                  📋
│   ├── embeddings/                📋
│   ├── rerank/                    📋
│   ├── storage/                   📋
│   └── api/                       📋
│
└── storage/                                  运行时数据（已 gitignore，目录本身已存在）
    ├── cache/                    ✅         FastEmbed ONNX 模型缓存（`[embedding].cache_dir`/`[rerank].cache_dir`）
    └── qdrant_data/               ✅         `[qdrant].mode="local"` 时的嵌入式持久化目录
```

**`tests/` 现状说明**：不同于 `AegisAgent/tests/`（已有 conftest 与各子系统空目录骨架），AegisRAG 目前连测试目录骨架都未建立。这与 `documents/里程碑/AegisRAG/rag_retrieval.md` 标注的 `[ ] [ ]`（代码未实现）一致——测试路线本身应在核心代码落地后另行规划（参照 `AegisAgent` 侧 `documents/测试路线.md` 的做法），不在本文档展开。

---

## 4. 裁决记录

| # | 冲突点 | 裁决 | 理由 |
| :-: | :--- | :--- | :--- |
| ① | `reranker.py` 归属：早期草稿放在 `indexer/`（`01` 旧版 §3 曾这样描述），还是独立 `rerank/` 包 | **独立 `src/rerank/` 包**，`rag_config.toml` 同步拆出独立的 `[rerank]` 段（不再共用 `[embedding]`） | 精排属于 Retrieve 阶段，与 Ingest 专属的 `indexer/` 语义不符；`rerank/` 与 `embeddings/` 同构（都是"加载 ONNX 模型 + 批处理"），更容易维护 |
| ② | 评测适配脚本放在 `AegisRAG/scripts/` 还是 `AegisAgent/src/evaluation/rag_bench/` | **放在 `AegisAgent` 侧**（`rag_service_client.py`），AegisRAG 不新增 `scripts/` 目录 | AegisRAG 是独立虚拟环境，无法 import `rag_bench` 的数据集/指标代码；评测脚本本质是 `rag_bench` 的一个 HTTP 数据源，归属方应看"它依赖谁"而非"它测的是谁" |
| ③ | `supported_languages` 是否包含 `python`/`rust` 的真 AST 支持 | **仅 C/C++/Go 是真 AST**（`tree-sitter-*` 已锁定依赖）；`python` 走 `indexer/fallback_splitter.py` 降级切分；`rust` 移出当前范围 | 见 `02` §3 的完整裁决理由；此处只做归档，不重复论证 |
| ④ | 召回/融合/返回数量（Top-K 系列）写死在代码里还是配置化 | **配置化**，`[retrieval]` 新增 `dense_top_k`/`sparse_top_k`/`fusion_top_k`/`default_top_k` | 与 `[indexer]`/`[embedding]` 等既有段落的配置纪律保持一致，避免调参需要改代码重新部署 |
| ⑤ | `AegisRAG/README.md` 当前是空文件，是否需要立刻补 | **暂不在本轮处理**，登记为已知缺口 | 本轮聚焦目录结构与架构设计两份文档；`README.md` 的内容应该在 `src/` 真正有代码之后再写（避免写一份很快过时的"快速开始"） |
| ⑥ | Dense Embedding / Rerank 是否维持 ADR 原定的"纯本地 ONNX"，还是改为可调用远端网关 | **双模式，远程为默认**：`[embedding]`/`[rerank]` 各自新增 `mode`（`"remote"`/`"local"`）+ 嵌套的 `.local`/`.remote` 子段；默认网关 `https://api.openlux.ai/v1`，本地 FastEmbed 保留为离线/无 key 时的兜底 | 用户明确要求补上远端 URL/模型配置；ADR §2.2 本就预留了"也可配置 OpenAI text-embedding-3-small"的可能性，双模式设计与 `[qdrant].mode` 的 local/server 先例一致，不引入新的设计语言 |
| ⑦ | Sparse (BM25) 是否跟随 `[embedding].mode` 一起切远端 | **不跟随，恒本地** | BM25 是基于语料的词法统计方法，本质上不存在"远程 BM25 API"这种东西；跟随切换没有意义，`[embedding].cache_dir` 因此无论 `mode` 为何都必须生效 |
| ⑧ | 远端 Rerank 走什么协议（OpenAI 官方无标准 rerank 端点） | **采用 `{model,query,documents}` → `{results:[{index,relevance_score}]}` 的事实标准约定**，明确标注"非官方规范，需对照实际网关核实" | 用户要求"只做 openai 格式兼容"；由于 OpenAI 本身无此端点，选用部分 OpenAI 兼容网关常见的约定作为最小合理假设，如实标注不确定性而非假装已验证 |
| ⑨ | `mode="remote"` 时 Dense 向量真实维度未知，`[qdrant].vector_size` 该怎么保证一致 | **启动期自动探测校验**：`EmbeddingPipeline.probe_dense_dimension()` 真实调用一次，与配置值不一致直接 `DimensionMismatchError` fail-fast | 从"文档里写一致性纪律靠人工遵守"升级为"代码自动校验"，避免真实模型 ID 填入后忘记同步改 `vector_size` 导致静默写坏索引 |

---

## 5. 依赖方向矩阵

行 = 调用方，列 = 被依赖方。`✔` 允许，`✘` 禁止。

| ↓ 调用 / → 被调用 | indexer | embeddings | rerank | storage | api |
| :--- | :--: | :--: | :--: | :--: | :--: |
| **indexer** | — | ✔ | ✘ | ✘ | ✘ |
| **embeddings** | ✘ | — | ✘ | ✘ | ✘ |
| **rerank** | ✘ | ✘ | — | ✘ | ✘ |
| **storage** | ✘ | ✘ | ✘ | — | ✘ |
| **api** | ✔ | ✔ | ✔ | ✔ | — |

**关键约束**：

* `indexer/` 只在"切分后立即向量化"这一条路径上依赖 `embeddings/`（对应 `01` §2.1 Ingest 流水线相邻两步），不得依赖 `rerank/`/`storage/`——落盘写入统一由 `api/` 编排调用 `storage/` 完成，`indexer/` 本身不碰 Qdrant；
* `embeddings/`、`rerank/`、`storage/` 三个底座包**互相之间零依赖**，也不得反向依赖 `api/`——保持三者是可独立单测的纯粹层，这也是 `06` 消融矩阵（Dense Only / Sparse Only / Hybrid+RRF / Hybrid+Rerank）能够干净拼装的前提；
* 全部五个包都不依赖 `AegisAgent` 的任何模块（`01` §1）；`api/settings.py` 直接读 `rag_config.toml`，不经过任何跨工程配置层。

---

## 6. 打包与资源约定

`pyproject.toml` 的 `[tool.hatch.build.targets.wheel] packages` 必须覆盖：

```toml
packages = ["src/api", "src/indexer", "src/embeddings", "src/rerank", "src/storage"]
```

（已同步更新至真实的 `AegisRAG/pyproject.toml`，与本文档保持一致。）

**依赖清单纪律**（呼应 `01` §6 与本文 §1 原则 5）：`dependencies` 列表里不得出现 `openai`、`anthropic` 等 Chat LLM SDK；新增依赖前先确认它是否会把一个"推理"能力偷偷带进这个本该是纯检索服务的子工程。

**模型缓存目录**：`[embedding].cache_dir` 与 `[rerank].cache_dir` 当前都指向 `storage/cache/fastembed`（同一目录），两个 ONNX 模型（`bge-small-en-v1.5` 与 `bge-reranker-base`）共享同一个缓存根目录，`fastembed` 库按模型名自动分子目录，不需要手工再拆分路径。

---

## 7. 命名与占位约定

* **切片标识**：一律 `chunk_id`（`storage/ids.py` 产出的确定性 UUID5 字符串），不使用自增整数或随机 UUID4——幂等写入与评测金标集复用都依赖这一点（`03` §3、`06` §2）。
* **实现状态标记**：`✅` = 已实现（目前仅 `rag_config.toml` 本体、`storage/` 下两个运行时数据目录、四个原有空包骨架）；`📋` = 规划中。本文档 §2/§3 中的具体文件**尚无一个已落地**，全部待创建。
* **空目录占位**：需要入库但暂无内容的目录一律放 `.gitkeep`；Python 包目录必须有 `__init__.py`（`src/rerank/__init__.py` 已随本轮创建，其余 `indexer/embeddings/storage/api` 下的具体模块文件尚未创建）。
* **仓库标识**：多仓库场景下统一用 `repo_name`（人类可读标识，如 `aegis-agent`），不与 `repo_root`（绝对路径，仅索引时使用）混用（`05` §1.2）。

---

## 8. 溯源对照

| 结构 | 依据 |
| :--- | :--- |
| `api/routes/retrieve.py` | `04`（混合检索与精排） |
| `api/routes/ingest.py` | `02` §1（索引触发）、`03` §3/§4（幂等写入与失效清理） |
| `api/routes/health.py` | `01` §5（故障隔离契约） |
| `indexer/ast_splitter.py` / `markdown_splitter.py` / `fallback_splitter.py` | `02` §2~§5 |
| `indexer/metadata.py` | `02` §6（证据元数据 Schema） |
| `embeddings/pipeline.py` | `03` §1 |
| `rerank/reranker.py` | `04` §3；归属裁决见本文 §4① |
| `storage/qdrant_store.py` / `ids.py` | `03` §2~§3 |
| `[retrieval]`/`[rerank]` 配置段 | `README.md` §4；本文 §4④ |
| `AegisAgent/src/evaluation/rag_bench/rag_service_client.py` | `06` §4；归属裁决见本文 §4② |

---

## 9. 落地状态台账

| 项 | 状态 |
| :--- | :--- |
| `pyproject.toml` 依赖声明与 `uv.lock` | ✅ 已完成（`packages` 列表已同步 `src/rerank`） |
| `rag_config.toml` 六段配置 | ✅ 已完成 |
| `src/{api,indexer,embeddings,rerank,storage}` 包骨架 | ✅ 已完成 |
| `src/` 下具体模块文件（§2 列出的全部 `.py`） | ✅ 已完成（18 个模块文件；已用真实本地 Qdrant + 真实 tree-sitter 解析跑通端到端 ingest→retrieve 冒烟验证，含幂等重复索引、dense_only 调试模式、维度不匹配 fail-fast、`workers>1`+`local` fail-fast） |
| RSE/MMR 算法本体（04 §6） | ⬜ 未实现（配置项可读取但不接线，符合非核心范围的既定裁决） |
| `tests/` 目录骨架与 pytest 用例 | ⬜ 未开始（本轮按要求不产出测试） |
| `AegisAgent/src/evaluation/rag_bench/rag_service_client.py` | ⬜ 未开始（归属 `AegisAgent` 一侧，不在本次编码范围内） |
| `AegisRAG/README.md` | ⬜ 空文件，待补（`src/` 已有实际代码，具备补写条件，暂未处理） |
