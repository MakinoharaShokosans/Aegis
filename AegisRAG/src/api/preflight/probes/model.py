"""向量模型加载、维度强对齐与推理时延探针。

验证 Dense (bge-m3)、Sparse (BM25) 与 Cross-Encoder (bge-reranker-base) 模型的完整性、
输出维度与 Qdrant vector_size 的一致性（fail-fast 核心），并记录基线时延。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, List

from api.preflight.models import CheckStatus, DiagnosticItem
from api.preflight.probes.base import BaseProbe
from embeddings.pipeline import EmbeddingPipeline
from rerank.reranker import Reranker

if TYPE_CHECKING:
    from api.settings import RagConfig

__all__ = ["ModelProbe"]


class ModelProbe(BaseProbe):
    """向量与精排模型完整性探针。"""

    @property
    def category_name(self) -> str:
        return "模型完整性、维度对齐与推理时延"

    def run_checks(self, settings: RagConfig) -> List[DiagnosticItem]:
        items: List[DiagnosticItem] = []

        # 1. Dense 向量模型加载、推理与维度强校验
        embedding_cfg = settings.embedding.model_copy(
            update={"cache_dir": str(settings.resolve_path(settings.embedding.cache_dir))}
        )
        embedder: EmbeddingPipeline | None = None
        try:
            start_load = time.perf_counter()
            embedder = EmbeddingPipeline(embedding_cfg)
            load_lat = (time.perf_counter() - start_load) * 1000.0

            # 维度探针推理
            start_infer = time.perf_counter()
            actual_dim = embedder.probe_dense_dimension()
            infer_lat = (time.perf_counter() - start_infer) * 1000.0

            expected_dim = settings.qdrant.vector_size
            model_id = (
                settings.embedding.local.model_name
                if settings.embedding.mode == "local"
                else settings.embedding.remote.model
            )

            if actual_dim == expected_dim:
                items.append(
                    DiagnosticItem(
                        name="Dense 模型维度强对齐",
                        status=CheckStatus.PASS,
                        message=(
                            f"模型 '{model_id}' (mode={settings.embedding.mode}) 实际输出 {actual_dim} 维，"
                            f"与 [qdrant].vector_size={expected_dim} 严格对齐 (加载: {load_lat:.1f}ms, 推理: {infer_lat:.1f}ms)"
                        ),
                        latency_ms=infer_lat,
                        details={
                            "model": model_id,
                            "mode": settings.embedding.mode,
                            "dimension": actual_dim,
                            "load_latency_ms": round(load_lat, 2),
                            "infer_latency_ms": round(infer_lat, 2),
                        },
                    )
                )
            else:
                items.append(
                    DiagnosticItem(
                        name="Dense 模型维度强对齐",
                        status=CheckStatus.FAIL,
                        message=(
                            f"模型 '{model_id}' 实际输出维度为 {actual_dim}，"
                            f"但配置 [qdrant].vector_size 为 {expected_dim}！"
                        ),
                        remediation=(
                            f"请将 config/rag_config.toml 中 [qdrant].vector_size 修改为 {actual_dim}，"
                            "或切换匹配该维度的 Dense 嵌入模型"
                        ),
                        details={"actual_dim": actual_dim, "expected_dim": expected_dim},
                    )
                )

        except Exception as exc:  # noqa: BLE001
            items.append(
                DiagnosticItem(
                    name="Dense 模型加载与推理",
                    status=CheckStatus.FAIL,
                    message=f"Dense 模型探针失败: {exc}",
                    remediation="请检查网络/本地权重缓存，或核对 .env 中的 API Key 是否有效",
                )
            )

        # 2. Sparse (BM25) 稀疏词法模型推理探针
        if embedder is not None:
            try:
                start_sparse = time.perf_counter()
                sparse_vec = embedder.embed_sparse_one("Preflight diagnostic probe query text.")
                sparse_lat = (time.perf_counter() - start_sparse) * 1000.0
                indices, values = sparse_vec
                items.append(
                    DiagnosticItem(
                        name="Sparse (BM25) 词法模型探针",
                        status=CheckStatus.PASS,
                        message=f"BM25 词法编码正常 (激活维度数: {len(indices)}, 推理: {sparse_lat:.1f}ms)",
                        latency_ms=sparse_lat,
                        details={"active_indices_count": len(indices)},
                    )
                )
            except Exception as exc:  # noqa: BLE001
                items.append(
                    DiagnosticItem(
                        name="Sparse (BM25) 词法模型探针",
                        status=CheckStatus.FAIL,
                        message=f"BM25 词法模型推理失败: {exc}",
                        remediation="请检查 fastembed 模型缓存或重新同步依赖",
                    )
                )
        else:
            items.append(
                DiagnosticItem(
                    name="Sparse (BM25) 词法模型探针",
                    status=CheckStatus.SKIP,
                    message="因 Dense 管道初始化失败，跳过 Sparse 探针",
                )
            )

        # 3. Cross-Encoder 精排模型探针
        rerank_cfg = settings.rerank.model_copy(
            update={"cache_dir": str(settings.resolve_path(settings.rerank.cache_dir))}
        )
        try:
            start_load_rr = time.perf_counter()
            reranker = Reranker(rerank_cfg)
            rr_load_lat = (time.perf_counter() - start_load_rr) * 1000.0

            start_score = time.perf_counter()
            scores = reranker.score(
                query="function definition",
                documents=["def calculate_hash(data): return sha256(data)", "SELECT * FROM users;"],
            )
            rr_score_lat = (time.perf_counter() - start_score) * 1000.0
            model_id = (
                settings.rerank.local.model_name
                if settings.rerank.mode == "local"
                else settings.rerank.remote.model
            )

            items.append(
                DiagnosticItem(
                    name="Cross-Encoder 精排模型探针",
                    status=CheckStatus.PASS,
                    message=(
                        f"精排模型 '{model_id}' (mode={settings.rerank.mode}) 样本打分正常 "
                        f"(样本分数: {[round(s, 3) for s in scores]}, 加载: {rr_load_lat:.1f}ms, 推理: {rr_score_lat:.1f}ms)"
                    ),
                    latency_ms=rr_score_lat,
                    details={
                        "model": model_id,
                        "mode": settings.rerank.mode,
                        "sample_scores": scores,
                        "load_latency_ms": round(rr_load_lat, 2),
                        "infer_latency_ms": round(rr_score_lat, 2),
                    },
                )
            )
            reranker.close()
        except Exception as exc:  # noqa: BLE001
            items.append(
                DiagnosticItem(
                    name="Cross-Encoder 精排模型探针",
                    status=CheckStatus.FAIL,
                    message=f"精排模型加载或打分失败: {exc}",
                    remediation="请核对 [rerank] 配置或检查 Cross-Encoder ONNX 权重完整性",
                )
            )

        if embedder is not None:
            embedder.close()

        return items
