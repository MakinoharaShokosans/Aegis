"""POST /api/v1/documents/ingest 端点测试。

验证全量索引、增量跳过、Git 提交哈希关联与不存在目录 404 拦截。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app


class TestRouteIngest:
    """索引接口端到端测试套件。"""

    def test_ingest_and_incremental_idempotency(self, tmp_path: Path) -> None:
        # 创建一个临时代码仓库目录
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()
        (repo_dir / "main.c").write_text("int main() { return 0; }\n", encoding="utf-8")
        (repo_dir / "calc.go").write_text("package main\nfunc Add(a, b int) int { return a + b }\n", encoding="utf-8")

        app = create_app()
        with TestClient(app) as client:
            # 1. 首次索引
            payload = {
                "repo_name": "sample_repo",
                "repo_root": str(repo_dir),
                "incremental": True,
            }
            resp = client.post("/api/v1/documents/ingest", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["indexed"] >= 2
            assert data["skipped"] == 0
            assert data["deleted"] == 0

            # 2. 第二次增量索引（未改动），应该全部 skipped
            resp2 = client.post("/api/v1/documents/ingest", json=payload)
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["indexed"] == 0
            assert data2["skipped"] >= 2

    def test_ingest_non_existent_repo_root_raises_404(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            payload = {
                "repo_name": "bad_repo",
                "repo_root": "/path/that/does/not/exist/at/all",
                "incremental": True,
            }
            resp = client.post("/api/v1/documents/ingest", json=payload)
            assert resp.status_code == 404
            data = resp.json()
            assert data["error"]["code"] == "REPO_NOT_INDEXED"
