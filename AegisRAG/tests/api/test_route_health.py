"""GET /api/v1/health 健康检查端点测试。

验证服务就绪状态、Qdrant 快照与 Embedding 模型加载状态。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app


class TestRouteHealth:
    """健康检查接口测试套件。"""

    def test_health_check_endpoint(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/api/v1/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] in ("ok", "degraded")
            assert "version" in data
            assert data["qdrant"]["collection_ready"] is True
            assert data["qdrant"]["vector_size"] == 1024
            assert data["embedding_model_loaded"] is True
