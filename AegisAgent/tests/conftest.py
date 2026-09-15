"""共享 pytest fixture：临时环境、测试配置与 Mock LLMGateway。"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
import pytest
from langchain_core.messages import BaseMessage

from agent_runtime.config import (
    AegisConfig,
    ContextConfig,
    GuardrailsConfig,
    MCPConfig,
    ModelsConfig,
    ModelTierConfig,
    RetryConfig,
    RuntimeConfig,
    ServerConfig,
    ServicesConfig,
    StorageConfig,
)
from agent_runtime.llm.client import LLMResponse, ModelTier


class MockLLMGateway:
    """测试用 Mock 大模型网关。"""

    def __init__(self, responses: Optional[Sequence[Any]] = None) -> None:
        self.responses: List[Any] = list(responses or [])
        self.calls: List[Dict[str, Any]] = []

    def set_responses(self, responses: Sequence[Any]) -> None:
        """重设预设响应列表。"""
        self.responses = list(responses)

    async def invoke(
        self,
        tier: ModelTier,
        messages: Sequence[BaseMessage],
        *,
        tools: Optional[Sequence[Dict[str, Any]]] = None,
        force_json: bool = False,
    ) -> LLMResponse:
        """录制调用并返回预设响应。"""
        self.calls.append({
            "tier": tier,
            "messages": list(messages),
            "tools": list(tools) if tools else None,
            "force_json": force_json,
        })
        if self.responses:
            next_resp = self.responses.pop(0)
            if isinstance(next_resp, Exception):
                raise next_resp
            if isinstance(next_resp, LLMResponse):
                return next_resp
            if isinstance(next_resp, str):
                return LLMResponse(content=next_resp, total_tokens=10, endpoint_name="mock-endpoint")
            if isinstance(next_resp, dict):
                import json
                return LLMResponse(
                    content=json.dumps(next_resp, ensure_ascii=False),
                    total_tokens=10,
                    endpoint_name="mock-endpoint",
                )
        return LLMResponse(content="{}", total_tokens=5, endpoint_name="mock-default")


@pytest.fixture
def mock_gateway_factory():
    """工厂 fixture：快速构造 MockLLMGateway。"""
    def _factory(responses: Optional[Sequence[Any]] = None) -> MockLLMGateway:
        return MockLLMGateway(responses)
    return _factory


@pytest.fixture
def test_config(tmp_path: Path) -> AegisConfig:
    """生成指向 tmp_path 隔离目录的测试用 AegisConfig。"""
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    traces_dir = tmp_path / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)

    runtime_cfg = RuntimeConfig(
        guardrails=GuardrailsConfig(
            max_steps=10,
            max_total_tokens=50000,
            max_wall_time_sec=60.0,
            consecutive_errors_limit=3,
            identical_fingerprint_limit=3,
        ),
        retry=RetryConfig(max_retries=1, backoff_factor=1.0),
        context=ContextConfig(
            session_token_limit=8000,
            compaction_high_watermark=0.8,
            compaction_ratio=0.4,
            active_window_turns=2,
            compaction_trigger_turns=5,
            max_observation_tokens=500,
            observation_head_lines=10,
            observation_tail_lines=15,
        ),
        storage=StorageConfig(
            checkpoint_db_path=str(storage_dir / "test_checkpoint.db"),
            metadata_db_path=str(storage_dir / "test_meta.db"),
            traces_dir=str(traces_dir),
            artifacts_dir=str(artifacts_dir),
        ),
    )

    return AegisConfig(
        runtime=runtime_cfg,
        models=ModelsConfig(
            reasoning=ModelTierConfig(temperature=0.0, endpoints=[]),
            fast=ModelTierConfig(temperature=0.0, endpoints=[]),
        ),
        server=ServerConfig(
            host="127.0.0.1",
            port=8000,
            max_concurrent_tasks=2,
            cors_allow_origins=["http://localhost:3000"],
            sse_heartbeat_sec=1.0,
            sse_buffer_events=100,
            artifact_preview_chars=100,
        ),
        services=ServicesConfig(
            rag_url="http://127.0.0.1:8001",
            shell_url="http://127.0.0.1:8002",
            web_url="http://127.0.0.1:8003",
            timeout_sec=5.0,
        ),
        mcp=MCPConfig(enabled=False, servers={}),
    )
