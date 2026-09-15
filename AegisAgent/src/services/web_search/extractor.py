"""网页抓取与正文清洗：``httpx``（异步并发）+ ``trafilatura``（降噪 + Markdown）。

流水线（ADR §2.2–§2.4）：
    1. ``httpx.AsyncClient`` 复用连接池、跟随重定向、按配置超时抓取 HTML；
    2. 命中 WAF 拦截状态码（403 / 429 / 503）时 **Fail-Fast**，不重试、不对抗，
       直接返回 ``status=BLOCKED``，交由上层降级为搜索 Snippet；
    3. ``trafilatura`` 启发式识别正文主干，输出保留代码块的 Markdown；
    4. 用字符/Token 近似比估算 Token 数，供上层决定是否离线落盘。

异步契约：
    ``trafilatura`` 是 CPU 密集的同步库，必须用 :func:`asyncio.to_thread` 包装。

解耦红线：本模块只依赖 ``services.settings``、httpx、trafilatura 与标准库。
"""

from __future__ import annotations

import asyncio
import math
import zlib
from enum import Enum
from typing import Final

import httpx
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from services.web_search.providers import ProviderConfigError
from services.web_search.settings import WebSearchSettings, get_settings

__all__ = [
    "PageStatus",
    "ExtractedPage",
    "WAF_STATUS_CODES",
    "create_http_client",
    "estimate_tokens",
    "fetch_and_extract",
]

#: WAF / 反爬挑战类 HTTP 状态码（ADR §2.4：命中即降级，不做逆向对抗与重试）
WAF_STATUS_CODES: Final[frozenset[int]] = frozenset({403, 429, 503})

#: 仅接受的标准协议前缀，避免把 file:// 之类的输入带进抓取层
_ALLOWED_SCHEMES: Final[tuple[str, ...]] = ("http://", "https://")


class PageStatus(str, Enum):
    """抓取与清洗结果的状态枚举（作为跨进程 HTTP 契约的一部分）。"""

    #: 抓取并成功提取到正文
    OK = "OK"
    #: 被 WAF / 反爬拦截，需上层降级为 Snippet
    BLOCKED = "BLOCKED"
    #: 网络错误、HTTP 错误或下游提取异常
    ERROR = "ERROR"
    #: 页面可达但正文为空（典型：纯 JS 渲染或超短页面）
    EMPTY = "EMPTY"


class ExtractedPage(BaseModel):
    """单页抓取与清洗的结果契约。

    Attributes:
        url: 请求的页面地址。
        title: 页面标题；缺失时由上层回退为 URL。
        markdown: trafilatura 清洗后的正文（Markdown，保留代码块）。
        token_estimate: 正文字符数按近似比估算的 Token 数。
        status: 处理结果状态，见 :class:`PageStatus`。
        error: 失败原因（成功为 ``None``），用于可观测与排障，不吞异常。
        http_status: 上游 HTTP 状态码；未拿到响应时为 ``None``。
    """

    model_config = ConfigDict(extra="ignore")

    url: str
    title: str = ""
    markdown: str = ""
    token_estimate: int = Field(default=0, ge=0)
    status: PageStatus = PageStatus.OK
    error: str | None = None
    http_status: int | None = None


def estimate_tokens(text: str, chars_per_token: float) -> int:
    """按字符/Token 近似比估算文本 Token 数。

    说明：``tiktoken`` 不在本服务允许依赖内（sidecar 依赖最小化），故采用可配置的
    近似比。该值只用于"是否落盘"的阈值判断，不参与上下文精确预算。

    Args:
        text: 待估算文本。
        chars_per_token: 字符/Token 近似比，来自配置，必须为正数。

    Returns:
        向上取整的 Token 估算值；空文本返回 ``0``。
    """
    if not text:
        return 0
    return max(1, math.ceil(len(text) / chars_per_token))


def create_http_client(settings: WebSearchSettings) -> httpx.AsyncClient:
    """按配置构建共享的异步 HTTP 客户端（连接池 + 重定向 + 超时治理）。

    Args:
        settings: web_search 配置视图。

    Returns:
        尚未关闭的 :class:`httpx.AsyncClient`；由调用方（FastAPI lifespan）负责关闭。

    Raises:
        httpx.HTTPError: 客户端参数不合法时由 httpx 抛出。
    """
    limits = httpx.Limits(
        max_connections=settings.fetch_concurrency,
        max_keepalive_connections=settings.fetch_concurrency,
    )
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout_sec),
        follow_redirects=True,
        limits=limits,
        headers={"User-Agent": settings.user_agent},
    )


def _pick_user_agent(settings: WebSearchSettings, url: str) -> str:
    """从 UA 池中确定性地为本次请求挑选 User-Agent。

    使用 URL 的 CRC32 做轮换索引：不同目标会分散到不同 UA，且同一 URL 的取值稳定，
    便于上游做请求复现与日志比对（比全局计数器更适合并发场景）。

    Args:
        settings: web_search 配置视图。
        url: 本次请求地址。

    Returns:
        选中的 User-Agent 字符串（全部来自配置，零硬编码）。
    """
    pool = settings.user_agent_pool
    if len(pool) == 1:
        return pool[0]
    return pool[zlib.crc32(url.encode("utf-8")) % len(pool)]


