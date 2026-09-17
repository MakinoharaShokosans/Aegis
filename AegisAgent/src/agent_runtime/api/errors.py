"""领域异常 → HTTP 响应 的映射。

**为什么单独一处**：领域层完全不感知 HTTP（见 :mod:`agent_runtime.errors`）。
把映射集中在这里，好处是"新增一种领域错误"只需要改这一张表，
而不是在几十个路由函数里各写一遍 ``try/except``。
"""

from __future__ import annotations

import uuid
from typing import Dict, Type

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger

from agent_runtime import errors as domain_errors
from agent_runtime.api.schemas import ErrorBody, ErrorDetail

__all__ = ["build_error_response", "install_exception_handlers", "trace_id_of"]

#: 领域异常 → HTTP 状态码。未登记的具体子类回落到其基类，再回落到 500。
_STATUS_MAP: Dict[Type[domain_errors.AgentError], int] = {
    domain_errors.NotFoundError: 404,
    domain_errors.ConflictError: 409,
    domain_errors.PathEscapeDetectedError: 422,
    domain_errors.TaskQueueFullError: 429,
    domain_errors.DependencyUnavailableError: 503,
    domain_errors.LLMUnavailableError: 503,
    domain_errors.ToolExecutionError: 500,
    domain_errors.ConfigError: 500,
}

_DEFAULT_STATUS = 500
_TRACE_HEADER = "X-Trace-ID"


def trace_id_of(request: Request) -> str:
    """取（或生成）当前请求的链路追踪 ID。

    Args:
        request: FastAPI 请求对象。

    Returns:
        追踪 ID；请求未携带时生成 UUID 并写入 ``request.state``。
    """
    existing = getattr(request.state, "trace_id", "") or request.headers.get(_TRACE_HEADER, "")
    if existing:
        return existing
    generated = str(uuid.uuid4())
    request.state.trace_id = generated
    return generated


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict,
    trace_id: str,
) -> JSONResponse:
    """构造统一错误响应。"""
    body = ErrorBody(error=ErrorDetail(code=code, message=message, details=details, trace_id=trace_id))
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(),
        headers={_TRACE_HEADER: trace_id},
    )


def build_error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict,
    trace_id: str,
) -> JSONResponse:
    """构造统一错误响应（**中间件等非路由场景的公开入口**）。

    安全闸门（``api/auth.py``）是纯 ASGI 中间件，不走 FastAPI 的异常处理器，
    因此需要直接拿到同一套响应形状，避免出现"两套错误体"。

    Args:
        status_code: HTTP 状态码。
        code: 稳定错误码。
        message: 面向人的说明。
        details: 附加上下文。
        trace_id: 链路追踪 ID。

    Returns:
        与领域异常处理器同构的 :class:`JSONResponse`。
    """
    return _error_response(status_code, code, message, details, trace_id)


def _status_for(exc: domain_errors.AgentError) -> int:
    """按 MRO 自下而上查找状态码映射。"""
    for klass in type(exc).__mro__:
        if klass in _STATUS_MAP:
            return _STATUS_MAP[klass]
    return _DEFAULT_STATUS


def install_exception_handlers(app: FastAPI) -> None:
    """为应用挂载统一异常处理器。

    Args:
        app: FastAPI 应用实例。
    """

    @app.exception_handler(domain_errors.AgentError)
    async def _handle_domain_error(request: Request, exc: domain_errors.AgentError) -> JSONResponse:
        """领域异常 → 语义化 HTTP 状态码。"""
        trace_id = trace_id_of(request)
        status_code = _status_for(exc)
        logger.warning(f"[API] 领域异常 {exc.code} (HTTP {status_code}) trace={trace_id}: {exc}")
        return _error_response(status_code, exc.code, exc.message, exc.context, trace_id)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """请求体校验失败 → 400。"""
        trace_id = trace_id_of(request)
        return _error_response(
            400,
            "VALIDATION_ERROR",
            "请求参数不合法",
            {"errors": exc.errors()[:10]},
            trace_id,
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        """未预期异常 → 500（细节只进日志，不外泄）。"""
        trace_id = trace_id_of(request)
        logger.exception(f"[API] 未预期异常 trace={trace_id}: {exc}")
        return _error_response(500, "INTERNAL_ERROR", "服务内部错误", {}, trace_id)
