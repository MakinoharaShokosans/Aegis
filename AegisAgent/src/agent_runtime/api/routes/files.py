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
    DirectoryBrowseResponse,
    DirectoryEntry,
    FileContentOut,
    FileContentUpdate,
    FileItem,
    FileTreeResponse,
    QuickLocation,
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


@router.get(
    "/system/fs/directories",
    response_model=DirectoryBrowseResponse,
    summary="浏览并选择本地目录",
)
async def browse_directories(
    path: Optional[str] = Query(None, description="要浏览的物理绝对路径，留空时默认为当前工作目录或用户主目录"),
) -> DirectoryBrowseResponse:
    """供前端工作区创建/接入选择器浏览本地物理目录。"""
    if path and path.strip():
        target_path = Path(path.strip()).expanduser().resolve()
    else:
        target_path = Path.cwd().resolve()

    if not target_path.exists() or not target_path.is_dir():
        if target_path.parent.exists() and target_path.parent.is_dir():
            target_path = target_path.parent
        else:
            target_path = Path.home().resolve()

    is_root = target_path == target_path.parent
    parent_str = str(target_path.parent) if not is_root else None

    subdirs: List[DirectoryEntry] = []
    try:
        for entry in sorted(target_path.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_dir():
                continue
            if entry.name.startswith(".") or entry.name in _IGNORED_DIRS:
                continue
            has_sub = False
            try:
                has_sub = any(child.is_dir() and not child.name.startswith(".") for child in entry.iterdir())
            except (OSError, PermissionError):
                has_sub = False

            subdirs.append(
                DirectoryEntry(
                    name=entry.name,
                    path=str(entry.resolve()),
                    is_directory=True,
                    has_subdirectories=has_sub,
                )
            )
    except (OSError, PermissionError):
        pass

    # 快捷路径推荐
    home_dir = Path.home().resolve()
    quick_locs: List[QuickLocation] = [
        QuickLocation(label="当前工程", path=str(Path.cwd().resolve())),
        QuickLocation(label="用户主目录 (~)", path=str(home_dir)),
    ]

    for rel_name, label in [
        ("Projects", "Projects (项目)"),
        ("Desktop", "Desktop (桌面)"),
        ("Documents", "Documents (文档)"),
        ("Downloads", "Downloads (下载)"),
    ]:
        candidate = home_dir / rel_name
        if candidate.is_dir():
            quick_locs.append(QuickLocation(label=label, path=str(candidate)))

    if Path("/tmp").is_dir():
        quick_locs.append(QuickLocation(label="临时目录 (/tmp)", path="/tmp"))

    quick_locs.append(QuickLocation(label="系统根目录 (/)", path="/"))

    return DirectoryBrowseResponse(
        current_path=str(target_path),
        parent_path=parent_str,
        is_root=is_root,
        directories=subdirs,
        quick_locations=quick_locs,
    )


async def _open_native_directory_dialog(initial_path: Optional[str] = None) -> Optional[str]:
    """在后台线程中唤起宿主机原生系统文件管理器/目录选择弹窗。"""
    import asyncio
    import shutil
    import subprocess

    def _sync_dialog() -> Optional[str]:
        # 1. 优先尝试 Zenity (GNOME / GTK Linux 标准文件管理器选择器)
        if shutil.which("zenity"):
            cmd = ["zenity", "--file-selection", "--directory", "--title=选择 Aegis 工程工作区目录"]
            if initial_path and os.path.isdir(initial_path):
                cmd.append(f"--filename={initial_path.rstrip('/')}/")
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if res.returncode == 0:
                    val = res.stdout.strip()
                    if val and os.path.isdir(val):
                        return val
                return None
            except Exception:
                pass

        # 2. 尝试 Kdialog (KDE Linux 环境)
        if shutil.which("kdialog"):
            start_dir = initial_path if (initial_path and os.path.isdir(initial_path)) else str(Path.home())
            cmd = ["kdialog", "--getexistingdirectory", start_dir, "--title", "选择 Aegis 工程工作区目录"]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if res.returncode == 0:
                    val = res.stdout.strip()
                    if val and os.path.isdir(val):
                        return val
                return None
            except Exception:
                pass

        # 3. 尝试 Python Tkinter 图形对话框
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            val = filedialog.askdirectory(
                initialdir=initial_path or str(Path.home()),
                title="选择 Aegis 工程工作区目录",
            )
            root.destroy()
            if val and os.path.isdir(val):
                return val
            return None
        except Exception:
            pass

        return None

    return await asyncio.to_thread(_sync_dialog)


@router.post(
    "/system/fs/pick-directory",
    summary="调用宿主机原生文件管理器选择目录",
)
async def pick_native_directory(
    path: Optional[str] = Query(None, description="初始浏览路径"),
) -> Dict[str, Any]:
    """直接调出系统原生文件管理器 (Zenity/Kdialog/Tkinter) 让用户点选目录。"""
    chosen = await _open_native_directory_dialog(path)
    if chosen:
        name = Path(chosen).name or "Workspace"
        return {
            "success": True,
            "path": chosen,
            "name": name,
            "cancelled": False,
        }
    return {
        "success": False,
        "path": None,
        "name": None,
        "cancelled": True,
    }


