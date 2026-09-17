"""工作区文件树、读取与保存端点。

严格以工作区 ``root_path`` 为物理安全边界：
所有路径参数必须解析后校验落在 ``root_path`` 之内，彻底防御路径穿越攻击（Path Traversal）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, status

from agent_runtime.api.deps import MemoryDep
from agent_runtime.api.schemas import (
    FileContentOut,
    FileContentUpdate,
    FileItem,
    FileTreeResponse,
)
from agent_runtime.errors import PathEscapeDetectedError, WorkspaceNotFoundError
from agent_runtime.memory.models import Workspace

__all__ = ["router"]

router = APIRouter(tags=["files"])

#: 扫描时忽略的目录名
_IGNORED_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    "coverage",
    "htmlcov",
    ".pytest_cache",
    ".hypothesis",
    ".mypy_cache",
    ".ruff_cache",
    "storage",
    ".cache",
    ".turbo",
}

#: 单文件读取上限（5 MB）
_MAX_FILE_BYTES = 5_000_000

#: 扩展名 → 语言标识映射
_EXTENSION_LANG_MAP = {
    ".py": "python",
    ".md": "markdown",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sh": "shell",
    ".bash": "shell",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".txt": "plaintext",
    ".ini": "ini",
    ".env": "properties",
}


def _infer_language(file_path: Path) -> str:
    """根据文件后缀推断语言/高亮语法标识。"""
    ext = file_path.suffix.lower()
    return _EXTENSION_LANG_MAP.get(ext, "plaintext")


async def _require_workspace(memory: MemoryDep, workspace_id: str) -> Workspace:
    """取工作区，不存在即抛领域异常。"""
    workspace = await memory.get_workspace(workspace_id)
    if workspace is None:
        raise WorkspaceNotFoundError(f"工作区不存在: {workspace_id}", context={"workspace_id": workspace_id})
    return workspace


def _build_tree(root_dir: Path, current_dir: Path, max_depth: int = 8, current_depth: int = 0) -> List[FileItem]:
    """递归构建工作区文件树。"""
    if current_depth > max_depth:
        return []

    items: List[FileItem] = []
    try:
        entries = sorted(current_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return []

    for entry in entries:
        if entry.name in _IGNORED_DIRS or entry.name.startswith("."):
            continue

        rel_path = entry.relative_to(root_dir).as_posix()
        if entry.is_dir():
            children = _build_tree(root_dir, entry, max_depth, current_depth + 1)
            items.append(
                FileItem(
                    path=rel_path,
                    name=entry.name,
                    type="directory",
                    size_bytes=0,
                    updated_at=entry.stat().st_mtime if entry.exists() else 0.0,
                    children=children,
                )
            )
        elif entry.is_file():
            stat = entry.stat()
            items.append(
                FileItem(
                    path=rel_path,
                    name=entry.name,
                    type="file",
                    size_bytes=stat.st_size,
                    updated_at=stat.st_mtime,
                    language=_infer_language(entry),
                )
            )

    return items


@router.get(
    "/workspaces/{workspace_id}/files/tree",
    response_model=FileTreeResponse,
    summary="获取工作区文件与规范目录树",
)
async def get_file_tree(workspace_id: str, memory: MemoryDep) -> FileTreeResponse:
    """返回工作区内有效文件与文档的树形结构。"""
    workspace = await _require_workspace(memory, workspace_id)
    root = Path(workspace.root_path).resolve()

    if not root.is_dir():
        return FileTreeResponse(
            workspace_id=workspace_id,
            root_path=str(root),
            items=[],
        )

    items = _build_tree(root, root)
    return FileTreeResponse(
        workspace_id=workspace_id,
        root_path=str(root),
        items=items,
    )


@router.get(
    "/workspaces/{workspace_id}/files/content",
    response_model=FileContentOut,
    summary="读取工作区内指定文件/文档内容",
)
async def get_file_content(
    workspace_id: str,
    path: str = Query(..., description="相对工作区根目录的路径"),
    memory: MemoryDep = None,
) -> FileContentOut:
    """读取工作区内文档或源码的文本内容。"""
    workspace = await _require_workspace(memory, workspace_id)
    root = Path(workspace.root_path).resolve()
    target = (root / path).resolve()

    # 严格安全防穿越校验
    if root != target and root not in target.parents:
        raise PathEscapeDetectedError(
            f"目标路径越出工作区边界: {path}",
            context={"path": path, "root_path": str(root)},
        )

    if not target.is_file():
        from agent_runtime.errors import ArtifactNotFoundError

        raise ArtifactNotFoundError(f"文件不存在: {path}", context={"path": path})

    stat = target.stat()
    if stat.st_size > _MAX_FILE_BYTES:
        content = f"[文件过大 ({stat.st_size} 字节)，超出 5MB 读取限制]"
    else:
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            content = f"[读取文件失败: {exc}]"

    return FileContentOut(
        workspace_id=workspace_id,
        path=path,
        content=content,
        size_bytes=stat.st_size,
        language=_infer_language(target),
        updated_at=stat.st_mtime,
    )


@router.put(
    "/workspaces/{workspace_id}/files/content",
    status_code=status.HTTP_200_OK,
    summary="保存或修改工作区内文件/文档内容",
)
async def save_file_content(
    workspace_id: str,
    payload: FileContentUpdate,
    memory: MemoryDep,
) -> Dict[str, Any]:
    """保存工作区内文件的新文本内容。"""
    workspace = await _require_workspace(memory, workspace_id)
    root = Path(workspace.root_path).resolve()
    target = (root / payload.path).resolve()

    # 严格安全防穿越校验
    if root != target and root not in target.parents:
        raise PathEscapeDetectedError(
            f"目标路径越出工作区边界: {payload.path}",
            context={"path": payload.path, "root_path": str(root)},
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    stat = target.stat()

    return {
        "status": "ok",
        "path": payload.path,
        "size_bytes": stat.st_size,
        "updated_at": stat.st_mtime,
    }
