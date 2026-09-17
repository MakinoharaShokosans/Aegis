"""AegisRAG 服务配置：``config/rag_config.toml`` → 强类型 Pydantic 模型。

规范：documents/rag_retrieval/07_directory_structure.md §2（``api/settings.py``）；
各字段语义详见 documents/rag_retrieval/README.md §4（配置项唯一真源）、§5（环境变量唯一真源）。

设计要点：
1. **零硬编码**：召回候选数、融合候选数、返回数量、精排阈值等全部可调参数
   一律取自 ``rag_config.toml``，代码中不出现散落的字面数字
   （呼应 04_hybrid_retrieval_and_rerank.md 开篇"本文档不重复配置数值"的纪律）。
2. **fail-closed**：六个配置段落中，除未来增强预留项（``rse_max_gap``/``mmr_lambda``）
   与占位阈值（``[rerank].min_score``）外，其余字段缺失即在启动阶段抛校验错误；
   ``[qdrant].mode="local"`` 与 ``[server].workers>1`` 同时出现同样在此处拒绝（01 §4）。
3. **物理独立**：本模块不依赖 ``AegisAgent`` 的任何模块（01_architecture_overview.md §1）；
   只依赖标准库 ``tomllib``、``pydantic`` 与（用于加载 ``.env``）``python-dotenv``
   ——后者已作为 ``pydantic-settings`` 的传递依赖存在，未额外声明新依赖。
"""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "RagConfig",
    "ServerConfig",
    "QdrantConfig",
    "EmbeddingConfig",
    "IndexerConfig",
    "RetrievalConfig",
    "RerankConfig",
    "get_settings",
    "project_root",
    "find_config_file",
]

#: 服务监听地址安全红线：仅允许回环地址（与 AegisAgent 侧 ServerConfig 的约束一致）
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

#: config/rag_config.toml 的候选相对路径（按优先级），兼容从项目根或子目录启动
_CANDIDATE_CONFIG_PATHS = (
    Path("config/rag_config.toml"),
    Path("AegisRAG/config/rag_config.toml"),
    Path(__file__).resolve().parent.parent.parent / "config" / "rag_config.toml",
)


def find_config_file() -> Path:
    """定位 ``rag_config.toml`` 的绝对路径。

    Returns:
        首个存在的候选路径。

    Raises:
        FileNotFoundError: 所有候选路径均不存在，且未设置 ``AEGIS_RAG_CONFIG`` 时抛出。
    """
    override = os.getenv("AEGIS_RAG_CONFIG", "").strip()
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"AEGIS_RAG_CONFIG 指向的文件不存在: {candidate}")

    for candidate in _CANDIDATE_CONFIG_PATHS:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "未找到 config/rag_config.toml，请从 AegisRAG 项目根目录启动或设置 AEGIS_RAG_CONFIG"
    )


def project_root() -> Path:
    """定位 AegisRAG 工程根目录。

    以 ``config/rag_config.toml`` 的位置反推：``<root>/config/rag_config.toml``
    ⇒ 根目录为其父目录的父目录。用于把配置中的相对路径解析为绝对路径，
    避免依赖进程启动时的当前工作目录。

    Returns:
        AegisRAG 工程根目录绝对路径。
    """
    return find_config_file().resolve().parent.parent


class ServerConfig(BaseModel):
    """``[server]`` 段：FastAPI 监听与请求超时。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    host: str = Field(description="HTTP 监听地址（安全红线：仅允许回环）")
    port: int = Field(ge=1, le=65535, description="HTTP 监听端口")
    workers: int = Field(ge=1, description="uvicorn worker 数量")
    timeout_sec: float = Field(gt=0, description="请求超时（秒）")

    @model_validator(mode="after")
    def _guard_loopback(self) -> "ServerConfig":
        """安全护栏：拒绝非回环监听地址。"""
        if self.host not in _LOOPBACK_HOSTS:
            raise ValueError(
                f"server.host 必须为回环地址，当前为 {self.host!r}。AegisRAG 不对外暴露。"
            )
        return self


class QdrantConfig(BaseModel):
    """``[qdrant]`` 段：Collection 寻址与双部署形态（01 §4）。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    mode: str = Field(description='"local"（本地嵌入式存储）或 "server"（独立容器）')
    storage_path: str = Field(description="本地模式的持久化目录")
    host: str = Field(description="独立容器模式的连接地址")
    port: int = Field(ge=1, le=65535, description="独立容器模式的连接端口")
    collection_name: str = Field(min_length=1, description="Collection 名称")
    vector_size: int = Field(gt=0, description="Dense 向量维度")
    distance: str = Field(description="向量距离度量（如 Cosine）")

    @model_validator(mode="after")
    def _validate_mode(self) -> "QdrantConfig":
        """校验 ``mode`` 取值合法。"""
        if self.mode not in ("local", "server"):
            raise ValueError(f'qdrant.mode 必须是 "local" 或 "server"，当前为 {self.mode!r}')
        return self

    @property
    def api_key(self) -> Optional[str]:
        """从环境变量解析 Qdrant 鉴权密钥（见 README.md §5）。

        Returns:
            ``QDRANT_API_KEY``（非空时）；``mode="local"`` 或未设置时为 ``None``。
        """
        if self.mode != "server":
            return None
        value = os.getenv("QDRANT_API_KEY", "").strip()
        return value or None


