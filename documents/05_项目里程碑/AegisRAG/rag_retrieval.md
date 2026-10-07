# AegisRAG 独立代码检索子系统功能与设计里程碑

> **对应设计规范**：`documents/技术选型/rag_retrieval.md`（ADR）与 `documents/rag_retrieval/`（实施技术规范 01~07）  
> **物理子工程**：`AegisRAG/`（独立 `uv` 虚拟环境与依赖空间）  
> **运行端口**：`:8001`（独立微服务进程）  
> **核心原则**：代码语法感知切分、ONNX 本地 CPU 推理（零 GPU 依赖）、Qdrant 稠密/稀疏单库双模混合检索、零 Chat LLM 依赖。  
> 
> **图例规范**：`[代码实现] [测试通过]`——本轮 `[x]` 均已用真实 tree-sitter 解析器 + 真实本地 Qdrant 跑通端到端手工冒烟验证（非 pytest 自动化用例），测试列统一保持 `[ ]`，如实区分"验证过能跑"与"有自动化回归覆盖"两件事。

---

## 一、架构设计与技术选型（已定稿）

- [x] [x] **物理独立子工程规划与环境解耦**
  - [x] [x] `AegisRAG` 作为独立子系统，拥有独立 `pyproject.toml` 与虚拟环境
  - [x] [x] 隔离 `tree-sitter`、`onnxruntime` 等 C/C++ 扩展重依赖，不污染 Agent 主工程
- [x] [x] **Qdrant 单库双模与内置 RRF 方案定稿**
  - [x] [x] 选型 Qdrant 原生同时支持 Dense 向量与 Sparse 向量空间
  - [x] [x] 采用数据库引擎层内置 RRF（倒排互惠融合）多路召回算子
- [x] [x] **FastEmbed 本地向量推理选型定稿**
  - [x] [x] 彻底告别 PyTorch / CUDA 强依赖，基于 ONNX Runtime 实现 CPU 毫秒级稠密/稀疏向量生成
  - [x] [x] 稠密向量对齐：默认 `BAAI/bge-small-en-v1.5`（384 维）
  - [x] [x] 稀疏向量对齐：采用 `Qdrant/bm25`
- [x] [x] **职责边界：AegisRAG 不持有 Chat LLM 客户端**（`documents/rag_retrieval/01` §6）
  - [x] [x] 全程只调用 FastEmbed（ONNX 本地推理）与 Qdrant，`pyproject.toml` 不出现任何 Chat Completions SDK
  - [x] [x] 查询语义改写类技术（HyDE 等）明确排除在 AegisRAG 职责外，需要时由 Agent 侧自行改写后传入普通 `query` 字符串

---

## 二、代码与文档语法感知切分 (`indexer/`)

- [x] [ ] **Tree-sitter AST 语法切分器 (`indexer/ast_splitter.py`)**
  - [x] [ ] 真 AST 范围锁定 C/C++/Go（对齐已锁定依赖 `tree-sitter-c/cpp/go`）；Python 走降级切分、Rust 移出范围——已用真实 C 源码验证 struct/function/`#define` 全部按语法边界正确切出，行号与证据元数据准确
  - [x] [ ] **"命中即停"递归遍历算法**：单一规则（命中边界节点类型就捕获且不再下探）同时处理"透明容器穿透"（`namespace_definition`/`declaration_list` 等非边界节点自动递归穿透）与"模板包裹边界"（`template_declaration` 整体作为一个切片，不会把内部 class/function 又切一遍）两类场景，不需要额外的"透明类型白名单"分支
  - [x] [ ] **尾随分号吸收**：`struct`/`class`/`enum`/`union` 定义节点本身不含结尾分号（tree-sitter 语法树把 `;` 作为独立兄弟节点），捕获后探测紧邻兄弟节点并吸收，保证切片是可直接阅读的完整语句
  - [x] [ ] **超大切片标记**：按 `len(text)//4` 近似 token 数（与 AegisAgent 侧 `observation_pruner` 等模块的估算口径保持一致）标记 `oversized`，不违反"保持语法块完整"原则去暴力腰斩
  - [x] [ ] **文件级降级**：单文件 AST 解析异常时捕获降级为通用切分并在 `IngestResponse.degraded_files` 如实上报，不中断整批 ingest；已用真实构造的非法 C 代码验证解析路径不崩溃
- [x] [ ] **Markdown 标题层级切分器 (`indexer/markdown_splitter.py`)**
  - [x] [ ] 按 H1~H3 切分，每个切片携带标题面包屑路径（`enclosing_scope`）
  - [x] [ ] **已知局限（如实记录，非遗漏）**：行号定位采用"按切片顺序累计原文行数"的近似算法，依赖 `MarkdownHeaderTextSplitter` 按文档顺序线性切分、不重排的假设——库版本升级若改变该行为需重新核实
