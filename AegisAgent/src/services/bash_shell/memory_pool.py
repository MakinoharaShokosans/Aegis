"""GlobalMemoryBudget：全局内存池（并发配额）与排队预估。

设计（ADR §2.2「并发资源协调」）：
1. **内存配额**：以 ``asyncio.Condition`` 守护「已用配额」计数，
   配额不足时**等待而不是失败**，任务完成后立即释放并唤醒队列中的下一个；
2. **并发上限**：以 ``asyncio.Semaphore(max_concurrent)`` 限制同时执行的任务数，
   与内存配额解耦（两者都由 ``[bash_shell]`` 段配置）；
3. **预估等待**：按「内存缺口比例 × 近期平均任务耗时 × 排队深度」给出启发式预估秒数，
   供 HTTP 层在返回 ``status: QUEUED`` 时告知调用方退避时长；
4. **非阻塞探测**：``try_acquire`` / ``acquire_or_queue`` 支持「0 等待预算」的探测语义，
   池满时立即返回失败，由调用方决定排队还是稍后重试。

所有协程均不在事件循环内做阻塞 I/O（纯内存计数）。

规范：documents/技术选型/bash_shell.md 第 2.2 节
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Tuple

from loguru import logger

__all__ = ["GlobalMemoryBudget"]


class GlobalMemoryBudget:
    """全局内存池：内存配额 + 并发槽位的排队与回收。

    Attributes:
        total_mb: 内存池总量（MB），来自 ``bash_shell.memory_pool_mb``。
        max_concurrent: 并发槽位上限，来自 ``bash_shell.max_concurrent``。
    """

    def __init__(
        self,
        total_mb: int,
        max_concurrent: int,
        *,
        default_task_mb: int,
        default_task_sec: float,
    ) -> None:
        """初始化内存池。

        Args:
            total_mb: 内存池总量（MB），必须为正。
            max_concurrent: 并发槽位上限，必须为正。
            default_task_mb: 未显式给出预估时的默认单任务内存占用（MB）。
            default_task_sec: 尚无历史样本时用于预估等待的单任务耗时（秒）。

        Raises:
            ValueError: ``total_mb`` 或 ``max_concurrent`` 非正时抛出。
        """
        if total_mb <= 0:
            raise ValueError(f"内存池总量必须为正，当前为 {total_mb}")
        if max_concurrent <= 0:
            raise ValueError(f"并发上限必须为正，当前为 {max_concurrent}")

        self.total_mb = int(total_mb)
        self.max_concurrent = int(max_concurrent)
        self._default_task_mb = max(1, int(default_task_mb))
        self._default_task_sec = max(0.0, float(default_task_sec))

        self._used_mb = 0
        self._active = 0
        self._waiters = 0
        self._completed = 0
        self._ema_duration_sec = 0.0

        # 注意：原语在事件循环内首次 await 时绑定循环，故可在 lifespan 中安全构造
        self._condition = asyncio.Condition()
        self._slots = asyncio.Semaphore(self.max_concurrent)

    # ------------------------------------------------------------------
    # 只读视图
    # ------------------------------------------------------------------
    @property
    def used_mb(self) -> int:
        """当前已用配额（MB）。"""
        return self._used_mb

    @property
    def available_mb(self) -> int:
        """当前剩余可用配额（MB），不会为负。"""
        return max(0, self.total_mb - self._used_mb)

    @property
    def waiting(self) -> int:
        """当前正在等待配额的排队任务数。"""
        return self._waiters

    # ------------------------------------------------------------------
    # 配额计算
    # ------------------------------------------------------------------
    def normalize(self, estimated_mb: int) -> int:
        """规范化单任务预估配额。

        单任务预估超过池总量时按池上限截断（否则该任务永远无法被满足而饿死），
        并返回截断后的值；``acquire`` 与 ``release`` 使用同一套规范化逻辑，
        保证借还与归还严格配平。

        Args:
            estimated_mb: 调用方给出的预估内存（MB）。

        Returns:
            落在 ``(0, total_mb]`` 区间内的规范化配额（MB）。

        Raises:
            ValueError: ``estimated_mb`` 非正时抛出。
        """
        if estimated_mb <= 0:
            raise ValueError(f"预估配额必须为正，当前为 {estimated_mb}")
        if estimated_mb > self.total_mb:
            logger.warning(
                "单任务预估 {}MB 超过内存池总量 {}MB，按池上限截断", estimated_mb, self.total_mb
            )
            return self.total_mb
        return int(estimated_mb)

    def estimate_wait_sec(self, estimated_mb: int | None = None) -> float:
        """启发式预估新任务需要排队等待的秒数。

        估算式：``平均耗时 × max(内存缺口比例, 1/并发上限) × (排队深度 + 1)``；
        其中平均耗时取历史完成任务的指数滑动均值，无样本时退化为默认任务耗时。

        Args:
            estimated_mb: 新任务的预估配额（MB）；``None`` 时取默认单任务占用。

        Returns:
            预估等待秒数（保留 3 位小数，无排队压力时为 0.0）。
        """
        need = self.normalize(estimated_mb if estimated_mb is not None else self._default_task_mb)
        deficit = self._used_mb + need - self.total_mb
        if deficit <= 0 and self._waiters == 0 and self._active < self.max_concurrent:
            return 0.0
        avg = self._ema_duration_sec or self._default_task_sec
        ratio = 0.0 if deficit <= 0 else min(1.0, deficit / self.total_mb)
        weight = max(ratio, 1.0 / self.max_concurrent)
        return round(avg * weight * (self._waiters + 1), 3)

    def snapshot(self, estimated_mb: int | None = None) -> Dict[str, Any]:
        """导出内存池运行时快照（用于 /health 与 QUEUED 响应）。

        Args:
            estimated_mb: 用于预估等待的假设配额（MB）；``None`` 时取默认单任务占用。

        Returns:
            含总量 / 已用 / 可用 / 排队数 / 并发占用 / 预估等待秒数的字典。
        """
        return {
            "total_mb": self.total_mb,
            "used_mb": self._used_mb,
            "available_mb": self.available_mb,
            "waiting_tasks": self._waiters,
            "max_concurrent": self.max_concurrent,
            "active_tasks": self._active,
            "completed_tasks": self._completed,
            "avg_task_sec": round(self._ema_duration_sec or self._default_task_sec, 3),
            "estimated_wait_sec": self.estimate_wait_sec(estimated_mb),
        }

    # ------------------------------------------------------------------
    # 配额借还
    # ------------------------------------------------------------------
    async def _acquire_slot(self) -> None:
        """获取一个并发槽位。"""
        await self._slots.acquire()
        self._active += 1

    def _release_slot(self) -> None:
        """归还一个并发槽位。"""
        if self._active > 0:
            self._active -= 1
        self._slots.release()

    async def acquire(self, estimated_mb: int) -> None:
        """获取内存配额与并发槽位；不足时排队等待而非失败。

        Args:
            estimated_mb: 本次任务的预估内存（MB）。

        Raises:
            ValueError: ``estimated_mb`` 非正时抛出。
            asyncio.CancelledError: 等待期间任务被取消时抛出（已获取的槽位会回滚）。
        """
        need = self.normalize(estimated_mb)
        await self._acquire_slot()
        try:
            async with self._condition:
                self._waiters += 1
                try:
                    while self._used_mb + need > self.total_mb:
                        await self._condition.wait()
                    self._used_mb += need
                finally:
                    self._waiters -= 1
        except BaseException:
            # 取消或异常路径：回滚并发槽位，避免配额泄漏（配额本身尚未记账）
            self._release_slot()
            raise

    async def try_acquire(self, estimated_mb: int) -> bool:
        """非阻塞尝试获取配额与并发槽位。

        Args:
            estimated_mb: 本次任务的预估内存（MB）。

        Returns:
            ``True`` 表示已成功占用（调用方必须配对 ``release``）；``False`` 表示需排队。

        Raises:
            ValueError: ``estimated_mb`` 非正时抛出。
        """
        need = self.normalize(estimated_mb)
        if self._slots.locked():
            return False
        await self._acquire_slot()
        async with self._condition:
            if self._used_mb + need > self.total_mb:
                self._release_slot()
                return False
            self._used_mb += need
            return True

    async def acquire_or_queue(self, estimated_mb: int, wait_sec: float) -> Tuple[bool, float]:
        """在给定等待预算内获取配额，超时即视为进入排队（返回 QUEUED 语义）。

        Args:
            estimated_mb: 本次任务的预估内存（MB）。
            wait_sec: 允许等待的秒数；``<= 0`` 时退化为非阻塞探测。

        Returns:
            ``(是否获取成功, 实际等待秒数)``。
        """
        if wait_sec <= 0:
            started = time.monotonic()
            acquired = await self.try_acquire(estimated_mb)
            return acquired, time.monotonic() - started

        started = time.monotonic()
        try:
            await asyncio.wait_for(self.acquire(estimated_mb), timeout=wait_sec)
        except asyncio.TimeoutError:
            # 等待预算耗尽：调用方按 QUEUED 处理，任务本身不入队（由调用方稍后重试）
            return False, time.monotonic() - started
        return True, time.monotonic() - started

    async def release(self, mb: int, *, duration_sec: float | None = None) -> None:
        """释放配额并唤醒排队中的下一个任务。

        传入值会先经 ``normalize`` 处理，与 ``acquire`` 侧完全对称，确保账目配平。

        Args:
            mb: 释放的配额（MB），应与 ``acquire`` 时的预估一致。
            duration_sec: 本次任务实际耗时（秒），用于刷新平均耗时估计；``None`` 表示不更新。

        Raises:
            ValueError: ``mb`` 非正时抛出。
        """
        if mb <= 0:
            raise ValueError(f"释放配额必须为正，当前为 {mb}")
        freed = self.normalize(mb)
        async with self._condition:
            self._used_mb = max(0, self._used_mb - freed)
            if duration_sec is not None and duration_sec >= 0:
                # 指数滑动平均（首样本直接作为初值），用于等待时长预估
                alpha = 0.3
                self._ema_duration_sec = (
                    duration_sec
                    if self._ema_duration_sec <= 0.0
                    else (1 - alpha) * self._ema_duration_sec + alpha * duration_sec
                )
                self._completed += 1
            self._condition.notify_all()
        self._release_slot()
        logger.debug(
            "配额释放 {}MB，当前已用 {}MB / {}MB，排队 {} 个",
            freed,
            self._used_mb,
            self.total_mb,
            self._waiters,
        )
