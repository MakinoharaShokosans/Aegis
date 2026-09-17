# 向量化管道与 Qdrant 存储规范

> **责任领域**：`AegisRAG/src/embeddings/`、`AegisRAG/src/storage/`
> **状态**：✅ 已实现（`embeddings/pipeline.py`、`storage/qdrant_store.py`、`storage/ids.py`）
> **核心原则**：Dense 向量来源可切换（远端 OpenAI 兼容接口默认 / 本地 ONNX 兜底）、Sparse 向量恒本地、维度一致性启动期强校验（含运行期真实探测）、幂等写入、失效数据主动清理。

---

## 1. Dense/Sparse 双路向量化管道

`embeddings/pipeline.py` 的 `EmbeddingPipeline`：

* **Dense**：按 `[embedding].mode` 二选一（v2 修订，原设计只有本地一条路径）——
  * `"remote"`（**默认**）：调用 OpenAI 兼容的 `POST {base_url}/embeddings`（`[embedding.remote]`，默认网关 `https://api.openlux.ai/v1`，鉴权走 `EMBEDDING_API_KEY`）；
  * `"local"`：`TextEmbedding(model_name=[embedding.local].model_name)`，默认 `BAAI/bge-m3`（1024 维，原生多语言与代码增强），离线/无 key 时的兜底路径；
* **Sparse**：`SparseTextEmbedding(model_name="Qdrant/bm25")`，与 `mode` **无关，恒本地计算**——BM25 是基于语料的词法统计方法，不存在"远程 BM25 API"这种东西；输出 `(indices, values)` 稀疏权重对。

> **维度不再是"文档里写死就当真"**：`mode="remote"` 时向量真实维度取决于网关背后的具体模型，实现前无法从文档里静态得知。`api/app.py` 的 `lifespan` 在启动期会调用 `EmbeddingPipeline.probe_dense_dimension()` 真实探测一次并与 `[qdrant].vector_size` 比对，不一致直接 `DimensionMismatchError` fail-fast——`03` 原有的"一致性纪律"从"人工核对文档"升级为"代码自动校验"。

两者共享同一批 `[embedding].batch_size` 批处理与 `[embedding].max_length` 截断策略：

* **截断而非拒绝**：切片原文超过 `max_length` 对应 token 数时，**参与向量化的文本**被截断到上限（保留前 N token，通常函数签名与主体开头信息密度最高），但落盘到 Qdrant Payload 的 `content` 字段是完整原文——检索到的证据文本不能因为向量化侧的截断而缺失，这是 `02` §4 "超大函数"处理原则在向量化层的延续。
* **批处理边界**：单次 `ingest` 请求可能产生成百上千个切片，`embeddings/pipeline.py` 必须按 `batch_size` 分批调用模型，不能一次性把整个仓库的切片堆进一次 `embed()` 调用——ONNX Runtime 的批处理内存占用与批大小近似线性，无节制的超大批次是本子系统在单机场景下最容易撞见的隐患。

## 2. Qdrant Collection Schema

单一 Collection（`[qdrant].collection_name`，默认 `aegis_code_chunks`）内使用**命名向量**同时承载 Dense 与 Sparse 两个向量空间（Qdrant 原生特性，ADR §2.1 已定型）：

```json
{
  "vectors": {
    "dense": {"size": 1024, "distance": "Cosine"}
  },
  "sparse_vectors": {
    "sparse": {}
  }
}
```

**Payload 字段**（对齐 `02` §6 的切片元数据 Schema，逐一建索引以支撑 `04` §2 的预过滤）：

| Payload 键 | 索引类型 | 用途 |
| :--- | :--- | :--- |
| `file_path` | keyword | 精确匹配 / 前缀过滤（删除、再索引时定位同文件旧切片） |
| `language` | keyword | `04` §2 语言过滤 |
| `repo_name` | keyword | 多仓库隔离过滤 |
| `content_hash` | keyword | 幂等写入判定（见 §3） |
| `start_line` / `end_line` | integer | 展示排序，非强制建索引 |
| `git_commit` | keyword | 证据溯源展示 |

### 启动期维度一致性强校验

`storage/qdrant_store.py` 在服务启动、首次连接 Qdrant 时必须执行：

