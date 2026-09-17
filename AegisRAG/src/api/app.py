"""FastAPI 契约层：装配路由、生命周期与异常处理器。

规范：documents/rag_retrieval/05_http_api_and_client_contract.md。

``lifespan`` 负责：装配配置 → 连接 Qdrant 并做启动期维度强校验（03 §2）→
加载 Dense/Sparse 向量化模型与 Cross-Encoder 精排模型。Embedding 模型加载失败
时服务仍以降级状态启动（健康检查可观测，01 §5）；精排模型是核心范围
（04 §3，非可选项），加载失败直接阻止服务启动，不做静默降级。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from api import __version__
from api.errors import (
    CollectionNotReadyError,
    DimensionMismatchError,
    RagError,
    RepoNotIndexedError,
    UpstreamModelError,
)
from api.routes import health, ingest, retrieve
from api.settings import get_settings
from embeddings.pipeline import EmbeddingPipeline
from rerank.reranker import Reranker
from storage.qdrant_store import QdrantStore

__all__ = ["app", "create_app"]

#: 领域异常 → HTTP 状态码映射（05 §2）
_ERROR_STATUS_CODES: Dict[type, int] = {
    CollectionNotReadyError: 503,
    DimensionMismatchError: 500,
    RepoNotIndexedError: 404,
    UpstreamModelError: 502,
}


def _structured_error(exc: RagError) -> Dict[str, Any]:
    """构造统一结构化错误响应体（对齐 AegisAgent 侧 bash_shell/web_search 既有约定）。

    Args:
        exc: 领域异常。

    Returns:
        ``{"error": {...}}`` 形态的响应体。
    """
    return {"error": exc.to_dict()}


def create_app() -> FastAPI:
    """构建 FastAPI 应用（便于多实例装配）。

    Returns:
        已注册路由、异常处理器与 lifespan 的 FastAPI 实例。
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """服务生命周期：装配配置 / Qdrant / 向量化管道 / 精排器。

        Args:
            application: FastAPI 实例（用于挂载共享状态）。

        Yields:
            应用运行期（``yield`` 之前为启动，之后为关闭）。
        """
        settings = get_settings()
        application.state.settings = settings

        store = QdrantStore(settings.qdrant, storage_path=settings.resolve_path(settings.qdrant.storage_path))
        store.ensure_collection()  # DimensionMismatchError 时直接向上抛出，阻止带病启动
        application.state.store = store

        # cache_dir 恒相对工程根解析为绝对路径，不依赖启动时的进程 cwd
        # （remote 模式下该字段仍会用于 Sparse/BM25 本地模型，见 embeddings/pipeline.py 模块说明）
        embedding_cfg = settings.embedding.model_copy(
            update={"cache_dir": str(settings.resolve_path(settings.embedding.cache_dir))}
        )
        try:
            embedder = EmbeddingPipeline(embedding_cfg)
            # 启动期维度自检：mode="remote" 时真实输出维度只有实际调用一次才知道，
            # 与 [qdrant].vector_size 不一致时必须 fail-fast，而不是留到第一次
            # 真实写入才在 Qdrant 侧报错（呼应 config 里 vector_size 旁的告警注释）。
            actual_dim = embedder.probe_dense_dimension()
            if actual_dim != settings.qdrant.vector_size:
                raise DimensionMismatchError(
                    f"Embedding 模型（mode={embedding_cfg.mode}）实际输出维度为 {actual_dim}，"
                    f"与配置 [qdrant].vector_size={settings.qdrant.vector_size} 不一致，请更新配置后重启",
                    actual_size=actual_dim,
                    expected_size=settings.qdrant.vector_size,
                )
            application.state.embedder = embedder
            application.state.embedding_model_loaded = True
        except DimensionMismatchError:
            raise  # 维度不匹配是配置错误，必须直接暴露、阻止带病启动，不能降级掩盖
        except Exception as exc:  # noqa: BLE001 — 其余加载失败（如远端未配置 key）以降级状态启动（01 §5）
            logger.error(f"[AegisRAG] Embedding 模型加载失败，服务以降级状态启动: {exc}")
            application.state.embedder = None
            application.state.embedding_model_loaded = False

        rerank_cfg = settings.rerank.model_copy(
            update={"cache_dir": str(settings.resolve_path(settings.rerank.cache_dir))}
        )
        reranker = Reranker(rerank_cfg)
        application.state.reranker = reranker

        logger.bind(
            host=settings.server.host,
            port=settings.server.port,
            qdrant_mode=settings.qdrant.mode,
            collection=settings.qdrant.collection_name,
            embedding_mode=settings.embedding.mode,
            rerank_mode=settings.rerank.mode,
        ).info("AegisRAG 服务启动")
        try:
            yield
        finally:
            store.close()
            if application.state.embedder is not None:
                application.state.embedder.close()
            reranker.close()
            logger.info("AegisRAG 服务关闭")

    application = FastAPI(
        title="AegisRAG",
        description="独立代码检索子系统（ADR: documents/技术选型/rag_retrieval.md）",
        version=__version__,
        lifespan=lifespan,
    )
    application.include_router(health.router)
    application.include_router(retrieve.router)
    application.include_router(ingest.router)

    @application.exception_handler(RagError)
    async def handle_rag_error(request: Request, exc: RagError) -> JSONResponse:
        """把领域异常映射为对应 HTTP 状态码 + 结构化错误体（05 §2）。

        Args:
            request: FastAPI 请求对象。
            exc: 领域异常。

        Returns:
            结构化错误响应。
        """
        status_code = _ERROR_STATUS_CODES.get(type(exc), 500)
        logger.bind(code=exc.code, path=request.url.path).warning(f"[AegisRAG] {exc.message}")
        return JSONResponse(status_code=status_code, content=_structured_error(exc))

    return application


#: 供 ``uvicorn api.app:app`` 直接引用的应用实例
app = create_app()
