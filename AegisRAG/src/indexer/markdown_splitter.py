"""Markdown 标题层级切分（02 §5）。

每个切片携带其标题面包屑路径作为 ``enclosing_scope``，保证切片脱离原文后
仍能看出所属章节上下文。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from langchain_text_splitters import MarkdownHeaderTextSplitter

from indexer.metadata import ChunkMetadata

__all__ = ["split_markdown"]

#: 切分的标题层级（H1~H3，对齐 02 §5 的设计意图）
_HEADERS_TO_SPLIT_ON = [("#", "h1"), ("##", "h2"), ("###", "h3")]


def split_markdown(
    *, content: str, file_path: str, repo_name: str, git_commit: Optional[str] = None
) -> List[ChunkMetadata]:
    """按标题层级切分 Markdown 文档，每个切片携带标题面包屑路径。

    Args:
        content: Markdown 原文。
        file_path: 相对仓库根目录的路径。
        repo_name: 仓库标识。
        git_commit: 索引时刻的提交哈希。

    Returns:
        携带 ``enclosing_scope``（标题面包屑）的切片列表；空文档返回空列表。

    已知局限：行号定位采用"按切片顺序累计原文行数"的近似算法（见
    :func:`_locate_span`），而非逐字节精确匹配——``MarkdownHeaderTextSplitter``
    按文档顺序线性切分、不重排、不跳跃，该假设在实践中成立；如果未来升级
    该库版本改变了这一行为，需要重新核实。
    """
    if not content.strip():
        return []

    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=_HEADERS_TO_SPLIT_ON, strip_headers=False)
    docs = splitter.split_text(content)
    if not docs:
        return []

    lines = content.splitlines()
    chunks: List[ChunkMetadata] = []
    cursor = 0
    for index, doc in enumerate(docs):
        breadcrumb = " > ".join(str(value) for value in doc.metadata.values()) or None
        piece = doc.page_content
        start_line, end_line, cursor = _locate_span(lines, piece, cursor)
        chunks.append(
            ChunkMetadata.build(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                content=piece,
                language="markdown",
                repo_name=repo_name,
                git_commit=git_commit,
                enclosing_scope=breadcrumb,
                chunk_index=index,
                chunk_type="markdown_section",
            )
        )
    return chunks


def _locate_span(lines: List[str], piece: str, cursor: int) -> Tuple[int, int, int]:
    """在原文行序列里定位一个切片文本对应的起止行号（近似匹配）。

    Args:
        lines: 原文按行拆分（不含换行符）。
        piece: 切片文本。
        cursor: 上一个切片结束后的搜索起点（已消费的行数）。

    Returns:
        ``(start_line, end_line, next_cursor)``，行号均为 1-indexed。
    """
    piece_line_count = max(piece.count("\n") + 1, 1)
    start_line = cursor + 1
    end_line = min(cursor + piece_line_count, len(lines)) or start_line
    return start_line, end_line, end_line
