"""本地 Sparse BM25 向量化单元测试。

验证 BM25 稀疏向量生成、(indices, values) 格式与批处理一致性。
"""

from __future__ import annotations

import pytest

from embeddings.pipeline import EmbeddingPipeline


class TestSparseEmbedding:
    """Sparse (BM25) 向量化测试套件。"""

    def test_sparse_embedding_generation_and_format(self, base_settings) -> None:
        cfg = base_settings.embedding.model_copy(
            update={"cache_dir": str(base_settings.resolve_path(base_settings.embedding.cache_dir))}
        )
        embedder = EmbeddingPipeline(cfg)
        try:
            texts = ["function calculate_sum in math.c", "select count(*) from users;"]
            sparse_vectors = embedder.embed_sparse(texts)

            assert len(sparse_vectors) == 2
            for indices, values in sparse_vectors:
                assert isinstance(indices, list)
                assert isinstance(values, list)
                assert len(indices) == len(values)
                assert len(indices) > 0
                assert all(isinstance(idx, int) for idx in indices)
                assert all(isinstance(val, float) for val in values)
        finally:
            embedder.close()

    def test_single_and_batch_consistency(self, base_settings) -> None:
        cfg = base_settings.embedding.model_copy(
            update={"cache_dir": str(base_settings.resolve_path(base_settings.embedding.cache_dir))}
        )
        embedder = EmbeddingPipeline(cfg)
        try:
            text = "unique test query for consistency check"
            single_vec = embedder.embed_sparse_one(text)
            batch_vec = embedder.embed_sparse([text])[0]

            assert single_vec[0] == batch_vec[0]
            assert pytest.approx(single_vec[1]) == batch_vec[1]
        finally:
            embedder.close()

    def test_empty_input_returns_empty_list(self, base_settings) -> None:
        cfg = base_settings.embedding.model_copy(
            update={"cache_dir": str(base_settings.resolve_path(base_settings.embedding.cache_dir))}
        )
        embedder = EmbeddingPipeline(cfg)
        try:
            assert embedder.embed_sparse([]) == []
        finally:
            embedder.close()
