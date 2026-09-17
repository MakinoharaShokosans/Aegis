"""``GET /api/v1/health``：进程健康 + Qdrant/Embedding 依赖连通性（05 §1.3，01 §5）。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from api import __version__
from api.schemas import HealthResponse, QdrantHealth
from storage.qdrant_store import QdrantStore

router = APIRouter()

__all__ = ["router"]


@router.get("/api/v1/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """健康检查：Collection 未就绪或 Embedding 模型未加载时整体降级（01 §5）。

    刻意声明为同步 ``def``（理由同 ``routes/retrieve.py::retrieve`` 的注释）。

    Args:
        request: FastAPI 请求对象（读取应用共享状态）。

    Returns:
        健康检查响应体。
    """
    store: QdrantStore = request.app.state.store
    embedding_model_loaded: bool = request.app.state.embedding_model_loaded

    snapshot = store.health_snapshot()
    status = "ok" if snapshot["collection_ready"] and embedding_model_loaded else "degraded"
    return HealthResponse(
        status=status,
        version=__version__,
        qdrant=QdrantHealth(**snapshot),
        embedding_model_loaded=embedding_model_loaded,
    )
