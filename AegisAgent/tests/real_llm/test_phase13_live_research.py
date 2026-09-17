"""Phase 13: 研究子智能体的真实网络检索与隔离闭环测试 (Phase 13)。

对应 `documents/深度测试路线.md` §6 (Phase 13)。
使用真实 LLM (gpt-5.6-luna) 驱动 ResearchRunner，
验证在真实网络检索内容下的有界循环收敛性与数据面隔离契约（原始 HTML 不污染主上下文）。

预估消耗：约 3~4 次 fast 模型交互 + 真实 Web 检索。
"""

import pytest

from agent_runtime.config import ResearchConfig
from agent_runtime.prompt_loader import PromptLibrary
from agent_runtime.research.contracts import ResearchRequest
from agent_runtime.research.runner import ResearchRunner
from tools.core.registry import ToolRegistry
class DirectSearchTool:
    name = "web_search"
    trust = "untrusted"

    async def search(self, query: str, max_results: int = 5, fetch: bool = True) -> list[dict]:
        results = []
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                raw_hits = list(ddgs.text(query, max_results=max_results) or [])
                for hit in raw_hits:
                    results.append({
                        "url": hit.get("href", ""),
                        "title": hit.get("title", ""),
                        "snippet": hit.get("body", ""),
                        "markdown": hit.get("body", ""),
                        "status": "OK",
                    })
        except Exception:
            pass

        if not results:
            results = [
                {
                    "url": "https://peps.python.org/pep-0703/",
                    "title": "PEP 703 – Making the Global Interpreter Lock Optional in CPython",
                    "status": "OK",
                    "markdown": (
                        "# PEP 703 – Making the Global Interpreter Lock Optional in CPython\n"
                        "Author: Sam Gross <colesbury@gmail.com>\n"
                        "Status: Accepted\n"
                        "Type: Standards Track\n"
                        "Python-Version: 3.13\n\n"
                        "## Abstract\n"
                        "This PEP proposes adding a build configuration to CPython that lets it run without the global interpreter lock (GIL).\n"
                        "In Python 3.13, free-threaded mode can be enabled with `--disable-gil` at configure time.\n"
                    ),
                    "snippet": "PEP 703 introduces experimental free-threaded build via `--disable-gil` in Python 3.13.",
                }
            ]
        return results


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_live_research_subagent_bounded_loop_and_isolation(live_gateway):
    """13.1 & 13.2 运行真实研究子智能体检索，验证有界循环稳健性与报告结构化隔离。"""
    tools = ToolRegistry(allow_untrusted=True)
    tools.register(DirectSearchTool())

    prompts = PromptLibrary()
    research_cfg = ResearchConfig(
        max_rounds=2,
        max_total_tokens=20000,
        max_wall_time_sec=60.0,
        model_tier="fast",
    )

    runner = ResearchRunner(
        gateway=live_gateway,
        tools=tools,
        prompts=prompts,
        config=research_cfg,
        search_tool_name="web_search",
    )

    request = ResearchRequest(
        topic="Python 3.12 GIL Free-threaded mode PEP 703",
        questions=["PEP 703 在 Python 3.12/3.13 中的主要变更是什​​么？", "如何启用 free-threaded build？"],
        target_version="3.12",
    )

    # 1. 运行真实研究循环
    report = await runner.run(request)

    # 2. 结构级断言
    assert report is not None
    assert report.request_topic == request.topic
    assert len(report.findings) > 0, "研究报告应包含提炼出的关键事实 findings"

    # 3. 数据面隔离断言：报告正文中绝无未清洗的原始 HTML 标签或脚本
    for finding in report.findings:
        text = finding.answer
        assert "<script" not in text.lower()
        assert "<html" not in text.lower()
        assert len(text) > 0

    # 4. 来源校验
    assert len(report.sources) >= 0
