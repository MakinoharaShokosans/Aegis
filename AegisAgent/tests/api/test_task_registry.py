"""TaskRegistry 任务注册表、会话白名单与生命周期状态机测试 (api/task_registry.py)。"""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from agent_runtime.api.task_registry import TaskHandle, TaskRegistry
from agent_runtime.errors import (
    TaskAlreadyRunningError,
    TaskNotFoundError,
    TaskQueueFullError,
)
from agent_runtime.workflow import TaskOutcome


# ==============================================================================
# 1. 任务基础登记与并发控制
# ==============================================================================

@pytest.mark.asyncio
async def test_task_registry_submit_and_get():
    """测试任务基本登记、查询与 DTO 投影。"""
    registry = TaskRegistry(max_concurrent=2)
    mock_deps = AsyncMock()
    mock_deps.config.permissions.default_level = "workspace_write"

    # 用 mock 替换后台协程执行
    with patch.object(registry, "_run", new_callable=AsyncMock):
        handle = await registry.submit(
            mock_deps,
            workspace_id="ws_1",
            session_id="sess_1",
            task_goal="测试任务目标",
            permission_level="read_only",
        )

        assert handle.task_id is not None
        assert handle.workspace_id == "ws_1"
        assert handle.session_id == "sess_1"
        assert handle.permission_level == "read_only"

        # 查询句柄
        fetched = registry.get(handle.task_id)
        assert fetched.task_id == handle.task_id

        # 投影为 TaskOut DTO
        dto = handle.to_out()
        assert dto.task_id == handle.task_id
        assert dto.status == "queued"
        assert dto.permission_level == "read_only"


@pytest.mark.asyncio
async def test_task_registry_concurrency_and_session_conflict():
    """测试同一会话并发冲突与全局并发上限拦截。"""
    registry = TaskRegistry(max_concurrent=1)
    mock_deps = AsyncMock()
    mock_deps.config.permissions.default_level = "workspace_write"

    with patch.object(registry, "_run", new_callable=AsyncMock):
        # 1. 提交第一个任务
        await registry.submit(
            mock_deps,
            workspace_id="ws_1",
            session_id="sess_1",
            task_goal="任务 1",
        )

        # 2. 对同一会话并发提交 -> 抛 TaskAlreadyRunningError
        with pytest.raises(TaskAlreadyRunningError):
            await registry.submit(
                mock_deps,
                workspace_id="ws_1",
                session_id="sess_1",
                task_goal="任务 2",
            )

        # 3. 对不同会话提交但超出 max_concurrent(1) -> 抛 TaskQueueFullError
        with pytest.raises(TaskQueueFullError):
            await registry.submit(
                mock_deps,
                workspace_id="ws_1",
                session_id="sess_2",
                task_goal="任务 3",
            )


# ==============================================================================
# 2. HITL 审批状态迁移与会话白名单存活
# ==============================================================================

@pytest.mark.asyncio
async def test_task_registry_apply_outcome_waiting_for_approval():
    """测试图挂起时 _apply_outcome 正确置位 waiting_for_approval 与 approval_request。"""
    registry = TaskRegistry()
    handle = TaskHandle(
        task_id="t_appr",
        session_id="s_1",
        workspace_id="w_1",
        task_goal="构建测试",
    )
    registry._tasks[handle.task_id] = handle

    outcome = TaskOutcome(
        state={"task_id": "t_appr", "step_count": 2, "total_tokens": 100},
        approval_request={
            "approval_id": "appr_999",
            "required_level": "full_permissions",
            "current_level": "workspace_write",
            "action_type": "network_egress",
            "command": "git push",
            "reason": "需要外联权限",
        },
    )

    await registry._apply_outcome(handle, outcome)

    assert handle.status == "waiting_for_approval"
    assert handle.approval_request is not None
    assert handle.approval_request["approval_id"] == "appr_999"
    dto = handle.to_out()
    assert dto.status == "waiting_for_approval"
    assert dto.approval_request.approval_id == "appr_999"