- [x] [ ] **通用降级切分器 (`indexer/fallback_splitter.py`，milestone 草案未列出，本轮新增)**
  - [x] [ ] Python 走 `langchain_text_splitters.Language.PYTHON` 启发式切分（非真 AST，不引入新的 C 扩展依赖）；未识别语言走纯字符定长切分
  - [x] [ ] `[indexer].chunk_size`/`chunk_overlap` 两项配置**仅在本模块生效**——AST 与 Markdown 切分都以语法边界为准，不消费这两个值
- [x] [ ] **统一证据元数据 Schema (`indexer/metadata.py`)**
  - [x] [ ] `ChunkMetadata` 用 Pydantic 必填字段把"元数据缺失即拒绝入库"钉死在类型系统上，而非调用方散落的 if 判断
  - [x] [ ] 预留 `enclosing_scope`（CCH 未来增强）、`chunk_index`（RSE 未来增强）两个非强制字段

---

## 三、向量嵌入与 Qdrant 存储引擎 (`embeddings/`、`storage/`)

- [x] [ ] **Dense/Sparse 向量化管道 (`embeddings/pipeline.py`)**
  - [x] [ ] `SparseTextEmbedding`（Sparse，固定 `Qdrant/bm25`）批处理封装，Ingest 与 Retrieve 两条流水线共用同一份编码逻辑
  - [x] [ ] **v2 修订：Dense 向量来源改为可切换双模式**（`[embedding].mode`，默认 `"remote"`）——远端走 OpenAI 兼容 `POST {base_url}/embeddings`（默认网关 `https://api.openlux.ai/v1`，鉴权 `EMBEDDING_API_KEY`），本地保留 `TextEmbedding` 作为离线/无 key 兜底；已用 `httpx.MockTransport` 真实验证远端请求体/响应解析（`{"model","input"}` → 按 `index` 排序还原 `data[].embedding`）逻辑正确
  - [x] [ ] **Sparse 恒本地，刻意不跟随 `mode`**：BM25 是词法统计方法，没有"远程 BM25 API"这个概念，`[embedding].cache_dir` 因此无论 `mode` 为何都必须生效——这是本轮唯一没有被"改远程"波及的向量路径
  - [x] [ ] **`probe_dense_dimension()` 启动期自检**：远端模型真实维度实现前未知，`api/app.py` 的 `lifespan` 启动时真实探测一次并与 `[qdrant].vector_size` 比对，不一致直接 `DimensionMismatchError` fail-fast——把"一致性纪律"从人工核对升级为代码自动校验
- [x] [ ] **Qdrant 混合索引存储适配器 (`storage/qdrant_store.py`)**
  - [x] [ ] Collection 自动初始化；已存在时做**启动期维度强校验**并 fail-fast（`DimensionMismatchError`）——已用真实构造的维度不匹配场景验证会正确拒绝启动，不会带病运行到第一次写入才报错
  - [x] [ ] 命名向量（`dense`+`sparse`）+ Payload 混合写入，Payload 直接落地完整 `ChunkMetadata`
  - [x] [ ] 按语言的前置过滤（Payload Filtering）下推到 `prefetch` 查询层，而非先取回再在 Python 里过滤
- [x] [ ] **确定性 Point ID 与幂等写入 (`storage/ids.py`，milestone 草案未列出，本轮新增)**
  - [x] [ ] `uuid5(NAMESPACE, "repo_name:file_path:start_line:content_hash")`——同一切片重复 `ingest` 得到相同 ID，upsert 天然覆盖式幂等
  - [x] [ ] **已用真实重复 ingest 验证幂等性生效**：同一仓库第二次调用 `POST /documents/ingest`，`indexed=0, skipped=3`（全部因 ID 已存在被跳过），不是纸面设计
- [x] [ ] **失效数据清理 (`delete_stale`)**
  - [x] [ ] 按 `repo_name` + `file_path not in keep_list`（`must` + `must_not(MatchAny)`）批量删除源文件已不存在的旧切片，避免检索到"已被删除的代码"这种比"没检索到"更危险的错误
- [x] [ ] **批量写入分批处理（本轮性能优化，milestone 草案未列出）**
  - [x] [ ] `upsert_chunks`/`existing_ids` 按 256/批分批请求，避免大仓库一次 ingest 把数千个切片塞进单次超大 Qdrant 请求

---

