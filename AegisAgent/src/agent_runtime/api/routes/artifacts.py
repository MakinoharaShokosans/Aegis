"""产物端点：列出与下载任务产生的离线卸载文件。

**路径安全是硬要求**：artifact 的磁盘路径由服务端维护映射（``artifact_id → path``），
客户端**只能提交 ID**。解析后仍要复核最终路径落在 ``artifacts_dir`` 之内，
避免通过伪造 ID 读取任意文件。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from agent_runtime.api.deps import ConfigDep, RegistryDep
from agent_runtime.api.schemas import ArtifactDescriptor
from agent_runtime.errors import ArtifactNotFoundError, PathEscapeDetectedError

__all__ = ["router"]

router = APIRouter(tags=["artifacts"])

#: 单个产物的最大下载体积（超出则提示改用分片/命令行工具）
_MAX_DOWNLOAD_BYTES = 5_000_000


@router.get("/tasks/{task_id}/artifacts", response_model=list[ArtifactDescriptor], summary="列出任务产物")
async def list_artifacts(task_id: str, registry: RegistryDep, config: ConfigDep) -> list[ArtifactDescriptor]:
    """列出该任务离线落盘的产物句柄。

    Args:
        task_id: 任务 ID。
        registry: 任务注册表。
        config: 全局配置。

    Returns:
        产物描述列表。
    """
    handle = registry.get(task_id)
    artifacts = dict((handle.state or {}).get("artifacts") or {})
    artifacts_root = Path(config.runtime.storage.artifacts_dir)
    preview_chars = int(config.server.artifact_preview_chars)

    descriptors: list[ArtifactDescriptor] = []
    for artifact_id, raw_path in artifacts.items():
        path = Path(raw_path)
        size = path.stat().st_size if path.is_file() else 0
        preview = ""
        if path.is_file() and size > 0:
            try:
                preview = path.read_text(encoding="utf-8", errors="replace")[:preview_chars]
            except OSError:
                preview = ""
        descriptors.append(
            ArtifactDescriptor(
                artifact_id=artifact_id,
                task_id=task_id,
                size_bytes=size,
                created_at=path.stat().st_mtime if path.is_file() else 0.0,
                preview=preview,
            )
        )
    return descriptors


@router.get("/tasks/{task_id}/artifacts/{artifact_id}", summary="下载产物原文")
async def download_artifact(
    task_id: str,
    artifact_id: str,
    registry: RegistryDep,
    config: ConfigDep,
) -> PlainTextResponse:
    """读取产物全文。

    Args:
        task_id: 任务 ID。
        artifact_id: 产物句柄标识。
        registry: 任务注册表。
        config: 全局配置。

    Returns:
        文本响应。

    Raises:
        ArtifactNotFoundError: 句柄不存在或文件已清理。
        PathEscapeDetectedError: 解析后的路径越出产物目录。
    """
    handle = registry.get(task_id)
    artifacts = dict((handle.state or {}).get("artifacts") or {})
    raw_path = artifacts.get(artifact_id)
    if not raw_path:
        raise ArtifactNotFoundError(
            f"产物句柄不存在: {artifact_id}",
            context={"task_id": task_id, "artifact_id": artifact_id},
        )

    resolved = Path(raw_path).resolve()
    artifacts_root = Path(config.runtime.storage.artifacts_dir).resolve()
    if artifacts_root != resolved and artifacts_root not in resolved.parents:
        raise PathEscapeDetectedError(
            "产物路径越界，已拒绝读取", context={"artifact_id": artifact_id}
        )
    if not resolved.is_file():
        raise ArtifactNotFoundError("产物文件已不存在（可能已被清理）", context={"artifact_id": artifact_id})

    size = resolved.stat().st_size
    if size > _MAX_DOWNLOAD_BYTES:
        return PlainTextResponse(
            content=f"[产物过大（{size} 字节），请直接读取磁盘文件: {resolved}]",
            media_type="text/plain; charset=utf-8",
        )

    return PlainTextResponse(
        content=resolved.read_text(encoding="utf-8", errors="replace"),
        media_type="text/plain; charset=utf-8",
    )
