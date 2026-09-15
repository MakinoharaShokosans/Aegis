"""搜索源适配器（Adapter Pattern）：DuckDuckGo 与 Tavily 双模搜索。

设计依据 ``documents/技术选型/web_search.md`` §2.1：
    - **默认源 DuckDuckGo**：零成本、无需注册，保证任何人 clone 后可即刻跑通；
    - **增强源 Tavily**：面向 AI Agent 定制，返回更干净的摘要；
    - 通过配置文件 ``[web_search].provider`` 无缝切换，调用方只依赖
      :class:`SearchProvider` 抽象基类。

异步契约：
    ``duckduckgo_search`` 与 ``tavily`` 都是**同步阻塞**库，因此所有网络调用一律
    用 :func:`asyncio.to_thread` 投递到工作线程，严禁在事件循环里直接调用。

解耦红线：本模块只依赖 ``services.settings``、Pydantic 与标准库。
"""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from typing import Any, Final

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from services.web_search.settings import (
    PROVIDER_DDG,
    PROVIDER_TAVILY,
    WebSearchSettings,
    get_settings,
    normalize_provider_name,
)

__all__ = [
    "SearchHit",
    "SearchProvider",
    "SearchProviderError",
    "ProviderConfigError",
    "DuckDuckGoProvider",
    "TavilyProvider",
    "build_provider",
    "DEFAULT_TAVILY_API_KEY_ENV",
]

#: Tavily API Key 的环境变量名（ADR §2.1 规定的契约常量，凭据不进 config.toml）
DEFAULT_TAVILY_API_KEY_ENV: Final[str] = "TAVILY_API_KEY"


class SearchProviderError(RuntimeError):
    """搜索源调用失败（网络异常、上游限流、返回结构异常等）。"""


class ProviderConfigError(SearchProviderError):
    """搜索源配置缺失或不合法（例如未设置 Tavily API Key）。"""


class SearchHit(BaseModel):
    """单条搜索结果的规范化契约。

    Attributes:
        title: 结果标题；上游缺失时为空串。
        url: 结果链接（必填，空链接会被上游适配器过滤）。
        snippet: 搜索引擎随附的摘要，WAF 阻断时作为降级内容。
        published_at: 发布时间（上游可提供时），统一存原始字符串。
    """

    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="", description="结果标题")
    url: str = Field(min_length=1, description="结果链接")
    snippet: str = Field(default="", description="搜索结果摘要")
    published_at: str | None = Field(default=None, description="发布时间（可空）")


class SearchProvider(ABC):
    """搜索源抽象基类：所有适配器必须实现统一的异步检索接口。

    Attributes:
        name: 规范化后的搜索源名称，用于日志与健康检查展示。
    """

    #: 子类必须覆盖为 ``PROVIDER_DDG`` / ``PROVIDER_TAVILY``
    name: str = ""

    def __init__(self, *, default_max_results: int) -> None:
        """初始化基类公共状态。

        Args:
            default_max_results: 调用方未显式指定条数时使用的默认上限，
                来自 ``[web_search].max_results``。

        Raises:
            ValueError: ``default_max_results`` 非正数。
        """
        if default_max_results < 1:
            raise ValueError(f"default_max_results 必须为正整数，实际为 {default_max_results}")
        self._default_max_results = default_max_results

    @abstractmethod
    async def search(self, query: str, max_results: int | None = None) -> list[SearchHit]:
        """执行一次检索。

        Args:
            query: 自然语言检索词，调用方保证非空。
            max_results: 期望返回条数；``None`` 时使用配置的默认上限。

        Returns:
            规范化后的搜索结果列表，按上游排序返回。

        Raises:
            SearchProviderError: 上游调用失败或返回结构不可解析。
        """
        raise NotImplementedError

    def _resolve_limit(self, max_results: int | None) -> int:
        """把可选的条数参数收敛为合法的正整数上限。

        Args:
            max_results: 调用方传入的期望条数，可为 ``None``。

        Returns:
            实际生效的条数上限（不超过配置默认值，防越权放大）。
        """
        limit = self._default_max_results if max_results is None else int(max_results)
        return max(1, min(limit, self._default_max_results))


class DuckDuckGoProvider(SearchProvider):
    """默认搜索源：``duckduckgo_search``（免费、无需 API Key）。

    该库为同步阻塞实现，因此真实调用被放入工作线程执行。
    """

    name = PROVIDER_DDG

    @staticmethod
    def _search_sync(query: str, max_results: int) -> list[dict[str, Any]]:
        """在工作线程中执行 DDG 同步检索。

        Args:
            query: 检索词。
            max_results: 返回条数上限。

        Returns:
            上游原始结果字典列表（键一般为 ``title`` / ``href`` / ``body``）。

        Raises:
            ProviderConfigError: 未安装 ``duckduckgo_search`` 依赖。
            SearchProviderError: 上游限流、超时或其他调用失败。
        """
        try:
            from duckduckgo_search import DDGS
        except ImportError as exc:  # 可选依赖缺失时给出可操作的提示
            raise ProviderConfigError(
                "未安装 duckduckgo_search，无法使用默认搜索源；请安装该依赖或改用 provider=tavily"
            ) from exc

        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results) or [])
        except Exception as exc:  # 同步库异常谱系不稳定，此处统一翻译为领域异常
            raise SearchProviderError(f"DuckDuckGo 检索失败: {exc}") from exc

    async def search(self, query: str, max_results: int | None = None) -> list[SearchHit]:
        """异步执行 DuckDuckGo 检索。

        Args:
            query: 自然语言检索词。
            max_results: 期望返回条数；``None`` 时使用配置默认值。

        Returns:
            :class:`SearchHit` 列表；无结果时返回空列表。

        Raises:
            SearchProviderError: 上游调用失败。
        """
        cleaned = (query or "").strip()
        if not cleaned:
            raise SearchProviderError("检索词不能为空")

        limit = self._resolve_limit(max_results)
        logger.debug(f"[ddg] 检索: query={cleaned!r} max_results={limit}")
        raw_items = await asyncio.to_thread(self._search_sync, cleaned, limit)

        hits: list[SearchHit] = []
        for item in raw_items:
            url = str(item.get("href") or item.get("url") or "").strip()
            if not url:
                continue  # 无链接的结果对 Agent 无证据价值，直接丢弃
            hits.append(
                SearchHit(
                    title=str(item.get("title") or "").strip(),
                    url=url,
                    snippet=str(item.get("body") or item.get("snippet") or "").strip(),
                    published_at=item.get("published") or item.get("published_at"),
                )
            )
        logger.debug(f"[ddg] 命中 {len(hits)} 条")
        return hits


