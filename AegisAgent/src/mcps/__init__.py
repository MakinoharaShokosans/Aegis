"""MCP（Model Context Protocol）协议集成与运行时治理。

对齐 ``documents/agent_runtime/09_mcp_integration_and_governance.md``。

**为什么 MCP 单独成包而不放进 ``tools/``**：MCP 涉及**外部子进程托管**
（stdio 模式）与网络会话（SSE 模式），它的主要复杂度在生命周期治理——
防僵尸进程、懒加载握手、命名空间隔离——而不是工具的业务逻辑。
把 adapter / manager / models 收在一处，便于集中审计"谁拉起了什么进程"。

三个文件职责：

* :mod:`~mcps.models`  —— 纯数据契约与命名空间规则
* :mod:`~mcps.manager` —— 连接生命周期、懒加载、防僵尸
* :mod:`~mcps.adapter` —— 把远端 MCP 工具伪装成本地 :class:`~tools.core.protocol.AegisTool`
"""

from mcps.adapter import MCPToolAdapter
from mcps.manager import MCPManager
from mcps.models import MCPToolDefinition, parse_namespaced_tool, to_namespaced_name
from mcps.vetting import VettingOutcome, vet_tool_definition

__all__ = [
    "MCPManager",
    "MCPToolAdapter",
    "MCPToolDefinition",
    "VettingOutcome",
    "parse_namespaced_tool",
    "to_namespaced_name",
    "vet_tool_definition",
]
