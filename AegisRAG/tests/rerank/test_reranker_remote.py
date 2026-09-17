"""远端 Rerank 协议与 Mock 单元测试。

验证 /rerank 请求体格式、按 index 还原顺序、网关故障 502/503 转译与密钥缺失快速失败。
"""

from __future__ import annotations

import httpx
import pytest

from api.errors import UpstreamModelError
from rerank.reranker import Reranker


class TestRerankerRemote:
    """远端 Reranker Mock 测试套件。"""

    def test_remote_rerank_protocol_and_index_reordering(self, base_settings, monkeypatch) -> None:
        monkeypatch.setenv("TEST_RERANK_KEY", "sk-rerank-key-999")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/rerank"
            assert request.headers.get("Authorization") == "Bearer sk-rerank-key-999"
            mock_resp = {
                "results": [
                    {"index": 1, "relevance_score": 0.85},
                    {"index": 0, "relevance_score": 0.42},
                ]
            }
            return httpx.Response(200, json=mock_resp)

        mock_transport = httpx.MockTransport(handler)

        cfg = base_settings.rerank.model_copy(
            update={
                "mode": "remote",
                "cache_dir": str(base_settings.resolve_path(base_settings.rerank.cache_dir)),
                "remote": base_settings.rerank.remote.model_copy(
                    update={"api_key_env": "TEST_RERANK_KEY", "base_url": "https://mock.rerank/v1"}
                ),
            }
        )

        reranker = Reranker(cfg)
        reranker._remote_client = httpx.Client(
            transport=mock_transport,
            base_url="https://mock.rerank/v1",
            headers={"Authorization": "Bearer sk-rerank-key-999"},
        )

        try:
            scores = reranker.score(query="hello", documents=["doc 0", "doc 1"])
            assert len(scores) == 2
            # 经过 index 还原后，doc 0 得分 0.42，doc 1 得分 0.85
            assert scores[0] == 0.42
            assert scores[1] == 0.85
        finally:
            reranker.close()

    def test_remote_rerank_gateway_error(self, base_settings, monkeypatch) -> None:
        monkeypatch.setenv("TEST_RERANK_KEY", "sk-rerank-key-999")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(502, json={"error": "bad gateway upstream"})

        mock_transport = httpx.MockTransport(handler)

        cfg = base_settings.rerank.model_copy(
            update={
                "mode": "remote",
                "cache_dir": str(base_settings.resolve_path(base_settings.rerank.cache_dir)),
                "remote": base_settings.rerank.remote.model_copy(
                    update={"api_key_env": "TEST_RERANK_KEY", "base_url": "https://mock.rerank/v1"}
                ),
            }
        )

        reranker = Reranker(cfg)
        reranker._remote_client = httpx.Client(
            transport=mock_transport,
            base_url="https://mock.rerank/v1",
            headers={"Authorization": "Bearer sk-rerank-key-999"},
        )

        try:
            with pytest.raises(UpstreamModelError) as exc_info:
                reranker.score(query="hello", documents=["doc 0"])
            assert "远端 Rerank 请求失败" in exc_info.value.message
        finally:
            reranker.close()

    def test_missing_api_key_raises_error(self, base_settings, monkeypatch) -> None:
        monkeypatch.delenv("NON_EXISTENT_RERANK_KEY", raising=False)

        cfg = base_settings.rerank.model_copy(
            update={
                "mode": "remote",
                "cache_dir": str(base_settings.resolve_path(base_settings.rerank.cache_dir)),
                "remote": base_settings.rerank.remote.model_copy(
                    update={"api_key_env": "NON_EXISTENT_RERANK_KEY"}
                ),
            }
        )

        with pytest.raises(UpstreamModelError) as exc_info:
            Reranker(cfg)
        assert "未设置或为空" in exc_info.value.message
