"""确定性护栏层（Pure Policies）。

本层是"确定性包围非确定性"的落点：**全部为纯函数或持有极小状态的策略对象**，
不调用 LLM、不做网络 I/O、不感知 LangGraph，因此可以 100% 离线单测。

包含五件武器：
* :mod:`~agent_runtime.guardrails.loop_detector`  —— 双轨死循环防御（指纹 + 连续错误）
* :mod:`~agent_runtime.guardrails.physical_budget` —— 物理预算硬熔断
* :mod:`~agent_runtime.guardrails.observation_pruner` —— 观察值离线卸载与蒸馏
* :mod:`~agent_runtime.guardrails.canary` —— 金丝雀令牌派生、指令构造与外泄熔断
* :mod:`~agent_runtime.guardrails.permission` —— 三级权限分级与越级判定（HITL 判定核心）
* :mod:`~agent_runtime.guardrails.injection_guard` —— 注入样态标注（纵深防御，非安全边界）

注：``canary``（防外泄）与 ``injection_guard``（防注入执行）是**互补**的两种机制，
前者保护系统提示词不被套取，后者标注外部不可信内容；真正的注入边界是
权限分离（见 ``documents/agent_runtime/12_research_subagent.md``）。
"""

from agent_runtime.guardrails.canary import (
    build_canary_directive,
    derive_session_canary,
    detect_canary_leak,
    generate_canary_token,
    sanitize_canary,
)
from agent_runtime.guardrails.injection_guard import (
    InjectionMatch,
    InjectionScan,
    redact_injection,
    scan_injection,
    summarize_matches,
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
from agent_runtime.guardrails.permission import (
    LEVEL_ORDER,
    PermissionDecision,
    action_signature,
    check_permission,
    normalize_level,
    required_level_for,
)
from agent_runtime.guardrails.physical_budget import PhysicalBudgetGuard

__all__ = [
    "InjectionMatch",
    "InjectionScan",
    "LEVEL_ORDER",
    "ObservationPruner",
    "PermissionDecision",
    "PhysicalBudgetGuard",
    "PrunedObservation",
    "action_signature",
    "build_canary_directive",
    "build_replan_notice",
    "check_permission",
    "compute_fingerprint",
    "derive_session_canary",
    "detect_canary_leak",
    "generate_canary_token",
    "is_failure_observation",
    "is_fingerprint_loop",
    "normalize_level",
    "register_fingerprints",
    "required_level_for",
    "sanitize_canary",
    "update_consecutive_errors",
]
