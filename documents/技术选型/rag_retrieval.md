# 架构决策记录：独立 RAG 检索基础设施 (Retrieval Service)

> **状态**：已定稿 (Accepted)  
> **责任领域**：`services/rag_retrieval/`  
> **核心目标**：为 Agent 提供高精度、源码语义感知、结合关键词与语义的双路召回与重排微服务。

---

## 1. 架构总览与检索流水线

```text
               User / Agent Query (通过 httpx 调用 /api/v1/retrieve)
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 ▼                                           ▼
       [ 稠密向量生成: Dense ]                    [ 稀疏向量生成: Sparse ]
   (fastembed bge-small 或 OpenAI)              (fastembed Qdrant/bm25)
                 │                                           │
                 ▼                                           ▼
       Qdrant 稠密索引检索 (Top 50)               Qdrant 稀疏索引检索 (Top 50)
                 │                                           │
                 └─────────────────────┬─────────────────────┘
                                       ▼
                       Qdrant 原生 RRF (倒排互惠融合)
                                       │ (Top 30 候选切片)
                                       ▼
                     Cross-Encoder Reranker (bge-reranker)
                            (本地 ONNX 极速精排)
                                       │ (Top 5 高置信度切片)
                                       ▼
                        返回包含代码行号的结构化 JSON
```

---

## 2. 核心技术决策与权衡依据

### 2.1 数据库选型：Qdrant (单库双模与双部署形态)

* **为什么选择 Qdrant 而非 Chroma / Milvus / Elasticsearch？**
  1. **单库搞定混合检索**：打破传统的“ES 存文本 + 向量库做语义”的双库架构，同一个 Collection 中原生同时支持 `dense` 与 `sparse` 向量空间；
  2. **内置 RRF (Reciprocal Rank Fusion) 倒排融合算子**：直接在数据库引擎层完成多路召回的去重与合并排序，无需在 Python 应用层写复杂的打分合并胶水代码；
  3. **极强的 Payload 结构化条件过滤**：支持按代码语言（`language`）、仓库名（`repo_name`）、文件路径前缀进行毫秒级预过滤；
  4. **双部署形态**：
     - **本地嵌入模式（Embedded Mode）**：指定单文件目录持久化（`storage/qdrant_data/`），零部署开箱即跑；
     - **独立容器模式（Docker Mode）**：一键起 Docker 容器，暴露可视化 Web Dashboard (`:6333/dashboard`)，多进程并发安全。

### 2.2 向量推理底座：选用 fastembed（彻底告别 PyTorch / GPU 依赖）

* **决策理由**：
  1. **零 GPU 门槛与体积轻量**：传统 PyTorch + Transformers 环境动辄占用 5GB+ 空间，配置 CUDA 极易踩坑。Qdrant 官方维护的 `fastembed` 底层基于 ONNX Runtime，在单机 CPU 上几十毫秒即可完成批量向量计算；
  2. **多模态模型原生支持**：
     - 稠密向量：**默认 `BAAI/bge-small-en-v1.5`（384 维）**，与 `rag_config.toml` 的 `vector_size = 384` 严格一致；也可配置 OpenAI `text-embedding-3-small`；
       - 中文语料为主时可换 `BAAI/bge-small-zh-v1.5`，但该模型为 **512 维**，必须同步修改 `[qdrant].vector_size` 并重建 Collection，否则写入即报维度不匹配；
     - 稀疏向量：原生支持 `Qdrant/bm25`，直接输出用于倒排索引的权重字典。

> **一致性纪律**：`[embedding].model_name`、`[qdrant].vector_size` 与本文档三者必须始终一致，任何一方的改动都要同时修订另外两处。

### 2.3 精排重塑：Cross-Encoder Reranker (`bge-reranker-base`)

* **决策理由**：
  1. **防范 Context 膨胀**：双路召回合并后通常有 30~50 条候选切片，直接塞给 LLM 会造成注意力迷失并消耗大量 Token；
  2. **深度交互注意力（Deep Cross-Attention）**：Bi-Encoder（向量检索）速度快但精度有限，Cross-Encoder 同时输入 Query 与 Document 计算相关度，打分更精准；
  3. **落地形态**：使用 `fastembed.Rerank` 加载 ONNX 版本的 `bge-reranker-base`，将候选集高效压缩至高质量的 Top-5。

### 2.4 代码与文档语法感知切分：tree-sitter + Markdown Splitter

* **决策理由**：
  1. **拒绝暴力定长切片**：工程研究对象是 C/C++、Go 源码与技术规范。固定字符切片容易把一个系统调用实现或结构体腰斩；
  2. **代码 AST 切片**：利用 `tree-sitter` 解析函数、结构体、宏定义，保持代码块语法独立完整；
  3. **强元数据注入**：每个切片强制携带 `file_path`、`start_line`、`end_line`、`git_commit` 等元信息，供 Agent 生成报告时作为证据链反向索引。

### 2.5 服务接口与通信：FastAPI + httpx

* 暴露 `POST /api/v1/retrieve` 与 `POST /api/v1/documents/ingest`；
* Agent 端通过 `httpx` 连接池异步调用，自动在 HTTP 请求头中注入 `X-Trace-ID` 形成分布式追踪闭环。
