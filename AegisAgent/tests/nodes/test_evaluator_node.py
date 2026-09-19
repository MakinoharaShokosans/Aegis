"""``evaluator`` 节点单元测试。"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agent_runtime.llm.client import LLMResponse
from agent_runtime.nodes.evaluator import build_evaluator_node
from agent_runtime.state import Milestone


@pytest.fixture
def mock_gateway():
    gateway = MagicMock()
    gateway.invoke = AsyncMock()
    return gateway


@pytest.fixture
def mock_context():
    context = MagicMock()
    context.assemble = MagicMock(return_value=[{"role": "user", "content": "test"}])
    return context


@pytest.fixture
def mock_prompts():
    prompts = MagicMock()
    prompts.load = MagicMock(return_value="evaluator prompt")
    return prompts


@pytest.mark.asyncio
async def test_evaluator_standard_acceptance(mock_gateway, mock_context, mock_prompts):
    """测试标准 JSON 验收通过流程。"""
    mock_gateway.invoke.return_value = LLMResponse(
        content=json.dumps({
            "milestone_ok": True,
            "all_completed": True,
            "summary": "任务全部圆满完成",
            "confirmed_facts": ["已验证文件完整性"],
        }),
        endpoint_name="test-model",
        total_tokens=150,
        finish_reason="stop",
    )

    evaluator_node = build_evaluator_node(mock_gateway, mock_context, mock_prompts)
    state = {
        "step_count": 1,
        "total_tokens": 100,
        "milestones": [Milestone(id=1, title="M1", status="completed")],
        "current_milestone_idx": 0,
        "messages": [
            HumanMessage(content="列出工作区文件"),
            AIMessage(content="工作区包含 3 个文件：a.py, b.py, c.py"),
        ],
    }

    result = await evaluator_node(state)
    assert result["should_terminate"] is True
    assert result["milestones"][0].status == "completed"
    assert "已验证文件完整性" in result["confirmed_facts"]
    assert result["rolling_summary"] == "任务全部圆满完成"
    # 当已有 direct_reply 时，msg_updates 为空避免多余噪音
    assert result["messages"] == []


@pytest.mark.asyncio
async def test_evaluator_standard_rejection(mock_gateway, mock_context, mock_prompts):
    """测试标准打回流程。"""
    mock_gateway.invoke.return_value = LLMResponse(
        content=json.dumps({
            "milestone_ok": False,
            "all_completed": False,
            "summary": "用户要求将结果写入文件，当前未落盘，请执行写入",
        }),
        endpoint_name="test-model",
        total_tokens=120,
        finish_reason="stop",
    )

    evaluator_node = build_evaluator_node(mock_gateway, mock_context, mock_prompts)
    state = {
        "step_count": 2,
        "total_tokens": 200,
        "milestones": [Milestone(id=1, title="M1", status="pending")],
        "current_milestone_idx": 0,
        "messages": [
            HumanMessage(content="调研并写入到原神.md"),
            AIMessage(content="原神最新版本为 5.4"),
        ],
    }

    result = await evaluator_node(state)
    assert result["should_terminate"] is False
    assert result["milestones"][0].status == "pending"
    assert len(result["messages"]) == 1
    assert "【阶段验收未通过，需要继续推进】" in result["messages"][0].content


@pytest.mark.asyncio
async def test_evaluator_schema_drift_business_payload_auto_acceptance(
    mock_gateway, mock_context, mock_prompts
):
    """测试当模型发生 Schema 漂移返回业务载荷（如 files 列表）时的智能兼容放行。"""
    # 模拟真实日志中出现的 Evaluator 漂移输出：输出了工作区文件字典而不是顶层 milestone_ok
    drift_payload = {
        "workspace": "EyesPro",
        "files": [
            {"path": "index.html", "responsibility": "前端可视化页面"},
            {"path": "原神.md", "responsibility": "原神最新版本更新资讯"},
            {"path": "delta_force.md", "responsibility": "三角洲行动最新赛季"},
        ],
    }
    mock_gateway.invoke.return_value = LLMResponse(
        content=json.dumps(drift_payload),
        endpoint_name="test-model",
        total_tokens=200,
        finish_reason="stop",
    )

    evaluator_node = build_evaluator_node(mock_gateway, mock_context, mock_prompts)
    state = {
        "step_count": 4,
        "total_tokens": 500,
        "milestones": [Milestone(id=1, title="M1", status="completed")],
        "current_milestone_idx": 0,
        "messages": [
            HumanMessage(content="此工作区有哪些文件？分别负责了什么？"),
            AIMessage(content="### 工作区文件职责\n| 文件 | 职责 |\n| --- | --- |\n| index.html | 演示页面 |"),
        ],
    }

    result = await evaluator_node(state)
    # 应当智能放行，不再产生假阴性打回
    assert result["should_terminate"] is True
    assert result["milestones"][0].status == "completed"
    assert any("index.html" in fact for fact in result["confirmed_facts"])
    assert "工作区文件分析已完成" in result["rolling_summary"]
    assert result["messages"] == []


@pytest.mark.asyncio
async def test_evaluator_rejection_loop_breaker(
    mock_gateway, mock_context, mock_prompts
):
    """测试连续打回保护（Rejection Loop Breaker）。"""
    # 模拟 Evaluator 重复打回
    mock_gateway.invoke.return_value = LLMResponse(
        content=json.dumps({
            "milestone_ok": False,
            "all_completed": False,
            "summary": "仍需继续确认",
        }),
        endpoint_name="test-model",
        total_tokens=100,
        finish_reason="stop",
    )

    evaluator_node = build_evaluator_node(mock_gateway, mock_context, mock_prompts)
    state = {
        "step_count": 6,
        "total_tokens": 1000,
        "milestones": [Milestone(id=1, title="M1", status="completed")],
        "current_milestone_idx": 0,
        "messages": [
            HumanMessage(content="查询文件职责"),
            AIMessage(content="【阶段验收未通过，需要继续推进】当前目标尚未达成"),
            AIMessage(content="已完成查询，共有 4 个文件..."),
            AIMessage(content="【阶段验收未通过，需要继续推进】当前目标尚未达成"),
            AIMessage(content="### 最终总结\n所有文件职责已列出完毕。"),
        ],
    }

    result = await evaluator_node(state)
    # 历史已打回 2 次且当前已有完整答复，应当触发死循环熔断放行
    assert result["should_terminate"] is True
    assert result["milestones"][0].status == "completed"
