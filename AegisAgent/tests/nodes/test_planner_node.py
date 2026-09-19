"""``planner`` 节点与结构化输出格式化测试。"""

import pytest
from langchain_core.messages import AIMessage

from agent_runtime.execution_context import ExecutionContextManager
from agent_runtime.nodes.planner import format_structured_verdict_to_markdown


def test_format_structured_verdict_to_markdown_with_research_report():
    """测试将外部调研类自定义结构化输出自动格式化为 Markdown。"""
    custom_verdict = {
        "status": "completed",
        "topic": "《三角洲行动》最新赛季信息",
        "summary": {
            "season_name": "群星赛季",
            "official_status": "官方页面显示该赛季已正式开启",
            "version": "1.201.3798.86",
            "update_time_found": "9月26日",
            "main_changes": "现有检索结果只能确认赛季主题、战场叙事与内容入口更新",
        },
        "sources": [
            "https://df.qq.com/main.shtml",
            "https://df.qq.com/cp/a20240906fab/index-baidusem-PC.html",
        ],
        "limitations": [
            "检索结果未明确给出群星赛季的具体开启日期和时间",
            "未检索到与上一赛季相比的完整官方更新条目",
        ],
    }

    markdown = format_structured_verdict_to_markdown(custom_verdict)
    assert markdown is not None
    assert "### 《三角洲行动》最新赛季信息" in markdown
    assert "- **Season name**：群星赛季" in markdown
    assert "- **Version**：1.201.3798.86" in markdown
    assert "**参考来源**：" in markdown
    assert "https://df.qq.com/main.shtml" in markdown
    assert "**补充说明与局限性**：" in markdown
    assert "未检索到与上一赛季相比的完整官方更新条目" in markdown


def test_format_structured_verdict_to_markdown_with_file_operation():
    """测试将文件操作类结构化结果自动格式化为 Markdown。"""
    file_verdict = {
        "status": "completed",
        "message": "已调用 bash 在工作区创建 Markdown 文件。",
        "file": "playground.md",
        "path": "/home/user/Projects/EyesPro/playground.md",
        "verified": "文件已成功写入并通过 ls -l 检查存在。",
    }

    markdown = format_structured_verdict_to_markdown(file_verdict)
    assert markdown is not None
    assert "- **目标文件**：`playground.md`" in markdown
    assert "- **绝对路径**：`/home/user/Projects/EyesPro/playground.md`" in markdown
    assert "- **校验状态**：文件已成功写入并通过 ls -l 检查存在。" in markdown


def test_format_structured_verdict_to_markdown_standard_direct_response():
    """测试标准 direct_response 纯文本直接返回，不做多余包装。"""
    standard_verdict = {
        "thought": "纯问候",
        "direct_response": "你好！我是 Aegis 智能体。",
        "is_completed": True,
    }

    markdown = format_structured_verdict_to_markdown(standard_verdict)
    assert markdown == "你好！我是 Aegis 智能体。"


def test_extract_delivery_formats_raw_json_string():
    """测试 ExecutionContextManager.extract_delivery 遇到裸 JSON 字符串时自动格式化。"""
    raw_json_str = (
        '{"status": "completed", "topic": "测试主题", "summary": {"key1": "value1"}, "sources": ["http://example.com"]}'
    )
    state = {
        "messages": [AIMessage(content=raw_json_str)],
        "task_id": "test_task",
    }

    delivery = ExecutionContextManager.extract_delivery(state)
    assert "### 测试主题" in delivery
    assert "- **Key1**：value1" in delivery
    assert "**参考来源**：" in delivery
    assert "http://example.com" in delivery


class DummyLLMGateway:
    """Mock LLM 网关，按预设返回。"""

    def __init__(self, response_content: str):
        self.response_content = response_content

    async def invoke(self, tier: str, messages: list, force_json: bool = False, tools: list = None):
        from agent_runtime.llm.client import LLMResponse
        return LLMResponse(
            content=self.response_content,
            tool_calls=[],
            total_tokens=100,
            endpoint_name="test-model",
        )


