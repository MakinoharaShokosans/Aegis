"""Agent HTTP API 接入层（唯一用户入口）。

契约见 ``documents/agent_runtime/11_http_api.md``。

**分层纪律**：本包是**交付层**，只做三件事——
① 请求/响应格式转换（DTO ↔ 领域模型）；② 鉴权与安全策略；③ 把领域异常映射为 HTTP 状态码。
业务逻辑一律下沉到 ``workflow`` / ``memory`` / ``tools``，本包不得包含编排决策。
"""

from agent_runtime.api.app import create_app

__all__ = ["create_app"]
