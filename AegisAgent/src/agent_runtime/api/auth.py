"""接入层安全闸门：Host 校验 → Origin 校验 → 令牌校验。

对应 ``documents/agent_runtime/11_http_api.md`` §1。

## 为什么"只监听回环"还不够

本 API 的工具链包含受控命令执行能力，等价于对本机工程目录的读写与执行权限。
``server.host`` 的回环护栏（``config.py`` 的 fail-closed 校验）挡的是**对外暴露**，
挡不住下面两类：

1. **浏览器发起的跨站请求（CSRF / DNS rebinding）**。用户浏览器里的任意一个页面
   都能向 ``http://127.0.0.1:8000`` 发请求；``POST /approve`` 一旦被诱导调用，
   等于让攻击者**替用户批准**了一次高危操作，而用户看到的是自己刚打开的那个网页。
   —— Host 头校验挡 DNS rebinding，Origin 校验挡跨站表单/脚本，令牌挡住"猜到端口就能用"。
2. **同用户的其它本地进程**。它能直接读令牌文件，本层挡不住它——**这不是本方案的
   目标**（见 §"不提供的保证"）。

## 三道闸门的顺序不可调换

``Host → Origin → 令牌``：由外到内，先排除"请求根本不是发给我们的"，
再排除"请求是浏览器跨站发起的"，最后才做凭据校验。
这样日志里能明确区分"配置错"与"有人在探测"。

## 为什么用纯 ASGI 中间件而不是 ``BaseHTTPMiddleware``

本服务有 SSE 长连接。``BaseHTTPMiddleware`` 会包一层 anyio 内存对象流，
在长连接/取消场景下有额外的缓冲与取消传播开销（历史上出过挂起与断流问题）。
纯 ASGI 中间件**不碰 body**，对 SSE 完全透明。

## 令牌的来源

1. 环境变量（名由 ``server.api_token_env`` 指定，默认 ``AEGIS_API_TOKEN``）；
2. 否则从 ``server.api_token_file`` 读取**已有**令牌（重启不失效，前端无需改配置）；
3. 都没有则在启动阶段生成 ``secrets.token_urlsafe(32)`` 并以 ``0600`` 写入该文件。

**日志只打印文件路径，绝不打印令牌本身**——日志会被复制、粘贴、进 issue。
"""

from __future__ import annotations

import hmac
import os
import secrets
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional, Sequence, Set
from urllib.parse import parse_qs

from loguru import logger
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = ["SecurityGateMiddleware", "provision_api_token"]

#: 无需令牌即可访问的路径（存活探针与静态文档）。
#: 刻意**只**放这些：业务端点一律要求凭据，避免"新增路由忘了保护"。
_EXEMPT_PATHS: Set[str] = {
    "/",
    "/health",
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
}

#: 需要 Origin 校验的方法（浏览器只在"非简单请求"或跨站时带上 Origin）
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

#: 令牌可用的三种载体。``?token=`` 是给 ``EventSource`` 用的——
#: 浏览器原生 ``EventSource`` **不能**自定义请求头，这是唯一可行的传递方式。
_TOKEN_HEADER = "x-api-token"


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


def _extract_token(headers: Headers, query_string: bytes) -> str:
    """按优先级提取客户端提交的令牌。

    优先级：``Authorization: Bearer`` → ``X-API-Token`` → ``?token=``。

    Args:
        headers: 请求头。
        query_string: 原始查询串（bytes）。

    Returns:
        令牌原文；未提供时返回空串。
    """
    authorization = headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    api_token = headers.get(_TOKEN_HEADER, "")
    if api_token.strip():
        return api_token.strip()

    if query_string:
        try:
            values = parse_qs(query_string.decode("latin-1"), keep_blank_values=False)
        except Exception:  # noqa: BLE001 - 畸形查询串按"未提供令牌"处理
            return ""
        candidate = values.get("token") or []
        if candidate:
            return str(candidate[0]).strip()
    return ""


