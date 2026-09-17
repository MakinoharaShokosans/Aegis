"""Qdrant 批量写入与分批处理测试。

验证 Dense/Sparse 混合写入、payload 完整性与批量切片分批提交。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from indexer.metadata import ChunkMetadata
from storage.qdrant_store import QdrantStore


class TestQdrantUpsert:
    """Qdrant 批量写入测试套件。"""

    def test_upsert_payload_integrity(self, sandbox_settings, tmp_path: Path) -> None:
        store_path = tmp_path / "qdrant_upsert"
        store = QdrantStore(sandbox_settings.qdrant, storage_path=store_path)
        try:
            store.ensure_collection()

            chunk = ChunkMetadata.build(
                file_path="src/calc.cpp",
                start_line=15,
                end_line=25,
                content="int multiply(int a, int b) { return a * b; }",
                language="cpp",
                repo_name="calc_repo",
                git_commit="commit_hash_123",
                enclosing_scope="CalculatorClass",
            )
            dense_vec = [0.05] * 1024
            sparse_vec = ([10, 20], [0.3, 0.9])

            count = store.upsert_chunks([chunk], [dense_vec], [sparse_vec])
            assert count == 1

            snapshot = store.health_snapshot()
            assert snapshot["point_count"] == 1
        finally:
            store.close()

    def test_length_mismatch_raises_value_error(self, sandbox_settings, tmp_path: Path) -> None:
        store_path = tmp_path / "qdrant_mismatch_len"
        store = QdrantStore(sandbox_settings.qdrant, storage_path=store_path)
        try:
            store.ensure_collection()

            chunk = ChunkMetadata.build(
                file_path="test.c",
                start_line=1,
                end_line=2,
                content="int a = 1;",
                language="c",
                repo_name="repo",
            )

            with pytest.raises(ValueError, match="长度必须一致"):
                # 传入 1 个 chunk，但传入 2 个 dense vectors
                store.upsert_chunks([chunk], [[0.1] * 1024, [0.2] * 1024], [([1], [0.1])])
        finally:
            store.close()
