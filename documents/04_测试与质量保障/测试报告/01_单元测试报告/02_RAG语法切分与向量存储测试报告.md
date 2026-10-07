# 02_RAG 语法切分与向量存储测试报告

> **测试目标**：验证 `AegisRAG/` 独立微服务的 Tree-sitter AST 代码切分、Markdown 面包屑、Qdrant 向量存储幂等性及 Dense/Sparse 向量生成。  
> **执行环境**：单线程无冲突受控运行 (`OMP_NUM_THREADS=1`)  
> **实测数据**：**61 Passed, 0 Failed | 耗时: 73.18s | 通过率: 100%**

---

## 1. 模块测试数据明细

| 模块类别 | 测试文件路径 | 用例数 | 耗时 | 验证核心与实测数据 |
| :--- | :--- | :--- | :--- | :--- |
| **AST 与语法切片** | `tests/indexer/test_ast_splitter_c_cpp.py` | 4 | 0.05s | C 函数/结构体语法切分，C++ 模板类切分，超大切片标记 |
| **AST 与语法切片** | `tests/indexer/test_ast_splitter_go.py` | 1 | 0.02s | Go 结构体方法、函数边界精准识别，代码片段零割裂 |
| **Markdown 语法切片** | `tests/indexer/test_markdown_splitter.py` | 2 | 0.03s | 多级 Header 面包屑（Breadcrumbs）全层级元数据挂载 |
| **切分分发与兜底** | `tests/indexer/test_dispatch_and_fallback.py` | 5 | 0.04s | 语法错误代码平滑降级为按行切分，未知语言自动回退 |
| **元数据 Schema** | `tests/indexer/test_metadata.py` | 2 | 0.03s | 验证 ChunkMetadata 必填字段缺失时抛出校验异常 |
| **Qdrant 存储生命周期** | `tests/storage/test_qdrant_lifecycle.py` | 2 | 0.82s | Collection 自动创建、1024 维向量自检、维度不匹配硬拒 |
| **幂等写入与去重** | `tests/storage/test_ids_and_idempotency.py` | 3 | 0.54s | UUIDv5 确定性点位 ID 生成，元数据微变敏感度 100% |
| **Upsert 与失效清理** | `tests/storage/test_qdrant_upsert.py` | 2 | 0.45s | 批量写入 Payload 完整性校验、长短切片匹配异常拦截 |
| **代码库隔离与过期清理** | `tests/storage/test_stale_deletion.py` | 1 | 0.25s | 增量重构下旧切片物理清除，多代码库间数据硬隔离 |
| **Sparse 向量 (BM25)** | `tests/embeddings/test_sparse_embedding.py` | 3 | 4.25s | 词法统计 (indices, values) 二元组生成，批量与单条一致 |
| **Dense 远端与探测** | `tests/embeddings/test_dense_remote.py` | 4 | 4.98s | 协议映射与排序重组，无 Key 快速失败拦截 |
| **Dense 本地模型** | `tests/embeddings/test_dense_local.py` | 2 | 7.22s | `jina-embeddings-v3` 1024 维输出实测，批处理顺序一致 |
| **混合召回与重排** | `tests/rerank/test_hybrid_fusion.py` | 2 | 0.76s | Dense+Sparse 双路召回，语言过滤下推，未建表防护 |
| **消融实验模式** | `tests/rerank/test_ablation_modes.py` | 1 | 0.45s | Dense-Only / Sparse-Only / Hybrid 三态可控流转 |
| **Cross-Encoder 重排** | `tests/rerank/test_reranker_local.py` | 2 | 5.38s | `bge-reranker-base` 相关度打分排序，空文档防护 |
| **配置与自检探针** | `tests/config/` & `tests/preflight/` | 15 | 6.04s | 非回环 IP 拦截、Worker 单进程约束、环境探针全覆盖 |
| **服务路由与并发** | `tests/api/` (Health/Ingest/Retrieve) | 10 | 41.87s | Ingest 增量幂等、Retrieve 混合检索响应、并发无阻塞 |

---

## 2. 关键核心技术实测验证

### 1. 向量维度与 UUIDv5 确定性 (`test_point_id_for_deterministic`)
- **实测结果**：相同代码文本与文件路径在不同时间调用 1000 次，生成的 UUIDv5 命中率 100.0% 相同；代码任意修改一个空格，生成的 UUIDv5 立即雪崩变化，保障 Qdrant 幂等写入与零脏数据。

### 2. 1024 维向量真实生成 (`test_dense_embedding_1024_dimension`)
- **输入样本**：`["hello world from aegis rag test", "vector search engine"]`
- **输出向量**：形状为 `(2, 1024)`，元素全为 `float32`，范数满足余弦相似度归一化约束。
