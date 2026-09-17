"""Phase 9: 真实 LLM 结构化输出与 Tool Calls 解析契约测试 (Phase 9)。

对应 `documents/深度测试路线.md` §2 (Phase 9)。
直接向 gpt-5.6-terra / gpt-5.6-luna 发送真实请求，
验证 extract_json_object 与 to_tool_call_specs 在真实前沿模型输出样态下的解析稳健性。

预估消耗：2 次 reasoning 调用, 2 次 fast 调用。
"""

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from agent_runtime.nodes.base import to_tool_call_specs
from agent_runtime.structured_output import extract_json_object


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_live_reasoning_model_structured_json_output(live_gateway):
    """9.1 验证 gpt-5.6-terra (reasoning) 输出的结构化计划 JSON 能被 extract_json_object 正确解析。"""
    system_prompt = (
        "你是一个架构规划专家。请严格以 JSON 格式输出任务计划，包含 'milestones'（列表）和 'summary' 字段。"
        "允许在 JSON 外包含适量中文说明。"
    )
    user_prompt = "请为一个 Python CLI 工具制定 2 个开发里程碑，要求输出标准 JSON。"

    response = await live_gateway.invoke(
        tier="reasoning",
        messages=[
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ],
    )

    assert response.content, "真实模型返回内容不应为空"
    assert response.total_tokens > 0, "应有真实 Token 消耗记录"

    # 验证 extract_json_object 能稳健抽取 JSON 对象
    parsed = extract_json_object(response.content)
    assert parsed is not None, f"未能从模型返回中抽取 JSON：\n{response.content}"
    assert isinstance(parsed, dict)
    assert "milestones" in parsed or "summary" in parsed, f"JSON 字段缺失：{parsed.keys()}"


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_live_fast_model_tool_calls_contract(live_gateway):
    """9.2 验证 gpt-5.6-luna (fast) 在提供工具 Schema 时能生成合法的 tool_calls 且被 to_tool_call_specs 稳健解析。"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "向工作区写入文件",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "相对文件路径"},
                        "content": {"type": "string", "description": "文件内容"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "view_file",
                "description": "查看文件内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"},
                    },
                    "required": ["path"],
                },
            },
        },
    ]

    messages = [
        SystemMessage(content="你是一个代码执行助手。必须使用 write_file 工具创建 hello.py 文件，内容为 print('hello aegis')。"),
        HumanMessage(content="请帮我创建 hello.py。"),
    ]

    response = await live_gateway.invoke(
        tier="fast",
        messages=messages,
        tools=tools,
    )

    assert response.has_tool_calls, f"模型未触发期望的 tool_calls：{response.content}"
    assert len(response.tool_calls) > 0

    # 验证 to_tool_call_specs 解析
    specs = to_tool_call_specs(response.tool_calls)
    assert len(specs) > 0

    call_id, name, args = specs[0]
    assert isinstance(call_id, str) and len(call_id) > 0
    assert name in ("write_file", "view_file")
    assert isinstance(args, dict)
    assert "path" in args