class SecurityGateMiddleware:
    """Host / Origin / 令牌三道闸门（纯 ASGI，对 SSE 透明）。

    Args:
        app: 下游 ASGI 应用。
        require_token: 是否强制令牌（``server.auth_enabled``）。
        token: 期望的令牌（静态值）。
        token_provider: 期望令牌的**动态来源**（优先于 ``token``）。
            中间件在应用构造期就已挂载，而令牌要到 lifespan 启动阶段才准备就绪；
            因此生产装配传的是 ``lambda: app.state.api_token``，避免"构造期拿到空令牌
            导致全站 401"。``require_token`` 为真而两者都取不到令牌时**全部请求 401**
            （fail-closed：宁可全拒，不可静默放行）。
        allowed_hosts: 额外允许的 Host 主机名（配置项，回环名始终允许）。
        allow_origins: CORS 白名单，仅用于 Origin 校验。
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        require_token: bool,
        token: Optional[str] = None,
        token_provider: Optional[Callable[[], str]] = None,
        allowed_hosts: Optional[Sequence[str]] = None,
        allow_origins: Optional[Sequence[str]] = None,
    ) -> None:
        self.app = app
        self.require_token = bool(require_token)
        self.token = str(token or "")
        self.token_provider = token_provider
        self.allowed_hosts = _normalize_hosts(allowed_hosts)
        self.allow_origins = {str(item).rstrip("/") for item in (allow_origins or []) if str(item).strip()}
        # 回环名称与 IP 始终允许：服务本身就被 config 护栏限制在回环
        self.allowed_hosts |= {"127.0.0.1", "localhost", "::1"}

    def _current_token(self) -> str:
        """取当前生效的令牌（动态来源优先；取不到时返回空串 → fail-closed）。"""
        if self.token_provider is not None:
            try:
                return str(self.token_provider() or "")
            except Exception as exc:  # noqa: BLE001 - 取令牌失败按"无令牌"处理
                logger.error(f"[SecurityGate] 读取令牌失败（按未配置处理）: {exc}")
                return ""
        return self.token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI 入口：非 HTTP 直接放行，HTTP 走三道闸门。"""
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

        # ---- 闸门③：令牌 ---------------------------------------------------
        if self.require_token:
            supplied = _extract_token(headers, scope.get("query_string") or b"")
            expected = self._current_token()
            if not expected:
                # fail-closed：要求令牌却没有令牌可比对，一律拒绝
                await self._reject(
                    401,
                    "AUTH_MISCONFIGURED",
                    "服务端未配置访问令牌，拒绝全部请求（请检查启动日志）",
                    {},
                    trace_id,
                    send,
                )
                return
            if not supplied or not hmac.compare_digest(supplied, expected):
                logger.warning(
                    f"[SecurityGate] 令牌校验失败 path={path} method={method} "
                    f"host={hostname} supplied={'有' if supplied else '无'} trace={trace_id}"
                )
                await self._reject(
                    401,
                    "UNAUTHORIZED",
                    "缺少或无效的访问令牌",
                    {
                        "hint": (
                            f"请携带 Authorization: Bearer <token>、X-API-Token 头，"
                            f"或 ?token=<token> 查询参数；令牌见 server.api_token_file"
                        )
                    },
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
        """返回与其它端点同构的 JSON 错误响应。

        Args:
            status_code: HTTP 状态码。
            code: 稳定错误码（与 ``api/errors.py`` 同一套语义）。
            message: 面向人的说明。
            details: 附加上下文。
            trace_id: 链路追踪 ID。
            send: ASGI send 通道。
        """
        from agent_runtime.api.errors import build_error_response

        response = build_error_response(status_code, code, message, details, trace_id)
        if status_code == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        await response({"type": "http"}, _empty_receive, send)


async def _empty_receive() -> dict:  # pragma: no cover - ASGI 占位
    """占位 receive（错误响应不读取请求体）。"""
    return {"type": "http.request", "body": b"", "more_body": False}


def _normalize_hosts(hosts: Optional[Iterable[str]]) -> Set[str]:
    """归一化允许的 Host 主机名集合。"""
    result: Set[str] = set()
    for item in hosts or []:
        name = _hostname_of(str(item))
        if name:
            result.add(name)
    return result


def provision_api_token(server: Any) -> Optional[str]:
    """准备访问令牌（环境变量 → 已有文件 → 生成并落盘）。

    刻意只接收 ``ServerConfig``（而非整个 ``AegisConfig``），与
    ``PhysicalBudgetGuard.from_config`` 的粒度一致：**谁用哪一段就只拿哪一段**。

    Args:
        server: ``config.server``（``ServerConfig``）。

    Returns:
        生效的令牌；``server.auth_enabled`` 为假时返回 ``None``。
    """
    if not server.auth_enabled:
        logger.warning(
            "[SecurityGate] server.auth_enabled = false：接入层**不做令牌校验**"
            "（Host 与 Origin 闸门仍然生效）。本机单用户场景可用，"
            "但请勿在浏览器可访问的环境下长期关闭。"
        )
        return None

    env_name = str(server.api_token_env or "").strip()
    if env_name:
        env_value = os.environ.get(env_name, "").strip()
        if env_value:
            logger.info(f"[SecurityGate] 访问令牌来自环境变量 {env_name}")
            return env_value

    path = Path(server.api_token_file)
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.error(f"[SecurityGate] 读取令牌文件失败 {path}: {exc}")
            existing = ""
        if existing:
            logger.info(f"[SecurityGate] 复用已有访问令牌：{path}")
            return existing

    token = secrets.token_urlsafe(32)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 刻意用 os.open 指定 0600，并在写入后再 chmod 一次
        # （os.open 的 mode 会被 umask 削减，不能只依赖它）
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
        os.chmod(path, 0o600)
    except OSError as exc:
        # 落盘失败不致命：令牌仍在进程内生效，但重启后会变
        logger.error(
            f"[SecurityGate] 令牌文件写入失败 {path}: {exc}；"
            f"本次运行使用临时令牌（重启后失效）。可改用环境变量 {env_name or 'AEGIS_API_TOKEN'}"
        )
        return token

    logger.info(f"[SecurityGate] 已生成访问令牌并写入 {path}（权限 0600，日志不打印令牌本身）")
    return token


def public_exempt_paths() -> List[str]:  # pragma: no cover - 供文档/自省使用
    """返回无需令牌的路径列表（供文档与自省端点渲染）。"""
    return sorted(_EXEMPT_PATHS)