class EmbeddingLocalConfig(BaseModel):
    """``[embedding.local]`` 段：本地 FastEmbed ONNX Dense 模型。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    model_name: str = Field(min_length=1, description="本地 Dense 嵌入模型（FastEmbed/HuggingFace 模型 ID）")


class EmbeddingRemoteConfig(BaseModel):
    """``[embedding.remote]`` 段：远端 OpenAI 兼容 ``/embeddings`` 接口。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    base_url: str = Field(min_length=1, description="OpenAI 兼容网关基址")
    model: str = Field(min_length=1, description="远端 Dense 嵌入模型 ID")
    api_key_env: str = Field(min_length=1, description="引用自 .env 的 API Key 环境变量名")
    timeout_sec: float = Field(gt=0, description="单次请求超时（秒）")

    @property
    def api_key(self) -> Optional[str]:
        """从环境变量解析真实密钥；缺失时返回 ``None``（由调用方决定如何失败）。"""
        value = os.getenv(self.api_key_env, "").strip()
        return value or None


class EmbeddingConfig(BaseModel):
    """``[embedding]`` 段：Dense 向量生成（03 §1）。

    ``mode`` 二选一，仿照 ``[qdrant].mode`` 的 local/server 设计：
    ``"remote"``（默认）走 ``[embedding.remote]`` 的 OpenAI 兼容接口；``"local"``
    走 ``[embedding.local]`` 的本地 FastEmbed ONNX 模型。Sparse (BM25) 向量与
    ``mode`` 无关，永远走本地 FastEmbed（不存在"远程 BM25 API"这种东西），
    因此 ``cache_dir``/``batch_size``/``max_length`` 三项无论哪种 ``mode`` 都生效。
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    mode: str = Field(description='Dense 向量来源："remote"（默认）或 "local"')
    cache_dir: str = Field(min_length=1, description="FastEmbed ONNX 模型缓存目录（Sparse 恒生效）")
    batch_size: int = Field(gt=0, description="批处理大小")
    max_length: int = Field(gt=0, description="单切片截断上限（token 近似值）")
    local: EmbeddingLocalConfig
    remote: EmbeddingRemoteConfig

    @model_validator(mode="after")
    def _validate_mode(self) -> "EmbeddingConfig":
        """校验 ``mode`` 取值合法。"""
        if self.mode not in ("local", "remote"):
            raise ValueError(f'embedding.mode 必须是 "local" 或 "remote"，当前为 {self.mode!r}')
        return self


class IndexerConfig(BaseModel):
    """``[indexer]`` 段：切分参数（02）。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    chunk_size: int = Field(gt=0, description="降级/通用切分器的目标切片长度")
    chunk_overlap: int = Field(ge=0, description="降级/通用切分器的切片重叠长度")
    supported_languages: List[str] = Field(
        min_length=1, description="受支持的语言标签（真 AST 范围见 02 §3 纠偏说明）"
    )


class RetrievalConfig(BaseModel):
    """``[retrieval]`` 段：召回/融合/返回数量（04 §1/§3）。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    dense_top_k: int = Field(gt=0, description="Dense 向量 prefetch 候选数量")
    sparse_top_k: int = Field(gt=0, description="Sparse 向量 prefetch 候选数量")
    fusion_top_k: int = Field(gt=0, description="RRF 融合后进入精排的候选数量")
    default_top_k: int = Field(gt=0, description="未显式传 top_k 时的最终返回数量")
    # 以下两项供未来增强（RSE / MMR，04 §6）使用：当前阶段只读取、不接线生效。
    rse_max_gap: Optional[int] = Field(default=None, ge=0, description="RSE 缝合最大间隔（预留，未生效）")
    mmr_lambda: Optional[float] = Field(default=None, ge=0, le=1, description="MMR 权衡系数（预留，未生效）")


class RerankLocalConfig(BaseModel):
    """``[rerank.local]`` 段：本地 ``fastembed.rerank.cross_encoder.TextCrossEncoder``。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    model_name: str = Field(min_length=1, description="本地 Cross-Encoder 精排模型")


