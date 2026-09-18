"""任务端点：提交、状态、SSE 事件流、续跑、取消、时间线与轨迹。

对应 ``documents/agent_runtime/11_http_api.md`` §4.4、§5、§6。

**只登记不阻塞**：``POST /tasks`` 立即返回任务 ID，真正的执行在后台协程中进行，
进度通过 SSE 推送。前端必须能容忍"流中断 → 拉取快照重新同步"。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import PlainTextResponse
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from agent_runtime.api.deps import ConfigDep, RegistryDep, RuntimeDep
from agent_runtime.api.schemas import (
    ApproveRequest,
    RejectRequest,
    TaskOut,
    TaskSubmit,
    TimelineItem,
)

__all__ = ["router"]

router = APIRouter(tags=["tasks"])

#: 事件流结束哨兵
_STREAM_END = object()

#: 事件名 → SSE event 字段的直通集合
#:
#: 不在本集合内的事件会被降级为 ``message``（**白名单而非黑名单**：
#: 新增事件类型必须显式登记，避免内部事件意外泄漏到前端契约里）。
_KNOWN_EVENTS = {
    "task.started",
    "node.started",
    "node.finished",
    "plan",
    "tool.call",
    "tool.result",
    "task.waiting_for_approval",
    "task.approved",
    "task.rejected",
    "milestone.updated",
    "guard.warning",
    "task.finished",
    "task.error",
    "heartbeat",
    # 子智能体中间步骤（叶子工具内部，节点级流式不可见 → 经事件总线外发）
    "subagent.started",
    "subagent.step",
    "subagent.tool",
    "subagent.blocked",
    "subagent.finished",
    "research.started",
    "research.round",
    "research.finished",
    # 大模型底层 HTTP / Prompt 请求与应答透视
    "llm.call",
}


def _project_timeline(state: Dict[str, Any], limit: int) -> List[TimelineItem]:
    """把 ``AgentState.messages`` 投影为可渲染的时间线。

    LangChain 消息对象**绝不**直接外发；这里只保留角色、类型与精炼摘要，
    并把被裁剪的内容替换为产物句柄引用。

    Args:
        state: 任务终态或当前状态。
        limit: 最多返回的条目数（取最近 N 条）。

    Returns:
        时间线条目列表（时间正序）。
    """
    items: List[TimelineItem] = []
    messages: List[BaseMessage] = list(state.get("messages") or [])

    for index, message in enumerate(messages, start=1):
        if isinstance(message, ToolMessage):
            items.append(
                TimelineItem(
                    seq=index,
                    type="tool_result",
                    role="tool",
                    summary=str(message.content)[:2000],
                )
            )
        elif isinstance(message, SystemMessage):
            items.append(
                TimelineItem(seq=index, type="system_notice", role="system", summary=str(message.content)[:2000])
            )
        elif isinstance(message, AIMessage):
            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                for call in tool_calls:
                    items.append(
                        TimelineItem(
                            seq=index,
                            type="tool_call",
                            role="assistant",
                            summary=f"{call.get('name', '?')}({json.dumps(call.get('args', {}), ensure_ascii=False)[:400]})",
                        )
                    )
            else:
                items.append(
                    TimelineItem(
                        seq=index,
                        type="plan",
                        role="assistant",
                        summary=str(message.content)[:2000],
                    )
                )
        else:
            items.append(
                TimelineItem(seq=index, type="thought", role="user", summary=str(message.content)[:2000])
            )

    return items[-limit:] if limit > 0 else items


@router.post(
    "/sessions/{session_id}/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="提交任务（异步执行）",
)
async def submit_task(
    session_id: str,
    payload: TaskSubmit,
    runtime: RuntimeDep,
    registry: RegistryDep,
) -> TaskOut:
    """登记任务并在后台开始执行。

    Args:
        session_id: 会话标识。
        payload: 提交请求。
        runtime: 进程级运行时。
        registry: 任务注册表。

    Returns:
        任务状态快照（``status=queued``）。
    """
    session = await runtime.memory.get_session(session_id)
    if session is None:
        from agent_runtime.errors import SessionNotFoundError

        raise SessionNotFoundError(f"会话不存在: {session_id}", context={"session_id": session_id})

    handle = await registry.submit(
        runtime,
        workspace_id=session.workspace_id,
        session_id=session_id,
        task_goal=payload.task_goal,
        permission_level=payload.permission_level,
    )
    return handle.to_out()


@router.get("/tasks/{task_id}", response_model=TaskOut, summary="查询任务状态")
async def get_task(task_id: str, registry: RegistryDep) -> TaskOut:
    """返回任务状态快照（**不是** AgentState）。"""
    return registry.get(task_id).to_out()


@router.post(
    "/tasks/{task_id}/approve",
    status_code=status.HTTP_200_OK,
    summary="批准越级操作并恢复执行（HITL）",
)
async def approve_task(
    task_id: str,
    payload: ApproveRequest,
    runtime: RuntimeDep,
    registry: RegistryDep,
) -> Dict[str, Any]:
    """批准挂起中的越级操作。

    Args:
        task_id: 任务 ID。
        payload: ``decision`` 为 ``once``（仅本次）或 ``always``（加入会话白名单）。
        runtime: 进程级运行时。
        registry: 任务注册表。

    Returns:
        ``{"task_id", "status", "message"}``；图执行在后台恢复。
    """
    handle = await registry.submit_decision(
        runtime,
        task_id,
        approved=True,
        scope=payload.decision,
        approval_id=payload.approval_id or "",
    )
    return {
        "task_id": task_id,
        "status": handle.status,
        "message": "Approval granted, resuming execution.",
    }


@router.post(
    "/tasks/{task_id}/reject",
    status_code=status.HTTP_200_OK,
    summary="拒绝越级操作并反馈重规划（HITL）",
)
async def reject_task(
    task_id: str,
    payload: RejectRequest,
    runtime: RuntimeDep,
    registry: RegistryDep,
) -> Dict[str, Any]:
    """拒绝挂起中的越级操作。

    拒绝理由会作为工具观察值回灌给模型，驱动其给出合规的替代方案。

    Args:
        task_id: 任务 ID。
        payload: 拒绝理由。
        runtime: 进程级运行时。
        registry: 任务注册表。

    Returns:
        ``{"task_id", "status", "message"}``。
    """
    handle = await registry.submit_decision(
        runtime,
        task_id,
        approved=False,
        reason=payload.reason,
        approval_id=payload.approval_id or "",
    )
    return {
        "task_id": task_id,
        "status": handle.status,
        "message": "Rejection feedback sent to planner, resuming execution.",
    }


@router.post("/tasks/{task_id}/resume", response_model=TaskOut, status_code=status.HTTP_202_ACCEPTED, summary="续跑任务")
async def resume_task(task_id: str, runtime: RuntimeDep, registry: RegistryDep) -> TaskOut:
    """从最近一次 Checkpoint 继续执行。"""
    handle = await registry.resume(runtime, task_id)
    return handle.to_out()


@router.post("/tasks/{task_id}/cancel", status_code=status.HTTP_202_ACCEPTED, summary="取消任务")
async def cancel_task(task_id: str, registry: RegistryDep) -> dict[str, str]:
    """请求取消任务（在节点边界生效）。"""
    await registry.cancel(task_id)
    return {"status": "cancelling", "task_id": task_id}


@router.get("/tasks/{task_id}/timeline", response_model=list[TimelineItem], summary="查询执行时间线")
async def get_timeline(
    task_id: str,
    registry: RegistryDep,
    limit: int = Query(default=100, ge=1, le=500, description="返回最近 N 条"),
) -> List[TimelineItem]:
    """把任务消息投影为可渲染的时间线。"""
    handle = registry.get(task_id)
    if handle.state is None:
        return []
    return _project_timeline(dict(handle.state), limit)


@router.get("/tasks/{task_id}/trace", summary="下载全量因果轨迹（NDJSON）")
async def download_trace(task_id: str, config: ConfigDep, registry: RegistryDep) -> PlainTextResponse:
    """返回 ``storage/traces/{task_id}.jsonl`` 全文。

    Args:
        task_id: 任务 ID。
        config: 全局配置。
        registry: 任务注册表（用于校验任务存在）。

    Returns:
        NDJSON 文本响应。
    """
    registry.get(task_id)  # 不存在会抛 TaskNotFoundError
    trace_path = Path(config.runtime.storage.traces_dir) / f"{task_id}.jsonl"

    # 防御：即使 task_id 来自路径参数，也必须落在轨迹目录之内
    resolved = trace_path.resolve()
    traces_root = Path(config.runtime.storage.traces_dir).resolve()
    if traces_root not in resolved.parents and resolved.parent != traces_root:
        from agent_runtime.errors import PathEscapeDetectedError

        raise PathEscapeDetectedError("轨迹路径越界", context={"task_id": task_id})

    if not resolved.is_file():
        from agent_runtime.errors import ArtifactNotFoundError

        raise ArtifactNotFoundError("轨迹文件不存在（任务可能尚未产生任何步骤）", context={"task_id": task_id})

    return PlainTextResponse(
        content=resolved.read_text(encoding="utf-8", errors="replace"),
        media_type="application/x-ndjson",
    )


@router.get("/tasks/{task_id}/llm_calls", summary="获取任务的全部底层大模型调用记录")
async def get_task_llm_calls(task_id: str, registry: RegistryDep) -> List[Dict[str, Any]]:
    """返回任务在运行期产生的全部底层大模型请求/应答快照记录。"""
    handle = registry.get(task_id)
    return [ev for ev in handle.events if ev.get("event") == "llm.call"]


@router.get("/tasks/{task_id}/stream", summary="订阅任务事件流（SSE）")
async def stream_task(
    task_id: str,
    request: Request,
    runtime: RuntimeDep,
    registry: RegistryDep,
) -> EventSourceResponse:
    """以 SSE 推送任务执行事件。

    支持 ``Last-Event-ID`` 断线重连：服务端从环形缓冲重放其后事件；
    若游标已滑出缓冲，会先推送 ``STREAM_GAP`` 错误再结束，前端应改用
    ``/tasks/{id}`` 与 ``/timeline`` 做全量重新同步。

    Args:
        task_id: 任务 ID。
        request: 请求对象（读取 ``Last-Event-ID``）。
        runtime: 进程级运行时。
        registry: 任务注册表。

    Returns:
        SSE 响应。
    """
    registry.get(task_id)  # 校验存在性

    heartbeat_sec = float(runtime.config.server.sse_heartbeat_sec)
    last_event_id_header = request.headers.get("Last-Event-ID", "")
    last_event_id: Optional[int] = None
    if last_event_id_header.strip().isdigit():
        last_event_id = int(last_event_id_header.strip())

    async def event_generator() -> AsyncIterator[Dict[str, Any]]:
        """把注册表事件流转译为 SSE 帧，并在空闲时发送心跳。"""
        local: asyncio.Queue = asyncio.Queue()

        async def pump() -> None:
            """把注册表事件搬进本地队列（避免直接对异步生成器做超时取消）。"""
            try:
                async for payload in registry.stream(task_id, last_event_id):
                    await local.put(payload)
            except Exception as exc:  # noqa: BLE001 - 事件源异常不应让连接悬挂
                logger.error(f"[SSE] 事件源异常 task={task_id}: {exc}")
            finally:
                await local.put(_STREAM_END)

        pump_task = asyncio.create_task(pump())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(local.get(), timeout=heartbeat_sec)
                except asyncio.TimeoutError:
                    # 心跳：保持连接与中间代理存活
                    yield {"event": "heartbeat", "data": json.dumps({"task_id": task_id})}
                    continue

                if item is _STREAM_END:
                    return

                event_name = str(item.get("event", "message"))
                if event_name not in _KNOWN_EVENTS:
                    event_name = "message"
                yield {
                    "event": event_name,
                    "id": str(item.get("seq", "")),
                    "data": json.dumps(item, ensure_ascii=False, default=str),
                }
        finally:
            pump_task.cancel()

    return EventSourceResponse(event_generator())
