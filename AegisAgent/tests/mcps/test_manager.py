"""MCPManager 与 MCPToolAdapter 单元/组件测试 (mcps/manager.py & mcps/adapter.py)。"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest

from agent_runtime.config import MCPConfig, MCPServerConfig
from agent_runtime.errors import ToolExecutionError
from mcps.adapter import MCPToolAdapter
from mcps.manager import (
    MCPManager,
    _build_stdio_params,
    _flatten_content,
    _resolve_env,
    _resource_wrapper_args,
)
from mcps.models import MCPToolDefinition


# ==============================================================================
# 1. 资源包装与环境解析纯函数
# ==============================================================================

def test_resource_wrapper_args():
    """测试 Linux 资源配额包装脚本构造 (RLIMIT_AS/FSIZE/CPU + setsid)。"""
    config = SimpleNamespace(
        rlimit_as_mb=512,
        rlimit_fsize_mb=20,
        rlimit_cpu_sec=60,
    )
    args = _resource_wrapper_args("npx", ["-y", "mcp-server"], config)
    assert args[0] == "-c"
    script = args[1]
    assert "RLIMIT_AS" in script
    assert str(512 * 1024 * 1024) in script
    assert "RLIMIT_FSIZE" in script
    assert str(20 * 1024 * 1024) in script
    assert "RLIMIT_CPU" in script
    assert "(60, 60)" in script
    assert "os.setsid()" in script
    assert "os.execvp" in script
    assert args[2] == "npx"
    assert args[3:] == ["-y", "mcp-server"]


def test_resolve_env(monkeypatch):
    """测试 env:VAR 形式的环境变量解析。"""
    monkeypatch.setenv("MY_TEST_TOKEN", "secret_token_123")
    raw_env = {
        "GITHUB_TOKEN": "env:MY_TEST_TOKEN",
        "STATIC_VAL": "plain_text",
        "MISSING_TOKEN": "env:NOT_EXISTS_ENV",
    }
    resolved = _resolve_env(raw_env)
    assert resolved["GITHUB_TOKEN"] == "secret_token_123"
    assert resolved["STATIC_VAL"] == "plain_text"
    assert resolved["MISSING_TOKEN"] == ""


def test_flatten_content():
    """测试 CallToolResult 内容块压平。"""
    # 纯文本块
    block1 = SimpleNamespace(type="text", text="Hello MCP")
    block2 = SimpleNamespace(type="text", text="Second line")
    result = SimpleNamespace(content=[block1, block2])
    assert _flatten_content(result) == "Hello MCP\nSecond line"

    # 非文本块
    block_bin = SimpleNamespace(type="image")
    result_bin = SimpleNamespace(content=[block_bin])
    assert "<image content>" in _flatten_content(result_bin)


# ==============================================================================
# 2. MCPManager 生命周期与隔离测试
# ==============================================================================

@pytest.mark.asyncio
async def test_mcp_manager_disabled():
    """测试总开关关闭时直接跳过工具发现。"""
    config = MCPConfig(enabled=False, servers={})
    manager = MCPManager(config)
    assert manager.enabled is False
    tools = await manager.list_tools()
    assert tools == []


@pytest.mark.asyncio
async def test_mcp_manager_server_states():
    """测试服务器状态快照导出。"""
    server_cfg = MCPServerConfig(name="gh", enabled=True, transport="stdio", command="node")
    config = MCPConfig(enabled=True, servers={"gh": server_cfg})
    manager = MCPManager(config)
    states = manager.server_states()
    assert "gh" in states
    assert states["gh"]["enabled"] is True
    assert states["gh"]["connected"] is False


@pytest.mark.asyncio
async def test_mcp_manager_call_tool_validation():
    """测试 call_tool 针对非法名称与未配置服务器的防御。"""
    config = MCPConfig(enabled=True, servers={})
    manager = MCPManager(config)

    # 1. 命名缺少前缀
    with pytest.raises(ToolExecutionError, match="缺少 'mcp__' 前缀"):
        await manager.call_tool("bad_name", {})

    # 2. 未配置的服务器
    with pytest.raises(ToolExecutionError, match="未在配置中声明"):
        await manager.call_tool("mcp__unregistered__tool", {})


@pytest.mark.asyncio
async def test_mcp_manager_connection_failure_isolation():
    """测试单个服务器连接失败被隔离并记录在 failed 表中。"""
    server_cfg = MCPServerConfig(name="broken_srv", enabled=True, transport="stdio", command="non_existent_binary")
    config = MCPConfig(enabled=True, servers={"broken_srv": server_cfg})
    manager = MCPManager(config)

    # 模拟连接抛错
    with patch.object(MCPManager, "_connect", side_effect=RuntimeError("Subprocess failed to launch")):
        tools = await manager.list_tools()
        assert tools == []
        assert "broken_srv" in manager._failed

        # 再次调用直接短路
        with pytest.raises(ToolExecutionError, match="MCP 服务器不可用"):
            await manager.call_tool("mcp__broken_srv__do_something", {})


# ==============================================================================
# 3. MCPToolAdapter 适配器测试
# ==============================================================================

@pytest.mark.asyncio
async def test_mcp_tool_adapter_success():
    """测试 MCPToolAdapter 正常调用并返回 ToolResult。"""
    mock_manager = AsyncMock()
    mock_manager.call_tool.return_value = ("Success result from MCP", False)

    defn = MCPToolDefinition(
        server_name="test_srv",
        original_name="test_tool",
        namespaced_name="mcp__test_srv__test_tool",
        description="A test tool",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
    )
    adapter = MCPToolAdapter(defn, mock_manager, task_id="task_123")
    assert adapter.trust == "untrusted"
    assert adapter.name == "mcp__test_srv__test_tool"

    result = await adapter.invoke({"query": "search query"})
    assert result.ok is True
    assert result.content == "Success result from MCP"
    assert result.error is None
    mock_manager.call_tool.assert_awaited_once_with(
        namespaced_name="mcp__test_srv__test_tool",
        arguments={"query": "search query"},
        task_id="task_123",
    )


@pytest.mark.asyncio
async def test_mcp_tool_adapter_error_handling():
    """测试 MCPToolAdapter 捕获 ToolExecutionError 并降级为失败结果。"""
    mock_manager = AsyncMock()
    mock_manager.call_tool.side_effect = ToolExecutionError("Connection timeout")

    defn = MCPToolDefinition(
        server_name="test_srv",
        original_name="test_tool",
        namespaced_name="mcp__test_srv__test_tool",
        description="A test tool",
    )
    adapter = MCPToolAdapter(defn, mock_manager)
    result = await adapter.invoke({"query": "search query"})

    assert result.ok is False
    assert "Connection timeout" in str(result.content)
