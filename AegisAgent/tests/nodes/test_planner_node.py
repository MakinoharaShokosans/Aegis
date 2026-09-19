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
