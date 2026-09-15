"""模型端点解析与凭据注入。

对应 ``documents/agent_runtime/05_guardrails_implementation.md`` §3。

**凭据规则**（安全架构的一部分）：
``config.toml`` 入版本库，只写环境变量**名**（``api_key_env``）；真实密钥一律来自
``.env``。本模块负责把"环境变量名"解析成"真实密钥"，并对以下两种情况做处理：

1. **本地端点**（``localhost`` / ``127.0.0.1``）：密钥缺失时回填 ``EMPTY``，
   因为 Ollama 等本地服务不校验鉴权；
2. **云端端点**：密钥缺失时**跳过**该端点并告警——带着空密钥去请求只会拿到 401，
   白白浪费一次重试与超时预算。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, List

from loguru import logger

__all__ = ["EndpointPool", "ResolvedEndpoint"]

#: 视为"本地端点、无需鉴权"的主机名
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1")


@dataclass(frozen=True, slots=True)
class ResolvedEndpoint:
    """解析完成、可直接用于建连的端点。

    Attributes:
        name: 端点可读标识（用于日志与观测）。
        base_url: OpenAI 兼容接口基址。
        model: 模型代号。
        api_key: 已解析的真实密钥。
        timeout_sec: 单次请求超时。
    """

    name: str
    base_url: str
    model: str
    api_key: str
    timeout_sec: float


class EndpointPool:
    """单个模型层级（reasoning / fast）的端点池。

    Args:
        tier_config: ``config.models.reasoning`` 或 ``config.models.fast``。
        tier_name: 层级名，仅用于日志。
    """

    __slots__ = ("_config", "_tier_name", "_resolved")

    def __init__(self, tier_config: Any, tier_name: str) -> None:
        self._config = tier_config
        self._tier_name = tier_name
        self._resolved: List[ResolvedEndpoint] = []
        self._resolve()

    @property
    def temperature(self) -> float:
        """该层级的采样温度。"""
        return float(getattr(self._config, "temperature", 0.0))

    @property
    def endpoints(self) -> List[ResolvedEndpoint]:
        """可用端点列表（按声明顺序即为降级顺序）。"""
        return list(self._resolved)

    def _resolve(self) -> None:
        """把配置端点逐个解析为可用端点。"""
        for endpoint in getattr(self._config, "endpoints", []) or []:
            api_key = os.getenv(endpoint.api_key_env, "").strip()
            is_local = any(host in endpoint.base_url for host in _LOCAL_HOSTS)

            if not api_key:
                if is_local:
                    api_key = "EMPTY"
                    logger.debug(
                        f"[EndpointPool:{self._tier_name}] 本地端点 {endpoint.name} 未配置密钥，使用 EMPTY"
                    )
                else:
                    logger.warning(
                        f"[EndpointPool:{self._tier_name}] 跳过云端端点 {endpoint.name}："
                        f"环境变量 {endpoint.api_key_env} 未设置"
                    )
                    continue

            self._resolved.append(
                ResolvedEndpoint(
                    name=endpoint.name,
                    base_url=endpoint.base_url,
                    model=endpoint.model,
                    api_key=api_key,
                    timeout_sec=float(endpoint.timeout_sec),
                )
            )

        if not self._resolved:
            logger.error(f"[EndpointPool:{self._tier_name}] 没有任何可用端点，模型调用将直接失败")
