"""FastAPI 全局异常处理器单元测试。

验证领域异常与 HTTP 状态码的映射规范（05 §2）。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.app import create_app
from api.errors import (
    CollectionNotReadyError,
    DimensionMismatchError,
    RepoNotIndexedError,
    UpstreamModelError,
)


class TestErrorHandlers:
    """领域异常转译测试套件。"""

    def test_error_handlers_status_codes(self) -> None:
        app = create_app()

        # 注册临时测试路由以触发特定领域异常
        @app.get("/test/collection-not-ready")
        def raise_collection_not_ready():
            raise CollectionNotReadyError("collection missing", collection="c1")

        @app.get("/test/dimension-mismatch")
        def raise_dimension_mismatch():
            raise DimensionMismatchError("dimension mismatch", actual_size=768, expected_size=1024)

        @app.get("/test/repo-not-indexed")
        def raise_repo_not_indexed():
            raise RepoNotIndexedError("repo missing", repo_root="/tmp/fake")

        @app.get("/test/upstream-model-error")
        def raise_upstream_model_error():
            raise UpstreamModelError("gateway timeout", endpoint="embedding")

        with TestClient(app) as client:
            r1 = client.get("/test/collection-not-ready")
            assert r1.status_code == 503
            assert r1.json()["error"]["code"] == "COLLECTION_NOT_READY"

            r2 = client.get("/test/dimension-mismatch")
            assert r2.status_code == 500
            assert r2.json()["error"]["code"] == "DIMENSION_MISMATCH"

            r3 = client.get("/test/repo-not-indexed")
            assert r3.status_code == 404
            assert r3.json()["error"]["code"] == "REPO_NOT_INDEXED"

            r4 = client.get("/test/upstream-model-error")
            assert r4.status_code == 502
            assert r4.json()["error"]["code"] == "UPSTREAM_MODEL_ERROR"
