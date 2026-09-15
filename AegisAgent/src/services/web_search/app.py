"""web_search 子系统 HTTP 接入层（FastAPI，默认 ``127.0.0.1:8003``）。

契约与流程（ADR ``documents/技术选型/web_search.md`` §1）::

    POST /api/v1/search/query
      检索 → 去重 → （可选）并发抓取 Top-N → trafilatura 清洗 → 超长落盘 → 汇总
    GET  /api/v1/health

关键设计：
    - **共享连接池**：``httpx.AsyncClient`` 由 lifespan 创建/关闭，跨请求复用；
    - **并发治理**：``asyncio.Semaphore(fetch_concurrency)`` + ``asyncio.gather``；
    - **总超时**：``asyncio.timeout(total_timeout_sec)`` 覆盖"搜索 + 抓取 + 清洗"，
      超时返回 504，避免个别死链拖垮调用方；
    - **内容卸载**：正文 Token 超过阈值时全量写入
      ``{artifacts_dir}/{task_id}/web_{hash}.md``，响应只回头部 ``preview_chars``
      字符与产物句柄，保证 Agent 上下文预算安全；
    - **WAF 降级**：``status=BLOCKED`` 的结果只回搜索 Snippet，驱动调用方重规划。

解耦红线：本模块只依赖 ``services.web_search.*``、FastAPI/Pydantic/loguru/httpx。
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

import httpx
from fastapi import FastAPI, HTTPException, Request, status as http_status
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.web_search import __version__
from services.web_search.dedup import content_fingerprint, dedupe, url_fingerprint
from services.web_search.extractor import (
    ExtractedPage,
    PageStatus,
    create_http_client,
    fetch_and_extract,
)
from services.web_search.providers import (
    ProviderConfigError,
    SearchHit,
    SearchProvider,
    SearchProviderError,
    build_provider,
)
from services.web_search.settings import WebSearchSettings, get_settings

__all__ = ["app", "create_app"]

#: 子系统 API 版本前缀
API_PREFIX: Final[str] = "/api/v1"

#: 检索端点路径
SEARCH_PATH: Final[str] = f"{API_PREFIX}/search/query"

#: 健康检查端点路径
HEALTH_PATH: Final[str] = f"{API_PREFIX}/health"

#: 未发起抓取（或抓取降级）时的结果状态：仅有搜索摘要可用
STATUS_SNIPPET_ONLY: Final[str] = "SNIPPET_ONLY"

#: task_id 白名单：仅允许安全字符，杜绝 ``../`` 之类的路径穿越落到 artifacts 目录外
_TASK_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class SearchQueryRequest(BaseModel):
    """``POST /api/v1/search/query`` 的请求体。

    Attributes:
        query: 自然语言检索词，必填且非空。
        max_results: 期望候选条数；``None`` 时取配置默认值，且不得超过配置上限。
        fetch: 是否对 Top-N 候选页做全文抓取与清洗。
        task_id: 产物归属任务号；``None`` 时由服务端生成（影响落盘目录）。
    """

    model_config = ConfigDict(extra="ignore")

    query: str = Field(min_length=1, description="自然语言检索词")
    max_results: int | None = Field(default=None, ge=1, description="候选条数，可空")
    fetch: bool = Field(default=False, description="是否抓取正文")
    task_id: str | None = Field(default=None, description="产物归属任务号")

    @field_validator("query")
    @classmethod
    def _clean_query(cls, value: str) -> str:
        """去除检索词首尾空白并拒绝纯空白输入。"""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("query 不能为空")
        return cleaned

    @field_validator("task_id")
    @classmethod
    def _check_task_id(cls, value: str | None) -> str | None:
        """校验 task_id 字符集，防止路径穿越。"""
        if value is None:
            return None
        cleaned = value.strip()
        if not _TASK_ID_PATTERN.match(cleaned):
            raise ValueError("task_id 仅允许字母、数字、下划线与连字符，长度 1-64")
        return cleaned


class SearchResultItem(BaseModel):
    """单条检索结果（含清洗后的内容摘要与产物句柄）。

    Attributes:
        title: 标题；搜索结果缺失时回退为 URL。
        url: 结果链接。
        snippet: 搜索引擎摘要；WAF 阻断或未抓取时的降级内容。
        status: 结果状态，见 :class:`~services.web_search.extractor.PageStatus`
            与 :data:`STATUS_SNIPPET_ONLY`。
        published_at: 发布时间（上游提供时）。
        preview: 正文预览；未超 Token 阈值时为完整清洗正文，超阈值时为头部片段。
        token_estimate: 全文 Token 估算值（未抓取时为 0）。
        is_truncated: 正文是否已被落盘截断。
        artifact_path: 全量正文的落盘路径；未落盘时为 ``None``。
        error: 失败/降级原因，便于调用方重规划。
        fingerprint: 内容指纹，便于调用方做证据去重与引用。
    """

    model_config = ConfigDict(extra="ignore")

    title: str
    url: str
    snippet: str = ""
    status: str
    published_at: str | None = None
    preview: str = ""
    token_estimate: int = Field(default=0, ge=0)
    is_truncated: bool = False
    artifact_path: str | None = None
    error: str | None = None
    fingerprint: str


class SearchQueryResponse(BaseModel):
    """``POST /api/v1/search/query`` 的响应体。

    Attributes:
        query: 实际执行的检索词。
        provider: 实际使用的搜索源名称。
        task_id: 产物归属任务号。
        fetch: 是否执行了正文抓取。
        total: 去重后的结果条数。
        blocked: 其中被 WAF 阻断的条数（驱动调用方自愈重规划）。
        results: 结果列表，保持搜索排序。
        elapsed_ms: 服务端处理耗时（毫秒）。
    """

    model_config = ConfigDict(extra="ignore")

    query: str
    provider: str
    task_id: str
    fetch: bool
    total: int = Field(ge=0)
    blocked: int = Field(ge=0)
    results: list[SearchResultItem]
    elapsed_ms: int = Field(ge=0)


def _render_artifact(page: ExtractedPage) -> str:
    """为落盘的正文生成带出处信息的 Markdown 文档。

    Args:
        page: 抓取与清洗结果。

    Returns:
        含标题、来源 URL 与 Token 估算的完整 Markdown 文本。
    """
    title = page.title or page.url
    header = (
        f"# {title}\n\n"
        f"> 来源: {page.url}\n"
        f"> 状态: {page.status.value} / Token 估算: {page.token_estimate}\n\n"
    )
    return header + page.markdown + "\n"


async def _offload_markdown(
    settings: WebSearchSettings,
    task_id: str,
    page: ExtractedPage,
) -> str:
    """把超长正文异步落盘，返回产物绝对路径。

    文件 I/O 通过 :func:`asyncio.to_thread` 投递，避免阻塞事件循环。

    Args:
        settings: web_search 配置视图。
        task_id: 产物归属任务号（已通过白名单校验）。
        page: 待落盘的抓取结果。

    Returns:
        落盘文件的绝对路径字符串。

    Raises:
        OSError: 目录创建或文件写入失败。
    """
    target_dir = settings.artifacts_dir / task_id
    target_path = target_dir / f"web_{url_fingerprint(page.url)}.md"

    def _write() -> None:
        """同步落盘（在工作线程中执行）。"""
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path.write_text(_render_artifact(page), encoding="utf-8")

    await asyncio.to_thread(_write)
    logger.info(f"正文落盘: task_id={task_id} path={target_path} tokens={page.token_estimate}")
    return str(target_path)


def _snippet_item(hit: SearchHit, status_text: str, error: str | None = None) -> SearchResultItem:
    """把一条搜索结果降级为"仅摘要"响应项。

    Args:
        hit: 搜索结果。
        status_text: 结果状态字符串。
        error: 降级原因，可为 ``None``。

    Returns:
        仅携带 Snippet 的响应项。
    """
    return SearchResultItem(
        title=hit.title or hit.url,
        url=hit.url,
        snippet=hit.snippet,
        status=status_text,
        published_at=hit.published_at,
        preview="",
        token_estimate=0,
        is_truncated=False,
        artifact_path=None,
        error=error,
        fingerprint=content_fingerprint(hit.title, hit.snippet),
    )


async def _build_item(
    hit: SearchHit,
    page: ExtractedPage | None,
    settings: WebSearchSettings,
    task_id: str,
) -> SearchResultItem:
    """把搜索结果与抓取结果合并为单条响应项（含超长落盘决策）。

    Args:
        hit: 搜索结果。
        page: 对应页面的抓取结果；未抓取时为 ``None``。
        settings: web_search 配置视图。
        task_id: 产物归属任务号。

    Returns:
        合并后的响应项。抓取失败或 WAF 阻断时降级为仅返回 Snippet。

    Raises:
        OSError: 超长正文落盘失败。
    """
    if page is None:
        return _snippet_item(hit, STATUS_SNIPPET_ONLY)

    if page.status is not PageStatus.OK:
        # BLOCKED / ERROR / EMPTY 一律降级为搜索摘要（ADR §2.4 Snippet Fallback）
        return _snippet_item(hit, page.status.value, error=page.error)

    if page.token_estimate > settings.max_content_tokens:
        artifact_path = await _offload_markdown(settings, task_id, page)
        return SearchResultItem(
            title=page.title or hit.title or hit.url,
            url=hit.url,
            snippet=hit.snippet,
            status=PageStatus.OK.value,
            published_at=hit.published_at,
            preview=page.markdown[: settings.preview_chars],
            token_estimate=page.token_estimate,
            is_truncated=True,
            artifact_path=artifact_path,
            error=None,
            fingerprint=content_fingerprint(page.title or hit.title, page.markdown),
        )

    return SearchResultItem(
        title=page.title or hit.title or hit.url,
        url=hit.url,
        snippet=hit.snippet,
        status=PageStatus.OK.value,
        published_at=hit.published_at,
        preview=page.markdown,
        token_estimate=page.token_estimate,
        is_truncated=False,
        artifact_path=None,
        error=None,
        fingerprint=content_fingerprint(page.title or hit.title, page.markdown),
    )


async def _fetch_pages(
    hits: list[SearchHit],
    settings: WebSearchSettings,
    client: httpx.AsyncClient,
) -> list[ExtractedPage | BaseException]:
    """并发抓取 Top-N 候选页（信号量限流 + gather 不中断）。

    Top-N 的 N 取配置 ``fetch_concurrency``（ADR §2.2：并发抓取候选页，总耗时取决于
    最慢单页而非串行累加）。

    Args:
        hits: 已去重的搜索结果（按排序取前 N 条）。
        settings: web_search 配置视图。
        client: lifespan 管理的共享 httpx 客户端。

    Returns:
        与 ``hits[:N]`` 等长的结果列表；线程/依赖级异常以异常对象原样返回，
        交由上层显式记录与降级，绝不静默吞掉。
    """
    targets = hits[: settings.fetch_concurrency]
    semaphore = asyncio.Semaphore(settings.fetch_concurrency)

    async def _guarded(hit: SearchHit) -> ExtractedPage:
        """在信号量保护下抓取单页。"""
        async with semaphore:
            return await fetch_and_extract(hit.url, client=client, settings=settings)

    return list(await asyncio.gather(*(_guarded(hit) for hit in targets), return_exceptions=True))


def _build_provider(settings: WebSearchSettings) -> SearchProvider:
    """按配置装配搜索源，并把配置类错误翻译为 503。

    Args:
        settings: web_search 配置视图。

    Returns:
        搜索源适配器实例。

    Raises:
        HTTPException: 搜索源未实现（500）或凭据缺失（503）。
    """
    try:
        return build_provider(settings.provider, default_max_results=settings.max_results)
    except ProviderConfigError as exc:
        logger.error(f"搜索源配置缺失: {exc}")
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        logger.error(f"搜索源配置非法: {exc}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


def _settings_of(request: Request) -> WebSearchSettings:
    """从应用状态取配置单例。

    Args:
        request: 当前请求。

    Returns:
        web_search 配置视图。
    """
    settings: WebSearchSettings = request.app.state.settings
    return settings


def _client_of(request: Request) -> httpx.AsyncClient:
    """从应用状态取共享 httpx 客户端。

    Args:
        request: 当前请求。

    Returns:
        lifespan 中创建、跨请求复用的异步客户端。
    """
    client: httpx.AsyncClient = request.app.state.http_client
    return client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """管理共享 httpx 客户端与配置单例的生命周期。

    Args:
        app: FastAPI 应用实例。

    Yields:
        ``None``；期间 ``app.state`` 上挂载 ``settings`` 与 ``http_client``。
    """
    settings = get_settings()
    client = create_http_client(settings)
    app.state.settings = settings
    app.state.http_client = client
    logger.info(
        f"web_search 服务启动: provider={settings.provider} "
        f"artifacts_dir={settings.artifacts_dir} concurrency={settings.fetch_concurrency}"
    )
    try:
        yield
    finally:
        await client.aclose()
        logger.info("web_search 服务已关闭，共享 HTTP 连接池已释放")


def create_app() -> FastAPI:
    """装配 FastAPI 应用（路由 + lifespan）。

    Returns:
        可直接交给 uvicorn 的 :class:`fastapi.FastAPI` 实例。
    """
    application = FastAPI(
        title="AegisAgent web_search",
        version=__version__,
        description="外部 Web 搜索与网页降噪清洗 sidecar（ADR: documents/技术选型/web_search.md）",
        lifespan=lifespan,
    )

    @application.get(HEALTH_PATH, summary="健康检查")
    async def health(request: Request) -> dict[str, object]:
        """返回服务存活状态与关键配置摘要。

        Args:
            request: 当前请求。

        Returns:
            含 ``status`` / ``service`` / ``version`` / ``provider`` 的字典。
        """
        settings = _settings_of(request)
        return {
            "status": "ok",
            "service": "web_search",
            "version": __version__,
            "provider": settings.provider,
            "max_results": settings.max_results,
            "fetch_concurrency": settings.fetch_concurrency,
        }

    @application.post(SEARCH_PATH, response_model=SearchQueryResponse, summary="检索并可选清洗正文")
    async def search_query(payload: SearchQueryRequest, request: Request) -> SearchQueryResponse:
        """执行"检索 → 去重 → 可选抓取 → 汇总"的完整流水线。

        Args:
            payload: 检索请求体。
            request: 当前请求，用于取共享客户端与配置。

        Returns:
            :class:`SearchQueryResponse`。

        Raises:
            HTTPException: 504（总超时）、502（搜索源失败）、503/500（配置问题）。
        """
        started = time.perf_counter()
        settings = _settings_of(request)
        client = _client_of(request)
        task_id = payload.task_id or uuid.uuid4().hex

        limit = payload.max_results or settings.max_results
        limit = min(limit, settings.max_results)  # 硬配额：不允许客户端放大检索开销
        provider = _build_provider(settings)

        try:
            # 总超时覆盖搜索 + 抓取 + 清洗；超时即放弃（工作线程内的同步调用无法强杀，
            # 但结果已被丢弃，不会污染响应）。
            async with asyncio.timeout(settings.total_timeout_sec):
                hits = await provider.search(payload.query, limit)
                unique_hits = dedupe(hits)

                pages: list[ExtractedPage | BaseException] = []
                if payload.fetch and unique_hits:
                    pages = await _fetch_pages(unique_hits, settings, client)

                items: list[SearchResultItem] = []
                for index, hit in enumerate(unique_hits):
                    page: ExtractedPage | None = None
                    if index < len(pages):
                        candidate = pages[index]
                        if isinstance(candidate, BaseException):
                            logger.opt(exception=candidate).error(
                                f"抓取线程异常，降级为 Snippet: url={hit.url}"
                            )
                            items.append(
                                _snippet_item(hit, PageStatus.ERROR.value, error=str(candidate))
                            )
                            continue
                        page = candidate
                    items.append(await _build_item(hit, page, settings, task_id))
        except TimeoutError as exc:
            logger.warning(
                f"检索总超时: query={payload.query!r} budget={settings.total_timeout_sec}s"
            )
            raise HTTPException(
                status_code=http_status.HTTP_504_GATEWAY_TIMEOUT,
                detail=f"检索总耗时超过 {settings.total_timeout_sec}s 预算",
            ) from exc
        except SearchProviderError as exc:
            logger.error(f"搜索源调用失败: provider={settings.provider} error={exc}")
            raise HTTPException(
                status_code=http_status.HTTP_502_BAD_GATEWAY,
                detail=f"搜索源 {settings.provider} 调用失败: {exc}",
            ) from exc
        except OSError as exc:
            logger.error(f"正文落盘失败: task_id={task_id} error={exc}")
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"正文落盘失败: {exc}",
            ) from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        blocked = sum(1 for item in items if item.status == PageStatus.BLOCKED.value)
        logger.info(
            f"检索完成: query={payload.query!r} provider={settings.provider} "
            f"total={len(items)} blocked={blocked} fetch={payload.fetch} elapsed_ms={elapsed_ms}"
        )

        return SearchQueryResponse(
            query=payload.query,
            provider=settings.provider,
            task_id=task_id,
            fetch=payload.fetch,
            total=len(items),
            blocked=blocked,
            results=items,
            elapsed_ms=elapsed_ms,
        )

    return application


#: 模块级应用实例，供 ``uvicorn services.web_search.app:app`` 或测试客户端直接使用
app = create_app()
