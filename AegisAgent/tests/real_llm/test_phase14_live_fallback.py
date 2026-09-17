"""Phase 14: 真实网络下的 FallbackChain 跨端点透明降级与成本对账 (Phase 14)。

对应 `documents/深度测试路线.md` §7 (Phase 14)。
配置首选必定连不上的哨兵端点 + 真实备用 OpenLux 端点，
验证在真实网络连接失败时，客户端透明切至备用端点并保持载荷完整完成真实请求。

预估消耗：约 2 次 fast 模型交互。
"""

import os
import pytest
from langchain_core.messages import HumanMessage

from agent_runtime.config import ModelEndpoint, ModelsConfig, ModelTierConfig, RetryConfig
from agent_runtime.llm.client import LLMGateway


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_live_fallback_chain_transparent_failover():
    """14.1 构造故障哨兵端点 + 真实端点，验证遭遇真实连接失败时透明降级至备用端点。"""
    luna_key = os.getenv("LUNA_KEY", "")

    # 1. 构造包含两个端点的 fast tier 配置：
    # 端点 1：必定超时的哨兵黑洞地址（短超时，快速失败）
    # 端点 2：真实 OpenLux 端点
    sentinel_endpoint = ModelEndpoint(
        name="sentinel-unreachable",
        base_url="https://127.0.0.1:59999/v1",
        model="unreachable-model",
        api_key_env="LUNA_KEY",
        timeout_sec=1.5,
    )
    real_endpoint = ModelEndpoint(
        name="real-openlux-mini",
        base_url="https://api.openlux.ai/v1",
        model="gpt-5.4-mini",
        api_key_env="LUNA_KEY",
        timeout_sec=30.0,
    )

    models_cfg = ModelsConfig(
        reasoning=ModelTierConfig(endpoints=[real_endpoint]),
        fast=ModelTierConfig(endpoints=[sentinel_endpoint, real_endpoint]),
    )
    retry_cfg = RetryConfig(max_retries=1, backoff_factor=0.5)

    gateway = LLMGateway.from_config(models_cfg, retry_cfg)

    # 2. 发起调用
    response = await gateway.invoke(
        tier="fast",
        messages=[HumanMessage(content="请回复一个单词：PONG")],
    )

    # 3. 验证透明切换到第二端点且执行成功
    assert response.content, "降级后应成功获取模型回复"
    assert response.endpoint_name == "real-openlux-mini", f"预期命中备用真实端点，实际命中: {response.endpoint_name}"
    assert response.total_tokens > 0, "真实 Token 消耗应大于 0"
