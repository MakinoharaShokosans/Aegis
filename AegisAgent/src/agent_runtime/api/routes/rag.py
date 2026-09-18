"""RAG 知识库与文档索引统一网关代理端点。

将前端的知识库索引、切片检视与在线检索请求统一转发给 AegisRAG 独立微服务 (:8001)。
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Query, status

from agent_runtime.api.deps import MemoryDep, RuntimeDep
from agent_runtime.api.schemas import (
    RagIngestRequest,
    RagIngestResponse,
    RagRetrieveRequest,
    RagRetrieveResponse,
)
from agent_runtime.errors import DependencyUnavailableError
from tools.core.http_client import ServiceClient

__all__ = ["router"]

router = APIRouter(prefix="/rag", tags=["rag"])


@router.get("/health", summary="检查 RAG 独立检索子系统健康状况")
async def rag_health(runtime: RuntimeDep) -> Dict[str, Any]:
    """检查 AegisRAG (:8001) 服务存活与向量模型就绪状态。"""
    client = ServiceClient(runtime.config.services.rag_url, runtime.config.services.timeout_sec)
    try:
        return await client.request_json("GET", "/api/v1/health")
    finally:
        await client.aclose()


@router.post(
    "/ingest",
    response_model=RagIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="触发工作区文档与代码 RAG 索引",
)
async def rag_ingest(
    payload: RagIngestRequest,
    runtime: RuntimeDep,
    memory: MemoryDep,
    workspace_id: str | None = Query(default=None, description="可选工作区 ID（自动推导 repo_root 与 repo_name）"),
) -> RagIngestResponse:
    """触发 RAG 索引流水线（语法分块、Dense+Sparse 向量化、增量/全量写入）。"""
    repo_name = payload.repo_name or "default"
    repo_root = payload.repo_root or ""

    if workspace_id:
        workspace = await memory.get_workspace(workspace_id)
        if workspace:
            repo_name = payload.repo_name or workspace.name
            repo_root = payload.repo_root or workspace.root_path

    if not repo_root:
        raise DependencyUnavailableError("未指定 repo_root 且无法从 workspace 推导路径")

    client = ServiceClient(runtime.config.services.rag_url, timeout_sec=180.0)
    try:
        resp = await client.request_json(
            "POST",
            "/api/v1/documents/ingest",
            payload={
                "repo_name": repo_name,
                "repo_root": repo_root,
                "incremental": payload.incremental,
            },
        )
        return RagIngestResponse(**resp)
    finally:
        await client.aclose()


@router.post(
    "/retrieve",
    response_model=RagRetrieveResponse,
    status_code=status.HTTP_200_OK,
    summary="执行 RAG 混合检索与精排调试",
)
async def rag_retrieve(
    payload: RagRetrieveRequest,
    runtime: RuntimeDep,
) -> RagRetrieveResponse:
    """在线检索：双路召回 -> RRF 融合 -> Cross-Encoder 精排。"""
    client = ServiceClient(runtime.config.services.rag_url, runtime.config.services.timeout_sec)
    try:
        resp = await client.request_json(
            "POST",
            "/api/v1/retrieve",
            payload={
                "query": payload.query,
                "top_k": payload.top_k,
                "mode": payload.mode,
                "filters": {"language": payload.language} if payload.language else None,
            },
        )
        return RagRetrieveResponse(**resp)
    finally:
        await client.aclose()
