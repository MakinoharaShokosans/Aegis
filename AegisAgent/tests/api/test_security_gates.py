"""接入层安全闸门 (SecurityGateMiddleware) 与访问令牌专测。

对应 ``documents/agent_runtime/11_http_api.md`` §1 与 ``api/auth.py``。
覆盖：
1. 闸门① Host 校验（回环名、IPv6、白名单、DNS Rebinding 拦截）
2. 闸门② Origin 校验（安全方法免检、跨站 CSRF 拦截、CORS 白名单）
3. 闸门③ 令牌校验（Bearer / X-API-Token / ?token=、401 失败语义、豁免路径精确匹配、fail-closed）
4. 令牌准备与 0600 文件权限 (provision_api_token)
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.routing import Route

from agent_runtime.api.auth import (
    SecurityGateMiddleware,
    _extract_token,
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
    require_token: bool = True,
    token: Optional[str] = "secret-token-123",
    token_provider: Optional[callable] = None,
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
        require_token=require_token,
        token=token,
        token_provider=token_provider,
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


def test_extract_token_precedence():
    """验证令牌提取的优先级：Bearer -> X-API-Token -> ?token=。"""
    # 1. Bearer 优先
    h1 = Headers({"authorization": "Bearer token_bearer", "x-api-token": "token_header"})
    assert _extract_token(h1, b"token=token_query") == "token_bearer"

    # 2. X-API-Token 次之
    h2 = Headers({"x-api-token": "token_header"})
    assert _extract_token(h2, b"token=token_query") == "token_header"

    # 3. Query string 再次之（用于 EventSource SSE）
    h3 = Headers({})
    assert _extract_token(h3, b"token=token_query&other=1") == "token_query"

    # 4. 未提供
    assert _extract_token(Headers({}), b"") == ""
    assert _extract_token(Headers({}), b"malformed_query%FF") == ""


def test_public_exempt_paths_list():
    """验证公开豁免路径列表包含核心探针与文档端点。"""
    paths = public_exempt_paths()
    assert "/health" in paths
    assert "/api/v1/health" in paths
    assert "/docs" in paths
    assert "/api/v1/health/dependencies" not in paths


# ==============================================================================
# 2. 闸门①：Host 校验测试 (DNS Rebinding 防御)
# ==============================================================================


@pytest.mark.asyncio
async def test_host_gate_allows_loopback_and_configured_hosts():
    """验证回环地址与配置白名单允许通过 Host 闸门。"""
    app = _create_test_app(
        token="test-token",
        allowed_hosts=["custom.local"],
    )
    transport = ASGITransport(app=app)

    # 1. 127.0.0.1 允许
    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": "Bearer test-token"},
    ) as client:
        resp = await client.get("/api/v1/protected")
        assert resp.status_code == 200

    # 2. localhost 允许
    async with AsyncClient(
        transport=transport,
        base_url="http://localhost:8000",
        headers={"Authorization": "Bearer test-token"},
    ) as client:
        resp = await client.get("/api/v1/protected")
        assert resp.status_code == 200

    # 3. custom.local 允许
    async with AsyncClient(
        transport=transport,
        base_url="http://custom.local:8000",
        headers={"Authorization": "Bearer test-token"},
    ) as client:
        resp = await client.get("/api/v1/protected")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_host_gate_rejects_unauthorized_hosts():
    """验证虚构 Host / 外部未授权 Host 被拦截并返回 403 HOST_NOT_ALLOWED。"""
    app = _create_test_app(token="test-token")
    transport = ASGITransport(app=app)

    # 模拟攻击者通过 DNS Rebinding 使用 evil.com 发起请求
    async with AsyncClient(
        transport=transport,
        base_url="http://evil.com:8000",
        headers={"Authorization": "Bearer test-token"},
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
    app = _create_test_app(token="test-token", allow_origins=["http://127.0.0.1:3000"])
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": "Bearer test-token", "Origin": "http://malicious-website.com"},
    ) as client:
        # GET 方法不触发 Origin 校验（浏览器只在读数据，无法替用户执行变更操作）
        resp = await client.get("/api/v1/protected")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_origin_gate_unsafe_methods_without_origin_allowed():
    """验证非浏览器调用（无 Origin 头，如 curl 或 Python client）正常放行。"""
    app = _create_test_app(token="test-token", allow_origins=["http://127.0.0.1:3000"])
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": "Bearer test-token"},
    ) as client:
        resp = await client.post("/api/v1/protected")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_origin_gate_unsafe_methods_with_whitelisted_origin_allowed():
    """验证白名单内的 Origin 正常放行。"""
    app = _create_test_app(token="test-token", allow_origins=["http://127.0.0.1:3000"])
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": "Bearer test-token", "Origin": "http://127.0.0.1:3000"},
    ) as client:
        resp = await client.post("/api/v1/protected")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_origin_gate_unsafe_methods_with_unauthorized_origin_rejected():
    """验证浏览器跨站诱导发起的 POST /approve 被拦截并返回 403 ORIGIN_NOT_ALLOWED。"""
    app = _create_test_app(token="test-token", allow_origins=["http://127.0.0.1:3000"])
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": "Bearer test-token", "Origin": "http://evil-attacker.com"},
    ) as client:
        resp = await client.post("/api/v1/tasks/1/approve")
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"]["code"] == "ORIGIN_NOT_ALLOWED"
        assert data["error"]["details"]["origin"] == "http://evil-attacker.com"


# ==============================================================================
# 4. 闸门③：令牌校验测试 (Token Authentication)
# ==============================================================================


@pytest.mark.asyncio
async def test_token_gate_valid_carriers():
    """验证 Bearer 头、X-API-Token 头以及 ?token= 查询参数均可成功鉴权。"""
    app = _create_test_app(token="secret-xyz-456")
    transport = ASGITransport(app=app)

    # 1. Authorization: Bearer
    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": "Bearer secret-xyz-456"},
    ) as client:
        resp = await client.get("/api/v1/protected")
        assert resp.status_code == 200

    # 2. X-API-Token
    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        headers={"X-API-Token": "secret-xyz-456"},
    ) as client:
        resp = await client.get("/api/v1/protected")
        assert resp.status_code == 200

    # 3. Query string ?token=
    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
    ) as client:
        resp = await client.get("/api/v1/protected?token=secret-xyz-456")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_token_gate_rejects_missing_and_invalid_token():
    """验证缺失令牌与错误令牌均返回 401 UNAUTHORIZED 与 WWW-Authenticate 头。"""
    app = _create_test_app(token="secret-xyz-456")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # 无令牌
        resp1 = await client.get("/api/v1/protected")
        assert resp1.status_code == 401
        assert resp1.json()["error"]["code"] == "UNAUTHORIZED"
        assert resp1.headers["WWW-Authenticate"] == "Bearer"

        # 错误令牌
        resp2 = await client.get(
            "/api/v1/protected", headers={"Authorization": "Bearer wrong-token"}
        )
        assert resp2.status_code == 401
        assert resp2.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_token_gate_exempt_paths_and_options_preflight():
    """验证豁免路径与 OPTIONS 预检请求无需令牌即可访问。"""
    app = _create_test_app(token="secret-xyz-456")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # / 免检
        assert (await client.get("/")).status_code == 200
        # /health 免检
        assert (await client.get("/health")).status_code == 200
        # /api/v1/health 免检
        assert (await client.get("/api/v1/health")).status_code == 200
        # /docs 免检
        assert (await client.get("/docs")).status_code == 200

        # /api/v1/health/dependencies 虽含 health 但非精确匹配，仍要求令牌
        resp_deps = await client.get("/api/v1/health/dependencies")
        assert resp_deps.status_code == 401

        # OPTIONS 预检免检
        resp_options = await client.options("/api/v1/protected")
        assert resp_options.status_code in {200, 405}  # Starlette 路由处理，未被中间件 401 拦截


@pytest.mark.asyncio
async def test_token_gate_fail_closed_when_expected_token_missing():
    """验证 fail-closed：开启 auth_enabled 但服务端拿不到令牌时拒绝全部请求 (401 AUTH_MISCONFIGURED)。"""
    # token_provider 返回空
    app = _create_test_app(require_token=True, token="", token_provider=lambda: "")
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": "Bearer any-token"},
    ) as client:
        resp = await client.get("/api/v1/protected")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "AUTH_MISCONFIGURED"


@pytest.mark.asyncio
async def test_token_gate_dynamic_provider_resolution():
    """验证 token_provider 动态求值（解决 lifespan 就绪时序）。"""
    holder = {"token": ""}
    app = _create_test_app(
        require_token=True,
        token_provider=lambda: holder["token"],
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": "Bearer late-ready-token"},
    ) as client:
        # 启动前 holder 为空 -> 401
        assert (await client.get("/api/v1/protected")).status_code == 401

        # lifespan 启动后 token 就绪 -> 200
        holder["token"] = "late-ready-token"
        assert (await client.get("/api/v1/protected")).status_code == 200


# ==============================================================================
# 5. 令牌准备 (provision_api_token) 与 0600 权限测试
# ==============================================================================


def test_provision_token_disabled():
    """验证 auth_enabled=False 时返回 None。"""
    cfg = ServerConfig(auth_enabled=False)
    assert provision_api_token(cfg) is None


def test_provision_token_from_environment(monkeypatch: pytest.MonkeyPatch):
    """验证从指定环境变量读取令牌。"""
    monkeypatch.setenv("CUSTOM_API_TOKEN_ENV", "env-secret-token-888")
    cfg = ServerConfig(
        auth_enabled=True,
        api_token_env="CUSTOM_API_TOKEN_ENV",
    )
    assert provision_api_token(cfg) == "env-secret-token-888"


def test_provision_token_reusing_existing_file(tmp_path: Path):
    """验证复用已有令牌文件。"""
    token_file = tmp_path / "existing_token.txt"
    token_file.write_text("persisted-token-999\n", encoding="utf-8")

    cfg = ServerConfig(
        auth_enabled=True,
        api_token_env="NON_EXISTENT_ENV_VAR",
        api_token_file=str(token_file),
    )
    token = provision_api_token(cfg)
    assert token == "persisted-token-999"


def test_provision_token_generates_new_file_with_0600_permissions(tmp_path: Path):
    """验证新生成令牌文件且权限严格为 0600 (仅所有者读写)。"""
    token_file = tmp_path / "sub_dir" / "new_token.txt"
    assert not token_file.exists()

    cfg = ServerConfig(
        auth_enabled=True,
        api_token_env="NON_EXISTENT_ENV_VAR",
        api_token_file=str(token_file),
    )
    token = provision_api_token(cfg)
    assert token and len(token) > 20
    assert token_file.is_file()

    # 验证文件内容
    assert token_file.read_text(encoding="utf-8").strip() == token

    # 验证文件权限为 0600 (Unix 文件模式)
    mode = token_file.stat().st_mode
    permissions = stat.S_IMODE(mode)
    assert permissions == 0o600, f"期望权限 0600，实际权限 {oct(permissions)}"
