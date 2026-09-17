"""对外 DTO：``RetrieveRequest``/``Response``、``IngestRequest``/``Response``、``HealthResponse``。

规范：documents/rag_retrieval/05_http_api_and_client_contract.md §1。

字段命名与 Agent 侧 ``AegisAgent/src/tools/builtin/rag_search.py``（已实现）严格对齐；
``chunk_id`` 字段不可省略——``src/evaluation/rag_bench/`` 评测 harness 靠它比对金标
（见 06_evaluation_and_benchmarking.md §1，05 §1.1 的说明）。
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "RetrieveFilters",
    "RetrieveRequest",
    "ChunkResult",
    "RetrieveResponse",
    "IngestRequest",
    "IngestResponse",
    "QdrantHealth",
    "HealthResponse",
]

#: 06 §3 消融矩阵的调试模式；生产 Agent 侧调用永远不传（默认 "hybrid"）
RetrieveMode = Literal["hybrid", "dense_only", "sparse_only", "hybrid_no_rerank"]


class RetrieveFilters(BaseModel):
    """可选的 Payload 预过滤条件（04 §2）。"""

    model_config = ConfigDict(extra="ignore")

    language: Optional[str] = Field(default=None, description="限定语言（c/cpp/go/python/markdown 等）")


class RetrieveRequest(BaseModel):
    """``POST /api/v1/retrieve`` 请求体。

    Attributes:
        query: 检索意图文本。
        top_k: 返回切片数量上限；缺省取 ``[retrieval].default_top_k``。
        filters: 可选 Payload 过滤条件。
        mode: 消融调试模式（06 §3），生产调用不传，默认走完整 Hybrid+Rerank 链路。
    """

    model_config = ConfigDict(extra="ignore")

    query: str = Field(min_length=1, description="检索意图文本")
    top_k: Optional[int] = Field(default=None, gt=0, description="返回切片数量上限")
    filters: Optional[RetrieveFilters] = Field(default=None, description="可选 Payload 过滤条件")
    mode: RetrieveMode = Field(default="hybrid", description="消融调试模式（06 §3），生产调用不传")


class ChunkResult(BaseModel):
    """检索结果中的单个切片。

    Attributes:
        chunk_id: Qdrant 确定性 Point ID（03 §3），评测 harness 比对金标的关键字段。
        file_path: 相对仓库根目录路径。
        start_line: 起始行号。
        end_line: 终止行号。
        content: 切片原文（完整未截断）。
        git_commit: 索引时的提交哈希，可选。
        score: 精排相关性分数（`mode="hybrid_no_rerank"` 或 `*_only` 时为融合/相似度分数）。
    """

    model_config = ConfigDict(extra="ignore")

    chunk_id: str = Field(description="Qdrant 确定性 Point ID")
    file_path: str
    start_line: int
    end_line: int
    content: str
    git_commit: Optional[str] = None
    enclosing_scope: Optional[str] = None
    score: float


class RetrieveResponse(BaseModel):
    """``POST /api/v1/retrieve`` 响应体。

    Attributes:
        results: 切片数组（唯一权威字段名，不使用 ``chunks``，见 05 §1.1 说明）。
        low_confidence: 见 04 §4，全部结果精排分数偏低时置 ``true``。
    """

    model_config = ConfigDict(extra="ignore")

    results: List[ChunkResult] = Field(default_factory=list)
    low_confidence: bool = False


class IngestRequest(BaseModel):
    """``POST /api/v1/documents/ingest`` 请求体（05 §1.2）。

    Attributes:
        repo_root: 目标仓库绝对路径。
        repo_name: 仓库标识（Payload 过滤用，见 03 §2）。
        incremental: ``True``（默认）走哈希增量策略；``False`` 忽略现存哈希强制全量重建。
    """

    model_config = ConfigDict(extra="ignore")

    repo_root: str = Field(min_length=1, description="目标仓库绝对路径")
    repo_name: str = Field(min_length=1, description="仓库标识")
    incremental: bool = Field(default=True, description="是否走哈希增量策略")


class IngestResponse(BaseModel):
    """``POST /api/v1/documents/ingest`` 响应体（05 §1.2）。

    Attributes:
        indexed: 新写入/更新的切片数。
        skipped: 内容未变、跳过向量化的切片数（见 03 §3）。
        deleted: 因源文件已不存在而清理的旧切片数（见 03 §4）。
        degraded_files: AST 解析失败、降级走通用切分的文件列表（见 02 §4）。
        duration_ms: 本次 ingest 总耗时。
    """

    model_config = ConfigDict(extra="ignore")

    indexed: int = 0
    skipped: int = 0
    deleted: int = 0
    degraded_files: List[str] = Field(default_factory=list)
    duration_ms: int = 0


class QdrantHealth(BaseModel):
    """健康检查中的 Qdrant 子状态（05 §1.3）。"""

    model_config = ConfigDict(extra="ignore")

    mode: str
    collection_ready: bool
    point_count: int
    vector_size: int


class HealthResponse(BaseModel):
    """``GET /api/v1/health`` 响应体（05 §1.3）。

    ``collection_ready=False`` 或 ``embedding_model_loaded=False`` 时，
    ``status`` 应整体置为 ``"degraded"``（01 §5 故障隔离契约）。
    """

    model_config = ConfigDict(extra="ignore")

    status: str
    service: str = "aegis-rag"
    version: str
    qdrant: QdrantHealth
    embedding_model_loaded: bool
