"""研究子智能体强类型契约与有界执行循环测试 (research/contracts.py, runner.py, tool.py)。"""

from typing import Any, Dict, List, Mapping, Optional
from unittest.mock import AsyncMock
import pytest

from agent_runtime.config import ResearchConfig
from agent_runtime.llm.client import LLMResponse
from agent_runtime.prompt_loader import PromptLibrary
from agent_runtime.research.contracts import (
    VERSION_PATTERN,
    ResearchRequest,
    ResearchSource,
    build_report,
)
from agent_runtime.research.runner import ResearchRunner
from agent_runtime.research.tool import DelegateResearchTool, build_research_tool
from tools.core.registry import ToolRegistry


# ==============================================================================
# 1. 强类型契约与静态防护测试 (contracts.py)
# ==============================================================================

def test_version_pattern():
    """测试 semver 风格版本号正则校验。"""
    valid_versions = ["1.0", "1.2.3", "6.1.0-rc1", "2.0.0+build5", "0.19.0.beta"]
    for v in valid_versions:
        assert VERSION_PATTERN.match(v) is not None, f"Failed on {v}"

    invalid_versions = [
        "latest",
        "version 1.0",
        "1.0.0; rm -rf /",
        "https://evil.com",
        "v1.0.0",  # 必须以数字开头
    ]
    for v in invalid_versions:
        assert VERSION_PATTERN.match(v) is None, f"Should reject {v}"


def test_build_report_url_whitelist_and_sanitization():
    """测试 build_report 的四道安全过滤：URL 白名单、版本正则、长度截断与注入标注。"""
    config = ResearchConfig(
        max_findings=3,
        max_answer_chars=100,
        max_code_examples=2,
        max_code_chars=150,
        max_report_chars=2000,
    )
    # 真实抓取的来源白名单
    fetched = [
        ResearchSource(url="https://docs.python.org/3/lib.html", title="Python Docs"),
        ResearchSource(url="https://github.com/fastapi/fastapi", title="FastAPI Repo"),
    ]

    raw_json = {
        "findings": [
            # 1. 合法 finding（来源在白名单内）
            {
                "question": "FastAPI 如何启动？",
                "answer": "使用 uvicorn main:app 启动。" + "A" * 200,  # 测试超长截断
                "confidence": "high",
                "sources": ["https://github.com/fastapi/fastapi"],
            },
            # 2. 伪造/幻觉来源（不在白名单内，应被剔除来源）
            {
                "question": "恶意或幻觉来源",
                "answer": "一条结论",
                "sources": ["https://phishing-site.com/evil"],
            },
        ],
        "version_facts": [
            # 合法版本
            {"component": "fastapi", "version": "0.110.0", "source_url": "https://github.com/fastapi/fastapi"},
            # 格式不合规或伪造来源（应被丢弃）
            {"component": "python", "version": "latest", "source_url": "https://docs.python.org/3/lib.html"},
            {"component": "redis", "version": "7.0.0", "source_url": "https://unverified.org"},
        ],
        "code_examples": [
            {
                "language": "python",
                "code": "import fastapi\napp = fastapi.FastAPI()",
                "source_url": "https://github.com/fastapi/fastapi",
            },
            # 缺少白名单来源（应被丢弃）
            {
                "language": "bash",
                "code": "rm -rf /",
                "source_url": "https://unknown.com",
            },
        ],
    }

    report = build_report(
        raw_json,
        topic="FastAPI 测试",
        fetched=fetched,
        config=config,
        rounds_used=1,
        total_tokens=100,
        elapsed_sec=2.0,
    )

    # 1. 验证 Findings 截断与来源过滤
    assert len(report.findings) == 2
    assert len(report.findings[0].answer) <= 100
    assert report.findings[0].sources == ["https://github.com/fastapi/fastapi"]
    assert report.findings[1].sources == []  # 伪造来源被清空

    # 2. 验证版本事实过滤（仅保留 1 条合规记录）
    assert len(report.version_facts) == 1
    assert report.version_facts[0].component == "fastapi"
    assert report.version_facts[0].version == "0.110.0"

    # 3. 验证代码示例过滤与 display_only 不变式
    assert len(report.code_examples) == 1
    assert report.code_examples[0].display_only is True

    # 4. 验证渲染文本包含 untrusted 外部信封
    rendered = report.render_for_model(max_chars=2000)
    assert '<external_content source="research" trust="untrusted"' in rendered
    assert "</external_content>" in rendered
    assert "uvicorn main:app" in rendered


