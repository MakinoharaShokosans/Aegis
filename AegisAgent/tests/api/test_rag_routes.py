"""RAG 网关代理端点测试 (tests/api/test_rag_routes.py)。"""

from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient

from agent_runtime.api.app import create_app
from agent_runtime.config import AegisConfig


@pytest.fixture
async def api_client(test_config: AegisConfig):
    """创建绑定 ASGI Lifespan 生命周期的测试客户端。"""
    app = create_app(test_config)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        token = str(getattr(app.state, "api_token", "") or "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8000", headers=headers
        ) as client:
            setattr(client, "app", app)
            yield client


@pytest.mark.asyncio
async def test_rag_gateway_proxy_endpoints(api_client: AsyncClient, tmp_path: Path):
    """测试 RAG 健康检查、索引触发与检索代理。"""
    # 1. GET /api/v1/rag/health
    with patch("tools.core.http_client.ServiceClient.request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {
            "status": "ok",
            "version": "1.0.0",
            "embedding_model_loaded": True,
            "qdrant_ready": True,
        }
        resp = await api_client.get("/api/v1/rag/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["embedding_model_loaded"] is True

    # 2. POST /api/v1/rag/ingest
    ws_dir = tmp_path / "rag_proxy_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    create_ws = await api_client.post(
        "/api/v1/workspaces",
        json={"name": "RAG Proxy WS", "root_path": str(ws_dir)},
    )
    ws_id = create_ws.json()["workspace_id"]

    with patch("tools.core.http_client.ServiceClient.request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {
            "indexed": 15,
            "skipped": 2,
            "deleted": 0,
            "degraded_files": [],
            "duration_ms": 320,
        }
        ingest_resp = await api_client.post(
            "/api/v1/rag/ingest",
            params={"workspace_id": ws_id},
            json={"incremental": True},
        )
        assert ingest_resp.status_code == 200
        data = ingest_resp.json()
        assert data["indexed"] == 15
        assert data["duration_ms"] == 320

    # 3. POST /api/v1/rag/retrieve
    with patch("tools.core.http_client.ServiceClient.request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {
            "results": [
                {
                    "chunk_id": "c1",
                    "file_path": "docs/11_http_api.md",
                    "start_line": 25,
                    "end_line": 60,
                    "content": "三道安全闸门设计规范",
                    "score": 0.95,
                }
            ],
            "low_confidence": False,
        }
        retrieve_resp = await api_client.post(
            "/api/v1/rag/retrieve",
            json={
                "query": "三道安全闸门",
                "top_k": 3,
                "mode": "hybrid",
            },
        )
        assert retrieve_resp.status_code == 200
        ret_data = retrieve_resp.json()
        assert len(ret_data["results"]) == 1
        assert ret_data["results"][0]["file_path"] == "docs/11_http_api.md"
        assert ret_data["results"][0]["score"] == 0.95
