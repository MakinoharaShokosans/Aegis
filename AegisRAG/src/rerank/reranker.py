"""Cross-Encoder 精排封装（04 §3，核心范围，非可选项）。

独立成包而非挂在 ``indexer/`` 下：精排发生在 Retrieve 阶段查询到达之后，
与 Ingest 侧的语法切分生命周期完全不同（归属裁决见 07_directory_structure.md §4①）。

按 ``[rerank].mode`` 二选一：
- ``"remote"``（默认）：调用 OpenAI 兼容风格的 ``POST {base_url}/rerank`` 接口
  （``[rerank.remote]``，默认网关 ``https://api.openlux.ai/v1``）。
  **协议提醒**：OpenAI 官方 API 本身没有标准 rerank 端点，这里采用的
  ``{"model","query","documents"}`` → ``{"results":[{"index","relevance_score"}]}``
  是部分 OpenAI 兼容网关常见的事实标准约定，首次真实联调前需对照实际网关
  文档核实，不能当作已验证过的规范。
- ``"local"``：本地 ``fastembed.rerank.cross_encoder.TextCrossEncoder``
  （``[rerank.local]``），离线/无 key 时的兜底。
"""

from __future__ import annotations

from typing import List, Sequence

import httpx
from fastembed.rerank.cross_encoder import TextCrossEncoder

from api.errors import UpstreamModelError
from api.settings import RerankConfig

__all__ = ["Reranker"]


class Reranker:
    """Cross-Encoder 精排器封装。

    Args:
        config: ``[rerank]`` 段强类型配置（含 ``mode``/``local``/``remote`` 三块）。
    """

    def __init__(self, config: RerankConfig) -> None:
        self._config = config
        self._local: TextCrossEncoder | None = None
        self._remote_client: httpx.Client | None = None

        if config.mode == "local":
            self._local = TextCrossEncoder(model_name=config.local.model_name, cache_dir=config.cache_dir)
        else:
            api_key = config.remote.api_key
            if not api_key:
                raise UpstreamModelError(
                    f"rerank.mode=\"remote\" 但环境变量 {config.remote.api_key_env} 未设置或为空",
                    endpoint="rerank",
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

    def score(self, query: str, documents: Sequence[str]) -> List[float]:
        """对一批候选文档相对 query 的相关性打分。

        Args:
            query: 查询文本。
            documents: 候选文档正文列表；应为一次批量调用（04 §3），不逐条调用。

        Returns:
            与 ``documents`` 等长的相关性分数列表；分数未做归一化，
            ``[rerank].min_score`` 的阈值需基于这里的真实输出分布校准（04 §4）。
            空输入返回空列表。

        Raises:
            UpstreamModelError: ``mode="remote"`` 且请求失败（网络异常、非 2xx
                响应、返回条目数不匹配）时抛出。
        """
        if not documents:
            return []
        if self._local is not None:
            return list(self._local.rerank(query, list(documents)))
        return self._score_remote(query, documents)

    def _score_remote(self, query: str, documents: Sequence[str]) -> List[float]:
        """调用远端 ``/rerank`` 接口（见类文档的协议约定与免责提醒）。"""
        assert self._remote_client is not None  # noqa: S101 — 内部不变量，mode="remote" 时必然已构造
        docs = list(documents)
        try:
            response = self._remote_client.post(
                "/rerank", json={"model": self._config.remote.model, "query": query, "documents": docs}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamModelError(
                f"远端 Rerank 请求失败: {exc}", endpoint="rerank", base_url=self._config.remote.base_url
            ) from exc

        payload = response.json()
        results = sorted(payload.get("results", []), key=lambda item: item.get("index", 0))
        if len(results) != len(docs):
            raise UpstreamModelError(
                f"远端 Rerank 返回条目数 {len(results)} 与请求条目数 {len(docs)} 不一致", endpoint="rerank"
            )
        return [float(item["relevance_score"]) for item in results]
