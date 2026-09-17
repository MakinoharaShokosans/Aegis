"""内存沙箱端到端闭环冒烟探针。

在独立内存 Qdrant 数据库中执行微型代码切分 -> 双路向量化 -> 写入 -> 混合召回 -> 精排打分，
验证整条 RAG 流水线在内存级 100% 畅通闭环，零磁盘副作用。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, List

from qdrant_client import QdrantClient, models

from api.preflight.models import CheckStatus, DiagnosticItem
from api.preflight.probes.base import BaseProbe
from embeddings.pipeline import EmbeddingPipeline
from indexer.dispatch import split_file
from rerank.reranker import Reranker
from storage.ids import point_id_for

if TYPE_CHECKING:
    from api.settings import RagConfig

__all__ = ["SmokeProbe"]

_SMOKE_COLLECTION = "aegis_smoke_probe_collection"
_PAYLOAD_VECTOR_DENSE = "dense"
_PAYLOAD_VECTOR_SPARSE = "sparse"


class SmokeProbe(BaseProbe):
    """端到端内存沙箱冒烟探针。"""

    @property
    def category_name(self) -> str:
        return "内存沙箱端到端闭环冒烟"

    def run_checks(self, settings: RagConfig) -> List[DiagnosticItem]:
        items: List[DiagnosticItem] = []

        sample_code = (
            "package main\n\n"
            "// ComputeSHA calculates hash\n"
            "func ComputeSHA(data []byte) string {\n"
            "\treturn \"dummy_hash\"\n"
            "}\n"
        )

        start_total = time.perf_counter()
        memory_client: QdrantClient | None = None
        embedder: EmbeddingPipeline | None = None
        reranker: Reranker | None = None

        try:
            # 1. 内存 Qdrant 实例隔离初始化
            memory_client = QdrantClient(":memory:")
            distance = getattr(models.Distance, settings.qdrant.distance.upper(), models.Distance.COSINE)
            memory_client.create_collection(
                collection_name=_SMOKE_COLLECTION,
                vectors_config={
                    _PAYLOAD_VECTOR_DENSE: models.VectorParams(
                        size=settings.qdrant.vector_size, distance=distance
                    )
                },
                sparse_vectors_config={_PAYLOAD_VECTOR_SPARSE: models.SparseVectorParams()},
            )

            # 2. 语法分块
            outcome = split_file(
                content=sample_code,
                file_path="main.go",
                repo_name="smoke_sandbox",
                chunk_size=settings.indexer.chunk_size,
                chunk_overlap=settings.indexer.chunk_overlap,
            )
            chunks = outcome.chunks
            if not chunks:
                raise ValueError("沙箱切分未能产生任何切片")

            # 3. 双路向量化
            embedding_cfg = settings.embedding.model_copy(
                update={"cache_dir": str(settings.resolve_path(settings.embedding.cache_dir))}
            )
            embedder = EmbeddingPipeline(embedding_cfg)
            texts = [c.content for c in chunks]
            dense_vectors = embedder.embed_dense(texts)
            sparse_vectors = embedder.embed_sparse(texts)

            # 4. 内存写入
            points = [
                models.PointStruct(
                    id=point_id_for(chunk),
                    vector={
                        _PAYLOAD_VECTOR_DENSE: d_vec,
                        _PAYLOAD_VECTOR_SPARSE: models.SparseVector(indices=s_idx, values=s_val),
                    },
                    payload=chunk.model_dump(),
                )
                for chunk, d_vec, (s_idx, s_val) in zip(chunks, dense_vectors, sparse_vectors)
            ]
            memory_client.upsert(_SMOKE_COLLECTION, points=points)

            # 5. 混合检索召回 (Dense + Sparse + RRF)
            query_str = "ComputeSHA calculate hash"
            q_dense = embedder.embed_dense_one(query_str)
            q_s_idx, q_s_val = embedder.embed_sparse_one(query_str)

            search_res = memory_client.query_points(
                _SMOKE_COLLECTION,
                prefetch=[
                    models.Prefetch(
                        query=q_dense,
                        using=_PAYLOAD_VECTOR_DENSE,
                        limit=5,
                    ),
                    models.Prefetch(
                        query=models.SparseVector(indices=q_s_idx, values=q_s_val),
                        using=_PAYLOAD_VECTOR_SPARSE,
                        limit=5,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=3,
                with_payload=True,
            )

            if not search_res.points:
                raise ValueError("沙箱混合召回结果为空")

            # 6. Cross-Encoder 精排打分
            rerank_cfg = settings.rerank.model_copy(
                update={"cache_dir": str(settings.resolve_path(settings.rerank.cache_dir))}
            )
            reranker = Reranker(rerank_cfg)
            doc_texts = [p.payload["content"] for p in search_res.points]
            rerank_scores = reranker.score(query=query_str, documents=doc_texts)

            total_lat = (time.perf_counter() - start_total) * 1000.0

            items.append(
                DiagnosticItem(
                    name="端到端流水线闭环 (切分->编码->召回->精排)",
                    status=CheckStatus.PASS,
                    message=(
                        f"沙箱全流程闭环验证成功 (召回命中: {len(search_res.points)}, "
                        f"精排首位分数: {rerank_scores[0]:.3f}, 耗时: {total_lat:.1f}ms)"
                    ),
                    latency_ms=total_lat,
                    details={
                        "retrieved_count": len(search_res.points),
                        "top_score": rerank_scores[0] if rerank_scores else None,
                        "duration_ms": round(total_lat, 2),
                    },
                )
            )

        except Exception as exc:  # noqa: BLE001
            total_lat = (time.perf_counter() - start_total) * 1000.0
            items.append(
                DiagnosticItem(
                    name="端到端流水线闭环 (切分->编码->召回->精排)",
                    status=CheckStatus.FAIL,
                    message=f"内存沙箱冒烟异常: {exc}",
                    latency_ms=total_lat,
                    remediation="请查看详细日志或检查各子模块在联合调度时的参数一致性",
                )
            )
        finally:
            if memory_client is not None:
                memory_client.close()
            if embedder is not None:
                embedder.close()
            if reranker is not None:
                reranker.close()

        return items
