"""Point ID 确定性生成与幂等去重测试。

验证 UUIDv5 确定性哈希、元数据敏感性与 existing_ids 增量过滤。
"""

from __future__ import annotations

from pathlib import Path

from indexer.metadata import ChunkMetadata
from storage.ids import point_id_for
from storage.qdrant_store import QdrantStore


class TestIdsAndIdempotency:
    """确定性 Point ID 与幂等性测试套件。"""

    def test_point_id_for_deterministic(self) -> None:
        chunk1 = ChunkMetadata.build(
            file_path="src/main.c",
            start_line=1,
            end_line=10,
            content="int main() { return 0; }",
            language="c",
            repo_name="demo_repo",
        )
        chunk2 = ChunkMetadata.build(
            file_path="src/main.c",
            start_line=1,
            end_line=10,
            content="int main() { return 0; }",
            language="c",
            repo_name="demo_repo",
        )

        id1 = point_id_for(chunk1)
        id2 = point_id_for(chunk2)
        assert id1 == id2
        assert len(id1) == 36  # 标准 UUID 长度

    def test_point_id_sensitivity_to_metadata(self) -> None:
        chunk_base = ChunkMetadata.build(
            file_path="src/main.c",
            start_line=1,
            end_line=10,
            content="int main() { return 0; }",
            language="c",
            repo_name="demo_repo",
        )
        chunk_diff_line = ChunkMetadata.build(
            file_path="src/main.c",
            start_line=2,
            end_line=11,
            content="int main() { return 0; }",
            language="c",
            repo_name="demo_repo",
        )
        chunk_diff_repo = ChunkMetadata.build(
            file_path="src/main.c",
            start_line=1,
            end_line=10,
            content="int main() { return 0; }",
            language="c",
            repo_name="other_repo",
        )

        id_base = point_id_for(chunk_base)
        assert id_base != point_id_for(chunk_diff_line)
        assert id_base != point_id_for(chunk_diff_repo)

    def test_existing_ids_filtering(self, sandbox_settings, tmp_path: Path) -> None:
        store_path = tmp_path / "qdrant_idempotency"
        store = QdrantStore(sandbox_settings.qdrant, storage_path=store_path)
        try:
            store.ensure_collection()

            chunk = ChunkMetadata.build(
                file_path="src/main.c",
                start_line=1,
                end_line=5,
                content="int x = 1;",
                language="c",
                repo_name="repo1",
            )
            pid = point_id_for(chunk)

            # 初始为空
            assert store.existing_ids([pid]) == set()

            # 写入点
            dense_vec = [0.1] * 1024
            sparse_vec = ([1, 2], [0.5, 0.8])
            store.upsert_chunks([chunk], [dense_vec], [sparse_vec])

            # 再次查询已存在
            assert store.existing_ids([pid]) == {pid}
            # 查询不存在的 ID
            assert store.existing_ids(["00000000-0000-0000-0000-000000000000"]) == set()
        finally:
            store.close()
