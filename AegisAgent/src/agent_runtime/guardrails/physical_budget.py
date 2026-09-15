"""物理预算守卫（确定性硬熔断）。

对应 ``documents/agent_runtime/05_guardrails_implementation.md`` §2。

**为什么不用费用（cost_usd）做预算**：外部计费接口不可控、不可复现，且需要联网。
Aegis 只用本地可严格度量的物理指标做熔断：

===========  ==================  ==========================
指标          字段                熔断条件
===========  ==================  ==========================
步数          ``step_count``      ``>= max_steps``
Token         ``total_tokens``    ``>= max_total_tokens``
挂钟时间      实例持有的起点        ``elapsed >= max_wall_time_sec``
===========  ==================  ==========================

**挂钟时间为什么不放进 AgentState**：它是守卫实例的运行时属性。放进 State 会污染
Checkpoint 语义（回放时时间不可复现）。因此任务恢复时必须**重新实例化**本守卫。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple

from loguru import logger

__all__ = ["BudgetVerdict", "PhysicalBudgetGuard"]

#: 软告警触发比例（达到阈值的 90% 时提醒模型收敛，但不终止）
WARNING_RATIO = 0.9


@dataclass(frozen=True, slots=True)
class BudgetVerdict:
    """一次预算检查的结论。"""

    terminated: bool
    reason: Optional[str]
    warnings: tuple[str, ...]


class PhysicalBudgetGuard:
    """单任务物理预算守卫。

    每个任务实例化一次（内部持有 ``start_time``），在 ``budget_guard`` 节点中被调用。

    Args:
        max_steps: 最大步数。
        max_total_tokens: 累计 Token 硬上限。
        max_wall_time_sec: 挂钟时间上限（秒）。
        start_time: 起点时间戳；缺省取构造时刻。
    """

    __slots__ = ("max_steps", "max_total_tokens", "max_wall_time_sec", "start_time")

    def __init__(
        self,
        max_steps: int,
        max_total_tokens: int,
        max_wall_time_sec: float,
        start_time: Optional[float] = None,
    ) -> None:
        self.max_steps = max_steps
        self.max_total_tokens = max_total_tokens
        self.max_wall_time_sec = max_wall_time_sec
        self.start_time = time.time() if start_time is None else start_time

    @classmethod
    def from_config(cls, guardrails_config: Any) -> "PhysicalBudgetGuard":
        """从 ``RuntimeConfig.guardrails`` 构造守卫。

        Args:
            guardrails_config: ``config.runtime.guardrails``（Pydantic 模型）。

        Returns:
            新的守卫实例（起点为当前时刻）。
        """
        return cls(
            max_steps=guardrails_config.max_steps,
            max_total_tokens=guardrails_config.max_total_tokens,
            max_wall_time_sec=guardrails_config.max_wall_time_sec,
        )

    @property
    def elapsed_sec(self) -> float:
        """自任务开始以来的挂钟秒数。"""
        return time.time() - self.start_time

    def check(self, state: Mapping[str, Any]) -> Tuple[bool, Optional[str]]:
        """执行硬熔断检查。

        Args:
            state: ``AgentState``（只读）。

        Returns:
            ``(是否终止, 终止原因)``；未触发时原因为 ``None``。
        """
        step_count = int(state.get("step_count", 0) or 0)
        if step_count >= self.max_steps:
            return True, f"执行总步数达上限（{self.max_steps} 步），触发安全熔断"

        total_tokens = int(state.get("total_tokens", 0) or 0)
        if total_tokens >= self.max_total_tokens:
            return True, f"累计消耗 Token 达上限（{self.max_total_tokens}），触发安全熔断"

        elapsed = self.elapsed_sec
        if elapsed >= self.max_wall_time_sec:
            return (
                True,
                f"单任务物理运行时间耗尽（{elapsed:.1f}s >= {self.max_wall_time_sec}s）",
            )

        return False, None

    def warnings(self, state: Mapping[str, Any]) -> list[str]:
        """生成软告警（达到阈值 90% 时提醒，不终止）。

        Args:
            state: ``AgentState``（只读）。

        Returns:
            告警文本列表；无告警时为空列表。
        """
        alerts: list[str] = []

        step_count = int(state.get("step_count", 0) or 0)
        if self.max_steps > 0 and step_count >= self.max_steps * WARNING_RATIO:
            alerts.append(f"步数告警: {step_count}/{self.max_steps}")

        total_tokens = int(state.get("total_tokens", 0) or 0)
        if self.max_total_tokens > 0 and total_tokens >= self.max_total_tokens * WARNING_RATIO:
            alerts.append(f"Token 告警: {total_tokens}/{self.max_total_tokens}")

        elapsed = self.elapsed_sec
        if self.max_wall_time_sec > 0 and elapsed >= self.max_wall_time_sec * WARNING_RATIO:
            alerts.append(f"时间告警: {elapsed:.0f}s/{self.max_wall_time_sec:.0f}s")

        if alerts:
            logger.warning(f"[BudgetGuard] {'; '.join(alerts)}")
        return alerts
