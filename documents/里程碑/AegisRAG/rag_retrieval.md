# AegisRAG 独立代码检索子系统功能与设计里程碑

> **对应设计规范**：`documents/技术选型/rag_retrieval.md`  
> **物理子工程**：`AegisRAG/`（独立 `uv` 虚拟环境与依赖空间）  
> **运行端口**：`:8001`（独立微服务进程）  
> **核心原则**：代码语法感知切分、ONNX 本地 CPU 推理（零 GPU 依赖）、Qdrant 稠密/稀疏单库双模混合检索。  
> 
> **图例规范**：`[代码实现] [测试通过]`

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

---

## 二、代码与文档语法感知切分（待落地推进）

- [ ] [ ] **Tree-sitter 源码 AST 语义感知切片器 (`indexer/ast_splitter.py`)**
  - [ ] [ ] 支持 C/C++、Go、Python、Rust 语法树解析
  - [ ] [ ] 保持函数体、类结构体、接口定义的语法块完整性，拒绝定长机械腰斩
  - [ ] [ ] 切片强制附加 `file_path`、`start_line`、`end_line` 等证据元数据
- [ ] [ ] **Markdown 结构化标题分块器 (`indexer/markdown_splitter.py`)**
  - [ ] [ ] 按文档章节标题层级（H1/H2/H3）保持上下文完整分块

---

## 三、向量嵌入与 Qdrant 存储引擎（待落地推进）

- [ ] [ ] **FastEmbed 向量化管道 (`embeddings/pipeline.py`)**
  - [ ] [ ] 稠密向量生成器与稀疏 BM25 向量生成器集成
  - [ ] [ ] 批量处理与线程池并发加速
- [ ] [ ] **Qdrant 混合索引存储适配器 (`storage/qdrant_store.py`)**
  - [ ] [ ] Collection 自动初始化与向量维度匹配校验
  - [ ] [ ] 稠密与稀疏多路写入管道
  - [ ] [ ] 按语言、仓库与路径的前置过滤（Payload Filtering）

---

## 四、重排模型与微服务接口（待落地推进）

- [ ] [ ] **Cross-Encoder 极速精排器 (`indexer/reranker.py`)**
  - [ ] [ ] 基于 `fastembed.Rerank` 加载 ONNX 版本 `bge-reranker-base`
  - [ ] [ ] 将 Top-30 融合候选集精准重排提炼至高质量 Top-5 切片
- [ ] [ ] **FastAPI 微服务端点与 Agent 适配器 (`api/`)**
  - [ ] [ ] `POST /api/v1/retrieve`：双路混合检索与重排查询接口
  - [ ] [ ] `POST /api/v1/documents/ingest`：代码与文档异步索引入库接口
