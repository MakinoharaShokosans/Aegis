"""确定性 Point ID 计算：幂等写入的核心机制。

规范：documents/rag_retrieval/03_embedding_and_storage.md §3。

Point ID 由 ``(repo_name, file_path, start_line, content_hash)`` 确定性派生——
同一切片（同文件同位置同内容）在任意一次 ``ingest`` 中重复计算都得到相同 ID，
使 Qdrant 的 ``upsert`` 天然具备覆盖式幂等语义（内容变了就覆盖，内容没变就是
一次无副作用的重复写入）。这也是 ``06_evaluation_and_benchmarking.md`` 里
金标数据集 ``gold_chunk_ids`` 能跨多次重新索引长期复用的前提。
"""

from __future__ import annotations

import uuid

from indexer.metadata import ChunkMetadata

__all__ = ["NAMESPACE", "point_id_for"]

#: 派生命名空间（固定值，不得更改——更改会导致所有既有 Point ID 一次性全部失效）
NAMESPACE = uuid.UUID("a3f5c9d2-8b1e-4f6a-9c3d-1e7b5a2f8d4c")


def point_id_for(chunk: ChunkMetadata) -> str:
    """计算一个切片的确定性 Qdrant Point ID。

    Args:
        chunk: 已计算好 ``content_hash`` 的切片元数据。

    Returns:
        UUID5 字符串形式的 Point ID，同输入恒定不变。
    """
    key = f"{chunk.repo_name}:{chunk.file_path}:{chunk.start_line}:{chunk.content_hash}"
    return str(uuid.uuid5(NAMESPACE, key))