## 四、重排模型与微服务接口 (`rerank/`、`api/`)

- [x] [ ] **Cross-Encoder 精排器 (`rerank/reranker.py`)**
  - [x] [ ] **API 纠偏**：实际类是 `fastembed.rerank.cross_encoder.TextCrossEncoder`，不是早期文档泛称的 `fastembed.Rerank`——本轮实现前逐一在 REPL 里核实了 FastEmbed/qdrant-client/tree-sitter 的真实签名，不凭记忆写代码
  - [x] [ ] **独立成 `rerank/` 顶层包，不挂在 `indexer/` 下**：精排发生在 Retrieve 阶段查询到达之后，与 Ingest 侧的语法切分生命周期完全不同（归属裁决见 `documents/rag_retrieval/07_directory_structure.md` §4①），`rag_config.toml` 同步拆出独立的 `[rerank]` 段
  - [x] [ ] `[rerank].min_score` 显式标注为**占位值**，代码与文档都注明需要用未来的评测基线（`06_evaluation_and_benchmarking.md`）校准，不假装是一个已验证过的合理默认值
  - [x] [ ] **v2 修订：改为可切换双模式**（`[rerank].mode`，默认 `"remote"`）——远端走 `POST {base_url}/rerank`（默认网关 `https://api.openlux.ai/v1`，鉴权 `RERANK_API_KEY`，与 embedding 端点**各自独立的 key**），本地保留 `TextCrossEncoder` 作为兜底
  - [x] [ ] **协议如实标注不确定性**：OpenAI 官方 API 没有标准 rerank 端点，`{"model","query","documents"}` → `{"results":[{"index","relevance_score"}]}` 是采用的事实标准约定而非已验证规范，代码注释与文档都明确写了"首次真实联调前需核实"，没有假装这是查证过的官方协议
  - [x] [ ] 已用 `httpx.MockTransport` 真实验证远端请求体/响应解析逻辑正确（不是空写没测过就当完工）
