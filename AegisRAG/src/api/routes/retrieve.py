"""``POST /api/v1/retrieve``：双路召回 → RRF 融合 → Payload 过滤 → 精排。

规范：documents/rag_retrieval/04_hybrid_retrieval_and_rerank.md、05 §1.1。
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from api.schemas import ChunkResult, RetrieveRequest, RetrieveResponse
from embeddings.pipeline import EmbeddingPipeline
from rerank.reranker import Reranker
from storage.qdrant_store import QdrantStore

router = APIRouter()

__all__ = ["router"]

#: 不经过精排、直接按召回/融合分数截取的调试模式（06 §3 消融矩阵）
_NO_RERANK_MODES = {"dense_only", "sparse_only", "hybrid_no_rerank"}


@router.post("/api/v1/retrieve", response_model=RetrieveResponse)
def retrieve(payload: RetrieveRequest, request: Request) -> RetrieveResponse:
    """检索端点：召回 → 融合 → 过滤 → 精排（04 §1~§4）。

    刻意声明为同步 ``def`` 而非 ``async def``：函数体内没有任何真正的 ``await``
    （FastEmbed / qdrant-client 都是同步阻塞调用），FastAPI 会把同步路由函数
    自动派发到线程池执行；若写成 ``async def`` 反而会在事件循环上直接阻塞整个
    进程，让并发的 ``/retrieve`` 与 ``/documents/ingest`` 请求互相卡住，违反
    01_architecture_overview.md §2.2"两条流水线必须能独立失败而不互相拖累"的要求。

    Args:
        payload: 检索请求体。
        request: FastAPI 请求对象（读取配置 / 存储 / 向量化管道 / 精排器）。

    Returns:
        结构化检索结果；召回阶段零命中时返回空 ``results``，不进入精排（04 §4）。
    """
    settings = request.app.state.settings
    store: QdrantStore = request.app.state.store
    embedder: EmbeddingPipeline = request.app.state.embedder
    reranker: Reranker = request.app.state.reranker

    language = payload.filters.language if payload.filters else None
    dense_vector = embedder.embed_dense_one(payload.query)
    sparse_vector = embedder.embed_sparse_one(payload.query)

    points = store.query_hybrid(
        dense_vector=dense_vector,
        sparse_vector=sparse_vector,
        dense_top_k=settings.retrieval.dense_top_k,
        sparse_top_k=settings.retrieval.sparse_top_k,
        fusion_top_k=settings.retrieval.fusion_top_k,
        language=language,
        mode=payload.mode,
    )

    if not points:
        return RetrieveResponse(results=[], low_confidence=False)

    top_k = payload.top_k or settings.retrieval.default_top_k

    if payload.mode in _NO_RERANK_MODES:
        # 调试/消融路径：分数是原始 Qdrant 相似度或 RRF 融合分数，与
        # [rerank].min_score（专为 Cross-Encoder 分数校准）量纲不同，
        # 不能拿来判定 low_confidence，故恒为 False（06 §3）。
        selected = [(point, float(point.score)) for point in points[:top_k]]
        low_confidence = False
    else:
        documents = [str(point.payload.get("content", "")) for point in points]
        scores = reranker.score(payload.query, documents)
        ranked = sorted(zip(points, scores), key=lambda item: item[1], reverse=True)
        selected = ranked[:top_k]
        low_confidence = bool(selected) and all(score < settings.rerank.min_score for _, score in selected)

    results = [
        ChunkResult(
            chunk_id=str(point.id),
            file_path=str(point.payload.get("file_path", "")),
            start_line=int(point.payload.get("start_line", 0)),
            end_line=int(point.payload.get("end_line", 0)),
            content=str(point.payload.get("content", "")),
            git_commit=point.payload.get("git_commit"),
            enclosing_scope=point.payload.get("enclosing_scope"),
            score=float(score),
        )
        for point, score in selected
    ]
    return RetrieveResponse(results=results, low_confidence=low_confidence)
