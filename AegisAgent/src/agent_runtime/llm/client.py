"""LLM 统一门面：双模型分层 + 自动降级。

调用方（节点）只需要 ``await gateway.invoke(tier="reasoning", messages=...)``，
不用关心：有几个端点、密钥从哪来、失败如何重试、何时切换备用。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence

import openai
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from loguru import logger

from agent_runtime.llm.endpoints import EndpointPool
from agent_runtime.llm.fallback import FallbackChain

__all__ = ["LLMGateway", "LLMResponse", "ModelTier"]

ModelTier = Literal["reasoning", "fast"]


@dataclass(slots=True)
class LLMResponse:
    """一次模型调用的规范化结果。

    Attributes:
        content: 文本内容。
        tool_calls: 规范化的工具调用列表，元素形如 ``{"id","name","args"}``。
        total_tokens: 本次调用消耗的 Token（用于物理预算累加）。
        endpoint_name: 实际命中的端点名（用于观测与降级统计）。
        finish_reason: 结束原因。
    """

    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    endpoint_name: str = ""
    finish_reason: str = ""

    @property
    def has_tool_calls(self) -> bool:
        """是否包含工具调用。"""
        return bool(self.tool_calls)


def _to_openai_messages(messages: Sequence[BaseMessage]) -> List[Dict[str, Any]]:
    """把 LangChain 消息转换为 OpenAI 兼容的请求体。

    手写转换而不依赖框架工具函数，是为了让"线上协议格式"显式可见、
    不受 LangChain 版本变更影响。

    Args:
        messages: LangChain 消息序列。

    Returns:
        OpenAI ``messages`` 数组。
    """
    converted: List[Dict[str, Any]] = []
    for message in messages:
        if isinstance(message, SystemMessage):
            converted.append({"role": "system", "content": _as_text(message.content)})
        elif isinstance(message, HumanMessage):
            converted.append({"role": "user", "content": _as_text(message.content)})
        elif isinstance(message, ToolMessage):
            converted.append(
                {
                    "role": "tool",
                    "content": _as_text(message.content),
                    "tool_call_id": message.tool_call_id,
                }
            )
        elif isinstance(message, AIMessage):
            content_str = _as_text(message.content) if message.content is not None else ""
            item: Dict[str, Any] = {
                "role": "assistant",
                "content": content_str,
            }
            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                item["tool_calls"] = [
                    {
                        "id": call.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": call.get("name", ""),
                            # OpenAI 要求 arguments 是 JSON **字符串**
                            "arguments": json.dumps(call.get("args", {}), ensure_ascii=False),
                        },
                    }
                    for call in tool_calls
                ]
            converted.append(item)
        else:
            # 兜底：未知消息类型按用户消息处理，避免整轮请求失败
            converted.append({"role": "user", "content": _as_text(message.content)})
    return converted


def _as_text(content: Any) -> str:
    """把消息内容（可能是多模态分片列表）压平为纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for chunk in content:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, Mapping) and "text" in chunk:
                parts.append(str(chunk["text"]))
        return "\n".join(parts)
    return str(content)


def _normalize_tool_calls(raw_tool_calls: Any) -> List[Dict[str, Any]]:
    """把端点返回的 tool_calls 规范化为 ``{"id","name","args"}``。

    不同厂商的参数可能是 JSON 字符串、dict 或 None，统一在此收敛。
    """
    normalized: List[Dict[str, Any]] = []
    for call in raw_tool_calls or []:
        function = getattr(call, "function", None)
        if function is None:
            continue
        raw_args = getattr(function, "arguments", None)
        if isinstance(raw_args, Mapping):
            args: Dict[str, Any] = dict(raw_args)
        else:
            try:
                args = json.loads(raw_args) if raw_args else {}
            except (ValueError, TypeError):
                # 参数不是合法 JSON 时保留原文，让模型在下一轮自我修正
                args = {"_raw": raw_args}
        normalized.append(
            {
                "id": getattr(call, "id", ""),
                "name": getattr(function, "name", ""),
                "args": args,
            }
        )
    return normalized


class LLMGateway:
    """双模型分层网关。

    Args:
        reasoning_pool: reasoning 层端点池。
        fast_pool: fast 层端点池。
        max_retries: 单端点最大尝试次数。
        backoff_factor: 指数退避倍数。
    """

    __slots__ = ("_pools", "_chains")

    def __init__(
        self,
        reasoning_pool: EndpointPool,
        fast_pool: EndpointPool,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ) -> None:
        self._pools: Dict[str, EndpointPool] = {
            "reasoning": reasoning_pool,
            "fast": fast_pool,
        }
        self._chains: Dict[str, FallbackChain] = {
            tier: FallbackChain(pool.endpoints, max_retries, backoff_factor)
            for tier, pool in self._pools.items()
        }

    @classmethod
    def from_config(cls, models_config: Any, retry_config: Any) -> "LLMGateway":
        """从 ``config.models`` 与 ``config.runtime.retry`` 构造网关。

        Args:
            models_config: ``config.models``。
            retry_config: ``config.runtime.retry``。

        Returns:
            网关实例。
        """
        return cls(
            reasoning_pool=EndpointPool(models_config.reasoning, "reasoning"),
            fast_pool=EndpointPool(models_config.fast, "fast"),
            max_retries=retry_config.max_retries,
            backoff_factor=retry_config.backoff_factor,
        )

    def has_endpoints(self, tier: ModelTier) -> bool:
        """该层级是否至少有一个可用端点。"""
        return bool(self._pools[tier].endpoints)

    async def invoke(
        self,
        tier: ModelTier,
        messages: Sequence[BaseMessage],
        *,
        tools: Optional[Sequence[Mapping[str, Any]]] = None,
        force_json: bool = False,
    ) -> LLMResponse:
        """调用指定层级的模型。

        Args:
            tier: ``"reasoning"`` 或 ``"fast"``。
            messages: LangChain 消息序列。
            tools: OpenAI function calling 定义列表（可选）。
            force_json: 是否强制 JSON 输出（用于记忆压缩等结构化场景）。

        Returns:
            :class:`LLMResponse`。

        Raises:
            LLMUnavailableError: 降级链耗尽。
        """
        pool = self._pools[tier]
        chain = self._chains[tier]
        temperature = pool.temperature
        payload_messages = _to_openai_messages(messages)

        async def attempt(endpoint: Any) -> LLMResponse:
            client = openai.AsyncOpenAI(
                base_url=endpoint.base_url,
                api_key=endpoint.api_key,
                timeout=endpoint.timeout_sec,
            )
            kwargs: Dict[str, Any] = {
                "model": endpoint.model,
                "temperature": temperature,
                "messages": payload_messages,
            }
            if tools:
                kwargs["tools"] = list(tools)
            if force_json:
                kwargs["response_format"] = {"type": "json_object"}

            completion = await client.chat.completions.create(**kwargs)
            choice = completion.choices[0]
            usage = getattr(completion, "usage", None)
            return LLMResponse(
                content=choice.message.content or "",
                tool_calls=_normalize_tool_calls(getattr(choice.message, "tool_calls", None)),
                total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
                endpoint_name=endpoint.name,
                finish_reason=getattr(choice, "finish_reason", "") or "",
            )

        response, endpoint = await chain.execute(attempt, operation=f"invoke[{tier}]")
        logger.debug(
            f"[LLMGateway] tier={tier} endpoint={endpoint.name} "
            f"tokens={response.total_tokens} tool_calls={len(response.tool_calls)}"
        )
        return response