@pytest.mark.asyncio
async def test_task_registry_submit_decision_and_allowlist():
    """测试提交审批决策、恢复执行与会话白名单管理。"""
    registry = TaskRegistry()
    mock_deps = AsyncMock()

    handle = TaskHandle(
        task_id="t_appr_2",
        session_id="s_session_x",
        workspace_id="w_1",
        task_goal="构建测试",
        status="waiting_for_approval",
        approval_request={"approval_id": "appr_xyz"},
    )
    registry._tasks[handle.task_id] = handle

    # 1. 针对非 waiting 状态的任务提交决策 -> 报错
    with pytest.raises(TaskAlreadyRunningError):
        invalid_handle = TaskHandle(task_id="t_run", session_id="s_2", workspace_id="w_1", task_goal="g", status="running")
        registry._tasks["t_run"] = invalid_handle
        await registry.submit_decision(mock_deps, "t_run", approved=True)

    # 2. 正常提交批准决策（附带 scope="always"）
    with patch.object(registry, "_run", new_callable=AsyncMock):
        resumed_handle = await registry.submit_decision(
            mock_deps,
            "t_appr_2",
            approved=True,
            scope="always",
            approval_id="appr_xyz",
        )
        assert resumed_handle.status == "queued"
        assert resumed_handle.approval_request is None

        # 验证会话级白名单集合已创建
        allowlist = registry._allowlist_for("s_session_x")
        assert isinstance(allowlist, set)


# ==============================================================================
# 3. SSE 事件流与游标重放
# ==============================================================================

@pytest.mark.asyncio
async def test_task_registry_event_stream_and_replay():
    """测试事件广播与 Last-Event-ID 游标重放机制。"""
    registry = TaskRegistry(buffer_size=10)
    handle = TaskHandle(
        task_id="t_stream",
        session_id="s_1",
        workspace_id="w_1",
        task_goal="流式测试",
    )
    registry._tasks[handle.task_id] = handle

    # 发送 3 个事件
    await registry.emit("t_stream", {"event": "node.started", "node": "planner"})
    await registry.emit("t_stream", {"event": "node.finished", "node": "planner"})
    await registry.emit("t_stream", {"event": "task.waiting_for_approval", "approval_id": "appr_1"})

    assert len(handle.events) == 3
    assert handle.events[0]["seq"] == 1
    assert handle.events[2]["seq"] == 3

    # 重放从 seq=2 之后的事件
    handle.finished_at = 1000.0  # 标记已完成以退出生成器
    replayed = []
    async for event in registry.stream("t_stream", last_event_id=2):
        replayed.append(event)

    assert len(replayed) == 1
    assert replayed[0]["seq"] == 3
    assert replayed[0]["event"] == "task.waiting_for_approval"


# ==============================================================================
# 4. Phase 6: 真实并发与竞态测试 (Concurrency & Race Conditions)
# ==============================================================================

@pytest.mark.asyncio
async def test_task_registry_real_coroutine_concurrency():
    """6.1 不 patch _run，真实协程交错调度下的多会话并发执行与队列一致性。"""
    registry = TaskRegistry(max_concurrent=3)
    mock_deps = AsyncMock()
    mock_deps.config.permissions.default_level = "workspace_write"

    # 用 fast dummy run_streaming 模拟真实异步 I/O 耗时
    async def mock_streaming(*args, **kwargs):
        await asyncio.sleep(0.02)
        event_sink = kwargs.get("event_sink")
        if callable(event_sink):
            await event_sink({"event": "node.finished", "node": "evaluator"})
        return TaskOutcome(
            state={"task_id": kwargs.get("task_id"), "step_count": 1, "termination_reason": "task_goal achieved"},
            approval_request=None,
        )

    with patch("agent_runtime.api.task_registry.run_streaming", side_effect=mock_streaming):
        # 并发提交 3 个不同会话的任务
        handles = await asyncio.gather(
            registry.submit(mock_deps, workspace_id="ws_1", session_id="s_c1", task_goal="g1"),
            registry.submit(mock_deps, workspace_id="ws_1", session_id="s_c2", task_goal="g2"),
            registry.submit(mock_deps, workspace_id="ws_1", session_id="s_c3", task_goal="g3"),
        )

        assert len(handles) == 3
        # 等待后台全部真实协程运行结束
        await asyncio.gather(*(h.runner for h in handles if h.runner))

        # 校验全部任务最终状态
        for h in handles:
            assert h.status == "succeeded"
            assert h.finished_at is not None
        assert registry.running_count == 0


