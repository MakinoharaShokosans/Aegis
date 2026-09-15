"""Tool Core 框架单元测试 (Schema, Registry, Dispatcher)。"""

import asyncio
from typing import Any, Mapping
import pytest

from tools.core.protocol import AegisTool, ToolResult
from tools.core.schema import to_openai_tool, to_openai_tools
from tools.core.registry import ToolRegistry
from tools.core.dispatcher import ToolDispatcher
from agent_runtime.errors import ToolExecutionError


class DummyEchoTool(AegisTool):
    """测试用虚拟工具。"""
    name = "dummy_echo"
    description = "Echo tool for testing"
    parameters = {
        "type": "object",
        "properties": {"msg": {"type": "string"}},
        "required": ["msg"],
    }

    def __init__(self, delay: float = 0.0, should_fail: bool = False):
        self.delay = delay
        self.should_fail = should_fail
        self.timeout_sec = 2.0

    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        if self.should_fail:
            raise RuntimeError("Dummy error happened")
        return ToolResult(ok=True, content=f"echo: {args.get('msg', '')}")


def test_to_openai_tool_schema():
    """测试将 AegisTool 转译为标准 OpenAI tool schema。"""
    tool = DummyEchoTool()
    schema = to_openai_tool(tool)

    assert schema["type"] == "function"
    fn = schema["function"]
    assert fn["name"] == "dummy_echo"
    assert fn["description"] == "Echo tool for testing"
    assert "msg" in fn["parameters"]["properties"]


def test_tool_registry_registration_and_duplicate():
    """测试工具注册、获取与重名拦截。"""
    registry = ToolRegistry()
    tool1 = DummyEchoTool()
    registry.register(tool1)

    assert len(registry) == 1
    assert registry.get("dummy_echo") is tool1
    assert registry.require("dummy_echo") is tool1
    assert registry.names() == ["dummy_echo"]

    # 重复注册同名工具抛出异常
    with pytest.raises(ToolExecutionError, match="工具名重复注册"):
        registry.register(DummyEchoTool())

    # 查询不存在工具
    assert registry.get("not_exist") is None
    with pytest.raises(ToolExecutionError, match="未注册的工具"):
        registry.require("not_exist")


@pytest.mark.asyncio
async def test_tool_dispatcher_concurrent_execution():
    """测试 ToolDispatcher 使用 asyncio.gather 并发派发多个工具。"""
    registry = ToolRegistry()
    # 注册一个有 0.1s 延迟的工具
    registry.register(DummyEchoTool(delay=0.1))
    dispatcher = ToolDispatcher(registry)

    calls = [
        ("call_1", "dummy_echo", {"msg": "hello"}),
        ("call_2", "dummy_echo", {"msg": "world"}),
        ("call_3", "dummy_echo", {"msg": "foo"}),
    ]

    started = asyncio.get_event_loop().time()
    results = await dispatcher.dispatch(calls)
    duration = asyncio.get_event_loop().time() - started

    assert len(results) == 3
    # 如果是串行执行，耗时需 > 0.3s；并发执行耗时应接近 0.1s（小于 0.25s）
    assert duration < 0.25

    assert results[0].tool_call_id == "call_1"
    assert results[0].result.ok is True
    assert "hello" in results[0].result.content
    assert results[1].result.content == "echo: world"


@pytest.mark.asyncio
async def test_tool_dispatcher_error_and_timeout_isolation():
    """测试单个工具报错或未知工具时平稳降级，不中断其它调用。"""
    registry = ToolRegistry()
    registry.register(DummyEchoTool(should_fail=True))
    dispatcher = ToolDispatcher(registry)

    calls = [
        ("call_err", "dummy_echo", {"msg": "test"}),
        ("call_unknown", "unknown_tool", {"msg": "test"}),
    ]

    results = await dispatcher.dispatch(calls)
    assert len(results) == 2

    # 抛异常的工具被降级为 failure
    assert results[0].result.ok is False
    assert "Dummy error happened" in results[0].result.content

    # 未知工具被降级为 failure
    assert results[1].result.ok is False
    assert "未知工具" in results[1].result.content
