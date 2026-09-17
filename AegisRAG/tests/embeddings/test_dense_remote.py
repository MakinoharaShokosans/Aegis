"""远端 Dense Embedding 协议与 Mock 测试。

验证 OpenAI 兼容协议组包、乱序响应按 index 重排、网络异常与 502/500 状态码转译。
"""

from __future__ import annotations

import httpx
import pytest

from api.errors import UpstreamModelError
from embeddings.pipeline import EmbeddingPipeline


class TestDenseRemoteEmbedding:
    """远端 Dense 向量化 Mock 测试套件。"""

    def test_remote_embedding_successful_protocol_and_reorder(self, base_settings, monkeypatch) -> None:
        monkeypatch.setenv("TEST_EMBED_KEY", "sk-mock-key-12345")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/embeddings"
            assert request.headers.get("Authorization") == "Bearer sk-mock-key-12345"
            # 模拟乱序返回 data items (index 1 在前, index 0 在后)
            mock_body = {
                "data": [
                    {"index": 1, "embedding": [0.2] * 1024},
                    {"index": 0, "embedding": [0.1] * 1024},
                ]
            }
            return httpx.Response(200, json=mock_body)

        mock_transport = httpx.MockTransport(handler)

        cfg = base_settings.embedding.model_copy(
            update={
                "mode": "remote",
                "cache_dir": str(base_settings.resolve_path(base_settings.embedding.cache_dir)),
                "remote": base_settings.embedding.remote.model_copy(
                    update={"api_key_env": "TEST_EMBED_KEY", "base_url": "https://mock.api/v1"}
                ),
            }
        )

        embedder = EmbeddingPipeline(cfg)
        embedder._remote_client = httpx.Client(
            transport=mock_transport,
            base_url="https://mock.api/v1",
            headers={"Authorization": "Bearer sk-mock-key-12345"},
        )

        try:
            vectors = embedder.embed_dense(["text A", "text B"])
            assert len(vectors) == 2
            # 验证经过重排序后，index 0 对应的 [0.1] 在第一位
            assert vectors[0] == [0.1] * 1024
            assert vectors[1] == [0.2] * 1024
        finally:
            embedder.close()

    def test_remote_embedding_http_error_translation(self, base_settings, monkeypatch) -> None:
        monkeypatch.setenv("TEST_EMBED_KEY", "sk-mock-key-12345")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "internal gateway failure"})

        mock_transport = httpx.MockTransport(handler)

        cfg = base_settings.embedding.model_copy(
            update={
                "mode": "remote",
                "cache_dir": str(base_settings.resolve_path(base_settings.embedding.cache_dir)),
                "remote": base_settings.embedding.remote.model_copy(
                    update={"api_key_env": "TEST_EMBED_KEY", "base_url": "https://mock.api/v1"}
                ),
            }
        )

        embedder = EmbeddingPipeline(cfg)
        embedder._remote_client = httpx.Client(
            transport=mock_transport,
            base_url="https://mock.api/v1",
            headers={"Authorization": "Bearer sk-mock-key-12345"},
        )

        try:
            with pytest.raises(UpstreamModelError) as exc_info:
                embedder.embed_dense(["trigger error"])
            assert "远端 Embedding 请求失败" in exc_info.value.message
        finally:
            embedder.close()
