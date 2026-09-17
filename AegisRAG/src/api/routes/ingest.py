"""``POST /api/v1/documents/ingest``：索引触发、语言分发、幂等写入、失效清理编排。

规范：documents/rag_retrieval/02_chunking_and_parsing.md §1、03 §3/§4、05 §1.2。
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Iterator, List, Optional, Set

from fastapi import APIRouter, Request
from loguru import logger

from api.errors import RepoNotIndexedError
from api.schemas import IngestRequest, IngestResponse
from embeddings.pipeline import EmbeddingPipeline
from indexer.dispatch import split_file
from indexer.metadata import ChunkMetadata
from storage.ids import point_id_for
from storage.qdrant_store import QdrantStore

router = APIRouter()

__all__ = ["router"]

#: 索引时跳过的目录名（隐藏目录一律跳过，见 _iter_repo_files）
_SKIP_DIR_NAMES = {
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "qdrant_data",
    "cache",
    "dist",
    "build",
    "htmlcov",
}

#: 索引时跳过的固定文件名（如包管理 lockfile，避免冗余切分占用计算资源）
_SKIP_FILE_NAMES = {
    "uv.lock",
    "package-lock.json",
    "poetry.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "go.sum",
    ".DS_Store",
}

#: 单文件读取体积上限（字节）——防御性工程上限，非业务可调参数，故不进配置
_MAX_FILE_BYTES = 5 * 1024 * 1024


@router.post("/api/v1/documents/ingest", response_model=IngestResponse)
def ingest_documents(payload: IngestRequest, request: Request) -> IngestResponse:
    """索引写入端点：遍历仓库 → 语言分发切分 → 增量幂等写入 → 失效清理。

    刻意声明为同步 ``def``（理由同 ``routes/retrieve.py::retrieve`` 的注释）：
    这条路径尤其重要——它是长耗时批处理，写成 ``async def`` 会在事件循环上
    独占执行，直接卡住同进程内所有并发的 ``/retrieve`` 请求。

    Args:
        payload: 索引请求体。
        request: FastAPI 请求对象（读取配置 / 存储 / 向量化管道）。

    Returns:
        本次索引的统计结果（02 §1、03 §3/§4，05 §1.2）。

    Raises:
        RepoNotIndexedError: ``repo_root`` 不存在或不是目录时抛出。
    """
    started = time.monotonic()
    settings = request.app.state.settings
    store: QdrantStore = request.app.state.store
    embedder: EmbeddingPipeline = request.app.state.embedder

    repo_root = Path(payload.repo_root).expanduser()
    if not repo_root.is_dir():
        raise RepoNotIndexedError(f"repo_root 不存在或不是目录: {repo_root}", repo_root=str(repo_root))

    git_commit = _resolve_git_commit(repo_root)

    all_chunks: List[ChunkMetadata] = []
    degraded_files: List[str] = []
    keep_paths: Set[str] = set()

    for abs_path in _iter_repo_files(repo_root):
        rel_path = abs_path.relative_to(repo_root).as_posix()
        text = _read_text(abs_path)
        if text is None:
            continue
        keep_paths.add(rel_path)

        outcome = split_file(
            content=text,
            file_path=rel_path,
            repo_name=payload.repo_name,
            chunk_size=settings.indexer.chunk_size,
            chunk_overlap=settings.indexer.chunk_overlap,
            max_tokens=settings.embedding.max_length,
            git_commit=git_commit,
        )
        if outcome.degraded:
            degraded_files.append(rel_path)
        all_chunks.extend(outcome.chunks)

    if not all_chunks:
        deleted = store.delete_stale(payload.repo_name, keep_paths)
        return IngestResponse(
            indexed=0,
            skipped=0,
            deleted=deleted,
            degraded_files=degraded_files,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    if payload.incremental:
        ids = [point_id_for(chunk) for chunk in all_chunks]
        existing = store.existing_ids(ids)
        new_chunks = [chunk for chunk, point_id in zip(all_chunks, ids) if point_id not in existing]
    else:
        # 非增量：忽略现存哈希，强制全量重新向量化（05 §1.2）
        new_chunks = all_chunks
    skipped = len(all_chunks) - len(new_chunks)

    indexed = 0
    if new_chunks:
        # CCH 上下文切片标题头：仅用于 Dense/Sparse 向量化编码，Qdrant Payload 仍保留干净的原文
        texts = [
            f"[{chunk.enclosing_scope}]\n{chunk.content}" if chunk.enclosing_scope else chunk.content
            for chunk in new_chunks
        ]
        dense_vectors = embedder.embed_dense(texts)
        sparse_vectors = embedder.embed_sparse(texts)
        indexed = store.upsert_chunks(new_chunks, dense_vectors, sparse_vectors)

    deleted = store.delete_stale(payload.repo_name, keep_paths)

    logger.bind(repo_name=payload.repo_name, indexed=indexed, skipped=skipped, deleted=deleted).info(
        "[Ingest] 索引完成"
    )
    return IngestResponse(
        indexed=indexed,
        skipped=skipped,
        deleted=deleted,
        degraded_files=degraded_files,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def _iter_repo_files(repo_root: Path) -> Iterator[Path]:
    """遍历仓库文件，跳过隐藏目录、锁定文件与常见的构建/依赖目录。"""
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if path.name in _SKIP_FILE_NAMES:
            continue
        rel_parts = path.relative_to(repo_root).parts[:-1]
        if rel_parts and rel_parts[0] == "storage":
            continue
        if any(part.startswith(".") or part in _SKIP_DIR_NAMES for part in rel_parts):
            continue
        if path.stat().st_size > _MAX_FILE_BYTES:
            continue
        yield path


def _read_text(path: Path) -> Optional[str]:
    """尝试以 UTF-8 读取文件；非文本/二进制文件静默跳过（不计入切分范围）。"""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _resolve_git_commit(repo_root: Path) -> Optional[str]:
    """获取索引时刻的 git 提交哈希；非 git 仓库返回 ``None``（02 §6）。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
