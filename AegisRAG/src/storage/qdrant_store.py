"""Qdrant 客户端适配器：Collection 初始化、维度校验、混合检索、幂等写入、失效清理。

规范：documents/rag_retrieval/03_embedding_and_storage.md、04_hybrid_retrieval_and_rerank.md §1/§2。

Ingest 与 Retrieve 两条流水线共用本模块（01 §3）；`indexer/`、`embeddings/`、`rerank/`
互不依赖，只有 `api/` 编排调用本模块（依赖矩阵见 07_directory_structure.md §5）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, TypeVar

from loguru import logger
from qdrant_client import QdrantClient, models

from api.errors import CollectionNotReadyError, DimensionMismatchError
from api.settings import QdrantConfig
from embeddings.pipeline import SparseVector
from indexer.metadata import ChunkMetadata
from storage.ids import point_id_for

__all__ = ["QdrantStore"]

_T = TypeVar("_T")

#: 单次 upsert/retrieve 请求的最大条目数——大仓库一次 ingest 可能产生数千个
#: 切片，分批请求比单次超大 payload 更稳妥（既不测试也不调过具体数值，
#: 256 是 Qdrant 官方文档常见的批量写入参考量级，非配置项：这是工程健全性
#: 上限，不是业务可调参数，与 [retrieval]/[rerank] 的定位不同）。
_BATCH_SIZE = 256


def _chunked(items: Sequence[_T], size: int) -> Iterator[Sequence[_T]]:
    """把序列切成固定大小的批次（最后一批可能不足 size）。"""
    for start in range(0, len(items), size):
        yield items[start : start + size]


#: Payload 中承载"命名空间"字段（多仓库过滤，03 §2）
_PAYLOAD_VECTOR_DENSE = "dense"
_PAYLOAD_VECTOR_SPARSE = "sparse"


class QdrantStore:
    """AegisRAG 的 Qdrant 存储适配器。

    Args:
        config: ``[qdrant]`` 段强类型配置。
        storage_path: ``mode="local"`` 时的本地持久化目录（已解析为绝对路径）。
    """

    def __init__(self, config: QdrantConfig, *, storage_path: Path) -> None:
        self._config = config
        if config.mode == "local":
            self._client = QdrantClient(path=str(storage_path))
        else:
            self._client = QdrantClient(host=config.host, port=config.port, api_key=config.api_key)
        self._collection_ready = False

    @property
    def collection_ready(self) -> bool:
        """Collection 是否已就绪（维度校验通过或刚创建成功）。"""
        return self._collection_ready

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def ensure_collection(self) -> None:
        """确保 Collection 存在且维度一致；不存在则创建，存在则强校验（03 §2）。

        Raises:
            DimensionMismatchError: 已存在的 Collection 的 dense 向量维度与
                ``[qdrant].vector_size`` 不一致时抛出（启动期 fail-fast）。
        """
        name = self._config.collection_name
        if not self._client.collection_exists(name):
            distance = getattr(models.Distance, self._config.distance.upper(), None)
            if distance is None:
                raise ValueError(f"未知的距离度量: {self._config.distance!r}")
            self._client.create_collection(
                collection_name=name,
                vectors_config={
                    _PAYLOAD_VECTOR_DENSE: models.VectorParams(size=self._config.vector_size, distance=distance)
                },
                sparse_vectors_config={_PAYLOAD_VECTOR_SPARSE: models.SparseVectorParams()},
            )
            logger.info(f"[QdrantStore] Collection {name!r} 已创建（vector_size={self._config.vector_size}）")
            self._collection_ready = True
            return

        info = self._client.get_collection(name)
        actual_size = info.config.params.vectors[_PAYLOAD_VECTOR_DENSE].size
        if actual_size != self._config.vector_size:
            self._collection_ready = False
            raise DimensionMismatchError(
                f"Collection {name!r} 现有 dense 向量维度为 {actual_size}，"
                f"与配置 vector_size={self._config.vector_size} 不一致",
                collection=name,
                actual_size=actual_size,
                expected_size=self._config.vector_size,
            )
        self._collection_ready = True

    def close(self) -> None:
        """关闭底层客户端连接。"""
        self._client.close()

    # ------------------------------------------------------------------
    # 写入（Ingest 侧）
    # ------------------------------------------------------------------

    def existing_ids(self, point_ids: Sequence[str]) -> set:
        """批量查询哪些 Point ID 已存在（用于增量跳过判定，03 §3）。

        大仓库一次 ingest 可能产生成千上万个切片；分批查询（见 ``_BATCH_SIZE``），
        避免把全部 ID 塞进单次请求。

        Args:
            point_ids: 待检查的 Point ID 列表。

        Returns:
            已存在于 Collection 中的 ID 集合。
        """
        if not point_ids:
            return set()
        existing: set = set()
        for batch in _chunked(list(point_ids), _BATCH_SIZE):
            records = self._client.retrieve(
                self._config.collection_name, ids=batch, with_payload=False, with_vectors=False
            )
            existing.update(str(record.id) for record in records)
        return existing

    def upsert_chunks(
        self,
        chunks: Sequence[ChunkMetadata],
        dense_vectors: Sequence[List[float]],
        sparse_vectors: Sequence[SparseVector],
    ) -> int:
        """幂等写入一批切片（确定性 Point ID，覆盖式 upsert，03 §3）。

        Args:
            chunks: 切片元数据列表。
            dense_vectors: 与 ``chunks`` 等长的 Dense 向量。
            sparse_vectors: 与 ``chunks`` 等长的 Sparse 向量。

        Returns:
            实际写入的切片数。

        Raises:
            ValueError: 三个序列长度不一致时抛出。
        """
        if not (len(chunks) == len(dense_vectors) == len(sparse_vectors)):
            raise ValueError("chunks / dense_vectors / sparse_vectors 长度必须一致")
        if not chunks:
            return 0

        points: List[models.PointStruct] = [
            models.PointStruct(
                id=point_id_for(chunk),
                vector={
                    _PAYLOAD_VECTOR_DENSE: dense_vec,
                    _PAYLOAD_VECTOR_SPARSE: models.SparseVector(indices=sparse_idx, values=sparse_val),
                },
                payload=chunk.model_dump(),
            )
            for chunk, dense_vec, (sparse_idx, sparse_val) in zip(chunks, dense_vectors, sparse_vectors)
        ]
        # 分批写入（见 _BATCH_SIZE）：大仓库单次 ingest 可能产生数千个切片，
        # 一次性塞进单个 upsert 请求不是好习惯。
        for batch in _chunked(points, _BATCH_SIZE):
            self._client.upsert(self._config.collection_name, points=batch)
        return len(points)

    def delete_stale(self, repo_name: str, keep_file_paths: Iterable[str]) -> int:
        """清理某仓库下"本次 ingest 未再产出"的旧切片（文件删除场景，03 §4）。

        Args:
            repo_name: 仓库标识。
            keep_file_paths: 本次 ingest 实际处理到的 ``file_path`` 集合（应保留）。

        Returns:
            本次实际删除的切片数（近似值：删除前的匹配计数）。
        """
        keep_list = list(keep_file_paths)
        stale_filter = models.Filter(
            must=[models.FieldCondition(key="repo_name", match=models.MatchValue(value=repo_name))],
            must_not=(
                [models.FieldCondition(key="file_path", match=models.MatchAny(any=keep_list))]
                if keep_list
                else []
            ),
        )
        before = self._client.count(self._config.collection_name, count_filter=stale_filter, exact=True).count
        if before == 0:
            return 0
        self._client.delete(self._config.collection_name, points_selector=models.FilterSelector(filter=stale_filter))
        return before

    # ------------------------------------------------------------------
    # 查询（Retrieve 侧）
    # ------------------------------------------------------------------

    def query_hybrid(
        self,
        *,
        dense_vector: List[float],
        sparse_vector: SparseVector,
        dense_top_k: int,
        sparse_top_k: int,
        fusion_top_k: int,
        language: Optional[str] = None,
        mode: str = "hybrid",
    ) -> List[models.ScoredPoint]:
        """执行一次检索（04 §1/§2）。

        Args:
            dense_vector: 查询的 Dense 向量。
            sparse_vector: 查询的 Sparse 向量。
            dense_top_k: Dense 路 prefetch 候选数量（``[retrieval].dense_top_k``）。
            sparse_top_k: Sparse 路 prefetch 候选数量（``[retrieval].sparse_top_k``）。
            fusion_top_k: RRF 融合后的候选数量（``[retrieval].fusion_top_k``）。
            language: 可选语言过滤（下推到 prefetch 查询层，04 §2）。
            mode: ``"hybrid"``/``"hybrid_no_rerank"``（双路召回 + RRF 融合，两者在
                本层行为一致，精排与否由调用方决定）、``"dense_only"``、``"sparse_only"``
                （06 §3 消融调试用，生产调用恒为 ``"hybrid"``）。

        Returns:
            候选点列表（含 payload），已按相关性排序。

        Raises:
            CollectionNotReadyError: Collection 尚未就绪时抛出。
        """
        if not self._collection_ready:
            raise CollectionNotReadyError(
                f"Collection {self._config.collection_name!r} 尚未就绪，请先调用 ensure_collection() "
                "或该仓库尚未 ingest",
                collection=self._config.collection_name,
            )

        query_filter = self._build_language_filter(language)

        if mode == "dense_only":
            result = self._client.query_points(
                self._config.collection_name,
                query=dense_vector,
                using=_PAYLOAD_VECTOR_DENSE,
                limit=fusion_top_k,
                query_filter=query_filter,
                with_payload=True,
            )
            return result.points

        if mode == "sparse_only":
            indices, values = sparse_vector
            result = self._client.query_points(
                self._config.collection_name,
                query=models.SparseVector(indices=indices, values=values),
                using=_PAYLOAD_VECTOR_SPARSE,
                limit=fusion_top_k,
                query_filter=query_filter,
                with_payload=True,
            )
            return result.points

        indices, values = sparse_vector
        result = self._client.query_points(
            self._config.collection_name,
            prefetch=[
                models.Prefetch(
                    query=dense_vector,
                    using=_PAYLOAD_VECTOR_DENSE,
                    limit=dense_top_k,
                    filter=query_filter,
                ),
                models.Prefetch(
                    query=models.SparseVector(indices=indices, values=values),
                    using=_PAYLOAD_VECTOR_SPARSE,
                    limit=sparse_top_k,
                    filter=query_filter,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=fusion_top_k,
            with_payload=True,
        )
        return result.points

    def _build_language_filter(self, language: Optional[str]) -> Optional[models.Filter]:
        """构造语言过滤条件（04 §2：下推到召回层，而非事后过滤）。"""
        if not language:
            return None
        return models.Filter(must=[models.FieldCondition(key="language", match=models.MatchValue(value=language))])

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------

    def health_snapshot(self) -> dict:
        """健康检查所需的 Qdrant 子状态快照（05 §1.3）。

        Returns:
            ``{"mode", "collection_ready", "point_count", "vector_size"}``。
        """
        point_count = 0
        if self._collection_ready:
            try:
                # exact=False：健康检查是高频存活探针，用近似计数（O(1)）即可，
                # 不该为了报个大概的 point_count 在大 Collection 上做一次精确扫描。
                point_count = self._client.count(self._config.collection_name, exact=False).count
            except Exception as exc:  # noqa: BLE001 — 健康检查不应因计数失败而崩溃
                logger.warning(f"[QdrantStore] 健康检查计数失败: {exc}")
        return {
            "mode": self._config.mode,
            "collection_ready": self._collection_ready,
            "point_count": point_count,
            "vector_size": self._config.vector_size,
        }
