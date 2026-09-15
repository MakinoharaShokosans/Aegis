"""运行中任务注册表与 SSE 事件广播。

对应 ``documents/agent_runtime/11_http_api.md`` §6–§7。

**设计要点**：

1. **单进程内存态**：本机单实例部署，任务句柄与事件环形缓冲只存在于内存。
   进程重启后事件流丢失，但 Checkpoint（SQLite）仍在，任务可通过 ``/resume`` 继续——
   前端必须能容忍"流中断 → 重新拉取快照"这种情况。
2. **环形缓冲 + 游标重放**：客户端用 ``Last-Event-ID`` 重连时，从缓冲区重放其后事件；
   若游标已滑出缓冲，立即以 ``STREAM_GAP`` 错误收尾，强制前端做全量重新同步。
3. **并发闸门**：``max_concurrent_tasks`` 限制同时在跑的任务数，超出直接拒绝，
   与会话级水位压缩、Bash 全局内存池共同构成串行化的资源治理。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Deque, Dict, List, Optional, Set

from loguru import logger

from agent_runtime.api.schemas import TaskOut
from agent_runtime.errors import TaskAlreadyRunningError, TaskNotFoundError, TaskQueueFullError
from agent_runtime.state import AgentState, TaskStatus
from agent_runtime.workflow import RuntimeDeps, resume_agent, run_streaming

__all__ = ["TaskHandle", "TaskRegistry"]

#: 单任务事件缓冲上限（超出后最旧事件被丢弃，重连将触发 STREAM_GAP）
DEFAULT_BUFFER_SIZE = 1000

#: 订阅者队列上限（消费者过慢时丢弃事件而不是拖垮执行）
_SUBSCRIBER_QUEUE_SIZE = 256

#: 事件流结束哨兵
_STREAM_END = None


@dataclass
class TaskHandle:
    """单个任务的运行期句柄。"""

    task_id: str
    session_id: str
    workspace_id: str
    task_goal: str
    status: TaskStatus = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    state: Optional[AgentState] = None
    events: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=DEFAULT_BUFFER_SIZE))
    subscribers: Set[asyncio.Queue] = field(default_factory=set)
    runner: Optional[asyncio.Task] = None
    seq: int = 0

    def oldest_seq(self) -> int:
        """缓冲区中最旧事件的序号（空缓冲返回 0）。"""
        return self.events[0]["seq"] if self.events else 0

    def to_out(self) -> TaskOut:
        """投影为对外 DTO。"""
        state = self.state or {}
        milestones = [
            milestone.model_dump() if hasattr(milestone, "model_dump") else dict(milestone)
            for milestone in (state.get("milestones") or [])
        ]
        return TaskOut(
            task_id=self.task_id,
            session_id=self.session_id,
            workspace_id=self.workspace_id,
            task_goal=self.task_goal,
            status=self.status,
            milestones=milestones,
            current_milestone_idx=int(state.get("current_milestone_idx", 0) or 0),
            step_count=int(state.get("step_count", 0) or 0),
            total_tokens=int(state.get("total_tokens", 0) or 0),
            consecutive_errors=int(state.get("consecutive_errors", 0) or 0),
            should_terminate=bool(state.get("should_terminate", False)),
            termination_reason=str(state.get("termination_reason", "") or ""),
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            artifact_count=len(state.get("artifacts") or {}),
        )


class TaskRegistry:
    """任务注册表（进程内单例，由 lifespan 持有）。

    Args:
        max_concurrent: 同时运行的任务上限。
        buffer_size: 单任务事件缓冲上限。
    """

    def __init__(self, max_concurrent: int = 1, buffer_size: int = DEFAULT_BUFFER_SIZE) -> None:
        self._max_concurrent = max(1, max_concurrent)
        self._buffer_size = buffer_size
        self._tasks: Dict[str, TaskHandle] = {}
        self._running: Set[str] = set()
        self._lock = asyncio.Lock()

    # ==========================================================================
    # 查询
    # ==========================================================================

    def get(self, task_id: str) -> TaskHandle:
        """按 ID 取句柄。

        Raises:
            TaskNotFoundError: 任务不存在。
        """
        handle = self._tasks.get(task_id)
        if handle is None:
            raise TaskNotFoundError(f"任务不存在: {task_id}", context={"task_id": task_id})
        return handle

    def find(self, task_id: str) -> Optional[TaskHandle]:
        """按 ID 取句柄（不存在返回 ``None``）。"""
        return self._tasks.get(task_id)

    def list_by_session(self, session_id: str) -> List[TaskHandle]:
        """列出某会话下的全部任务（按创建时间倒序）。"""
        return sorted(
            (handle for handle in self._tasks.values() if handle.session_id == session_id),
            key=lambda handle: handle.created_at,
            reverse=True,
        )

    @property
    def running_count(self) -> int:
        """当前运行中的任务数。"""
        return len(self._running)

    # ==========================================================================
    # 提交与执行
    # ==========================================================================

    async def submit(
        self,
        deps: RuntimeDeps,
        *,
        workspace_id: str,
        session_id: str,
        task_goal: str,
    ) -> TaskHandle:
        """登记并在后台启动任务。

        Args:
            deps: 进程级运行时。
            workspace_id: 工作区标识。
            session_id: 会话标识。
            task_goal: 任务目标。

        Returns:
            新建的任务句柄（此时状态为 ``queued``）。

        Raises:
            TaskAlreadyRunningError: 同一会话已有任务在跑。
            TaskQueueFullError: 全局并发已达上限。
        """
        async with self._lock:
            if any(
                handle.session_id == session_id and handle.status in ("queued", "running")
                for handle in self._tasks.values()
            ):
                raise TaskAlreadyRunningError(
                    "该会话已有任务在执行，请等待完成或先取消",
                    context={"session_id": session_id},
                )
            if len(self._running) >= self._max_concurrent:
                raise TaskQueueFullError(
                    f"并发任务数已达上限（{self._max_concurrent}）",
                    context={"running": len(self._running)},
                )

            handle = TaskHandle(
                task_id=str(uuid.uuid4()),
                session_id=session_id,
                workspace_id=workspace_id,
                task_goal=task_goal,
                events=deque(maxlen=self._buffer_size),
            )
            self._tasks[handle.task_id] = handle
            self._running.add(handle.task_id)

        # 在独立 Task 中运行，避免阻塞 HTTP 请求
        handle.runner = asyncio.create_task(self._run(deps, handle))
        logger.info(f"[TaskRegistry] 已提交任务 {handle.task_id}（会话 {session_id}）")
        return handle

    async def resume(self, deps: RuntimeDeps, task_id: str) -> TaskHandle:
        """从 Checkpoint 续跑既有任务。

        Args:
            deps: 进程级运行时。
            task_id: 原任务 ID。

        Returns:
            原任务句柄（状态重置为 ``queued``）。

        Raises:
            TaskNotFoundError: 任务不存在。
            TaskQueueFullError: 并发已达上限。
        """
        handle = self.get(task_id)
        async with self._lock:
            if len(self._running) >= self._max_concurrent:
                raise TaskQueueFullError(f"并发任务数已达上限（{self._max_concurrent}）")
            self._running.add(task_id)
            handle.status = "queued"
            handle.finished_at = None

        handle.runner = asyncio.create_task(self._run(deps, handle, resume=True))
        logger.info(f"[TaskRegistry] 已恢复任务 {task_id}")
        return handle

    async def cancel(self, task_id: str) -> None:
        """请求取消任务（在节点边界生效，不强杀）。

        Args:
            task_id: 任务 ID。

        Raises:
            TaskNotFoundError: 任务不存在。
        """
        handle = self.get(task_id)
        if handle.runner is not None and not handle.runner.done():
            handle.runner.cancel()
            handle.status = "cancelled"
            handle.finished_at = time.time()
            logger.info(f"[TaskRegistry] 已请求取消任务 {task_id}")

    async def _run(self, deps: RuntimeDeps, handle: TaskHandle, *, resume: bool = False) -> None:
        """任务执行体（后台协程）。"""
        handle.status = "running"
        handle.started_at = time.time()
        await self.emit(handle.task_id, {"event": "task.started", "task_goal": handle.task_goal})

        try:
            if resume:
                final_state = await resume_agent(
                    deps,
                    task_id=handle.task_id,
                    workspace_id=handle.workspace_id,
                    session_id=handle.session_id,
                    task_goal=handle.task_goal,
                    event_sink=lambda event: self.emit(handle.task_id, event),
                )
            else:
                final_state = await run_streaming(
                    deps,
                    workspace_id=handle.workspace_id,
                    session_id=handle.session_id,
                    task_goal=handle.task_goal,
                    task_id=handle.task_id,
                    event_sink=lambda event: self.emit(handle.task_id, event),
                )
            handle.state = final_state
            handle.status = self._derive_status(final_state)
        except asyncio.CancelledError:
            handle.status = "cancelled"
            handle.finished_at = time.time()
            await self.emit(handle.task_id, {"event": "task.error", "code": "CANCELLED", "message": "任务已取消"})
            raise
        except Exception as exc:  # noqa: BLE001 - 后台任务必须兜住所有异常
            handle.status = "failed"
            logger.exception(f"[TaskRegistry] 任务 {handle.task_id} 执行失败")
            await self.emit(
                handle.task_id,
                {"event": "task.error", "code": type(exc).__name__, "message": str(exc)},
            )
        finally:
            handle.finished_at = handle.finished_at or time.time()
            self._running.discard(handle.task_id)
            await self.emit(
                handle.task_id,
                {
                    "event": "task.finished",
                    "status": handle.status,
                    "termination_reason": str((handle.state or {}).get("termination_reason", "")),
                    "step_count": int((handle.state or {}).get("step_count", 0) or 0),
                    "total_tokens": int((handle.state or {}).get("total_tokens", 0) or 0),
                },
            )
            self._close_subscribers(handle)

    @staticmethod
    def _derive_status(final_state: AgentState) -> TaskStatus:
        """由终态推导对外状态。"""
        reason = str(final_state.get("termination_reason") or "")
        if reason == "task_goal achieved":
            return "succeeded"
        if final_state.get("should_terminate"):
            return "terminated"
        return "failed"

    # ==========================================================================
    # 事件广播
    # ==========================================================================

    async def emit(self, task_id: str, event: Dict[str, Any]) -> None:
        """追加事件并广播给订阅者。

        Args:
            task_id: 任务 ID。
            event: 事件体（``event`` 字段为事件名）。
        """
        handle = self._tasks.get(task_id)
        if handle is None:
            return

        handle.seq += 1
        payload = {"task_id": task_id, "seq": handle.seq, "ts": time.time(), **event}
        handle.events.append(payload)

        for queue in list(handle.subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # 消费者过慢：丢弃事件而不是阻塞任务执行
                logger.warning(f"[TaskRegistry] 订阅者队列已满，丢弃事件 seq={handle.seq}")

    def _close_subscribers(self, handle: TaskHandle) -> None:
        """向所有订阅者发送流结束哨兵。"""
        for queue in list(handle.subscribers):
            try:
                queue.put_nowait(_STREAM_END)
            except asyncio.QueueFull:
                pass

    async def stream(
        self,
        task_id: str,
        last_event_id: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """订阅任务事件流（先重放缓冲，再推送实时事件）。

        Args:
            task_id: 任务 ID。
            last_event_id: 客户端上次收到的序号（断线重连游标）。

        Yields:
            事件字典；出现游标缺口时先 yield 一条 ``STREAM_GAP`` 错误后结束。
        """
        handle = self.get(task_id)

        # 1. 环形缓冲重放
        if last_event_id is not None and last_event_id < handle.oldest_seq() - 1:
            yield {
                "task_id": task_id,
                "seq": handle.seq,
                "event": "task.error",
                "code": "STREAM_GAP",
                "message": "事件游标已滑出缓冲区，请改用任务快照与时间线重新同步",
            }
            return

        replayed_upto = last_event_id or 0
        for payload in list(handle.events):
            if payload["seq"] > replayed_upto:
                yield payload

        # 2. 任务已结束：重放完毕即可收尾
        if handle.finished_at is not None:
            return

        # 3. 订阅实时事件
        queue: asyncio.Queue = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_SIZE)
        handle.subscribers.add(queue)
        try:
            while True:
                item = await queue.get()
                if item is _STREAM_END:
                    return
                yield item
        finally:
            handle.subscribers.discard(queue)

    async def shutdown(self) -> None:
        """取消全部运行中任务（由 lifespan 关闭阶段调用）。"""
        for task_id in list(self._running):
            try:
                await self.cancel(task_id)
            except TaskNotFoundError:
                continue
        logger.info("[TaskRegistry] 已关闭全部运行中任务")
