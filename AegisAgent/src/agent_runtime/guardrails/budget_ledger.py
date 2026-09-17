"""子智能体预算账本（**父级唯一记账方**）与子级计数器。

对应 ``documents/agent_runtime/13_subagent_delegation.md`` §4。

## 为什么需要这一层

工具层此前的隐含契约是"工具是叶子、无状态、便宜"。动态子智能体三条全破——
它内部要跑模型循环，会消耗**父任务看不见的 Token**。若不显式补偿，父任务的
物理预算熔断就被绕过：子任务可以烧掉远超父任务上限的额度，而父任务的计量增量为 0。

本模块提供两个职责正交的对象：

=========================  ==========================================================
:class:`ChildBudget`        子级计数器：**被执行方**用它自我约束（步数/Token/挂钟）
:class:`BudgetLedger`       父级账本：**授权方**用它做准入与结算（唯一记账权）
=========================  ==========================================================

## 三条硬纪律

1. **账本归父级持有，被执行方只能报告不能记账**。子智能体的用量由框架从模型响应
   直接读出后交给 :meth:`BudgetLedger.settle`；**绝不采信子智能体在输出文本里自述的用量**
   ——后者可被注入内容伪造。
2. **先预留、后执行、再结算**（而非事后累加）。事后累加在并发下不成立：
   父任务在子智能体返回**之前**不知道它花了多少，N 个并发子任务各自按上限开销，
   第一次对账时就已超支。
3. **预留是原子的**：:meth:`BudgetLedger.reserve` 内部**不含任何 ``await``**，
   因此在单线程事件循环里天然原子。一旦引入 ``await``，并发派发就会超额分配。

## 与 State 的关系

本模块**不写 State**。父级账本的已结算量由 ``tool_runner`` 冲销进 ``total_tokens``，
从而复用既有的 :class:`~agent_runtime.guardrails.physical_budget.PhysicalBudgetGuard`，
不必新增预算口径。冲销必须发生在**审批闸门之后**——原因见 ``tool_runner`` 的说明。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from loguru import logger

__all__ = ["BudgetLedger", "ChildBudget", "Reservation"]


@dataclass(slots=True)
class ChildBudget:
    """**子级**预算计数器（自我约束用）。

    ``max_tokens`` 来自父级的 :meth:`BudgetLedger.reserve` 实际授予额度，
    **不是**配置里的名义上限——这是"切片"语义的落点。

    Args:
        max_tokens: 授予的 Token 上限。
        max_wall_time_sec: 挂钟上限（秒）。
    """

    max_tokens: int
    max_wall_time_sec: float
    started_at: float = field(default_factory=time.perf_counter)
    tokens: int = 0

    def add_tokens(self, amount: int) -> None:
        """累加 Token 消耗（负数按 0 计，防止上游给出异常值反而"充值"）。"""
        self.tokens += max(0, int(amount or 0))

    @property
    def elapsed(self) -> float:
        """已消耗的挂钟秒数。"""
        return time.perf_counter() - self.started_at

    @property
    def remaining(self) -> int:
        """剩余 Token 额度。"""
        return max(0, self.max_tokens - self.tokens)

    @property
    def exhausted(self) -> bool:
        """Token 或挂钟任一耗尽即视为耗尽。"""
        return self.tokens >= self.max_tokens or self.elapsed >= self.max_wall_time_sec

    def reason(self) -> str:
        """预算耗尽的说明（用于 warnings）；未耗尽时返回空串。"""
        if self.tokens >= self.max_tokens:
            return f"子智能体 Token 预算耗尽（{self.tokens}/{self.max_tokens}）"
        if self.elapsed >= self.max_wall_time_sec:
            return f"子智能体挂钟预算耗尽（{self.elapsed:.1f}s/{self.max_wall_time_sec}s）"
        return ""


@dataclass(slots=True)
class Reservation:
    """一次预留记录（父级账本持有的凭据）。

    Attributes:
        reservation_id: 预留标识（用于日志与轨迹关联）。
        label: 用途标签（如子智能体角色）。
        amount: 预留额度。
        actual: 结算后的实际消耗；未结算时为 0。
        settled: 是否已结算（保证重复结算无副作用）。
    """

    reservation_id: str
    label: str
    amount: int
    actual: int = 0
    settled: bool = False

    @property
    def refund(self) -> int:
        """应退回父级余额的额度（多退少补）。"""
        return max(0, self.amount - self.actual)

    @property
    def overspent(self) -> bool:
        """实际消耗是否超出预留额度（子级计数器失守的告警信号）。"""
        return self.actual > self.amount


class BudgetLedger:
    """**父级**预算账本：准入闸门 + 在途统计 + 结算。

    每个任务实例化一次，与 :class:`~agent_runtime.guardrails.physical_budget.PhysicalBudgetGuard`
    同生命周期（见 ``workflow.prepare_task``）。

    Args:
        max_total_tokens: 父任务的 Token 硬上限（与守卫同源，保证口径一致）。
        max_spawns: 单任务允许的子智能体派发次数上限。
            "委派意愿"是模型唯一不受内容约束的自由度，因此必须有一个物理旋钮。
        min_grant_tokens: 最小可授予额度；低于此值直接拒绝派发，
            避免"给一个跑不动任何东西的额度"制造无意义的失败。
    """

    __slots__ = (
        "_max_total_tokens",
        "_max_spawns",
        "_min_grant_tokens",
        "_parent_used",
        "_consumed",
        "_in_flight",
        "_spawn_count",
    )

    def __init__(
        self,
        max_total_tokens: int,
        *,
        max_spawns: int = 4,
        min_grant_tokens: int = 1000,
    ) -> None:
        self._max_total_tokens = max(0, int(max_total_tokens))
        self._max_spawns = max(0, int(max_spawns))
        self._min_grant_tokens = max(1, int(min_grant_tokens))
        self._parent_used = 0
        self._consumed = 0
        self._in_flight = 0
        self._spawn_count = 0

    # ==========================================================================
    # 观测面
    # ==========================================================================

    @property
    def consumed(self) -> int:
        """子智能体**已结算**的 Token 消耗。"""
        return self._consumed

    @property
    def in_flight(self) -> int:
        """在途预留额度之和（已授权、尚未结算）。"""
        return self._in_flight

    @property
    def spawn_count(self) -> int:
        """已成功派发的子智能体次数。"""
        return self._spawn_count

    @property
    def available(self) -> int:
        """当前可授予余额。

        不变量：``父任务已用 + 子智能体已结算 + 在途预留 ≤ 父任务上限``。
        """
        return max(0, self._max_total_tokens - self._parent_used - self._consumed - self._in_flight)

    def snapshot(self) -> Dict[str, Any]:
        """账本快照（供日志、轨迹与 API 观测）。"""
        return {
            "parent_used": self._parent_used,
            "subagent_consumed": self._consumed,
            "subagent_in_flight": self._in_flight,
            "subagent_spawns": self._spawn_count,
            "available": self.available,
            "max_total_tokens": self._max_total_tokens,
        }

    # ==========================================================================
    # 写入面
    # ==========================================================================

    def sync_parent_usage(self, tokens: int) -> None:
        """同步"父任务自身已消耗的 Token"。

        由 ``tool_runner`` 在派发前调用一次。父任务的用量由主图各节点写入 State，
        账本无权也不该去改 State，因此采用"外部推送"而非"反向读取"。
        本方法只做赋值，不含 ``await``，可与 :meth:`reserve` 安全交错。

        Args:
            tokens: ``state["total_tokens"]`` 的当前值。
        """
        self._parent_used = max(0, int(tokens or 0))

    def reserve(self, amount: int, label: str) -> Tuple[Optional[Reservation], str]:
        """准入并预留额度（**本方法无 ``await``，因而是原子的**）。

        准入三重闸门，全部通过才占用一次派发名额：

        1. 派发次数未超上限；
        2. 余额足以授予最小额度；
        3. 授予额 = ``min(申请额, 余额)``（**收窄而非拒绝**——余额只剩一半时
           给一半额度比整体失败更有用，但仍受 ``min_grant_tokens`` 兜底）。

        Args:
            amount: 申请额度。
            label: 用途标签（子智能体角色）。

        Returns:
            ``(预留凭据, 空串)``；被拒绝时返回 ``(None, 拒绝原因)``。
            拒绝原因用于构造面向模型的失败观察值，**不参与任何判定**。
        """
        if self._spawn_count >= self._max_spawns:
            return None, f"本任务子智能体派发次数已达上限（{self._max_spawns} 次）"

        available = self.available
        if available < self._min_grant_tokens:
            return None, (
                f"父任务剩余预算不足（剩余 {available} Token，"
                f"低于单次派发最小额度 {self._min_grant_tokens}）"
            )

        requested = max(1, int(amount or 0))
        granted = min(requested, available)
        if granted < self._min_grant_tokens:
            return None, (
                f"父任务剩余预算仅够 {granted} Token，"
                f"低于单次派发最小额度 {self._min_grant_tokens}"
            )

        reservation = Reservation(
            reservation_id=f"rsv_{uuid.uuid4().hex[:12]}",
            label=str(label or "subagent"),
            amount=granted,
        )
        self._in_flight += granted
        self._spawn_count += 1
        logger.info(
            f"[Ledger] 预留守恒 {reservation.reservation_id} label={reservation.label} "
            f"授予={granted} 申请={requested} 在途={self._in_flight} 可用={self.available}"
        )
        return reservation, ""

    def settle(self, reservation: Optional[Reservation], actual_tokens: int) -> int:
        """结算预留：多退少补（**幂等**，重复调用无副作用）。

        必须在**所有**退出路径上调用：成功、失败、超时被取消、异常。
        由于超时会取消子智能体所在的任务，结算的调用点必须在未受取消保护的
        父级代码里，而非子智能体内部。

        Args:
            reservation: :meth:`reserve` 返回的凭据；``None`` 时为空操作。
            actual_tokens: 实际消耗（来自子级计数器的**运行时计量**）。

        Returns:
            退回父级余额的额度。
        """
        if reservation is None or reservation.settled:
            return 0

        actual = max(0, int(actual_tokens or 0))
        reservation.actual = actual
        reservation.settled = True

        self._in_flight = max(0, self._in_flight - reservation.amount)
        self._consumed += actual

        if reservation.overspent:
            # 子级计数器失守：账本按实际值记账（宁可多记，不可少记），并告警
            logger.warning(
                f"[Ledger] 子智能体实际消耗超出预留额度 "
                f"({actual} > {reservation.amount})，已按实际值记账"
            )

        logger.info(
            f"[Ledger] 结算 {reservation.reservation_id} 实际={actual} "
            f"预留={reservation.amount} 退回={reservation.refund} "
            f"累计子智能体消耗={self._consumed}"
        )
        return reservation.refund
