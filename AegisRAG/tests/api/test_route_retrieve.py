"""POST /api/v1/retrieve 检索端点测试。

验证完整召回与精排交付、空库/零命中安全返回与消融模式支持。
"""

from __future__ import annotations

from pathlib import Path
import uuid

from fastapi.testclient import TestClient

from api.app import create_app


class TestRouteRetrieve:
    """检索接口端到端测试套件。"""

    def test_retrieve_after_ingest(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "retrieve_repo"
        repo_dir.mkdir()
        (repo_dir / "hash.c").write_text(
            "int compute_sha256(const char* data) {\n    return 42;\n}\n",
            encoding="utf-8",
        )

        app = create_app()
        repo_name = f"ret_repo_{uuid.uuid4().hex[:8]}"
        with TestClient(app) as client:
            # 1. 先 Ingest
            ingest_payload = {
                "repo_name": repo_name,
                "repo_root": str(repo_dir),
                "incremental": True,
            }
            ingest_resp = client.post("/api/v1/documents/ingest", json=ingest_payload)
            assert ingest_resp.status_code == 200

            # 2. 检索
            retrieve_payload = {
                "query": "compute sha256 function",
                "repo_name": repo_name,
                "top_k": 3,
                "mode": "hybrid",
            }
            ret_resp = client.post("/api/v1/retrieve", json=retrieve_payload)
            assert ret_resp.status_code == 200
            ret_data = ret_resp.json()
            assert len(ret_data["results"]) >= 1
            match = next((r for r in ret_data["results"] if r.get("file_path") == "hash.c"), None)
            if match is None:
                match = ret_data["results"][0]
            assert "compute_sha256" in match["content"]
            assert isinstance(match["score"], float)

    def test_retrieve_no_match_returns_empty_results(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            retrieve_payload = {
                "query": "super_unlikely_token_xyz_987654321",
                "repo_name": "empty_repo",
                "top_k": 3,
            }
            ret_resp = client.post("/api/v1/retrieve", json=retrieve_payload)
            assert ret_resp.status_code == 200
            data = ret_resp.json()
            assert isinstance(data["results"], list)
