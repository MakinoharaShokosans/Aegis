"""Cross-Encoder 精排，Retrieve 阶段专属（04 §3，核心范围，非可选项）。

独立成包而非挂在 ``indexer/`` 下——归属裁决见 07_directory_structure.md §4①。
只有一个模块 ``reranker.py``：封装 ``fastembed.rerank.cross_encoder.TextCrossEncoder``。

依赖方向：不依赖 ``indexer``/``embeddings``/``storage``/``api``（07_directory_structure.md §5）。
"""

from __future__ import annotations

__all__: list[str] = []