class DummyContextManager:
    """Mock 上下文装配器。"""

    def assemble(self, state, node_instruction: str = ""):
        from langchain_core.messages import HumanMessage
        return [HumanMessage(content="test goal")]


class DummyPromptLibrary:
    """Mock 提示词库。"""

    def load(self, name: str, default: str = "") -> str:
        return f"instruction for {name}"


@pytest.mark.asyncio
async def test_planner_node_intermediate_step_preserves_next_step_action():
    """测试中间推进轮次（包含调研 summary 但 is_completed 为 false 且有 next_step）不会被误判为完成，且正确派发 next_step 指令。"""
    from agent_runtime.nodes.planner import build_planner_node
    from agent_runtime.state import Milestone

    # 模拟模型在第2轮返回：包含调研 summary，但明确 next_step 是写文件且 is_completed=false
    intermediate_json = """{
        "thought": "已完成调研，下一步写入文件",
        "summary": {
            "version": "5.0",
            "characters": "玛拉妮"
        },
        "milestone_updates": [
            {"id": 1, "status": "completed"},
            {"id": 2, "status": "in_progress"}
        ],
        "next_step": "调用 write_file 将调研内容写入 genshin_latest_update.md",
        "is_completed": false
    }"""

    gateway = DummyLLMGateway(intermediate_json)
    context = DummyContextManager()
    prompts = DummyPromptLibrary()
    planner_node = build_planner_node(gateway=gateway, context=context, prompts=prompts)

    state = {
        "task_goal": "调研原神最新版本并写入 md 文件",
        "step_count": 1,
        "milestones": [
            Milestone(id=1, title="调研原神更新", status="in_progress"),
            Milestone(id=2, title="写入工作区 md 文件", status="pending"),
        ],
        "total_tokens": 500,
        "messages": [],
    }

    result = await planner_node(state)

    # 1. 验证下发的指令是具体的 next_step 动作，而非被 summary 覆盖
    assert "调用 write_file" in result["messages"][0].content
    assert "genshin_latest_update.md" in result["messages"][0].content

    # 2. 验证里程碑未被粗暴全量置为 completed
    milestones = result["milestones"]
    assert len(milestones) == 2
    assert milestones[0].status == "completed"
    assert milestones[1].status == "in_progress"


@pytest.mark.asyncio
async def test_planner_node_terminal_step_delivers_direct_response():
    """测试最终收敛轮次（is_completed=true）正确下发 Markdown 交付文本并将里程碑全绿。"""
    from agent_runtime.nodes.planner import build_planner_node
    from agent_runtime.state import Milestone

    completion_json = """{
        "thought": "所有操作已执行完毕",
        "milestone_updates": [
            {"id": 2, "status": "completed"}
        ],
        "direct_response": "### 原神最新版本更新报告\\n\\n文件已成功写入工作区 `genshin_latest_update.md`。",
        "is_completed": true
    }"""

    gateway = DummyLLMGateway(completion_json)
    context = DummyContextManager()
    prompts = DummyPromptLibrary()
    planner_node = build_planner_node(gateway=gateway, context=context, prompts=prompts)

    state = {
        "task_goal": "调研原神最新版本并写入 md 文件",
        "step_count": 2,
        "milestones": [
            Milestone(id=1, title="调研原神更新", status="completed"),
            Milestone(id=2, title="写入工作区 md 文件", status="in_progress"),
        ],
        "total_tokens": 1000,
        "messages": [],
    }

    result = await planner_node(state)

    # 1. 验证交付内容包含 Markdown 总结
    assert "### 原神最新版本更新报告" in result["messages"][0].content

    # 2. 验证所有里程碑均为 completed
    milestones = result["milestones"]
    assert all(m.status == "completed" for m in milestones)

