"""访问 sidecar 微服务的共享 HTTP 客户端。

**为什么要共享**：Agent 一轮可能并发调用 RAG / Shell / Web 三个 sidecar。
每个请求各建一个连接会反复做 TCP + TLS 握手。用一个长生命周期的
``httpx.AsyncClient`` 复用连接池，并统一注入 ``X-Trace-ID`` 实现全链路追踪。

**解耦设计**：本类只接受 ``base_url`` 与超时，**不读全局配置**——
由装配层（tool 工厂）注入具体地址，便于单测替换为 mock 地址。
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

import httpx
from loguru import logger

from agent_runtime.errors import DependencyUnavailableError

__all__ = ["ServiceClient"]


class ServiceClient:
    """面向单个 sidecar 的异步 HTTP 客户端封装。

    Args:
        base_url: sidecar 基址，如 ``http://127.0.0.1:8001``。
        timeout_sec: 单次请求超时。
        trace_id: 可选的链路追踪 ID。
    """

    __slots__ = ("base_url", "timeout_sec", "trace_id", "_client")

    def __init__(self, base_url: str, timeout_sec: float = 60.0, trace_id: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.trace_id = trace_id
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """懒加载底层连接池。"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_sec),
                headers={"X-Trace-ID": self.trace_id} if self.trace_id else None,
            )
        return self._client

    async def aclose(self) -> None:
        """关闭连接池（由 lifespan 或工具生命周期回调调用）。"""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[Mapping[str, Any]] = None,
        expected_status: tuple[int, ...] = (200, 201, 202),
    ) -> Dict[str, Any]:
        """发起请求并解析 JSON 响应。

        Args:
            method: HTTP 方法。
            path: 相对路径，如 ``/api/v1/retrieve``。
            payload: JSON 请求体。
            expected_status: 视为成功的状态码集合。

        Returns:
            解析后的 JSON 字典。

        Raises:
            DependencyUnavailableError: 连接失败、超时或返回非预期状态码。
        """
        client = await self._ensure_client()
        try:
            response = await client.request(method, path, json=dict(payload) if payload else None)
        except httpx.HTTPError as exc:
            logger.error(f"[ServiceClient] {method} {self.base_url}{path} 网络异常: {exc}")
            raise DependencyUnavailableError(
                f"sidecar 不可达: {self.base_url}{path}",
                context={"reason": str(exc)},
            ) from exc

        if response.status_code not in expected_status:
            raise DependencyUnavailableError(
                f"sidecar 返回异常状态码: {response.status_code}",
                context={"url": f"{self.base_url}{path}", "body": response.text[:500]},
            )
        try:
            return response.json()
        except ValueError as exc:
            raise DependencyUnavailableError(
                "sidecar 返回体不是合法 JSON",
                context={"url": f"{self.base_url}{path}"},
            ) from exc

    async def request_text(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[Mapping[str, Any]] = None,
        expected_status: tuple[int, ...] = (200,),
    ) -> str:
        """发起请求并返回纯文本响应（用于产物下载）。

        Args:
            method: HTTP 方法。
            path: 相对路径。
            payload: JSON 请求体。
            expected_status: 视为成功的状态码集合。

        Returns:
            响应正文。

        Raises:
            DependencyUnavailableError: 网络异常或状态码非预期。
        """
        client = await self._ensure_client()
        try:
            response = await client.request(method, path, json=dict(payload) if payload else None)
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError(
                f"sidecar 不可达: {self.base_url}{path}", context={"reason": str(exc)}
            ) from exc

        if response.status_code not in expected_status:
            raise DependencyUnavailableError(
                f"sidecar 返回异常状态码: {response.status_code}",
                context={"url": f"{self.base_url}{path}"},
            )
        return response.text
