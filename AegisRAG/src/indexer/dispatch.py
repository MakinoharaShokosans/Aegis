"""语言分发：按扩展名路由到具体切分器（02 §2），并处理文件级降级（02 §4）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from loguru import logger

from indexer.ast_splitter import AST_EXTENSIONS, split_ast
from indexer.fallback_splitter import split_fallback
from indexer.markdown_splitter import split_markdown
from indexer.metadata import ChunkMetadata

__all__ = ["SplitOutcome", "split_file"]

#: Markdown 走标题切分而非降级切分
_MARKDOWN_EXTENSIONS = {".md", ".mdx"}


@dataclass
class SplitOutcome:
    """单个文件的切分结果。

    Attributes:
        chunks: 该文件产出的切片列表。
        degraded: AST 解析失败、降级为通用切分时为 ``True``（02 §4，需如实上报）。
    """

    chunks: List[ChunkMetadata] = field(default_factory=list)
    degraded: bool = False


def split_file(
    *,
    content: str,
    file_path: str,
    repo_name: str,
    chunk_size: int,
    chunk_overlap: int,
    max_tokens: Optional[int] = None,
    git_commit: Optional[str] = None,
) -> SplitOutcome:
    """把单个文件切分为携带证据元数据的切片列表。

    Args:
        content: 文件原文。
        file_path: 相对仓库根目录的路径。
        repo_name: 仓库标识。
        chunk_size: 降级切分器的目标切片长度。
        chunk_overlap: 降级切分器的切片重叠长度。
        max_tokens: AST 切分的"超大切片"判定阈值（近似 token 数），见 02 §4。
        git_commit: 索引时刻的提交哈希。

    Returns:
        :class:`SplitOutcome`。AST 解析失败（语法错误等）会记录告警并降级为
        通用切分，不中断整批 ingest（02 §4"文件级失败降级"）。
    """
    ext = _extension_of(file_path)

    if ext in _MARKDOWN_EXTENSIONS:
        chunks = split_markdown(content=content, file_path=file_path, repo_name=repo_name, git_commit=git_commit)
        return SplitOutcome(chunks=chunks, degraded=False)

    if ext in AST_EXTENSIONS:
        try:
            chunks = split_ast(
                content=content,
                file_path=file_path,
                repo_name=repo_name,
                git_commit=git_commit,
                max_tokens=max_tokens,
            )
            return SplitOutcome(chunks=chunks, degraded=False)
        except Exception as exc:  # noqa: BLE001 — AST 解析的失败模式无法穷举，统一降级
            logger.warning(f"[Indexer] {file_path} AST 解析失败，降级为通用切分: {exc}")

    chunks = split_fallback(
        content=content,
        file_path=file_path,
        repo_name=repo_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        git_commit=git_commit,
    )
    degraded = ext in AST_EXTENSIONS  # 只有"本该走 AST 但解析失败"才算降级，本就是通用语言不算
    return SplitOutcome(chunks=chunks, degraded=degraded)


def _extension_of(file_path: str) -> str:
    """提取文件扩展名（小写，含前导点）。"""
    idx = file_path.rfind(".")
    return file_path[idx:].lower() if idx != -1 else ""
