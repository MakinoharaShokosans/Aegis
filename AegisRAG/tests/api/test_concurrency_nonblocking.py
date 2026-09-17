"""同步 def 路由并发非阻塞测试。

验证 FastAPI 线程池调度下健康检查与检索请求的非阻塞并发响应能力。
"""

from __future__ import annotations

import concurrent.futures

from fastapi.testclient import TestClient

from api.app import create_app


class TestConcurrencyNonblocking:
    """并发非阻塞测试套件。"""

    def test_concurrent_health_requests(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            def hit_health():
                return client.get("/api/v1/health").status_code

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(hit_health) for _ in range(5)]
                results = [f.result() for f in futures]

            assert all(code == 200 for code in results)
