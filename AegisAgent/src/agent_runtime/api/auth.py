"""接入层安全闸门：Host 校验 → Origin 校验。

对应 ``documents/agent_runtime/11_http_api.md`` §1。

## 核心防护能力

1. **Host 校验（防 DNS Rebinding / 非法主机名拦截）**：
   严格限制请求仅发往回环接口（127.0.0.1, localhost, ::1）或配置的白名单主机名。
2. **Origin 校验（防 CSRF 跨站伪造与诱导攻击）**：
   浏览器发起的写操作（POST / PUT / PATCH / DELETE）必须匹配 CORS 白名单 Origin。

## 纯 ASGI 中间件设计

本服务包含 SSE 执行流长连接。纯 ASGI 中间件**不碰 body**，对 SSE 完全透明，
无 anyio 缓冲与取消传播开销。
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Iterable, List, Optional, Sequence, Set

from loguru import logger
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = ["SecurityGateMiddleware", "provision_api_token", "public_exempt_paths"]

#: 公开可访问路径（存活探针与静态文档）。
_EXEMPT_PATHS: Set[str] = {
    "/",
    "/health",
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
}

#: 需要 Origin 校验的方法（浏览器在非简单请求或跨站提交时带上 Origin）。
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _hostname_of(host_header: str) -> str:
    """从 ``Host`` 头中取出主机名（去掉端口与 IPv6 方括号）。

    Args:
        host_header: ``Host`` 头原文，如 ``127.0.0.1:8000`` 或 ``[::1]:8000``。

    Returns:
        小写主机名；无法解析时返回空串。
    """
    text = str(host_header or "").strip().lower()
    if not text:
        return ""
    if text.startswith("["):  # IPv6 字面量
        end = text.find("]")
        return text[1:end] if end > 0 else text
    return text.rsplit(":", 1)[0] if ":" in text else text


def _normalize_hosts(hosts: Optional[Iterable[str]]) -> Set[str]:
    """归一化允许的 Host 主机名集合。"""
    result: Set[str] = set()
    for item in hosts or []:
        name = _hostname_of(str(item))
        if name:
            result.add(name)
    return result


class SecurityGateMiddleware:
    """Host 与 Origin 双道网络安全闸门（纯 ASGI，对 SSE 透明）。

    Args:
        app: 下游 ASGI 应用。
        allowed_hosts: 额外允许的 Host 主机名（回环名始终允许）。
        allow_origins: CORS 白名单，仅用于 Origin 校验。
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_hosts: Optional[Sequence[str]] = None,
        allow_origins: Optional[Sequence[str]] = None,
        require_token: bool = False,
        token: Optional[str] = None,
        token_provider: Optional[Callable[[], str]] = None,
    ) -> None:
        self.app = app
        self.allowed_hosts = _normalize_hosts(allowed_hosts)
        self.allow_origins = {str(item).rstrip("/") for item in (allow_origins or []) if str(item).strip()}
        # 回环名称与 IP 始终允许：服务本身就被 config 护栏限制在回环
        self.allowed_hosts |= {"127.0.0.1", "localhost", "::1"}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI 入口：非 HTTP 直接放行，HTTP 走 Host 与 Origin 闸门。"""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        method = str(scope.get("method") or "GET").upper()
        headers = Headers(scope=scope)
        trace_id = headers.get("x-trace-id") or str(uuid.uuid4())

        # ---- 豁免路径与 CORS 预检 -------------------------------------------
        if path in _EXEMPT_PATHS or method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # ---- 闸门①：Host（挡 DNS rebinding） --------------------------------
        hostname = _hostname_of(headers.get("host", ""))
        if hostname not in self.allowed_hosts:
            await self._reject(
                403,
                "HOST_NOT_ALLOWED",
                "请求的 Host 不在允许列表内",
                {"host": hostname, "allowed": sorted(self.allowed_hosts)},
                trace_id,
                send,
            )
            return

        # ---- 闸门②：Origin（挡跨站脚本/表单） -------------------------------
        if method in _UNSAFE_METHODS:
            origin = (headers.get("origin") or "").rstrip("/")
            if origin and origin not in self.allow_origins:
                await self._reject(
                    403,
                    "ORIGIN_NOT_ALLOWED",
                    "跨站请求被拒绝：Origin 不在 CORS 白名单内",
                    {"origin": origin},
                    trace_id,
                    send,
                )
                return

        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(
        status_code: int,
        code: str,
        message: str,
        details: dict,
        trace_id: str,
        send: Send,
    ) -> None:
        """返回与其它端点同构的 JSON 错误响应。"""
        from agent_runtime.api.errors import build_error_response

        response = build_error_response(status_code, code, message, details, trace_id)
        await response({"type": "http"}, _empty_receive, send)


async def _empty_receive() -> dict:  # pragma: no cover - ASGI 占位
    """占位 receive（错误响应不读取请求体）。"""
    return {"type": "http.request", "body": b"", "more_body": False}


def provision_api_token(server: Any = None) -> Optional[str]:
    """令牌兼容占位函数（单用户本地开发模式无需访问令牌）。"""
    return None


def public_exempt_paths() -> List[str]:  # pragma: no cover - 供文档/自省使用
    """返回无需鉴权的路径列表（供文档与自省端点渲染）。"""
    return sorted(_EXEMPT_PATHS)