1. Collection 不存在 → 按 `[qdrant].vector_size`/`distance` 自动创建（首次启动的正常路径）；
2. Collection 已存在 → 读取其 `dense` 向量配置的实际 `size`，与 `[qdrant].vector_size` 比对，**不一致则拒绝启动并给出明确报错**（而不是继续跑到第一次写入时才因维度不匹配报错——ADR §2.2 的"一致性纪律"在这里必须是代码强制的，不能只是文档约定）。

## 3. 幂等写入：确定性 Point ID

**这是既有 ADR 与里程碑都未覆盖的关键机制**——没有它，`ingest` 每次调用都会不断堆积重复切片，Collection 会无限膨胀且检索结果充满同一内容的多个副本。

* **Point ID 计算**：`point_id = uuid5(NAMESPACE, f"{repo_name}:{file_path}:{start_line}:{content_hash}")`——确定性生成，同一切片（同文件同位置同内容）在任意一次 `ingest` 中重复计算都得到相同 ID；
* **写入语义**：使用 Qdrant 的 `upsert`（而非 `insert`）——ID 相同则覆盖旧向量与 Payload，ID 不存在则新增。这样"重复调用 `ingest` 是廉价且无副作用的"这个 `02` §1 承诺的前提，才在存储层真正成立；
* **内容未变则整体跳过**：更进一步的优化——`ingest` 处理某文件前，先按 `file_path` 查询该文件现存切片的 `content_hash` 集合，若切分结果的哈希集合与现存完全一致，直接跳过该文件的向量化与写入（省下最耗时的 embedding 计算），只有哈希不同的切片才重新计算并 upsert。

## 4. 失效数据清理（文件删除 / 内容大幅变更）

同样是既有文档完全没提及的空白：

* **文件被删除**：`ingest` 请求应支持传入"本次全量仓库文件清单"（或至少是"本次实际处理到的 `file_path` 集合"），完成写入后，按 `repo_name` 过滤查询 Qdrant 中所有 `file_path` **不在**本次清单内的切片，批量删除——否则被删除文件的旧切片会永久残留，被检索到时会给模型呈现已经不存在的代码作为"证据"，属于比"没有检索到"更危险的错误；
* **文件内容变更导致切片数量减少**（如一个大函数被拆成多个小函数，旧切片的行号范围整体作废）：靠 §3 的"内容未变则跳过"机制的反面自然处理——凡是这次切分没有重新生成的旧 `content_hash`，视为已失效，同样按 `file_path` 维度做"先删后插"或"多退少补"的 diff 式更新，而不是简单地在旧数据之上叠加新数据。

## 5. 双部署形态的存储路径

呼应 `01` §4：

* `mode="local"`：`QdrantClient(path=[qdrant].storage_path)`，本地文件持久化，单进程独占；
* `mode="server"`：`QdrantClient(host=[qdrant].host, port=[qdrant].port, api_key=os.getenv("QDRANT_API_KEY") or None)`——`QDRANT_API_KEY` 已在 `AegisRAG/.env.example` 预留，仅在独立容器模式且容器启用了鉴权时需要，本地模式恒为空。

## 6. 上下文切片标题头（CCH，已在 Ingest 落地）

**原理**：在切片前拼接一段"全局情境摘要头"能显著降低检索丢失率。代码切片与 Markdown 切片的"所属章印"——文件路径、封闭的 `namespace`/`class`/`struct`、Markdown 标题面包屑（`MarkdownHeaderTextSplitter` 产生的 `enclosing_scope`）——在切分阶段就已经**确定性地**提取完毕。

**落地方式**（区分"参与向量化的文本"与"返回给用户的证据文本"，两者不是同一份）：

```text
embedding_text = f"[{enclosing_scope}]\n{content}"   # 只用于 Dense/Sparse 编码
content（Payload 中落盘的原文）= 不变，仍是切片原文本身
```

即 `api/routes/ingest.py` 在调用向量化前，对携带 `enclosing_scope` 的切片做轻量拼接得到 `embedding_text` 用于生成 Dense 与 Sparse 向量；Qdrant Payload 里的 `content` 字段保持原文不变，`05` 响应体里返回给 Agent 的依然是未拼接的干净代码/文档，同时通过 `enclosing_scope` 字段透传面包屑供展示。
