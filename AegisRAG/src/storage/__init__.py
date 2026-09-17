"""Qdrant 客户端适配，Ingest 与 Retrieve 两条流水线共用（03 §2~§4）。

模块分工：
- ``qdrant_store``：Collection 初始化与维度校验、幂等写入、混合检索、失效清理、健康快照；
- ``ids``：确定性 Point ID 计算（幂等写入与评测金标复用的地基，03 §3）。

依赖方向：不依赖 ``indexer``/``embeddings``/``rerank``/``api``（07_directory_structure.md §5）。
"""

from __future__ import annotations

__all__: list[str] = []
