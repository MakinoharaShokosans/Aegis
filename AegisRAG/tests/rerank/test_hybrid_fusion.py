"""Qdrant 原生 RRF (Reciprocal Rank Fusion) 混合召回测试。

验证双路 Prefetch 融合、语言过滤下推与 Collection 未就绪异常拦截。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.errors import CollectionNotReadyError
from indexer.metadata import ChunkMetadata
from storage.qdrant_store import QdrantStore


class TestHybridFusion:
    """混合召回与 RRF 融合测试套件。"""

    def test_hybrid_recall_and_language_filter_pushdown(self, sandbox_settings, tmp_path: Path) -> None:
        store_path = tmp_path / "qdrant_fusion"
        store = QdrantStore(sandbox_settings.qdrant, storage_path=store_path)
        try:
            store.ensure_collection()

            # 写入 1 个 C 语言切片和 1 个 Go 语言切片
            chunk_c = ChunkMetadata.build(
                file_path="src/main.c", start_line=1, end_line=5, content="int add(int a, int b) { return a + b; }", language="c", repo_name="repo1"
            )
            chunk_go = ChunkMetadata.build(
                file_path="pkg/main.go", start_line=1, end_line=5, content="func Add(a, b int) int { return a + b }", language="go", repo_name="repo1"
            )

            dense_c = [0.1] * 1024
            dense_go = [0.2] * 1024
            sparse_c = ([1, 2], [0.8, 0.4])
            sparse_go = ([2, 3], [0.4, 0.8])

            store.upsert_chunks([chunk_c, chunk_go], [dense_c, dense_go], [sparse_c, sparse_go])

            # 1. 混合检索（带 language="c" 过滤）
            query_dense = [0.1] * 1024
            query_sparse = ([1, 2], [1.0, 0.5])

            points = store.query_hybrid(
                dense_vector=query_dense,
                sparse_vector=query_sparse,
                dense_top_k=5,
                sparse_top_k=5,
                fusion_top_k=5,
                language="c",
                mode="hybrid",
            )

            assert len(points) == 1
            assert points[0].payload["language"] == "c"
            assert points[0].payload["file_path"] == "src/main.c"

            # 2. 混合检索（无语言过滤）
            points_all = store.query_hybrid(
                dense_vector=query_dense,
                sparse_vector=query_sparse,
                dense_top_k=5,
                sparse_top_k=5,
                fusion_top_k=5,
                language=None,
                mode="hybrid",
            )
            assert len(points_all) == 2
        finally:
            store.close()

    def test_query_hybrid_before_ensure_collection_raises_error(self, sandbox_settings, tmp_path: Path) -> None:
        store_path = tmp_path / "qdrant_unready"
        store = QdrantStore(sandbox_settings.qdrant, storage_path=store_path)
        try:
            with pytest.raises(CollectionNotReadyError):
                store.query_hybrid(
                    dense_vector=[0.1] * 1024,
                    sparse_vector=([1], [0.1]),
                    dense_top_k=5,
                    sparse_top_k=5,
                    fusion_top_k=5,
                )
        finally:
            store.close()
