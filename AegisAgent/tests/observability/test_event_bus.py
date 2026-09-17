"""任务级事件总线 (TaskEventBus) 与子智能体事件流专测。

对应 ``documents/agent_runtime/11_http_api.md`` §6 与
``13_subagent_delegation.md`` §10 裁决项 6。
覆盖：
1. TaskEventBus 绑定与解绑状态机 (bind, unbind, bound, emitted)
2. 未绑定静默降级（非 SSE 场景不报错、不阻塞）
3. 摘要字段 300 字符强制限长截断 (_TRUNCATABLE_KEYS & _clip)
4. 异常隔离（可观测性旁路失败绝不影响任务执行）
5. subagent.* (5 类) 与 research.* (3 类) 事件分发契约
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from agent_runtime.observability.event_bus import (
    MAX_SUMMARY_CHARS,
    TaskEventBus,
    _clip,
)


# ==============================================================================
# 1. 基础状态机与生命周期测试
# ==============================================================================


def test_event_bus_initial_state():
    """验证事件总线初始状态：未绑定、发出计数为 0。"""
    bus = TaskEventBus(task_id="task-101")
    assert bus.bound is False
    assert bus.emitted == 0


def test_event_bus_bind_and_unbind():
    """验证 bind 绑定与 unbind 解绑状态切换。"""
    bus = TaskEventBus(task_id="task-101")

    async def mock_sink(event: Dict[str, Any]) -> None:
        pass

    # 1. 绑定
    bus.bind(mock_sink, task_id="task-202")
    assert bus.bound is True

    # 2. 解绑
    bus.unbind()
    assert bus.bound is False


# ==============================================================================
# 2. 事件发送与静默降级测试
# ==============================================================================


@pytest.mark.asyncio
async def test_event_bus_emit_unbound_silent_downgrade():
    """验证在未绑定 sink 时（如 run_agent 非流式运行），emit 静默降级且递增计数。"""
    bus = TaskEventBus(task_id="task-303")
    assert bus.bound is False

    # 发送正常事件 -> 不抛异常，计数 +1
    await bus.emit({"event": "subagent.started", "subagent_id": "sub-1"})
    assert bus.emitted == 1

    await bus.emit({"event": "subagent.finished", "subagent_id": "sub-1"})
    assert bus.emitted == 2


@pytest.mark.asyncio
async def test_event_bus_emit_ignores_empty_event_name():
    """验证缺少或为空的 event 字段被安全忽略，不递增计数。"""
    bus = TaskEventBus(task_id="task-303")

    await bus.emit({})
    assert bus.emitted == 0

    await bus.emit({"event": "   ", "data": 123})
    assert bus.emitted == 0


@pytest.mark.asyncio
async def test_event_bus_emit_with_bound_sink():
    """验证绑定 sink 后事件正确流转，且自动注入 task_id。"""
    bus = TaskEventBus(task_id="task-404")
    received: List[Dict[str, Any]] = []

    async def sink(event: Dict[str, Any]) -> None:
        received.append(event)

    bus.bind(sink)

    await bus.emit({"event": "subagent.step", "step": 1, "action": "search"})
    assert bus.emitted == 1
    assert len(received) == 1
    assert received[0]["event"] == "subagent.step"
    assert received[0]["task_id"] == "task-404"
    assert received[0]["step"] == 1
    assert received[0]["action"] == "search"


# ==============================================================================
# 3. 摘要字段限长与防泄漏测试
# ==============================================================================


def test_clip_helper():
    """验证 _clip 辅助函数的空白规范化与截断逻辑。"""
    # 1. 正常短文本
    assert _clip("Hello world", limit=300) == "Hello world"

    # 2. 多余空白合并
    assert _clip("Hello   \n\t  world", limit=300) == "Hello world"

    # 3. 超过限制截断并加省略号
    long_text = "a" * 350
    clipped = _clip(long_text, limit=300)
    assert len(clipped) == 301  # 300 字符 + 1 字符 '…'
    assert clipped.endswith("…")


@pytest.mark.asyncio
async def test_event_bus_truncates_summary_fields_strictly():
    """验证 summary / excerpt / detail / reason 字段被强制截断到 MAX_SUMMARY_CHARS (300)。"""
    bus = TaskEventBus(task_id="task-505")
    received: List[Dict[str, Any]] = []

    async def sink(event: Dict[str, Any]) -> None:
        received.append(event)

    bus.bind(sink)

    long_payload = {
        "event": "subagent.blocked",
        "subagent_id": "sub-research-9",
        # 4 个需要截断的摘要字段
        "summary": "S" * 500,
        "excerpt": "E" * 400,
        "detail": "D" * 600,
        "reason": "R" * 450,
        # 不受限字段（如 id 或数字）
        "count": 42,
    }

    await bus.emit(long_payload)
    assert len(received) == 1
    item = received[0]

    assert len(item["summary"]) == MAX_SUMMARY_CHARS + 1
    assert item["summary"].endswith("…")

    assert len(item["excerpt"]) == MAX_SUMMARY_CHARS + 1
    assert item["excerpt"].endswith("…")

    assert len(item["detail"]) == MAX_SUMMARY_CHARS + 1
    assert item["detail"].endswith("…")

    assert len(item["reason"]) == MAX_SUMMARY_CHARS + 1
    assert item["reason"].endswith("…")

    assert item["count"] == 42


# ==============================================================================
# 4. 异常隔离测试
# ==============================================================================


@pytest.mark.asyncio
async def test_event_bus_exception_isolation():
    """验证 Sink 抛出异常时，emit 自动捕获隔离，绝不影响任务执行流程。"""
    bus = TaskEventBus(task_id="task-606")

    async def failing_sink(event: Dict[str, Any]) -> None:
        raise ConnectionResetError("SSE 客户端异常断开连接")

    bus.bind(failing_sink)

    # emit 绝不抛异常
    try:
        await bus.emit({"event": "subagent.step", "step": 2})
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"TaskEventBus.emit 不应向上抛出异常: {exc}")

    # 计数仍然增加
    assert bus.emitted == 1


# ==============================================================================
# 5. 子智能体与研究事件分发完整性测试
# ==============================================================================


@pytest.mark.asyncio
async def test_subagent_and_research_lifecycle_events():
    """验证 subagent.* 5 类事件与 research.* 3 类事件的分发格式。"""
    bus = TaskEventBus(task_id="task-707")
    events: List[Dict[str, Any]] = []

    async def sink(event: Dict[str, Any]) -> None:
        events.append(event)

    bus.bind(sink)

    # 1. subagent.started
    await bus.emit({"event": "subagent.started", "subagent_type": "coder", "depth": 1})
    # 2. subagent.step
    await bus.emit({"event": "subagent.step", "step": 1, "thought": "analyzing file"})
    # 3. subagent.tool
    await bus.emit({"event": "subagent.tool", "tool": "view_file", "path": "main.py"})
    # 4. subagent.blocked
    await bus.emit({"event": "subagent.blocked", "reason": "越级操作被拒"})
    # 5. subagent.finished
    await bus.emit({"event": "subagent.finished", "success": True})

    # 6. research.started
    await bus.emit({"event": "research.started", "topic": "Qdrant RRF"})
    # 7. research.round
    await bus.emit({"event": "research.round", "round": 1, "query": "RRF formula"})
    # 8. research.finished
    await bus.emit({"event": "research.finished", "sources_count": 3})

    assert len(events) == 8
    event_names = [e["event"] for e in events]
    assert event_names == [
        "subagent.started",
        "subagent.step",
        "subagent.tool",
        "subagent.blocked",
        "subagent.finished",
        "research.started",
        "research.round",
        "research.finished",
    ]