# ==============================================================================
# 2. 有界执行循环测试 (runner.py)
# ==============================================================================

class MockSearchTool:
    """测试用 Mock 结构化检索工具。"""

    def __init__(self, items: Optional[List[Dict[str, Any]]] = None):
        self.name = "web_search"
        self.trust = "untrusted"
        self.items = items or [
            {
                "url": "https://docs.python.org/3/",
                "title": "Python Documentation",
                "markdown": "Python is a programming language...",
                "status": "OK",
            }
        ]

    async def search(self, query: str, *, max_results: Optional[int] = None, fetch: bool = True) -> List[Dict[str, Any]]:
        return self.items


@pytest.mark.asyncio
async def test_research_runner_bounded_loop(mock_gateway_factory):
    """测试 ResearchRunner 规划 -> 检索 -> 提炼两阶段有界闭环。"""
    # 模拟两轮响应：1. 规划检索词；2. 提炼结构化结论
    plan_resp = {"queries": ["python async io guide"]}
    distill_resp = {
        "findings": [
            {
                "question": "Python 异步原理？",
                "answer": "通过 asyncio 事件循环与协程实现。",
                "confidence": "high",
                "sources": ["https://docs.python.org/3/"],
            }
        ],
        "version_facts": [{"component": "python", "version": "3.12.0", "source_url": "https://docs.python.org/3/"}],
    }

    mock_gateway = mock_gateway_factory([plan_resp, {"queries": []}, distill_resp])
    tools = ToolRegistry(allow_untrusted=True)
    tools.register(MockSearchTool())

    config = ResearchConfig(
        enabled=True,
        max_rounds=2,
        max_sources=3,
        max_total_tokens=5000,
        max_wall_time_sec=10.0,
    )
    runner = ResearchRunner(
        gateway=mock_gateway,  # type: ignore[arg-type]
        tools=tools,
        prompts=PromptLibrary(),
        config=config,
    )

    req = ResearchRequest(topic="Python Async", questions=["Python 异步原理？"])
    report = await runner.run(req)

    assert report.is_empty is False
    assert len(report.findings) == 1
    assert report.findings[0].question == "Python 异步原理？"
    assert report.rounds_used >= 1


# ==============================================================================
# 3. DelegateResearchTool 工具适配器测试 (tool.py)
# ==============================================================================

@pytest.mark.asyncio
async def test_delegate_research_tool_invocation():
    """测试 DelegateResearchTool 包装输入、调用 runner 与生成 ToolResult。"""
    mock_runner = AsyncMock()
    mock_runner.run.return_value = build_report(
        {
            "findings": [
                {
                    "question": "Q1",
                    "answer": "A1",
                    "confidence": "high",
                    "sources": ["https://trusted.org"],
                }
            ]
        },
        topic="Test",
        fetched=[ResearchSource(url="https://trusted.org", title="T")],
        config=ResearchConfig(),
        rounds_used=1,
        total_tokens=50,
        elapsed_sec=1.0,
    )

    tool = DelegateResearchTool(mock_runner, max_report_chars=2000)
    assert tool.trust == "trusted"
    assert tool.name == "delegate_research"

    # 1. 缺失 topic -> 失败
    res_empty = await tool.invoke({})
    assert res_empty.ok is False
    assert "缺少 topic 参数" in str(res_empty.content)

    # 2. 正常调用 -> 返回净化后的 Markdown 报告
    res_ok = await tool.invoke({"topic": "Test Topic", "questions": ["Q1"]})
    assert res_ok.ok is True
    assert '<external_content source="research"' in res_ok.content
    assert "A1" in res_ok.content
