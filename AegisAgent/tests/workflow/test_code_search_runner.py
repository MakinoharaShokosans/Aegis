"""代码检索子智能体强类型契约与有界执行循环测试 (code_search/contracts.py, runner.py, tool.py)。"""

from typing import Any, Dict, List, Mapping, Optional
from unittest.mock import AsyncMock
import pytest

from agent_runtime.config import CodeSearchConfig
from agent_runtime.prompt_loader import PromptLibrary
from agent_runtime.code_search.contracts import (
    CodeChunkEvidence,
    CodeSearchRequest,
    build_code_report,
)
from agent_runtime.code_search.runner import CodeSearchRunner
from agent_runtime.code_search.tool import DelegateCodeSearchTool, build_code_search_tool


# ==============================================================================
# 1. 强类型契约与位置白名单过滤测试 (contracts.py)
# ==============================================================================

def test_build_code_report_location_whitelist_and_sanitization():
    """测试 build_code_report 的位置白名单、长度截断与状态机净化。"""
    config = CodeSearchConfig(
        max_findings=3,
        max_answer_chars=100,
        max_code_snippets=2,
        max_code_chars=150,
        max_report_chars=2000,
    )
    # 真实召回的代码切片证据
    fetched = [
        CodeChunkEvidence(
            file_path="src/net/packet.c",
            start_line=10,
            end_line=40,
            scope="process_packet",
            content="int process_packet() { return 0; }",
        ),
        CodeChunkEvidence(
            file_path="src/include/packet.h",
            start_line=1,
            end_line=20,
            scope="struct packet",
            content="struct packet { int len; };",
        ),
    ]

    raw_json = {
        "status": "found",
        "findings": [
            # 1. 合法 finding（位置在白名单内）
            {
                "question": "函数 process_packet 的逻辑？",
                "answer": "处理网络数据包。" + "B" * 200,  # 测试超长截断
                "confidence": "high",
                "locations": ["src/net/packet.c:10-40"],
            },
            # 2. 伪造/幻觉位置（不在真实召回中，应被过滤）
            {
                "question": "虚构函数",
                "answer": "未经验证的推断",
                "confidence": "low",
                "locations": ["src/unrelated/fake.c:99-120"],
            },
        ],
        "code_snippets": [
            # 合法代码块
            {
                "file_path": "src/net/packet.c",
                "start_line": 10,
                "end_line": 40,
                "language": "c",
                "code": "int process_packet() { return 0; }",
            },
            # 伪造文件代码块（应被丢弃）
            {
                "file_path": "src/fake/evil.c",
                "start_line": 1,
                "end_line": 5,
                "language": "c",
                "code": "void evil() {}",
            },
        ],
        "unresolved": [],
    }

    report = build_code_report(
        raw_json,
        target="查找 packet 处理实现",
        fetched_evidence=fetched,
        attempted_queries=["packet.c", "process_packet"],
        config=config,
        rounds_used=1,
        total_tokens=100,
        elapsed_sec=1.5,
    )

    # 1. 验证 Findings 截断与位置白名单
    assert report.status == "found"
    assert len(report.findings) == 2
    assert len(report.findings[0].answer) <= 100
    assert report.findings[0].locations == ["src/net/packet.c:10-40"]
    assert report.findings[1].locations == []  # 伪造位置被清空

    # 2. 验证代码片段过滤与 display_only
    assert len(report.code_snippets) == 1
    assert report.code_snippets[0].file_path == "src/net/packet.c"
    assert report.code_snippets[0].display_only is True

    # 3. 验证渲染 Markdown 信封
    rendered = report.render_for_model(max_chars=2000)
    assert '<code_search_summary source="code_search" status="found" trust="trusted">' in rendered
    assert "</code_search_summary>" in rendered
    assert "src/net/packet.c:10-40" in rendered


# ==============================================================================
# 2. 有界执行循环与状态机测试 (runner.py)
# ==============================================================================