- [x] [ ] **FastAPI 微服务端点 (`api/`)**
  - [x] [ ] `POST /api/v1/retrieve`：双路召回（`[retrieval].dense_top_k`/`sparse_top_k`）→ RRF 融合（`fusion_top_k`）→ 精排 → `low_confidence` 标记；支持 `dense_only`/`sparse_only`/`hybrid_no_rerank` 调试模式（对应未来 `06` 消融矩阵）
  - [x] [ ] `POST /api/v1/documents/ingest`：遍历仓库 → 语言分发切分 → 增量幂等写入 → 失效清理，`git rev-parse HEAD` 解析索引时刻提交哈希（非 git 仓库安全降级为 `None`）
  - [x] [ ] `GET /api/v1/health`：Collection 未就绪或 Embedding 模型未加载时整体降级为 `degraded`（呼应 `01` §5 故障隔离契约）
  - [x] [ ] 领域异常体系（`RagError`/`CollectionNotReadyError`/`DimensionMismatchError`/`RepoNotIndexedError`/**`UpstreamModelError`（v2 新增，502，远端 Embedding/Rerank 网关失败）**）与 HTTP 状态码解耦，`app.py` 统一异常处理器转译（对齐 `AegisAgent` 侧 `bash_shell`/`web_search` 的既有约定风格）
  - [x] [ ] `chunk_id` 字段回填响应体——`05` 文档已把它列为不可省略字段，供未来 `rag_bench` 评测 harness 比对金标

---

## 五、关键设计决策与工程优化（本轮新增，milestone 草案完全未覆盖）

以下是实现过程中做出的、有实际约束力的设计判断，不是简单的"代码写完了"流水账：

- [x] [ ] **路由函数从 `async def` 改为同步 `def`（架构级修复）**
  - 三个端点函数体内没有任何真正的 `await`（FastEmbed/qdrant-client 都是同步阻塞调用），若保持 `async def`，每次 ONNX 推理与 Qdrant 调用都会独占事件循环，让并发的 `/retrieve` 与 `/documents/ingest` 请求互相卡住——直接违反 `01_architecture_overview.md` §2.2 "两条流水线不得互相拖累"的既定要求。FastAPI 对同步 `def` 路由会自动派发线程池，改后问题消失。
- [x] [ ] **`low_confidence` 量纲纠偏**：`dense_only`/`sparse_only`/`hybrid_no_rerank` 调试模式下的原始相似度/融合分数与 `[rerank].min_score`（专为 Cross-Encoder 分数校准）不是同一量纲，这三种模式下 `low_confidence` 恒为 `False`，不做无意义的跨量纲比较。
- [x] [ ] **健康检查改用 `count(exact=False)`**：存活探针不该为了报个大概的 `point_count` 在大 Collection 上付出精确扫描的代价。
- [x] [ ] **`local` 模式 + `workers>1` 启动期 fail-fast**（`01` §4 强制校验点，已用真实校验用例验证会正确拒绝）：本地嵌入式存储不支持多进程并发写入，写死在 `RagConfig` 的 `model_validator` 里，不留给用户在生产环境踩坑。
- [x] [ ] **评测脚本归属裁决**：`rag_service_client.py` 明确不放在 `AegisRAG/`，因为它要读取 `AegisAgent/src/evaluation/rag_bench/` 的数据集与指标代码，而两者是完全独立的虚拟环境——本轮不实现该脚本（归属 `AegisAgent` 一侧），只是把这条边界钉死，避免未来有人图省事放错位置。
- [x] [ ] **配置单一真源纪律**：召回/融合/返回数量、精排阈值全部抽成 `rag_config.toml` 的 `[retrieval]`/`[rerank]` 新增段，业务代码零散落字面量；发现自己早期文档描述里违反过这条纪律（Top-50/Top-30/Top-5 直接写死在 prose 里）后统一改成引用配置键名。
- [x] [ ] **v2：Dense Embedding / Rerank 从"纯本地 ONNX"改为"远端默认 + 本地兜底"双模式**（用户明确要求）：`[embedding]`/`[rerank]` 各自新增 `mode`，默认 `"remote"`，走 `https://api.openlux.ai/v1`；ADR §2.2 本就留了"也可配置 OpenAI Embedding"的口子，本次是把这个可能性落实为默认路径而非仅设计意图。**边界重新澄清**：`01` §6"AegisRAG 不持有 Chat LLM 客户端"这条硬边界并未被打破——远端 Embedding/Rerank 调用是结构化、单一职责的接口（固定输入输出形状，无对话历史、无开放式生成），与真正的 Chat Completions 是两类不同的依赖，边界约束针对的是后者。
- [x] [ ] **发现并如实记录一处真实配置错误**：核对 `.env` 时发现 `EMBEDDING_API_KEY` 的值被误填成了 `https://api.openlux.ai/v1`（这是网关地址，应该填在 `rag_config.toml` 而不是密钥槽位）——已在代码 review 脚本里实测验证这会导致鉴权头携带一个明显不是 Token 的字符串；未擅自"猜一个值改掉"，原样保留并在文档与本里程碑里两处标注，留给用户核实修正。

---

## 六、已知边界与后续工作（如实记录，未完成）

- [ ] [ ] **`[embedding.remote].model`/`[rerank.remote].model` 仍是占位符**（`CHANGE_ME_EMBEDDING_MODEL`/`CHANGE_ME_RERANK_MODEL`）：`api.openlux.ai/v1` 网关上这两个具体模型 ID 需要用户提供，填入前 `mode="remote"` 无法真实跑通。
- [ ] [ ] **`[qdrant].vector_size` 待与真实 Dense 模型维度对齐**：当前仍是本地 bge-small 的 384，真实模型 ID 填入后需要重启验证 `probe_dense_dimension()` 是否与之一致（若不一致会 fail-fast，见 §五）。
- [ ] [ ] **`.env` 里 `EMBEDDING_API_KEY` 误填成了 URL，需要用户替换成真实密钥**（见 §五 明确记录的配置错误）；`RERANK_API_KEY` 尚为空，同样待填。
- [ ] [ ] **远端 Rerank 协议未经真实网关验证**：`{"model","query","documents"}` → `{"results":[...]}` 是本轮采用的事实标准假设，不是核实过的官方文档，一旦真实联调发现网关实际协议不同，需要回头改 `rerank/reranker.py::_score_remote`。
- [ ] [ ] **RSE 相邻段落缝合 / MMR 多样性去重**（`04` §6 未来增强）：配置项 `rse_max_gap`/`mmr_lambda` 已能被正确读取（占位注释），算法本体未实现——需先有评测基线证明收益再投入。
- [ ] [ ] **`AegisAgent/src/evaluation/rag_bench/rag_service_client.py`**：评测 harness 接入脚本未写，`[rerank].min_score` 目前只是占位值。
- [ ] [ ] **`tests/` 目录骨架与 pytest 自动化用例**：本轮按要求不产出，当前的"能跑通"结论全部来自手工冒烟验证脚本（含本轮新增的 `httpx.MockTransport` 远端协议验证），不是可重复回归的测试套件。
- [ ] [ ] **`AegisRAG/README.md`**：仍是空文件，`src/` 已有实际代码具备补写条件，暂未处理。
