"""AegisRAG 领域异常体系（与 HTTP 状态码解耦，由 ``app.py`` 的异常处理器转译）。

规范：documents/rag_retrieval/05_http_api_and_client_contract.md §2。

边界约束：本模块零第三方依赖，不 import ``AegisAgent`` 的任何模块
（AegisRAG 是物理独立子工程，见 01_architecture_overview.md §1）。
"""

from __future__ import annotations

from typing import Any, Dict

__all__ = [
    "RagError",
    "CollectionNotReadyError",
    "DimensionMismatchError",
    "RepoNotIndexedError",
    "UpstreamModelError",
]


class RagError(Exception):
    """AegisRAG 领域异常基类。

    Attributes:
        code: 稳定错误码（见 05 §2 错误码表），供客户端做条件判断。
        message: 人类可读描述。
        extra: 附加结构化字段。
    """

    #: 子类必须覆盖：稳定错误码
    code: str = "RAG_ERROR"

    def __init__(self, message: str, **extra: Any) -> None:
        """初始化领域异常。

        Args:
            message: 人类可读描述。
            **extra: 附加结构化字段（进入 :meth:`to_dict` 输出）。
        """
        super().__init__(message)
        self.message = message
        self.extra = extra

    def to_dict(self) -> Dict[str, Any]:
        """转换为统一结构化错误响应体载荷。

        Returns:
            含 ``code``/``message`` 及附加字段的字典。
        """
        payload: Dict[str, Any] = {"code": self.code, "message": self.message}
        payload.update(self.extra)
        return payload


class CollectionNotReadyError(RagError):
    """Qdrant 未连接、Collection 未初始化，或目标仓库从未 ``ingest`` 过。

    对应 HTTP 503（见 05 §2）。
    """

    code = "COLLECTION_NOT_READY"


class DimensionMismatchError(RagError):
    """Collection 已存在的向量维度与 ``[qdrant].vector_size`` 不一致。

    理论上只应在启动期被 ``storage.qdrant_store.QdrantStore.ensure_collection``
    捕获并拒绝启动；运行期出现说明启动校验被绕过，属于服务端 bug（见 05 §2）。
    对应 HTTP 500。
    """

    code = "DIMENSION_MISMATCH"


class RepoNotIndexedError(RagError):
    """对不存在索引记录的 ``repo_name``/``repo_root`` 发起操作。

    对应 HTTP 404（见 05 §2）。
    """

    code = "REPO_NOT_INDEXED"


class UpstreamModelError(RagError):
    """``mode="remote"`` 时调用远端 Embedding/Rerank 网关失败（网络异常、鉴权失败、非 2xx 响应等）。

    对应 HTTP 502（网关错误——AegisRAG 自身正常，是它依赖的上游出了问题，
    与"AegisRAG 自己没准备好"的 503/COLLECTION_NOT_READY 语义不同）。
    """

    code = "UPSTREAM_MODEL_ERROR"
