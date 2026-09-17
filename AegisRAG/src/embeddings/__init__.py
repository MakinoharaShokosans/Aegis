"""Dense/Sparse 双路向量化管道，Ingest 与 Retrieve 两条流水线共用（03 §1）。

只有一个模块 ``pipeline.py``：封装 FastEmbed 的 ``TextEmbedding``（Dense）与
``SparseTextEmbedding``（Sparse，固定 ``Qdrant/bm25``）批处理调用。

依赖方向：不依赖 ``indexer``/``rerank``/``storage``/``api``（07_directory_structure.md §5）。
"""

from __future__ import annotations

__all__: list[str] = []
