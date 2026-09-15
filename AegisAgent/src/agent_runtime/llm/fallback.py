"""弹性降级链：端点内指数退避 → 跨端点切换。

对应 ``documents/agent_runtime/05_guardrails_implementation.md`` §3.1。

**两级策略**：
1. **端点内重试**：遇到超时 / 429 / 5xx / 连接故障时，用 ``tenacity`` 做
   ``max_retries`` 次指数退避；
2. **端点间降级**：该端点重试耗尽后，**透明切换**到下一个端点，
   并且严格保持相同的 ``messages`` / ``tools`` 载荷，保证语义一致。

只有整条链全部耗尽才抛 :class:`LLMUnavailableError`。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, List, Optional, TypeVar

import openai
from loguru import logger
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_runtime.errors import LLMUnavailableError
from agent_runtime.llm.endpoints import ResolvedEndpoint

__all__ = ["FallbackChain"]

T = TypeVar("T")

#: 值得重试的异常（可恢复的瞬时故障）
_RETRYABLE = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)


class FallbackChain:
    """多端点降级执行器。

    Args:
        endpoints: 已解析端点列表（顺序即降级顺序）。
        max_retries: 单端点最大尝试次数。
        backoff_factor: 指数退避倍数（秒）。
    """

    __slots__ = ("_endpoints", "_max_retries", "_backoff_factor")

    def __init__(
        self,
        endpoints: List[ResolvedEndpoint],
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ) -> None:
        self._endpoints = list(endpoints)
        self._max_retries = max(1, max_retries)
        self._backoff_factor = max(0.1, backoff_factor)

    async def execute(
        self,
        attempt: Callable[[ResolvedEndpoint], Awaitable[T]],
        *,
        operation: str = "llm_call",
    ) -> tuple[T, ResolvedEndpoint]:
        """按降级链执行一次调用。

        Args:
            attempt: 接收端点、返回协程结果的调用函数。
            operation: 操作名（仅用于日志）。

        Returns:
            ``(结果, 实际命中的端点)``。

        Raises:
            LLMUnavailableError: 全部端点均不可用。
        """
        if not self._endpoints:
            raise LLMUnavailableError("模型端点池为空，请检查 config.toml 与 .env 的密钥配置")

        last_error: Optional[BaseException] = None

        for index, endpoint in enumerate(self._endpoints):
            try:
                result = await self._attempt_with_retry(attempt, endpoint, operation)
                if index > 0:
                    logger.warning(f"[Fallback] {operation} 已降级至备用端点 {endpoint.name}")
                return result, endpoint
            except Exception as exc:  # noqa: BLE001 - 需要捕获所有失败以继续降级
                last_error = exc
                logger.error(
                    f"[Fallback] 端点 {endpoint.name} 连续失败，"
                    f"{'切换备用端点' if index + 1 < len(self._endpoints) else '降级链已耗尽'}: {exc}"
                )

        raise LLMUnavailableError(
            f"全部 {len(self._endpoints)} 个模型端点均不可用（{operation}）",
            context={"last_error": str(last_error)},
        ) from last_error

    async def _attempt_with_retry(
        self,
        attempt: Callable[[ResolvedEndpoint], Awaitable[T]],
        endpoint: ResolvedEndpoint,
        operation: str,
    ) -> T:
        """在单个端点内执行带指数退避的重试。"""
        async for retrying in AsyncRetrying(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=self._backoff_factor),
            retry=retry_if_exception_type(_RETRYABLE),
            reraise=True,
        ):
            with retrying:
                return await attempt(endpoint)
        # AsyncRetrying 在 reraise=True 时不会走到这里，仅为类型完整性保留
        raise LLMUnavailableError(f"{operation} 重试逻辑异常终止")
