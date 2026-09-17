"""Dense/Sparse 双路向量化管道（03 §1）。

Ingest 与 Retrieve 两条流水线共用同一份编码逻辑（切分后向量化 / 查询编码，见
01_architecture_overview.md §3）。

Dense 向量按 ``[embedding].mode`` 二选一：
- ``"remote"``（默认）：调用 OpenAI 兼容的 ``POST {base_url}/embeddings`` 接口
  （``[embedding.remote]``，默认网关 ``https://api.openlux.ai/v1``）；
- ``"local"``：本地 FastEmbed ONNX 推理（``[embedding.local]``），离线/无 key 时的兜底。

Sparse (BM25) 向量与 ``mode`` 无关，永远走本地 FastEmbed——不存在"远程 BM25 API"
这种东西，BM25 是基于语料的词法统计方法，本模块的导入本身不做任何网络 I/O，
只有实例化后才会视 ``mode`` 触发本地模型加载或远端请求。
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

import httpx
from fastembed import SparseTextEmbedding, TextEmbedding
from loguru import logger

from api.errors import UpstreamModelError
from api.settings import EmbeddingConfig

__all__ = ["EmbeddingPipeline", "SparseVector"]

#: 稀疏向量的 (indices, values) 二元组（对齐 Qdrant SparseVector 构造参数）
SparseVector = Tuple[List[int], List[float]]

#: Sparse 向量模型固定为 Qdrant/bm25（ADR §2.2，非配置项——见 03 §1）
_SPARSE_MODEL_NAME = "Qdrant/bm25"


class EmbeddingPipeline:
    """Dense + Sparse 双路向量化封装。

    Args:
        config: ``[embedding]`` 段强类型配置（含 ``mode``/``local``/``remote`` 三块）。
    """

    def __init__(self, config: EmbeddingConfig) -> None:
        self._config = config
        self._sparse = SparseTextEmbedding(model_name=_SPARSE_MODEL_NAME, cache_dir=config.cache_dir)

        self._local: TextEmbedding | None = None
        self._remote_client: httpx.Client | None = None

        if config.mode == "local":
            self._local = TextEmbedding(model_name=config.local.model_name, cache_dir=config.cache_dir)
        else:
            api_key = config.remote.api_key
            if not api_key:
                raise UpstreamModelError(
                    f"embedding.mode=\"remote\" 但环境变量 {config.remote.api_key_env} 未设置或为空",
                    endpoint="embedding",
                )
            self._remote_client = httpx.Client(
                base_url=config.remote.base_url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=config.remote.timeout_sec,
            )

    def close(self) -> None:
        """关闭远端 HTTP 客户端（``mode="local"`` 时为空操作）。"""
        if self._remote_client is not None:
            self._remote_client.close()

    # ------------------------------------------------------------------
    # Dense
    # ------------------------------------------------------------------

    def embed_dense(self, texts: Sequence[str]) -> List[List[float]]:
        """批量生成 Dense 向量（按 ``mode`` 分派本地/远端实现）。

        Args:
            texts: 待编码文本（切片正文或查询文本）。

        Returns:
            与 ``texts`` 等长的向量列表；空输入返回空列表。

        Raises:
            UpstreamModelError: 远端请求失败（网络异常、非 2xx 响应）时抛出。
        """
        if not texts:
            return []
        if self._local is not None:
            vectors = self._local.embed(list(texts), batch_size=self._config.batch_size)
            return [vector.tolist() for vector in vectors]
        return self._embed_dense_remote(texts)

    def _embed_dense_remote(self, texts: Sequence[str]) -> List[List[float]]:
        """调用 OpenAI 兼容 ``/embeddings`` 接口，按 ``batch_size`` 分批请求。

        Args:
            texts: 待编码文本。

        Returns:
            与 ``texts`` 等长的向量列表，按请求内 ``index`` 还原顺序。

        Raises:
            UpstreamModelError: 网络异常或响应非 2xx 时抛出。
        """
        assert self._remote_client is not None  # noqa: S101 — 内部不变量，mode="remote" 时必然已构造
        results: List[List[float]] = []
        batch_size = self._config.batch_size
        for start in range(0, len(texts), batch_size):
            batch = list(texts[start : start + batch_size])
            try:
                response = self._remote_client.post(
                    "/embeddings", json={"model": self._config.remote.model, "input": batch}
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise UpstreamModelError(
                    f"远端 Embedding 请求失败: {exc}", endpoint="embedding", base_url=self._config.remote.base_url
                ) from exc

            payload = response.json()
            items = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
            if len(items) != len(batch):
                raise UpstreamModelError(
                    f"远端 Embedding 返回条目数 {len(items)} 与请求条目数 {len(batch)} 不一致",
                    endpoint="embedding",
                )
            results.extend(item["embedding"] for item in items)
        return results

    def embed_dense_one(self, text: str) -> List[float]:
        """编码单条文本的 Dense 向量（查询编码的便捷入口）。"""
        return self.embed_dense([text])[0]

    # ------------------------------------------------------------------
    # Sparse（永远本地，与 mode 无关）
    # ------------------------------------------------------------------

    def embed_sparse(self, texts: Sequence[str]) -> List[SparseVector]:
        """批量生成 Sparse (BM25) 向量（恒本地计算，见模块级说明）。

        Args:
            texts: 待编码文本。

        Returns:
            与 ``texts`` 等长的 ``(indices, values)`` 列表；空输入返回空列表。
        """
        if not texts:
            return []
        embeddings = self._sparse.embed(list(texts), batch_size=self._config.batch_size)
        return [(embedding.indices.tolist(), embedding.values.tolist()) for embedding in embeddings]

    def embed_sparse_one(self, text: str) -> SparseVector:
        """编码单条文本的 Sparse 向量（查询编码的便捷入口）。"""
        return self.embed_sparse([text])[0]

    # ------------------------------------------------------------------
    # 自检
    # ------------------------------------------------------------------

    def probe_dense_dimension(self) -> int:
        """探测当前生效 Dense 模型的真实输出维度（供启动期与 ``[qdrant].vector_size`` 校验）。

        Returns:
            探测向量的长度。

        Raises:
            UpstreamModelError: 远端探测请求失败时抛出。
        """
        vector = self.embed_dense_one("dimension probe")
        logger.debug(f"[EmbeddingPipeline] 探测到 Dense 向量维度: {len(vector)}")
        return len(vector)
