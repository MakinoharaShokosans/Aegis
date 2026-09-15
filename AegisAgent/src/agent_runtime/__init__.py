"""Aegis Agent Runtime —— 工程研究智能体的编排内核。

对外稳定入口只暴露"能力边界"，不暴露内部实现细节：

* :func:`agent_runtime.config.get_config`  —— 强类型配置
* :class:`agent_runtime.state.AgentState`   —— 状态契约（唯一真源）
* :func:`agent_runtime.workflow.build_runtime` / ``run_agent`` / ``resume_agent``
* :func:`agent_runtime.api.app.create_app`  —— HTTP 接入层

内部分层（依赖严格单向，见 ``10_directory_structure.md``）::

    api  →  workflow/context/execution_context  →  nodes ⇄ edges
                                                  ↓
                                            guardrails（纯策略）
                                                  ↓
                            llm · memory · skills · observability · tools · mcps
                                                  ↓
                                     state · config · errors（契约层）
"""

from agent_runtime.config import AegisConfig, get_config
from agent_runtime.errors import AgentError
from agent_runtime.state import AgentState, FailedAttempt, Milestone, StepRecord

__all__ = [
    "AgentError",
    "AgentState",
    "AegisConfig",
    "FailedAttempt",
    "Milestone",
    "StepRecord",
    "get_config",
]

__version__ = "0.1.0"
