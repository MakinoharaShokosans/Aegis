"""检索与消融模式单元测试。

验证 dense_only、sparse_only、hybrid 模式在 QdrantStore 检索层的分派行为。
"""

from __future__ import annotations

from pathlib import Path

from indexer.metadata import ChunkMetadata
from storage.qdrant_store import QdrantStore


class TestAblationModes:
    """消融模式测试套件。"""

    def test_ablation_modes_execution(self, sandbox_settings, tmp_path: Path) -> None:
        store_path = tmp_path / "qdrant_ablation"
        store = QdrantStore(sandbox_settings.qdrant, storage_path=store_path)
        try:
            store.ensure_collection()

            chunk = ChunkMetadata.build(
                file_path="src/calc.c", start_line=1, end_line=5, content="int add(int a, int b) { return a + b; }", language="c", repo_name="repo1"
            )
            store.upsert_chunks([chunk], [[0.1] * 1024], [([1, 2], [0.5, 0.5])])

            query_dense = [0.1] * 1024
            query_sparse = ([1, 2], [0.5, 0.5])

            # 1. dense_only 模式
            pts_dense = store.query_hybrid(
                dense_vector=query_dense,
                sparse_vector=query_sparse,
                dense_top_k=5,
                sparse_top_k=5,
                fusion_top_k=5,
                mode="dense_only",
            )
            assert len(pts_dense) == 1

            # 2. sparse_only 模式
            pts_sparse = store.query_hybrid(
                dense_vector=query_dense,
                sparse_vector=query_sparse,
                dense_top_k=5,
                sparse_top_k=5,
                fusion_top_k=5,
                mode="sparse_only",
            )
            assert len(pts_sparse) == 1

            # 3. hybrid 模式
            pts_hybrid = store.query_hybrid(
                dense_vector=query_dense,
                sparse_vector=query_sparse,
                dense_top_k=5,
                sparse_top_k=5,
                fusion_top_k=5,
                mode="hybrid",
            )
            assert len(pts_hybrid) == 1
        finally:
            store.close()
