"""web_search 子系统的配置装配（**不依赖 agent_runtime**）。

本服务是独立进程 sidecar（默认 ``127.0.0.1:8003``）：搜索源、抓取配额、超时、
落盘路径等全部可调参数都来自 ``config/config.toml`` 的 ``[web_search]`` 段
（依据 ``documents/技术选型/web_search.md`` 与 ``10_directory_structure.md``
裁决项③：不拆子工程，但保持进程级解耦）。

模块只做三件事：
    1. 用 Pydantic 对原始 TOML 段做强类型校验（越界即 fail-fast，不带病启动）；
    2. 把相对路径解析为"项目根"下的绝对路径，避免结果随进程 cwd 漂移；
    3. 提供 ``get_settings()`` 进程级单例，保证全服务读取同一份不可变配置。

契约：
    - 禁止 import ``agent_runtime`` / ``tool_layer``（解耦红线）；
    - 零硬编码：端口、配额、超时、UA 一律取自配置段（唯一例外是"可被配置覆盖"
      的启发式默认值，均在字段说明中显式标注）。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.settings import find_config_file, load_section

__all__ = [
    "WebSearchSettings",
    "get_settings",
    "normalize_provider_name",
    "PROVIDER_DDG",
    "PROVIDER_TAVILY",
    "SUPPORTED_PROVIDERS",
]

#: 默认搜索源：DuckDuckGo（无需 API Key，开箱即用，见 ADR §2.1）
PROVIDER_DDG: Final[str] = "ddg"

#: 增强搜索源：Tavily（面向 AI Agent 的商业搜索 API，见 ADR §2.1）
PROVIDER_TAVILY: Final[str] = "tavily"

#: 配置段中 ``provider`` 允许的写法 → 规范化名称（兼容历史命名，避免拼写漂移）
_PROVIDER_ALIASES: Final[dict[str, str]] = {
    "ddg": PROVIDER_DDG,
    "duckduckgo": PROVIDER_DDG,
    "duckduckgo_search": PROVIDER_DDG,
    "tavily": PROVIDER_TAVILY,
}

#: 对外暴露的受支持搜索源集合（用于错误提示与自省）
SUPPORTED_PROVIDERS: Final[tuple[str, ...]] = tuple(sorted(set(_PROVIDER_ALIASES.values())))

#: 配置段的键名，集中一处避免字符串散落
_CONFIG_SECTION: Final[str] = "web_search"

#: Token 估算的字符/Token 近似比（启发式默认值）。
#: 说明：``tiktoken`` 不在本服务允许依赖内（sidecar 依赖最小化），因此 Token 数
#: 只能近似。该值可被 ``[web_search]`` 段的 ``token_chars_per_token`` 覆盖。
_DEFAULT_CHARS_PER_TOKEN: Final[float] = 4.0


def normalize_provider_name(name: str) -> str:
    """把配置中的搜索源名称规范化为受支持的标准名。

    Args:
        name: 原始名称，例如 ``"ddg"`` / ``"DuckDuckGo"`` / ``"tavily"``。

    Returns:
        规范化后的名称，取值属于 :data:`SUPPORTED_PROVIDERS`。

    Raises:
        ValueError: 名称为空或不在受支持列表内。
    """
    key = (name or "").strip().lower()
    resolved = _PROVIDER_ALIASES.get(key)
    if resolved is None:
        raise ValueError(
            f"不支持的搜索源 provider={name!r}，可选值: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    return resolved


class WebSearchSettings(BaseModel):
    """``[web_search]`` 配置段的强类型视图。

    所有字段都来自配置文件，模型本身不提供业务默认值；配置缺项会在构造时立刻
    抛出校验错误，避免服务"带病启动"后在请求期才暴露问题。

    Attributes:
        host: 服务监听地址（安全红线：应为回环地址）。
        port: 服务监听端口。
        provider: 搜索源名称，构造时会被规范化为标准名。
        max_results: 单次搜索返回的候选条数上限（同时是客户端请求的硬配额）。
        fetch_concurrency: 并发抓取页数（同时作为连接池上限与 Top-N 抓取条数）。
        request_timeout_sec: 单页抓取超时（秒）。
        total_timeout_sec: 单次检索（搜索 + 抓取 + 清洗）总超时（秒）。
        max_content_tokens: 正文超过该 Token 数则落盘，仅回头部摘要。
        preview_chars: 落盘时响应保留的头部字符数。
        user_agent: 请求头 User-Agent 基值（来自配置，零硬编码）。
        artifacts_dir: 长正文离线落盘根目录（相对路径按项目根解析）。
        user_agents: 可选的 UA 轮换池；留空时退化为 ``user_agent`` 单值。
        token_chars_per_token: Token 估算的字符/Token 近似比。
    """

    model_config = ConfigDict(extra="ignore")

    host: str = Field(min_length=1, description="服务监听地址")
    port: int = Field(ge=1, le=65535, description="服务监听端口")
    provider: str = Field(min_length=1, description="搜索源：ddg | tavily")
    max_results: int = Field(ge=1, description="单次搜索候选条数上限")
    fetch_concurrency: int = Field(ge=1, description="并发抓取页数上限")
    request_timeout_sec: float = Field(gt=0, description="单页抓取超时（秒）")
    total_timeout_sec: float = Field(gt=0, description="单次检索总超时（秒）")
    max_content_tokens: int = Field(ge=1, description="正文落盘 Token 阈值")
    preview_chars: int = Field(ge=0, description="落盘后响应保留的头部字符数")
    user_agent: str = Field(min_length=1, description="请求头 User-Agent 基值")
    artifacts_dir: Path = Field(description="长正文离线落盘根目录")
    user_agents: tuple[str, ...] = Field(
        default=(), description="UA 轮换池；留空则仅用 user_agent"
    )
    token_chars_per_token: float = Field(
        default=_DEFAULT_CHARS_PER_TOKEN,
        gt=0,
        description="Token 估算的字符/Token 近似比（可被配置覆盖的启发式默认值）",
    )

    @field_validator("provider")
    @classmethod
    def _normalize_provider(cls, value: str) -> str:
        """规范化搜索源名称（别名与大小写不敏感）。"""
        return normalize_provider_name(value)

    @field_validator("user_agents")
    @classmethod
    def _clean_user_agents(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """剔除 UA 池中的空串与首尾空白，保持配置容错。"""
        return tuple(item.strip() for item in value if item and item.strip())

    @field_validator("artifacts_dir")
    @classmethod
    def _resolve_artifacts_dir(cls, value: Path) -> Path:
        """把相对 ``artifacts_dir`` 解析为项目根下的绝对路径。

        项目根取 ``config.toml`` 所在目录的上一级（即 ``AegisAgent/``），
        这样无论从仓库根还是 ``AegisAgent/`` 启动，落盘位置都一致。

        Args:
            value: 配置中声明的落盘根目录，可为相对路径。

        Returns:
            绝对路径；已为绝对路径时原样返回。
        """
        if value.is_absolute():
            return value
        project_root = find_config_file().resolve().parent.parent
        return (project_root / value).resolve()

    @property
    def user_agent_pool(self) -> tuple[str, ...]:
        """返回实际可用的 UA 池。

        Returns:
            配置了 ``user_agents`` 时返回该列表，否则退化为 ``(user_agent,)``。
        """
        return self.user_agents or (self.user_agent,)


@lru_cache(maxsize=1)
def get_settings() -> WebSearchSettings:
    """读取并缓存 ``[web_search]`` 配置段（进程级单例）。

    Returns:
        校验通过的 :class:`WebSearchSettings` 实例。

    Raises:
        RuntimeError: 配置文件中缺少 ``[web_search]`` 段。
        pydantic.ValidationError: 配置项缺失或取值越界。
    """
    raw = load_section(_CONFIG_SECTION)
    if not raw:
        raise RuntimeError(f"config.toml 缺少 [{_CONFIG_SECTION}] 配置段，无法启动 web_search 服务")
    return WebSearchSettings(**raw)