def _extract_sync(html: str, url: str) -> tuple[str, str]:
    """在工作线程中执行 trafilatura 元数据与正文提取。

    Args:
        html: 页面 HTML 源码。
        url: 页面地址，用于相对链接解析与站点特征判定。

    Returns:
        二元组 ``(title, markdown)``；任一提取失败时对应项为空串。

    Raises:
        ProviderConfigError: 未安装 ``trafilatura`` 依赖。
    """
    try:
        import trafilatura
    except ImportError as exc:
        raise ProviderConfigError("未安装 trafilatura，无法清洗网页正文；请安装 trafilatura") from exc

    title = ""
    metadata = trafilatura.extract_metadata(html, default_url=url)
    if metadata is not None and metadata.title:
        title = str(metadata.title).strip()

    # output_format="markdown" + include_formatting 保证标题/列表/代码块被保留
    markdown = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_formatting=True,
        include_links=False,
        include_tables=True,
        include_comments=False,
    )
    return title, (markdown or "").strip()


async def fetch_and_extract(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    settings: WebSearchSettings | None = None,
) -> ExtractedPage:
    """抓取单个 URL 并清洗为 Markdown（不抛业务异常，失败以状态表达）。

    Args:
        url: 目标页面地址，仅支持 http/https。
        client: 共享的 httpx 客户端；``None`` 时临时创建并在结束后关闭
            （仅供单测与脚本调用，服务内一律复用 lifespan 的客户端）。
        settings: web_search 配置视图；``None`` 时读取进程级单例。

    Returns:
        :class:`ExtractedPage`。WAF 拦截返回 ``status=BLOCKED``；网络/HTTP 错误
        返回 ``status=ERROR`` 并填充 ``error``；正文为空返回 ``status=EMPTY``。

    Raises:
        ProviderConfigError: ``trafilatura`` 依赖缺失。
    """
    resolved_settings = settings or get_settings()

    target = (url or "").strip()
    if not target.startswith(_ALLOWED_SCHEMES):
        logger.warning(f"跳过非法 URL: {url!r}")
        return ExtractedPage(
            url=target,
            status=PageStatus.ERROR,
            error="仅支持 http/https 协议的 URL",
        )

    owns_client = client is None
    active_client = client or create_http_client(resolved_settings)
    headers = {"User-Agent": _pick_user_agent(resolved_settings, target)}

    try:
        try:
            response = await active_client.get(
                target,
                headers=headers,
                timeout=resolved_settings.request_timeout_sec,
            )
        except httpx.TimeoutException as exc:
            logger.warning(f"抓取超时: url={target} error={exc}")
            return ExtractedPage(
                url=target,
                status=PageStatus.ERROR,
                error=f"抓取超时({resolved_settings.request_timeout_sec}s): {exc}",
            )
        except httpx.HTTPError as exc:
            logger.warning(f"抓取网络错误: url={target} error={exc}")
            return ExtractedPage(url=target, status=PageStatus.ERROR, error=f"网络错误: {exc}")

        status_code = response.status_code
        if status_code in WAF_STATUS_CODES:
            # Fail-Fast：不与 Cloudflare 等 WAF 做逆向对抗，直接降级给上层
            logger.warning(f"WAF 拦截，降级为 Snippet: url={target} status={status_code}")
            return ExtractedPage(
                url=target,
                status=PageStatus.BLOCKED,
                error=f"WAF/反爬拦截: HTTP {status_code}",
                http_status=status_code,
            )
        if status_code >= 400:
            logger.warning(f"抓取失败: url={target} status={status_code}")
            return ExtractedPage(
                url=target,
                status=PageStatus.ERROR,
                error=f"HTTP {status_code}",
                http_status=status_code,
            )

        html = response.text
        if not html.strip():
            return ExtractedPage(
                url=target,
                title=str(response.url),
                status=PageStatus.EMPTY,
                error="响应体为空",
                http_status=status_code,
            )

        title, markdown = await asyncio.to_thread(_extract_sync, html, str(response.url))
        if not markdown:
            logger.info(f"正文提取为空（疑似 JS 渲染页）: url={target}")
            return ExtractedPage(
                url=target,
                title=title or str(response.url),
                status=PageStatus.EMPTY,
                error="trafilatura 未提取到正文",
                http_status=status_code,
            )

        return ExtractedPage(
            url=target,
            title=title or str(response.url),
            markdown=markdown,
            token_estimate=estimate_tokens(markdown, resolved_settings.token_chars_per_token),
            status=PageStatus.OK,
            http_status=status_code,
        )
    finally:
        if owns_client:
            await active_client.aclose()
