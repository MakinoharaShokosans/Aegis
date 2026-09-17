"""任务级事件总线：把**叶子工具内部**产生的事件接进 SSE 事件流。

对应 ``documents/agent_runtime/11_http_api.md`` §6 与
``13_subagent_delegation.md`` §10 裁决项 6。

## 为什么需要这一层

LangGraph 的节点级流式（``stream_mode="updates"``）**只暴露节点边界**。
子智能体（研究隔离区 / 动态委派）运行在 ``tool_runner`` 内部的**一个工具**里，
它的中间步骤对节点流完全不可见——前端只能看到一个长时间不动的"子任务进行中"。

本对象是**父级推送式绑定**的第三个实例（前两个是 ``BudgetLedger`` 与 ``TaskAuthority``）：

* ``_drive_graph`` 在开始执行前把本轮的 ``event_sink`` 绑进来；
* 叶子工具通过 :meth:`TaskEventBus.emit` 发送事件；
* 事件经 ``TaskRegistry.emit`` 获得序号、写入环形缓冲并广播，从而复用既有的
  断线重连（``Last-Event-ID``）与心跳机制——**不需要新增任何管道**。

## 三条纪律

1. **只发元数据与已裁剪摘要**：:meth:`emit` 会强制把 ``summary`` / ``excerpt`` 字段
   截断到 :data:`MAX_SUMMARY_CHARS`。原始正文仍**不进入**主状态、主 Checkpoint
   与事件流——隔离承诺不因"可观测性"而放宽。
2. **未绑定即静默降级**：非 SSE 运行（如 ``run_agent``）没有 sink，
   :meth:`emit` 只写 debug 日志，不抛异常、不阻塞执行。
3. **可观测性是旁路**：``emit`` **永不向上抛异常**。事件发送失败绝不能让任务失败。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Mapping, Optional

from loguru import logger

__all__ = ["MAX_SUMMARY_CHARS", "EventSink", "TaskEventBus"]

#: 事件流中摘要类字段的字符上限（强制裁剪，防止工具误把长正文塞进事件）
MAX_SUMMARY_CHARS = 300

#: 会被强制裁剪的字段名（摘要语义的字段一律限长）
_TRUNCATABLE_KEYS = ("summary", "excerpt", "detail", "reason")

#: 事件回调签名：接收结构化事件字典。与 ``workflow.EventSink`` 同构。
EventSink = Callable[[Dict[str, Any]], Awaitable[None]]


class TaskEventBus:
    """单任务的事件总线（**可变绑定**，每任务一个实例）。

    刻意不做事件缓冲：SSE 的断线重连由 ``TaskRegistry`` 的环形缓冲负责，
    在这里再存一份会造成"同一事实两处存储"的漂移风险。
    """

    __slots__ = ("_task_id", "_sink", "_emitted")

    def __init__(self, task_id: str = "") -> None:
        """构造总线。

        Args:
            task_id: 所属任务 ID（仅用于日志与事件回填）。
        """
        self._task_id = str(task_id or "")
        self._sink: Optional[EventSink] = None
        self._emitted = 0

    # ==========================================================================
    # 绑定
    # ==========================================================================

    def bind(self, sink: EventSink, task_id: str = "") -> None:
        """绑定本轮的对外事件回调（由 ``workflow._drive_graph`` 调用）。

        Args:
            sink: 事件回调（通常是 ``TaskRegistry.emit`` 的偏函数）。
            task_id: 任务 ID；为空时保留原值。
        """
        self._sink = sink
        if task_id:
            self._task_id = str(task_id)

    def unbind(self) -> None:
        """解绑（任务执行结束，避免闭包持有已完成的注册表句柄）。"""
        self._sink = None

    @property
    def bound(self) -> bool:
        """当前是否已绑定对外回调。"""
        return self._sink is not None

    @property
    def emitted(self) -> int:
        """本任务累计成功发出的事件数（用于自省与排障）。"""
        return self._emitted

    # ==========================================================================
    # 发送
    # ==========================================================================

    async def emit(self, event: Mapping[str, Any]) -> None:
        """发送一条事件（**永不抛异常**）。

        Args:
            event: 事件字典，必须含 ``event`` 键（事件名，如 ``subagent.tool``）。
                摘要类字段会被强制截断到 :data:`MAX_SUMMARY_CHARS`。
        """
        name = str(event.get("event") or "").strip()
        if not name:
            logger.debug("[EventBus] 忽略缺少 event 字段的事件")
            return

        payload: Dict[str, Any] = {"event": name}
        if self._task_id:
            payload["task_id"] = self._task_id
        for key, value in event.items():
            if key == "event":
                continue
            if key in _TRUNCATABLE_KEYS and isinstance(value, str):
                payload[key] = _clip(value)
            else:
                payload[key] = value

        self._emitted += 1

        if self._sink is None:
            # 非流式运行：只留一条 debug，不缓冲、不阻塞
            logger.debug(f"[EventBus] （未绑定 sink）{name} {payload}")
            return

        try:
            await self._sink(payload)
        except Exception as exc:  # noqa: BLE001 - 可观测性旁路失败不得影响任务
            logger.warning(f"[EventBus] 事件发送失败（已忽略）{name}: {exc}")


def _clip(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    """裁剪摘要文本并标注截断。"""
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "…"
