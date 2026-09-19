"""接入层安全闸门 (SecurityGateMiddleware) 专测。

对应 ``documents/agent_runtime/11_http_api.md`` §1 与 ``api/auth.py``。
覆盖：
1. 闸门① Host 校验（回环名、IPv6、白名单、DNS Rebinding 拦截 403 HOST_NOT_ALLOWED）
2. 闸门② Origin 校验（安全方法免检、跨站 CSRF 拦截 403 ORIGIN_NOT_ALLOWED、CORS 白名单）
3. 免令牌直接访问（本地单用户场景开箱即用，无需 401 凭据）
4. 豁免路径与 OPTIONS 预检请求放行
"""

from __future__ import annotations

from typing import Optional

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from agent_runtime.api.auth import (
    SecurityGateMiddleware,
    _hostname_of,
    _normalize_hosts,
    provision_api_token,
    public_exempt_paths,
)
from agent_runtime.config import ServerConfig


# ------------------------------------------------------------------------------
# 辅助轻量 ASGI App 夹具
# ------------------------------------------------------------------------------


def _create_test_app(
    *,
    allowed_hosts: Optional[list[str]] = None,
    allow_origins: Optional[list[str]] = None,
) -> Starlette:
    """创建挂载了 SecurityGateMiddleware 的极简 Starlette 应用。"""

    async def root(request):
        return JSONResponse({"message": "root"})

    async def health(request):
        return JSONResponse({"status": "ok"})

    async def health_deps(request):
        return JSONResponse({"dependencies": "ok"})

    async def protected_get(request):
        return JSONResponse({"data": "get_ok"})

    async def protected_post(request):
        return JSONResponse({"data": "post_ok"})

    routes = [
        Route("/", root, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Route("/api/v1/health", health, methods=["GET"]),
        Route("/api/v1/health/dependencies", health_deps, methods=["GET"]),
        Route("/docs", root, methods=["GET"]),
        Route("/api/v1/protected", protected_get, methods=["GET"]),
        Route("/api/v1/protected", protected_post, methods=["POST"]),
        Route("/api/v1/tasks/1/approve", protected_post, methods=["POST"]),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(
        SecurityGateMiddleware,
        allowed_hosts=allowed_hosts,
        allow_origins=allow_origins,
    )
    return app


# ==============================================================================
# 1. 辅助函数单元测试
# ==============================================================================


def test_hostname_of_parsing():
    """验证 _hostname_of 对各种 Host 头的解析。"""
    assert _hostname_of("127.0.0.1:8000") == "127.0.0.1"
    assert _hostname_of("localhost:8000") == "localhost"
    assert _hostname_of("[::1]:8000") == "::1"
    assert _hostname_of("[::1]") == "::1"
    assert _hostname_of("api.internal.local") == "api.internal.local"
    assert _hostname_of("API.Internal.Local:9000") == "api.internal.local"
    assert _hostname_of("") == ""
    assert _hostname_of("   ") == ""


def test_normalize_hosts():
    """验证 _normalize_hosts 批量归一化。"""
    hosts = _normalize_hosts(["127.0.0.1:8000", "Custom.Local", ""])
    assert "127.0.0.1" in hosts
    assert "custom.local" in hosts


def test_public_exempt_paths_list():
    """验证公开豁免路径列表包含核心探针与文档端点。"""
    paths = public_exempt_paths()
    assert "/health" in paths
    assert "/api/v1/health" in paths
    assert "/docs" in paths


# ==============================================================================
# 2. 闸门①：Host 校验测试 (DNS Rebinding 防御)
# ==============================================================================


@pytest.mark.asyncio
async def test_host_gate_allows_loopback_and_configured_hosts():
    """验证回环地址与配置白名单允许通过 Host 闸门。"""
    app = _create_test_app(allowed_hosts=["custom.local"])
    transport = ASGITransport(app=app)

    # 1. 127.0.0.1 允许
    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
    ) as client:
        resp = await client.get("/api/v1/protected")
        assert resp.status_code == 200
        assert resp.json()["data"] == "get_ok"

    # 2. localhost 允许
    async with AsyncClient(
        transport=transport,
        base_url="http://localhost:8000",
    ) as client:
        resp = await client.get("/api/v1/protected")
        assert resp.status_code == 200

    # 3. custom.local 允许
    async with AsyncClient(
        transport=transport,
        base_url="http://custom.local:8000",
    ) as client:
        resp = await client.get("/api/v1/protected")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_host_gate_rejects_unauthorized_hosts():
    """验证虚构 Host / 外部未授权 Host 被拦截并返回 403 HOST_NOT_ALLOWED。"""
    app = _create_test_app()
    transport = ASGITransport(app=app)

    # 模拟攻击者通过 DNS Rebinding 使用 evil.com 发起请求
    async with AsyncClient(
        transport=transport,
        base_url="http://evil.com:8000",
    ) as client:
        resp = await client.get("/api/v1/protected")
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"]["code"] == "HOST_NOT_ALLOWED"
        assert "evil.com" in data["error"]["details"]["host"]


# ==============================================================================
# 3. 闸门②：Origin 校验测试 (CSRF 跨站提交防御)
# ==============================================================================


@pytest.mark.asyncio
async def test_origin_gate_safe_methods_exempt():
    """验证 GET / HEAD 等安全方法即便携带跨站 Origin 也免受 Origin 闸门拦截。"""
    app = _create_test_app(allow_origins=["http://127.0.0.1:3000"])
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        headers={"Origin": "http://malicious-website.com"},
    ) as client:
        # GET 方法不触发 Origin 校验（浏览器只在读数据，无法替用户执行变更操作）
        resp = await client.get("/api/v1/protected")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_origin_gate_unsafe_methods_without_origin_allowed():
    """验证非浏览器调用（无 Origin 头，如 curl 或 Python client）正常放行。"""
    app = _create_test_app(allow_origins=["http://127.0.0.1:3000"])
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
    ) as client:
        resp = await client.post("/api/v1/protected")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_origin_gate_unsafe_methods_with_whitelisted_origin_allowed():
    """验证白名单内的 Origin 正常放行。"""
    app = _create_test_app(allow_origins=["http://127.0.0.1:3000"])
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        headers={"Origin": "http://127.0.0.1:3000"},
    ) as client:
        resp = await client.post("/api/v1/protected")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_origin_gate_unsafe_methods_with_unauthorized_origin_rejected():
    """验证浏览器跨站诱导发起的 POST /approve 被拦截并返回 403 ORIGIN_NOT_ALLOWED。"""
    app = _create_test_app(allow_origins=["http://127.0.0.1:3000"])
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        headers={"Origin": "http://evil-attacker.com"},
    ) as client:
        resp = await client.post("/api/v1/tasks/1/approve")
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"]["code"] == "ORIGIN_NOT_ALLOWED"
        assert data["error"]["details"]["origin"] == "http://evil-attacker.com"


# ==============================================================================
# 4. 免令牌与无摩擦调用测试
# ==============================================================================


@pytest.mark.asyncio
async def test_direct_access_without_token():
    """验证所有业务端点无需令牌即可直接请求成功。"""
    app = _create_test_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        resp = await client.get("/api/v1/protected")
        assert resp.status_code == 200
        assert resp.json()["data"] == "get_ok"

        resp_post = await client.post("/api/v1/protected")
        assert resp_post.status_code == 200
        assert resp_post.json()["data"] == "post_ok"


@pytest.mark.asyncio
async def test_exempt_paths_and_options_preflight():
    """验证豁免路径与 OPTIONS 预检请求正常放行。"""
    app = _create_test_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        assert (await client.get("/")).status_code == 200
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/api/v1/health")).status_code == 200
        assert (await client.get("/docs")).status_code == 200

        resp_options = await client.options("/api/v1/protected")
        assert resp_options.status_code in {200, 405}


def test_provision_token_placeholder():
    """验证 provision_api_token 占位函数安全返回 None。"""
    cfg = ServerConfig()
    assert provision_api_token(cfg) is None
    assert provision_api_token() is None
