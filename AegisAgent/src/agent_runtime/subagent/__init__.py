"""动态子智能体委派（能力衰减 + 预算切片 + 上下文隔离）。

对应 ``documents/agent_runtime/13_subagent_delegation.md``。

**包级边界**：本包只依赖 ``agent_runtime`` 的通用契约（llm / prompts / guardrails /
envelope / errors）与 ``tools.core`` 的注册表与派发契约，**不 import 任何具体工具**——
具体子工具表由 ``workflow`` 在装配时注入（依赖倒置，与 ``research`` 包同一手法）。

**与 ``research`` 包的关系**：两者是**刻意的能力分层**，不互相折叠——

========================  ==============================  ================================
                          ``delegate_research``           ``spawn_subagent``
========================  ==============================  ================================
广度                       单一用途（外部检索）             任意子任务
输出保证                   **强**（强类型 + 语义约束）        **弱**（固定信封 + 不可信）
回流信任级                 接口可信（类型化值）              一律不可信
========================  ==============================  ================================

理由：强契约是**逐用途手写**的语义判断，模型发明不出来。与其在通用工具里做一层
"预置角色 → 契约"的枚举（多一个选择失败点），不如让每个强契约都有自己的专用工具。
"""

from __future__ import annotations

from agent_runtime.subagent.contracts import (
    Citation,
    SubagentFinding,
    SubagentProposal,
    SubagentReport,
    SubagentRequest,
)
from agent_runtime.subagent.runner import SubagentRunner
from agent_runtime.subagent.tool import SpawnSubagentTool, build_subagent_tool

__all__ = [
    "Citation",
    "SpawnSubagentTool",
    "SubagentFinding",
    "SubagentProposal",
    "SubagentReport",
    "SubagentRequest",
    "SubagentRunner",
    "build_subagent_tool",
]
