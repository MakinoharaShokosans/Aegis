"""Qdrant Collection 生命周期与维度校验单元测试。

验证 Collection 自动创建、启动期维度不匹配拦截 (DimensionMismatchError) 与健康快照。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from qdrant_client import QdrantClient, models

from api.errors import DimensionMismatchError
from storage.qdrant_store import QdrantStore


class TestQdrantLifecycle:
    """Qdrant 生命周期测试套件。"""

    def test_ensure_collection_creates_new_collection(self, sandbox_settings, tmp_path: Path) -> None:
        store_path = tmp_path / "qdrant_lifecycle"
        store = QdrantStore(sandbox_settings.qdrant, storage_path=store_path)
        try:
            assert store.collection_ready is False
            store.ensure_collection()
            assert store.collection_ready is True

            snapshot = store.health_snapshot()
            assert snapshot["collection_ready"] is True
            assert snapshot["vector_size"] == 1024
            assert snapshot["mode"] == "local"
        finally:
            store.close()

    def test_dimension_mismatch_raises_error(self, sandbox_settings, tmp_path: Path) -> None:
        store_path = tmp_path / "qdrant_mismatch"
        coll_name = sandbox_settings.qdrant.collection_name

        # 1. 预先创建一个 768 维的冲突 Collection
        client = QdrantClient(path=str(store_path))
        client.create_collection(
            collection_name=coll_name,
            vectors_config={"dense": models.VectorParams(size=768, distance=models.Distance.COSINE)},
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )
        client.close()

        # 2. 配置要求 1024 维，调用 ensure_collection 必须抛出 DimensionMismatchError
        store = QdrantStore(sandbox_settings.qdrant, storage_path=store_path)
        try:
            with pytest.raises(DimensionMismatchError) as exc_info:
                store.ensure_collection()
            assert exc_info.value.extra["actual_size"] == 768
            assert exc_info.value.extra["expected_size"] == 1024
            assert store.collection_ready is False
        finally:
            store.close()
