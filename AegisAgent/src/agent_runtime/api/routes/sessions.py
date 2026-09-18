"""会话端点：会话 CRUD、对话流水与上下文检视。

一个工作区可挂载多个会话（1:N），会话之间**认知隔离**：
不同任务线的局部事实与活跃对话互不干扰，只有工作区级记忆共享。
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from agent_runtime.api.deps import ConfigDep, MemoryDep
from agent_runtime.api.schemas import ContextPreview, MemoryView, SessionCreate, SessionOut, TurnOut
from agent_runtime.config import get_config
from agent_runtime.errors import SessionNotFoundError, WorkspaceNotFoundError
from agent_runtime.memory.models import SessionMetadata, TurnRecord

__all__ = ["router"]

router = APIRouter(tags=["sessions"])


def _session_out(session: SessionMetadata) -> SessionOut:
    """内部模型 → DTO。"""
    return SessionOut(
        session_id=session.session_id,
        workspace_id=session.workspace_id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _turn_out(turn: TurnRecord) -> TurnOut:
    """轮次模型 → DTO。"""
    return TurnOut(
        id=int(turn.id or 0),
        role=turn.role,
        content=turn.content,
        token_count=turn.token_count,
        timestamp=turn.timestamp,
    )


async def _require_session(memory: MemoryDep, session_id: str) -> SessionMetadata:
    """取会话，不存在即抛领域异常。"""
    session = await memory.get_session(session_id)
    if session is None:
        raise SessionNotFoundError(f"会话不存在: {session_id}", context={"session_id": session_id})
    return session


@router.post(
    "/workspaces/{workspace_id}/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="在工作区下创建会话",
)
async def create_session(workspace_id: str, payload: SessionCreate, memory: MemoryDep) -> SessionOut:
    """新建一条任务线。"""
    if await memory.get_workspace(workspace_id) is None:
        raise WorkspaceNotFoundError(f"工作区不存在: {workspace_id}")
    session = await memory.create_session(workspace_id=workspace_id, title=payload.title)
    return _session_out(session)


@router.get(
    "/workspaces/{workspace_id}/sessions",
    response_model=list[SessionOut],
    summary="列出工作区下的会话",
)
async def list_sessions(workspace_id: str, memory: MemoryDep) -> list[SessionOut]:
    """按最近活跃时间倒序列出会话。"""
    if await memory.get_workspace(workspace_id) is None:
        raise WorkspaceNotFoundError(f"工作区不存在: {workspace_id}")
    return [_session_out(session) for session in await memory.list_sessions(workspace_id)]


@router.get("/sessions/{session_id}", response_model=SessionOut, summary="查询会话")
async def get_session(session_id: str, memory: MemoryDep) -> SessionOut:
    """按 ID 查询会话元数据。"""
    return _session_out(await _require_session(memory, session_id))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除会话")
async def delete_session(session_id: str, memory: MemoryDep) -> None:
    """级联删除会话及其流水与情境记忆。"""
    await _require_session(memory, session_id)
    await memory.delete_session(session_id)


@router.get("/sessions/{session_id}/turns", response_model=list[TurnOut], summary="分页查询对话流水")
async def list_turns(
    session_id: str,
    memory: MemoryDep,
    limit: int = Query(default=50, ge=1, le=200, description="单页条数"),
    before_id: int | None = Query(default=None, description="向后翻页游标（只取 id 更小的记录）"),
) -> list[TurnOut]:
    """按游标分页读取人机对话流水（返回时间正序）。"""
    await _require_session(memory, session_id)
    turns = await memory.list_turns(session_id, limit=limit, before_id=before_id)
    return [_turn_out(turn) for turn in turns]


@router.get("/sessions/{session_id}/memory", response_model=MemoryView, summary="读取会话已压缩记忆")
async def get_session_memory(session_id: str, memory: MemoryDep) -> MemoryView:
    """读取会话级情境记忆与压缩水位线。"""
    await _require_session(memory, session_id)
    record = await memory.get_compressed_memory(session_id)
    return MemoryView(
        scope="session",
        updated_at=record.updated_at,
        summary=record.summary,
        compacted_until_turn_id=record.compacted_until_turn_id,
        confirmed_facts=list(record.confirmed_facts),
        failed_attempts=[item.model_dump() for item in record.failed_attempts],
        last_action_target=dict(record.last_action_target),
    )


@router.get("/sessions/{session_id}/context", response_model=ContextPreview, summary="上下文检视")
async def preview_context(
    session_id: str,
    memory: MemoryDep,
    config: ConfigDep,
) -> ContextPreview:
    """返回"模型此刻会看到什么"的分层快照，用于前端调试与用户信任建立。

    注意：本端点返回的是**会话级**装配视图，不含某个具体任务的临时状态
    （任务级事实请查 ``/tasks/{task_id}``）。
    """
    session = await _require_session(memory, session_id)
    workspace, workspace_memory, session_memory, active_turns = await memory.load_session_context(
        session_id, workspace_id=session.workspace_id
    )

    context_cfg = get_config().runtime.context
    guardrails_cfg = get_config().runtime.guardrails
    active_tokens = await memory.store.get_active_turns_token_sum(session_id)

    from agent_runtime.tokenizer import count_tokens

    # 1. 第一层：系统提示词与规则（基础底模指令约 850 Token）
    system_tokens = 850

    # 2. 第二层：工作区长期记忆与用户画像
    workspace_mem_text = "\n".join(
        workspace_memory.user_profile
        + workspace_memory.confirmed_architecture
        + workspace_memory.project_conventions
        + [
            f"{item.action} {item.failure_reason} {item.conclusion}"
            for item in workspace_memory.global_failed_attempts
        ]
    )
    workspace_mem_tokens = count_tokens(workspace_mem_text)

    # 3. 第三层：会话级压缩记忆与关键事实
    session_mem_text = (
        session_memory.summary
        + "\n"
        + "\n".join(session_memory.confirmed_facts)
        + "\n"
        + "\n".join(
            f"{item.action} {item.failure_reason} {item.conclusion}"
            for item in session_memory.failed_attempts
        )
    )
    session_mem_tokens = count_tokens(session_mem_text)

    # 4. 第四层：活跃滑窗轮次
    active_turns_tokens = active_tokens

    total_context_tokens = (
        system_tokens + workspace_mem_tokens + session_mem_tokens + active_turns_tokens
    )
    water_level_pct = round(
        (total_context_tokens / max(1, context_cfg.session_token_limit)) * 100, 1
    )

    return ContextPreview(
        workspace={
            "workspace_id": workspace.workspace_id,
            "name": workspace.name,
            "root_path": workspace.root_path,
        },
        workspace_memory={
            "user_profile": list(workspace_memory.user_profile),
            "confirmed_architecture": list(workspace_memory.confirmed_architecture),
            "project_conventions": list(workspace_memory.project_conventions),
            "global_failed_attempts": [
                item.model_dump() for item in workspace_memory.global_failed_attempts
            ],
        },
        session_memory={
            "compacted_until_turn_id": session_memory.compacted_until_turn_id,
            "summary": session_memory.summary,
            "confirmed_facts": list(session_memory.confirmed_facts),
            "failed_attempts": [item.model_dump() for item in session_memory.failed_attempts],
            "last_action_target": dict(session_memory.last_action_target),
        },
        active_turns=[_turn_out(turn) for turn in active_turns],
        budget={
            "session_token_limit": context_cfg.session_token_limit,
            "active_tokens": active_tokens,
            "total_context_tokens": total_context_tokens,
            "water_level_pct": water_level_pct,
            "high_watermark": context_cfg.compaction_high_watermark,
            "compaction_ratio": context_cfg.compaction_ratio,
            "max_task_budget_tokens": guardrails_cfg.max_total_tokens,
        },
        layers_breakdown={
            "system_tokens": system_tokens,
            "workspace_memory_tokens": workspace_mem_tokens,
            "session_memory_tokens": session_mem_tokens,
            "active_turns_tokens": active_turns_tokens,
            "total_context_tokens": total_context_tokens,
        },
    )
