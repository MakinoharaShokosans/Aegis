"""确定性护栏层（Pure Policies）。

本层是"确定性包围非确定性"的落点：**全部为纯函数或持有极小状态的策略对象**，
不调用 LLM、不做网络 I/O、不感知 LangGraph，因此可以 100% 离线单测。

包含三件武器：
* :mod:`~agent_runtime.guardrails.loop_detector`  —— 双轨死循环防御（指纹 + 连续错误）
* :mod:`~agent_runtime.guardrails.physical_budget` —— 物理预算硬熔断
* :mod:`~agent_runtime.guardrails.observation_pruner` —— 观察值离线卸载与蒸馏
"""

from agent_runtime.guardrails.canary import (
    build_canary_directive,
    derive_session_canary,
    detect_canary_leak,
    generate_canary_token,
    sanitize_canary,
)
from agent_runtime.guardrails.loop_detector import (
    build_replan_notice,
    compute_fingerprint,
    is_failure_observation,
    is_fingerprint_loop,
    register_fingerprints,
    update_consecutive_errors,
)
from agent_runtime.guardrails.observation_pruner import ObservationPruner, PrunedObservation
from agent_runtime.guardrails.physical_budget import PhysicalBudgetGuard

__all__ = [
    "ObservationPruner",
    "PhysicalBudgetGuard",
    "PrunedObservation",
    "build_canary_directive",
    "build_replan_notice",
    "compute_fingerprint",
    "derive_session_canary",
    "detect_canary_leak",
    "generate_canary_token",
    "is_failure_observation",
    "is_fingerprint_loop",
    "register_fingerprints",
    "sanitize_canary",
    "update_consecutive_errors",
]
