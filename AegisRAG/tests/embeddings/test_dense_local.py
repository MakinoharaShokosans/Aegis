"""本地 Dense ONNX 向量化单元测试。

验证本地 Dense 嵌入生成、1024 输出维度及分批处理一致性。
"""

from __future__ import annotations

import pytest

from embeddings.pipeline import EmbeddingPipeline


class TestDenseLocalEmbedding:
    """本地 Dense 向量化测试套件。"""

    def test_dense_embedding_1024_dimension(self, base_settings) -> None:
        cfg = base_settings.embedding.model_copy(
            update={
                "mode": "local",
                "cache_dir": str(base_settings.resolve_path(base_settings.embedding.cache_dir)),
            }
        )
        embedder = EmbeddingPipeline(cfg)
        try:
            texts = ["hello world from aegis rag test", "vector search engine"]
            vectors = embedder.embed_dense(texts)

            assert len(vectors) == 2
            assert len(vectors[0]) == 1024
            assert len(vectors[1]) == 1024
            assert all(isinstance(v, float) for v in vectors[0])
        finally:
            embedder.close()

    def test_dense_batch_processing_order(self, base_settings) -> None:
        cfg = base_settings.embedding.model_copy(
            update={
                "mode": "local",
                "batch_size": 2,
                "cache_dir": str(base_settings.resolve_path(base_settings.embedding.cache_dir)),
            }
        )
        embedder = EmbeddingPipeline(cfg)
        try:
            texts = [f"sample text snippet number {i}" for i in range(5)]
            vectors = embedder.embed_dense(texts)

            assert len(vectors) == 5
            # 单独生成的向量应与批量生成完全一致
            single_vec = embedder.embed_dense_one(texts[2])
            assert pytest.approx(vectors[2]) == single_vec
        finally:
            embedder.close()
