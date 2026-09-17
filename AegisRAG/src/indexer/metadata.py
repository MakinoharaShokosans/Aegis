"""切片证据元数据 Schema：所有切分器的统一输出契约。

规范：documents/rag_retrieval/02_chunking_and_parsing.md §6。

元数据缺失即拒绝入库：``file_path``/``start_line``/``end_line``/``content_hash`` 四项
在 :class:`ChunkMetadata` 上都是必填字段（无默认值）。任何切分器产出不满足这四项的
半成品都无法构造出合法实例——用类型系统把"不完整证据不得入库"这条规则钉死，
而不是留给调用方在某处手写 if 判断。
"""

from __future__ import annotations

import hashlib
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ChunkMetadata", "ChunkType", "compute_content_hash"]

#: 切片类型标签（供未来结果展示分类使用，当前非强制消费，见 02 §6）
ChunkType = Literal["function", "struct", "markdown_section", "generic"]


def compute_content_hash(content: str) -> str:
    """计算切片原文的确定性哈希（幂等写入与增量判定的关键字段）。

    Args:
        content: 切片原文。

    Returns:
        SHA-1 十六进制摘要（见 03_embedding_and_storage.md §3）。
    """
    return hashlib.sha1(content.encode("utf-8")).hexdigest()


class ChunkMetadata(BaseModel):
    """一次切分产出的单个切片（含证据元数据）。

    Attributes:
        file_path: 相对仓库根目录的路径。
        start_line: 起始行号（1-indexed，闭区间）。
        end_line: 终止行号（1-indexed，闭区间）。
        content: 切片原文（完整未截断）。
        content_hash: ``content`` 的确定性哈希，幂等写入依据（见 03 §3）。
        language: 切分器判定的语言标签。
        repo_name: 仓库标识（多仓库场景的 Payload 过滤依据）。
        git_commit: 索引时刻的提交哈希，可选。
        enclosing_scope: 所属的封闭作用域路径（CCH 未来增强预留，见 02 §7）。
        chunk_index: 切片在其所属文件内的顺序序号（RSE 未来增强预留，见 02 §7）。
        chunk_type: 切片类型标签。
        oversized: 是否因超过 embedding 截断上限而被标记（见 02 §4）。
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    file_path: str = Field(min_length=1, description="相对仓库根目录的路径")
    start_line: int = Field(ge=1, description="起始行号（1-indexed）")
    end_line: int = Field(ge=1, description="终止行号（1-indexed）")
    content: str = Field(min_length=1, description="切片原文（完整未截断）")
    content_hash: str = Field(min_length=1, description="content 的确定性哈希")
    language: str = Field(min_length=1, description="切分器判定的语言标签")
    repo_name: str = Field(min_length=1, description="仓库标识")
    git_commit: Optional[str] = Field(default=None, description="索引时刻的提交哈希")
    enclosing_scope: Optional[str] = Field(default=None, description="封闭作用域路径（CCH 预留）")
    chunk_index: Optional[int] = Field(default=None, ge=0, description="文件内顺序序号（RSE 预留）")
    chunk_type: ChunkType = Field(default="generic", description="切片类型标签")
    oversized: bool = Field(default=False, description="是否超过 embedding 截断上限")

    @classmethod
    def build(
        cls,
        *,
        file_path: str,
        start_line: int,
        end_line: int,
        content: str,
        language: str,
        repo_name: str,
        git_commit: Optional[str] = None,
        enclosing_scope: Optional[str] = None,
        chunk_index: Optional[int] = None,
        chunk_type: ChunkType = "generic",
        oversized: bool = False,
    ) -> "ChunkMetadata":
        """构造实例并自动计算 ``content_hash``（切分器的标准入口）。

        Returns:
            已计算好 ``content_hash`` 的 :class:`ChunkMetadata`。
        """
        return cls(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            content=content,
            content_hash=compute_content_hash(content),
            language=language,
            repo_name=repo_name,
            git_commit=git_commit,
            enclosing_scope=enclosing_scope,
            chunk_index=chunk_index,
            chunk_type=chunk_type,
            oversized=oversized,
        )