@pytest.mark.asyncio
async def test_task_registry_concurrent_approve_vs_reject_race():
    """6.2 对同一 waiting_for_approval 任务真正并发发起 approve 与 reject 的竞态互斥测试。"""
    registry = TaskRegistry(max_concurrent=2)
    mock_deps = AsyncMock()

    handle = TaskHandle(
        task_id="t_race_appr",
        session_id="s_race",
        workspace_id="w_1",
        task_goal="竞态测试",
        status="waiting_for_approval",
        approval_request={"approval_id": "appr_race_target"},
    )
    registry._tasks[handle.task_id] = handle

    async def mock_resume(*args, **kwargs):
        await asyncio.sleep(0.01)
        return TaskOutcome(
            state={"task_id": handle.task_id, "step_count": 2, "termination_reason": "task_goal achieved"},
            approval_request=None,
        )

    with patch("agent_runtime.api.task_registry.resume_agent", side_effect=mock_resume):
        # 真正并发发起 approve 和 reject 请求
        res1, res2 = await asyncio.gather(
            registry.submit_decision(mock_deps, handle.task_id, approved=True, approval_id="appr_race_target"),
            registry.submit_decision(mock_deps, handle.task_id, approved=False, approval_id="appr_race_target"),
            return_exceptions=True,
        )

        # 必有且仅有一方成功，另一方被原子锁拦截抛出 TaskAlreadyRunningError
        successes = [r for r in (res1, res2) if isinstance(r, TaskHandle)]
        errors = [r for r in (res1, res2) if isinstance(r, TaskAlreadyRunningError)]

        assert len(successes) == 1
        assert len(errors) == 1
        assert "任务当前不处于等待审批状态" in str(errors[0].message)

        # 等待胜出的 runner 结束
        winner_handle = successes[0]
        if winner_handle.runner:
            await winner_handle.runner


@pytest.mark.asyncio
async def test_task_registry_concurrent_allowlist_writes():
    """6.3 多个协程并发向同一 session_id 写入 scope=always 白名单的安全性。"""
    registry = TaskRegistry()
    session_id = "sess_concurrent_allowlist"

    async def write_signature(sig: str):
        await asyncio.sleep(0.001)
        allowlist = registry._allowlist_for(session_id)
        allowlist.add(sig)

    signatures = [f"sig_{i}" for i in range(100)]
    await asyncio.gather(*(write_signature(sig) for sig in signatures))

    final_allowlist = registry._allowlist_for(session_id)
    assert len(final_allowlist) == 100
    assert final_allowlist == set(signatures)


@pytest.mark.asyncio
async def test_task_registry_concurrent_multi_subscriber_sse():
    """6.4 多个订阅者并发消费同一任务的 SSE 广播，测试独立队列与游标重放。"""
    registry = TaskRegistry(buffer_size=50)
    handle = TaskHandle(
        task_id="t_multi_sub",
        session_id="s_multi",
        workspace_id="w_1",
        task_goal="多订阅者测试",
        status="running",
    )
    registry._tasks[handle.task_id] = handle

    # 先发 3 个历史事件
    await registry.emit(handle.task_id, {"event": "step.1"})
    await registry.emit(handle.task_id, {"event": "step.2"})
    await registry.emit(handle.task_id, {"event": "step.3"})

    # 订阅者 1：从头订阅 (last_event_id=0)
    # 订阅者 2：从 seq=2 之后断线重连重放
    sub1_events = []
    sub2_events = []

    async def consume_sub1():
        async for evt in registry.stream(handle.task_id, last_event_id=0):
            sub1_events.append(evt)

    async def consume_sub2():
        async for evt in registry.stream(handle.task_id, last_event_id=2):
            sub2_events.append(evt)

    task1 = asyncio.create_task(consume_sub1())
    task2 = asyncio.create_task(consume_sub2())

    await asyncio.sleep(0.01)

    # 发送实时动态事件
    await registry.emit(handle.task_id, {"event": "step.4_live"})
    await registry.emit(handle.task_id, {"event": "step.5_live"})

    # 结束任务并关闭流
    handle.finished_at = 1000.0
    registry._close_subscribers(handle)

    await asyncio.gather(task1, task2)

    # 订阅者 1 应收到全部 5 个事件 (seq 1..5)
    assert len(sub1_events) == 5
    assert [e["seq"] for e in sub1_events] == [1, 2, 3, 4, 5]

    # 订阅者 2 从 2 之后开始，应收到 seq 3, 4, 5
    assert len(sub2_events) == 3
    assert [e["seq"] for e in sub2_events] == [3, 4, 5]

