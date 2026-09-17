"""维度探测与启动期缺失预检单元测试。

验证 probe_dense_dimension() 与 remote 模式环境变量缺失快速失败。
"""

from __future__ import annotations

import pytest

from api.errors import UpstreamModelError
from embeddings.pipeline import EmbeddingPipeline


class TestDimensionProbe:
    """维度探测与快速失败测试套件。"""

    def test_probe_dense_dimension_local(self, base_settings) -> None:
        cfg = base_settings.embedding.model_copy(
            update={"cache_dir": str(base_settings.resolve_path(base_settings.embedding.cache_dir))}
        )
        embedder = EmbeddingPipeline(cfg)
        try:
            dim = embedder.probe_dense_dimension()
            assert dim == 1024
        finally:
            embedder.close()

    def test_remote_mode_missing_api_key_fail_fast(self, base_settings, monkeypatch) -> None:
        monkeypatch.delenv("NON_EXISTENT_EMBEDDING_KEY", raising=False)

        cfg = base_settings.embedding.model_copy(
            update={
                "mode": "remote",
                "cache_dir": str(base_settings.resolve_path(base_settings.embedding.cache_dir)),
                "remote": base_settings.embedding.remote.model_copy(
                    update={"api_key_env": "NON_EXISTENT_EMBEDDING_KEY"}
                ),
            }
        )

        with pytest.raises(UpstreamModelError) as exc_info:
            EmbeddingPipeline(cfg)
        assert "未设置或为空" in exc_info.value.message
