"""失效数据增量清理单元测试。

验证 delete_stale 增量清理、文件删除场景与跨仓库数据隔离。
"""

from __future__ import annotations

from pathlib import Path

from indexer.metadata import ChunkMetadata
from storage.qdrant_store import QdrantStore


class TestStaleDeletion:
    """失效数据清理测试套件。"""

    def test_stale_deletion_and_cross_repo_isolation(self, sandbox_settings, tmp_path: Path) -> None:
        store_path = tmp_path / "qdrant_stale"
        store = QdrantStore(sandbox_settings.qdrant, storage_path=store_path)
        try:
            store.ensure_collection()

            # 1. 写入 repo_A 的 a.c 与 b.c
            chunk_a = ChunkMetadata.build(
                file_path="src/a.c", start_line=1, end_line=5, content="int a = 1;", language="c", repo_name="repo_A"
            )
            chunk_b = ChunkMetadata.build(
                file_path="src/b.c", start_line=1, end_line=5, content="int b = 2;", language="c", repo_name="repo_A"
            )
            # 2. 写入 repo_B 的 c.c
            chunk_c = ChunkMetadata.build(
                file_path="src/c.c", start_line=1, end_line=5, content="int c = 3;", language="c", repo_name="repo_B"
            )

            store.upsert_chunks(
                [chunk_a, chunk_b, chunk_c],
                [[0.1] * 1024, [0.2] * 1024, [0.3] * 1024],
                [([1], [0.1]), ([2], [0.2]), ([3], [0.3])],
            )

            assert store.health_snapshot()["point_count"] == 3

            # 3. 对 repo_A 执行清理，仅保留 a.c（模拟 b.c 被删除）
            deleted_count = store.delete_stale(repo_name="repo_A", keep_file_paths=["src/a.c"])
            assert deleted_count == 1

            # 4. 验证 repo_A 的 a.c 仍然存在，repo_B 的 c.c 未受任何影响
            snapshot = store.health_snapshot()
            assert snapshot["point_count"] == 2
        finally:
            store.close()
