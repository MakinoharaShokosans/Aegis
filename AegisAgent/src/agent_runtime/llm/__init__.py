"""双模型分层 LLM 网关。

把"调用大模型"这件事收敛到一个入口，让节点层完全不知道
端点数量、重试策略、降级链与鉴权细节：

* :mod:`~agent_runtime.llm.endpoints` —— 端点解析与凭据注入
* :mod:`~agent_runtime.llm.fallback`  —— 端点内指数退避 + 跨端点降级
* :mod:`~agent_runtime.llm.client`    —— 对外统一门面 :class:`LLMGateway`
"""

from agent_runtime.llm.client import LLMGateway, LLMResponse
from agent_runtime.llm.endpoints import EndpointPool, ResolvedEndpoint
from agent_runtime.llm.fallback import FallbackChain

__all__ = [
    "EndpointPool",
    "FallbackChain",
    "LLMGateway",
    "LLMResponse",
    "ResolvedEndpoint",
]
