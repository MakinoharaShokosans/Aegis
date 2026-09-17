"""AegisRAG 交付层：FastAPI 契约 + uvicorn 入口（05）。

模块分工：
- ``settings``：读取 ``config/rag_config.toml`` 为强类型 ``RagConfig``；
- ``schemas``：对外 DTO（``RetrieveRequest``/``Response``、``IngestRequest``/``Response``、``HealthResponse``）；
- ``errors``：领域异常体系（与 HTTP 状态码解耦）；
- ``routes/``：``retrieve`` / ``ingest`` / ``health`` 三个端点；
- ``app`` / ``__main__``：FastAPI 装配（lifespan 负责连接 Qdrant、加载向量化/精排模型）与 uvicorn 入口。

边界约束：本包不依赖 ``AegisAgent`` 的任何模块（AegisRAG 是物理独立子工程，
见 documents/rag_retrieval/01_architecture_overview.md §1），也不引入任何 Chat LLM
SDK（同文档 §6）。

规范：documents/技术选型/rag_retrieval.md；documents/rag_retrieval/07_directory_structure.md
"""

from __future__ import annotations

__all__ = ["__version__"]

#: 子系统版本号（仅元数据，不参与任何阈值判定）
__version__ = "0.1.0"
