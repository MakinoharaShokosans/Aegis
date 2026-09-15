"""Web 搜索配置装配与提供商名称规范化单元测试。"""

from pathlib import Path
import pytest
from pydantic import ValidationError

from services.web_search.settings import (
    PROVIDER_DDG,
    WebSearchSettings,
    normalize_provider_name,
)


def test_normalize_provider_name():
    """测试搜索源名称别名识别与大小写容错。"""
    assert normalize_provider_name("ddg") == PROVIDER_DDG
    assert normalize_provider_name("DDG") == PROVIDER_DDG
    assert normalize_provider_name("DuckDuckGo") == PROVIDER_DDG
    assert normalize_provider_name("  duckduckgo_search  ") == PROVIDER_DDG

    with pytest.raises(ValueError, match="不支持的搜索源"):
        normalize_provider_name("tavily")

    with pytest.raises(ValueError, match="不支持的搜索源"):
        normalize_provider_name("google")

    with pytest.raises(ValueError):
        normalize_provider_name("")


def test_web_search_settings_validation():
    """测试 WebSearchSettings 字段强类型校验与属性计算。"""
    raw_data = {
        "host": "127.0.0.1",
        "port": 8003,
        "provider": "DuckDuckGo",
        "max_results": 10,
        "fetch_concurrency": 3,
        "request_timeout_sec": 8.0,
        "total_timeout_sec": 15.0,
        "max_content_tokens": 1200,
        "preview_chars": 600,
        "user_agent": "AegisAgent/1.0",
        "artifacts_dir": "/tmp/aegis_artifacts",
    }

    settings = WebSearchSettings(**raw_data)
    # provider 自动规整为 ddg
    assert settings.provider == "ddg"
    assert settings.port == 8003
    # 未指定 user_agents 时退化为单项元组
    assert settings.user_agent_pool == ("AegisAgent/1.0",)

    # 端口越界测试
    with pytest.raises(ValidationError):
        WebSearchSettings(**{**raw_data, "port": 70000})

    # 超时 <= 0 测试
    with pytest.raises(ValidationError):
        WebSearchSettings(**{**raw_data, "request_timeout_sec": 0})
