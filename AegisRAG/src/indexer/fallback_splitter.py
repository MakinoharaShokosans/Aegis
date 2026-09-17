"""通用降级切分器：Python 与未匹配语言的兜底路径（02 §3）。

真 AST 语法切分范围锁定为 C/C++/Go（见 ``ast_splitter.py`` 与 02 §3 的纠偏裁决，
不为 Python/Rust 额外引入新的 C 扩展依赖）。Python 与其余未识别语言一律走本模块
的启发式切分，不承诺语法块完整性——这也是 ``[indexer].chunk_size``/``chunk_overlap``
两项配置**唯一真正生效**的路径（AST 与 Markdown 切分都以语法边界为准）。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from indexer.metadata import ChunkMetadata

__all__ = ["split_fallback"]

#: 扩展名 → langchain Language 枚举（有专属启发式规则的语言）
_LANGCHAIN_LANGUAGE_MAP = {".py": Language.PYTHON}


def split_fallback(
    *,
    content: str,
    file_path: str,
    repo_name: str,
    chunk_size: int,
    chunk_overlap: int,
    git_commit: Optional[str] = None,
) -> List[ChunkMetadata]:
    """按语言启发式（有对应 Language 枚举时）或纯字符定长切分内容。

    Args:
        content: 文件原文。
        file_path: 相对仓库根目录的路径。
        repo_name: 仓库标识。
        chunk_size: 目标切片长度（``[indexer].chunk_size``）。
        chunk_overlap: 切片重叠长度（``[indexer].chunk_overlap``）。
        git_commit: 索引时刻的提交哈希。

    Returns:
        切片列表；空文件返回空列表。

    已知局限：``RecursiveCharacterTextSplitter`` 允许切片重叠，行号定位按
    "本切片在原文中首次出现的位置"近似计算（见 :func:`_locate_start`）——
    重叠区间会被相邻切片共同覆盖，这是已知且可接受的近似，不影响切片内容本身
    的正确性，只影响展示行号在重叠区的精确度。
    """
    if not content.strip():
        return []

    ext = _extension_of(file_path)
    lang_enum = _LANGCHAIN_LANGUAGE_MAP.get(ext)
    language_label = lang_enum.value if lang_enum is not None else (ext.lstrip(".") or "generic")

    if lang_enum is not None:
        splitter = RecursiveCharacterTextSplitter.from_language(
            lang_enum, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
    else:
        splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    pieces = splitter.split_text(content)
    chunks: List[ChunkMetadata] = []
    search_from = 0
    for index, piece in enumerate(pieces):
        start_line, end_line, search_from = _locate_start(content, piece, search_from, chunk_overlap)
        chunks.append(
            ChunkMetadata.build(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                content=piece,
                language=language_label,
                repo_name=repo_name,
                git_commit=git_commit,
                chunk_index=index,
                chunk_type="generic",
            )
        )
    return chunks


def _locate_start(content: str, piece: str, search_from: int, chunk_overlap: int) -> Tuple[int, int, int]:
    """定位一个切片文本在原文中的起止行号（容忍重叠区间的近似匹配）。

    Args:
        content: 原文全文。
        piece: 切片文本。
        search_from: 上一次匹配结束的字符偏移。
        chunk_overlap: 切片重叠长度（向前回退搜索起点，覆盖重叠区间）。

    Returns:
        ``(start_line, end_line, next_search_from)``，行号均为 1-indexed。
    """
    found_at = content.find(piece, max(search_from - chunk_overlap, 0))
    if found_at == -1:
        found_at = search_from
    start_line = content.count("\n", 0, found_at) + 1
    end_line = start_line + piece.count("\n")
    return start_line, end_line, found_at + len(piece)


def _extension_of(file_path: str) -> str:
    """提取文件扩展名（小写，含前导点）。"""
    idx = file_path.rfind(".")
    return file_path[idx:].lower() if idx != -1 else ""