class RerankRemoteConfig(BaseModel):
    """``[rerank.remote]`` 段：远端 OpenAI 兼容风格 ``/rerank`` 接口。

    协议约定（非 OpenAI 官方规范——OpenAI 本身没有 rerank 端点，这是部分
    OpenAI 兼容网关常见的事实标准约定）：``POST {base_url}/rerank``，
    body ``{"model", "query", "documents"}``，响应
    ``{"results": [{"index", "relevance_score"}, ...]}``。首次真实联调前
    需对照实际网关文档核实。
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    base_url: str = Field(min_length=1, description="OpenAI 兼容风格网关基址")
    model: str = Field(min_length=1, description="远端精排模型 ID")
    api_key_env: str = Field(min_length=1, description="引用自 .env 的 API Key 环境变量名")
    timeout_sec: float = Field(gt=0, description="单次请求超时（秒）")

    @property
    def api_key(self) -> Optional[str]:
        """从环境变量解析真实密钥；缺失时返回 ``None``（由调用方决定如何失败）。"""
        value = os.getenv(self.api_key_env, "").strip()
        return value or None


class RerankConfig(BaseModel):
    """``[rerank]`` 段：Cross-Encoder 精排（04 §3，核心范围）。

    ``mode`` 语义同 ``[embedding]``："remote"（默认）走 ``[rerank.remote]``；
    "local" 走 ``[rerank.local]``。
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    mode: str = Field(description='精排模型来源："remote"（默认）或 "local"')
    cache_dir: str = Field(min_length=1, description="精排模型 ONNX 缓存目录（仅 mode=local 时生效）")
    min_score: float = Field(
        description="触发 low_confidence=true 的精排分数阈值（占位值，需用 06 的评测基线校准）"
    )
    local: RerankLocalConfig
    remote: RerankRemoteConfig

    @model_validator(mode="after")
    def _validate_mode(self) -> "RerankConfig":
        """校验 ``mode`` 取值合法。"""
        if self.mode not in ("local", "remote"):
            raise ValueError(f'rerank.mode 必须是 "local" 或 "remote"，当前为 {self.mode!r}')
        return self


class RagConfig(BaseModel):
    """``rag_config.toml`` 全量强类型视图。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    server: ServerConfig
    qdrant: QdrantConfig
    embedding: EmbeddingConfig
    indexer: IndexerConfig
    retrieval: RetrievalConfig
    rerank: RerankConfig

    @model_validator(mode="after")
    def _guard_local_mode_single_worker(self) -> "RagConfig":
        """`local` 模式下拒绝 `workers > 1`（01 §4 的强制校验点，fail-fast）。"""
        if self.qdrant.mode == "local" and self.server.workers > 1:
            raise ValueError(
                'qdrant.mode="local" 时 server.workers 必须为 1'
                "（本地嵌入式存储不支持多进程并发写入，见 01_architecture_overview.md §4）"
            )
        return self

    def resolve_path(self, raw: str) -> Path:
        """把配置中的相对路径解析为以工程根为基准的绝对路径。

        Args:
            raw: 配置里的原始路径字符串（相对或绝对）。

        Returns:
            已展开用户目录的绝对路径（不保证目录/文件已存在）。
        """
        path = Path(raw).expanduser()
        return path if path.is_absolute() else (project_root() / path)


def _load_toml(path: Path) -> Dict[str, Any]:
    """读取 TOML 文件为普通字典。"""
    with path.open("rb") as handle:
        return tomllib.load(handle)


@lru_cache(maxsize=1)
def get_settings() -> RagConfig:
    """读取并缓存 ``rag_config.toml``（进程内单例）。

    启动时额外加载 ``.env``（``QDRANT_API_KEY``/``EMBEDDING_API_KEY``，见 README.md §5）
    到进程环境变量；已存在的真实环境变量优先，不会被 ``.env`` 覆盖。

    Returns:
        进程内唯一的配置实例（``lru_cache`` 保证只解析一次）。

    Raises:
        FileNotFoundError: 找不到 ``rag_config.toml`` 时抛出。
        pydantic.ValidationError: 配置字段缺失或非法时抛出。
    """
    config_path = find_config_file()
    env_path = config_path.resolve().parent.parent / ".env"
    if env_path.is_file():
        load_dotenv(dotenv_path=env_path, override=False)

    data = _load_toml(config_path)
    return RagConfig.model_validate(data)
