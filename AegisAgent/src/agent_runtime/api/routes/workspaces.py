"""工作区端点：CRUD 与跨会话共享记忆。

工作区是 Aegis 的一等公民（见 ``06_memory_and_context_management`` §2）：
绑定物理根目录、承载跨会话共享的架构定论与避坑黑名单。
创建按 ``root_path`` **幂等**——同一个工程目录永远只有一个工作区身份。
"""

from __future__ import annotations

from fastapi import APIRouter, status

from agent_runtime.api.deps import MemoryDep
from agent_runtime.api.schemas import (
    FactCreate,
    FailureCreate,
    MemoryView,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceUpdate,
)
from agent_runtime.errors import WorkspaceNotFoundError
from agent_runtime.memory.models import Workspace

__all__ = ["router"]

router = APIRouter(tags=["workspaces"])


def _to_out(workspace: Workspace) -> WorkspaceOut:
    """内部模型 → DTO。"""
    return WorkspaceOut(
        workspace_id=workspace.workspace_id,
        name=workspace.name,
        root_path=workspace.root_path,
        description=workspace.description,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


async def _require_workspace(memory: MemoryDep, workspace_id: str) -> Workspace:
    """取工作区，不存在即抛领域异常（由异常处理器映射为 404）。"""
    workspace = await memory.get_workspace(workspace_id)
    if workspace is None:
        raise WorkspaceNotFoundError(f"工作区不存在: {workspace_id}", context={"workspace_id": workspace_id})
    return workspace


@router.post(
    "/workspaces",
    response_model=WorkspaceOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建工作区（按 root_path 幂等）",
)
async def create_workspace(payload: WorkspaceCreate, memory: MemoryDep) -> WorkspaceOut:
    """创建或返回已存在的同路径工作区。

    Args:
        payload: 创建请求。
        memory: 记忆管理器。

    Returns:
        工作区视图。
    """
    workspace = await memory.create_workspace(
        name=payload.name,
        root_path=payload.root_path,
        description=payload.description,
        workspace_id=payload.workspace_id,
    )
    return _to_out(workspace)


@router.get("/workspaces", response_model=list[WorkspaceOut], summary="列出全部工作区")
async def list_workspaces(memory: MemoryDep) -> list[WorkspaceOut]:
    """按最近活跃时间倒序列出工作区。"""
    return [_to_out(workspace) for workspace in await memory.list_workspaces()]


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceOut, summary="查询工作区")
async def get_workspace(workspace_id: str, memory: MemoryDep) -> WorkspaceOut:
    """按 ID 查询工作区。"""
    return _to_out(await _require_workspace(memory, workspace_id))


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceOut, summary="更新工作区元数据")
async def update_workspace(workspace_id: str, payload: WorkspaceUpdate, memory: MemoryDep) -> WorkspaceOut:
    """更新名称或描述。"""
    await _require_workspace(memory, workspace_id)
    updated = await memory.update_workspace(
        workspace_id, name=payload.name, description=payload.description
    )
    if updated is None:
        raise WorkspaceNotFoundError(f"工作区不存在: {workspace_id}")
    return _to_out(updated)


@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT, summary="级联删除工作区")
async def delete_workspace(workspace_id: str, memory: MemoryDep) -> None:
    """级联删除工作区及其全部会话、流水与记忆。"""
    await _require_workspace(memory, workspace_id)
    await memory.delete_workspace(workspace_id)


@router.get("/workspaces/{workspace_id}/memory", response_model=MemoryView, summary="读取工作区共享记忆")
async def get_workspace_memory(workspace_id: str, memory: MemoryDep) -> MemoryView:
    """读取跨会话共享的架构定论、规范与避坑黑名单。"""
    await _require_workspace(memory, workspace_id)
    record = await memory.get_workspace_memory(workspace_id)
    return MemoryView(
        scope="workspace",
        updated_at=record.updated_at,
        user_profile=list(record.user_profile),
        project_conventions=list(record.project_conventions),
        confirmed_architecture=list(record.confirmed_architecture),
        failed_attempts=[item.model_dump() for item in record.global_failed_attempts],
    )


@router.post(
    "/workspaces/{workspace_id}/memory/facts",
    status_code=status.HTTP_201_CREATED,
    summary="上浮事实到工作区共享记忆",
)
async def promote_fact(workspace_id: str, payload: FactCreate, memory: MemoryDep) -> dict[str, str]:
    """把单会话结论沉淀为工作区级长期记忆。"""
    await _require_workspace(memory, workspace_id)
    await memory.promote_fact_to_workspace(workspace_id, payload.fact, payload.category)
    return {"status": "ok", "category": payload.category}


@router.post(
    "/workspaces/{workspace_id}/memory/failures",
    status_code=status.HTTP_201_CREATED,
    summary="追加全局避坑记录",
)
async def record_failure(workspace_id: str, payload: FailureCreate, memory: MemoryDep) -> dict[str, str]:
    """把踩坑经验沉淀为工作区级负向记忆。"""
    from agent_runtime.state import FailedAttempt

    await _require_workspace(memory, workspace_id)
    await memory.record_global_failure(
        workspace_id,
        FailedAttempt(
            action=payload.action,
            failure_reason=payload.failure_reason,
            conclusion=payload.conclusion,
        ),
    )
    return {"status": "ok"}
