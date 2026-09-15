"""文件读写基础工具（受工作区 ``root_path`` 严格约束）。

**路径越界防护是这里的头等大事**：模型给出的路径可能包含 ``../../etc/passwd``
或指向另一个工作区。所有路径一律先 ``resolve()`` 再做子树校验，
越界立即拒绝——与 bash 子系统的防护策略保持一致（双保险，不依赖单点）。

**为什么还要文件工具而不是全用 bash**：读文件是最频繁的动作，
``view_file`` 能返回带行号、带截断提示的结构化结果，比 ``cat`` 更省 Token 也更安全。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Mapping

from loguru import logger

from tools.core.protocol import AegisTool, ToolResult

__all__ = ["FileWriteTool", "ViewFileTool", "build_file_tools"]

#: 单次 ``view_file`` 返回的最大行数
_MAX_VIEW_LINES = 400


def _resolve_within_root(target: str, root: Path) -> Path:
    """把目标路径规范化并校验其位于工作区根目录内。

    Args:
        target: 模型给出的路径（相对或绝对）。
        root: 工作区根目录（已 resolve）。

    Returns:
        规范化后的绝对路径。

    Raises:
        PermissionError: 路径越出工作区根目录。
    """
    candidate = Path(target).expanduser()
    resolved = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise PermissionError(f"路径越出工作区根目录，已拒绝: {target}")
    return resolved


class ViewFileTool(AegisTool):
    """带行号读取工作区内文件。

    Args:
        workspace_root: 工作区根目录。
    """

    name = "view_file"
    description = (
        "读取工作区内某个文件的指定行范围，返回带行号的文本。"
        "用于精确查看代码上下文；路径必须位于当前工作区内。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对工作区根目录的文件路径"},
            "start_line": {"type": "integer", "description": "可选，起始行（从 1 开始）"},
            "end_line": {"type": "integer", "description": "可选，结束行（含）"},
        },
        "required": ["path"],
    }

    def __init__(self, workspace_root: str) -> None:
        self._root = Path(workspace_root).resolve()
        self.timeout_sec = 15.0

    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        """读取文件片段。

        Args:
            args: ``{"path": str, "start_line"?: int, "end_line"?: int}``。

        Returns:
            :class:`ToolResult`。
        """
        raw_path = str(args.get("path", "")).strip()
        if not raw_path:
            return ToolResult.failure("缺少 path 参数")

        try:
            target = _resolve_within_root(raw_path, self._root)
        except PermissionError as exc:
            logger.warning(f"[ViewFileTool] 拒绝越界访问: {exc}")
            return ToolResult.failure(str(exc))

        if not target.is_file():
            return ToolResult.failure(f"文件不存在或不是普通文件: {raw_path}")

        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return ToolResult.failure(f"读取失败: {exc}")

        start = max(1, int(args.get("start_line") or 1))
        end = int(args.get("end_line") or (start + _MAX_VIEW_LINES - 1))
        end = min(end, start + _MAX_VIEW_LINES - 1, len(lines))

        if start > len(lines):
            return ToolResult.failure(f"起始行 {start} 超出文件总行数 {len(lines)}")

        excerpt = "\n".join(f"{number:>6}\t{lines[number - 1]}" for number in range(start, end + 1))
        truncated = end < len(lines)
        header = f"{raw_path}（第 {start}-{end} 行 / 共 {len(lines)} 行）"
        footer = "\n[已截断，如需后续内容请递增 start_line 继续查看]" if truncated else ""

        return ToolResult(
            ok=True,
            content=f"{header}\n{excerpt}{footer}",
            is_truncated=truncated,
            meta={"total_lines": len(lines), "start_line": start, "end_line": end},
        )


class FileWriteTool(AegisTool):
    """写入（覆盖）工作区内文件。

    Args:
        workspace_root: 工作区根目录。
        max_bytes: 单次写入体积上限。
    """

    name = "write_file"
    description = (
        "把完整内容写入工作区内的文件（覆盖已有内容）。"
        "修改已有代码时请先 view_file 确认上下文，避免误覆盖。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对工作区根目录的文件路径"},
            "content": {"type": "string", "description": "完整的新文件内容"},
        },
        "required": ["path", "content"],
    }

    def __init__(self, workspace_root: str, max_bytes: int = 1_000_000) -> None:
        self._root = Path(workspace_root).resolve()
        self._max_bytes = max_bytes
        self.timeout_sec = 15.0

    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        """写入文件。

        Args:
            args: ``{"path": str, "content": str}``。

        Returns:
            :class:`ToolResult`。
        """
        raw_path = str(args.get("path", "")).strip()
        content = str(args.get("content", ""))
        if not raw_path:
            return ToolResult.failure("缺少 path 参数")
        if len(content.encode("utf-8")) > self._max_bytes:
            return ToolResult.failure(f"内容超过单次写入上限（{self._max_bytes} 字节）")

        try:
            target = _resolve_within_root(raw_path, self._root)
        except PermissionError as exc:
            logger.warning(f"[FileWriteTool] 拒绝越界写入: {exc}")
            return ToolResult.failure(str(exc))

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult.failure(f"写入失败: {exc}")

        logger.info(f"[FileWriteTool] 已写入 {target}（{len(content)} 字符）")
        return ToolResult(ok=True, content=f"已写入 {raw_path}（{len(content)} 字符）")


def build_file_tools(workspace_root: str) -> List[AegisTool]:
    """构造文件读写工具组。

    Args:
        workspace_root: 工作区根目录。

    Returns:
        工具列表：``[ViewFileTool, FileWriteTool]``。
    """
    return [ViewFileTool(workspace_root), FileWriteTool(workspace_root)]