class TavilyProvider(SearchProvider):
    """增强搜索源：Tavily Search API（需要环境变量提供 API Key）。

    Key 不接受明文写入 ``config.toml``，只从 ``TAVILY_API_KEY`` 环境变量读取
    （ADR §2.1 与 ``config.toml`` 顶部"敏感凭据由 .env 提供"的约定）。
    """

    name = PROVIDER_TAVILY

    def __init__(
        self,
        *,
        default_max_results: int,
        api_key: str | None = None,
        api_key_env: str = DEFAULT_TAVILY_API_KEY_ENV,
    ) -> None:
        """初始化 Tavily 适配器并校验凭据。

        Args:
            default_max_results: 默认返回条数上限。
            api_key: 显式传入的 Key（主要供测试使用）；``None`` 时读环境变量。
            api_key_env: 读取 Key 的环境变量名。

        Raises:
            ProviderConfigError: 环境变量未配置且未显式传入 Key。
        """
        super().__init__(default_max_results=default_max_results)
        resolved = (api_key or os.getenv(api_key_env, "")).strip()
        if not resolved:
            raise ProviderConfigError(
                f"provider=tavily 需要配置环境变量 {api_key_env}（请在 .env 中设置），当前为空"
            )
        self._api_key = resolved
        self._api_key_env = api_key_env

    def _search_sync(self, query: str, max_results: int) -> dict[str, Any]:
        """在工作线程中执行 Tavily 同步检索。

        Args:
            query: 检索词。
            max_results: 返回条数上限。

        Returns:
            上游原始响应字典（``results`` 为结果列表）。

        Raises:
            ProviderConfigError: 未安装 ``tavily`` 依赖。
            SearchProviderError: 上游鉴权失败、限流或其他调用失败。
        """
        try:
            from tavily import TavilyClient
        except ImportError as exc:  # 可选依赖缺失时给出可操作的提示
            raise ProviderConfigError(
                "未安装 tavily 包，无法使用 provider=tavily；请安装 tavily-python"
            ) from exc

        try:
            client = TavilyClient(api_key=self._api_key)
            return dict(client.search(query=query, max_results=max_results, include_answer=False))
        except Exception as exc:  # 上游 SDK 异常谱系不稳定，统一翻译为领域异常
            raise SearchProviderError(f"Tavily 检索失败: {exc}") from exc

    async def search(self, query: str, max_results: int | None = None) -> list[SearchHit]:
        """异步执行 Tavily 检索。

        Args:
            query: 自然语言检索词。
            max_results: 期望返回条数；``None`` 时使用配置默认值。

        Returns:
            :class:`SearchHit` 列表；无结果时返回空列表。

        Raises:
            SearchProviderError: 上游调用失败。
        """
        cleaned = (query or "").strip()
        if not cleaned:
            raise SearchProviderError("检索词不能为空")

        limit = self._resolve_limit(max_results)
        logger.debug(f"[tavily] 检索: query={cleaned!r} max_results={limit}")
        payload = await asyncio.to_thread(self._search_sync, cleaned, limit)

        hits: list[SearchHit] = []
        for item in payload.get("results") or []:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            hits.append(
                SearchHit(
                    title=str(item.get("title") or "").strip(),
                    url=url,
                    snippet=str(item.get("content") or "").strip(),
                    published_at=item.get("published_date") or item.get("published_at"),
                )
            )
        logger.debug(f"[tavily] 命中 {len(hits)} 条")
        return hits


def build_provider(
    name: str,
    *,
    default_max_results: int | None = None,
    tavily_api_key: str | None = None,
) -> SearchProvider:
    """搜索源工厂：按配置名装配适配器。

    Args:
        name: 搜索源名称（支持 ``ddg`` / ``duckduckgo`` / ``tavily`` 等别名）。
        default_max_results: 默认返回条数；``None`` 时读取 ``[web_search]`` 配置。
        tavily_api_key: 显式 Tavily Key（仅测试用），默认走环境变量。

    Returns:
        对应搜索源的 :class:`SearchProvider` 实例。

    Raises:
        ValueError: 搜索源名称不受支持。
        ProviderConfigError: 所选搜索源的凭据缺失（例如 Tavily 无 Key）。
    """
    resolved = normalize_provider_name(name)
    if default_max_results is None:
        settings: WebSearchSettings = get_settings()
        default_max_results = settings.max_results

    if resolved == PROVIDER_DDG:
        return DuckDuckGoProvider(default_max_results=default_max_results)
    if resolved == PROVIDER_TAVILY:
        return TavilyProvider(
            default_max_results=default_max_results,
            api_key=tavily_api_key,
        )
    # normalize_provider_name 已保证不可达；保留兜底以满足穷尽性检查
    raise ValueError(f"未实现的搜索源适配器: {resolved!r}")