class MockRagTool:
    """测试用 Mock RAG 检索工具。"""

    def __init__(self, responses: Optional[Dict[str, List[Dict[str, Any]]]] = None):
        self.responses = responses or {}
        self.calls: List[str] = []

    async def search_chunks(
        self, query: str, *, top_k: int = 5, language: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        self.calls.append(query)
        return self.responses.get(query, [])


@pytest.mark.asyncio
async def test_code_search_runner_early_exit_on_sufficient(mock_gateway_factory):
    """测试 CodeSearchRunner 首轮命中后触发 Early Exit（早停）。"""
    # 模拟首轮规划返回检索词；第二轮评估返回 sufficient（早停）；提炼返回最终报告
    plan_resp = {"queries": ["process_packet"]}
    evaluate_resp = {"status": "sufficient", "queries": [], "reason": "已找到函数实现"}
    distill_resp = {
        "status": "found",
        "findings": [
            {
                "question": "函数实现",
                "answer": "在 packet.c 中实现",
                "confidence": "high",
                "locations": ["src/net/packet.c:10-40"],
            }
        ],
        "code_snippets": [
            {
                "file_path": "src/net/packet.c",
                "start_line": 10,
                "end_line": 40,
                "language": "c",
                "code": "int process_packet() {}",
            }
        ],
    }

    mock_gateway = mock_gateway_factory([plan_resp, evaluate_resp, distill_resp])
    mock_rag = MockRagTool(
        {
            "process_packet": [
                {
                    "file_path": "src/net/packet.c",
                    "start_line": 10,
                    "end_line": 40,
                    "enclosing_scope": "process_packet",
                    "content": "int process_packet() {}",
                }
            ]
        }
    )

    config = CodeSearchConfig(max_rounds=3, max_chunks_per_round=5)
    runner = CodeSearchRunner(
        gateway=mock_gateway,  # type: ignore[arg-type]
        rag_client_or_tool=mock_rag,
        prompts=PromptLibrary(),
        config=config,
    )

    req = CodeSearchRequest(target="查找 process_packet 实现")
    report = await runner.run(req)

    assert report.status == "found"
    assert len(report.findings) == 1
    assert report.rounds_used <= 2
    assert "process_packet" in report.attempted_queries


@pytest.mark.asyncio
async def test_code_search_runner_multi_round_query_reformulation(mock_gateway_factory):
    """测试 CodeSearchRunner 首轮未命中时自适应改词重搜（Multi-round Reformulation）。"""
    # 轮次 1: 规划 "packet_handler" -> 未中
    # 轮次 2: 评估 need_more，改词 "net_rx_action" -> 命中
    # 轮次 3: 评估 sufficient -> 早停
    plan_resp = {"queries": ["packet_handler"]}
    evaluate_round2 = {
        "status": "need_more",
        "queries": ["net_rx_action"],
        "reason": "首轮未找到符号，改搜底层入口",
    }
    evaluate_round3 = {"status": "sufficient", "queries": [], "reason": "已找到入口"}
    distill_resp = {
        "status": "found",
        "findings": [
            {
                "question": "网络收包入口",
                "answer": "net_rx_action 负责轮询",
                "confidence": "high",
                "locations": ["src/net/core.c:50-80"],
            }
        ],
    }

    mock_gateway = mock_gateway_factory([plan_resp, evaluate_round2, evaluate_round3, distill_resp])
    mock_rag = MockRagTool(
        {
            "packet_handler": [],  # 首轮无结果
            "net_rx_action": [     # 次轮命中
                {
                    "file_path": "src/net/core.c",
                    "start_line": 50,
                    "end_line": 80,
                    "enclosing_scope": "net_rx_action",
                    "content": "void net_rx_action() {}",
                }
            ],
        }
    )

    config = CodeSearchConfig(max_rounds=3)
    runner = CodeSearchRunner(
        gateway=mock_gateway,  # type: ignore[arg-type]
        rag_client_or_tool=mock_rag,
        prompts=PromptLibrary(),
        config=config,
    )

    req = CodeSearchRequest(target="查找收包逻辑")
    report = await runner.run(req)

    assert report.status == "found"
    assert len(report.findings) == 1
    assert "packet_handler" in report.attempted_queries
    assert "net_rx_action" in report.attempted_queries


@pytest.mark.asyncio
async def test_code_search_runner_not_found_fallback(mock_gateway_factory):
    """测试 CodeSearchRunner 3 轮无果时如实返回 not_found（确定性拒答）。"""
    plan_resp = {"queries": ["non_existent_func"]}
    evaluate_r2 = {"status": "need_more", "queries": ["fake_symbol_retry"]}
    evaluate_r3 = {"status": "need_more", "queries": ["final_attempt"]}

    mock_gateway = mock_gateway_factory([plan_resp, evaluate_r2, evaluate_r3])
    mock_rag = MockRagTool({})  # 全部未找到

    config = CodeSearchConfig(max_rounds=3)
    runner = CodeSearchRunner(
        gateway=mock_gateway,  # type: ignore[arg-type]
        rag_client_or_tool=mock_rag,
        prompts=PromptLibrary(),
        config=config,
    )

    req = CodeSearchRequest(target="查找不存在的模块")
    report = await runner.run(req)

    assert report.status == "not_found"
    assert len(report.findings) == 0
    assert "查找不存在的模块" in report.unresolved
    assert len(report.attempted_queries) == 3


# ==============================================================================
# 3. DelegateCodeSearchTool 工具适配器测试 (tool.py)
# ==============================================================================

@pytest.mark.asyncio
async def test_delegate_code_search_tool_invocation():
    """测试 DelegateCodeSearchTool 工具调用与降级表现。"""
    mock_runner = AsyncMock()
    mock_runner.run.return_value = build_code_report(
        {
            "status": "found",
            "findings": [
                {
                    "question": "Q1",
                    "answer": "A1",
                    "confidence": "high",
                    "locations": ["a.py:1-10"],
                }
            ],
        },
        target="测试目标",
        fetched_evidence=[CodeChunkEvidence(file_path="a.py", start_line=1, end_line=10, content="x=1")],
        attempted_queries=["a.py"],
        config=CodeSearchConfig(),
        rounds_used=1,
        total_tokens=50,
        elapsed_sec=1.0,
    )

    tool = DelegateCodeSearchTool(mock_runner, max_report_chars=2000)
    assert tool.trust == "trusted"
    assert tool.name == "delegate_code_search"

    # 1. 缺失 target -> 失败
    res_empty = await tool.invoke({})
    assert res_empty.ok is False
    assert "缺少 target 参数" in str(res_empty.content)

    # 2. 正常调用 -> 返回净化后的 Markdown 报告
    res_ok = await tool.invoke({"target": "测试目标", "questions": ["Q1"]})
    assert res_ok.ok is True
    assert '<code_search_summary source="code_search"' in res_ok.content
    assert "A1" in res_ok.content
