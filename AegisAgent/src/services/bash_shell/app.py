"""FastAPI 契约层：``POST /api/v1/shell/execute`` 与 ``GET /api/v1/health``。

契约（ADR §2.5）：
- 请求三要素 ``workspace_id`` / ``workspace_root`` / ``task_id`` + ``step_id`` + ``command``；
- 响应为强类型 ``ShellExecutionResult``；
- 审计拒绝 → ``400``（结构化 ``error`` 体）；路径越界 / 工作区非法 → ``422``；
- 内存池配额不足且等待预算耗尽 → 响应 ``status == "QUEUED"`` 与预估等待秒数；
- ``lifespan`` 负责内存池与审计器的初始化与关闭。

规范：documents/技术选型/bash_shell.md 第 2.5 节
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .audit import AuditRejected, CommandAudit, PathEscapeError
from .memory_pool import GlobalMemoryBudget
from .sandbox import ShellExecutionResult, WorkspaceInvalidError, run_command
from .settings import BashShellSettings, get_settings

__all__ = ["app", "create_app", "ShellExecuteRequest", "HealthResponse"]


# ==============================================================================
# 1. 请求 / 响应 DTO
# ==============================================================================


class ShellExecuteRequest(BaseModel):
    """命令执行请求体。

    Attributes:
        workspace_id: 工作区标识（审计与溯源用；服务端以 ``workspace_root`` 为执行边界）。
        workspace_root: 目标工程绝对路径（子进程 cwd，也是路径越界边界）。
        task_id: 任务标识，决定产物落盘目录。
        step_id: 步骤序号，决定日志文件名。
        command: 待执行命令。
        timeout_sec: 本次执行硬超时（秒）；``None`` 时取服务端默认值。
        queue_wait_sec: 允许等待内存池配额的秒数；``0`` 表示池满立即返回 QUEUED。
        write_paths: 调用方显式声明的写入/删除目标（额外越界校验）。
    """

    model_config = ConfigDict(extra="ignore")

    workspace_id: str = Field(min_length=1, description="工作区标识")
    workspace_root: str = Field(min_length=1, description="目标工程绝对路径（执行 cwd）")
    task_id: str = Field(min_length=1, description="任务标识（决定产物目录）")
    step_id: int = Field(ge=0, description="步骤序号（决定日志文件名）")
    command: str = Field(min_length=1, description="待执行命令")
    timeout_sec: Optional[float] = Field(default=None, gt=0, description="硬超时（秒），可选")
    queue_wait_sec: float = Field(default=0.0, ge=0, description="允许等待内存池配额的秒数")
    write_paths: List[str] = Field(default_factory=list, description="显式写入目标（越界校验）")


class HealthResponse(BaseModel):
    """健康检查响应体。

    Attributes:
        status: 固定为 ``ok``。
        service: 服务标识。
        version: 子系统版本。
        memory_pool: 内存池运行时快照。
    """

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="健康状态")
    service: str = Field(description="服务标识")
    version: str = Field(description="子系统版本")
    memory_pool: Dict[str, Any] = Field(description="内存池运行时快照")


# ==============================================================================
# 2. 应用装配
# ==============================================================================


def _structured_error(code: str, message: str, **extra: Any) -> Dict[str, Any]:
    """构造统一结构化错误响应体。

    Args:
        code: 稳定错误码（如 ``AUDIT_REJECTED``）。
        message: 人类可读描述。
        **extra: 附加结构化字段。

    Returns:
        ``{"error": {...}}`` 形态的响应体。
    """
    payload: Dict[str, Any] = {"code": code, "message": message}
    payload.update(extra)
    return {"error": payload}


def create_app() -> FastAPI:
    """构建 FastAPI 应用（便于单测注入与多实例装配）。

    Returns:
        已注册路由、异常处理器与 lifespan 的 FastAPI 实例。
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """服务生命周期：初始化配置 / 审计器 / 内存池，关闭时输出快照。

        Args:
            application: FastAPI 实例（用于挂载共享状态）。

        Yields:
            应用运行期（``yield`` 之前为启动，之后为关闭）。
        """
        settings: BashShellSettings = get_settings()
        application.state.settings = settings
        application.state.audit = CommandAudit()
        application.state.memory_pool = GlobalMemoryBudget(
            settings.memory_pool_mb,
            settings.max_concurrent,
            default_task_mb=settings.rlimit_as_mb,
            default_task_sec=settings.timeout_sec,
        )
        logger.bind(
            host=settings.host,
            port=settings.port,
            pool_mb=settings.memory_pool_mb,
            max_concurrent=settings.max_concurrent,
            artifacts_dir=str(settings.artifacts_root),
        ).info("bash_shell 子系统启动")
        try:
            yield
        finally:
            logger.bind(pool=application.state.memory_pool.snapshot()).info("bash_shell 子系统关闭")

    application = FastAPI(
        title="Aegis bash_shell",
        description="受控 Bash 执行沙箱与输出治理服务（ADR: documents/技术选型/bash_shell.md）",
        version=__version__,
        lifespan=lifespan,
    )

    @application.get("/api/v1/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        """健康检查：返回服务状态与内存池快照。

        Args:
            request: FastAPI 请求对象（读取应用共享状态）。

        Returns:
            健康检查响应体。
        """
        pool: GlobalMemoryBudget = request.app.state.memory_pool
        return HealthResponse(
            status="ok",
            service="bash_shell",
            version=__version__,
            memory_pool=pool.snapshot(),
        )

    @application.post(
        "/api/v1/shell/execute",
        response_model=ShellExecutionResult,
        responses={
            400: {"description": "命令审计拒绝（AUDIT_REJECTED）"},
            422: {"description": "路径越界（PATH_ESCAPE_DETECTED）或工作区非法（WORKSPACE_INVALID）"},
        },
    )
    async def execute_shell(payload: ShellExecuteRequest, request: Request) -> ShellExecutionResult:
        """执行受控命令：审计 → 配额 → 沙箱执行 → 蒸馏返回。

        Args:
            payload: 命令执行请求体。
            request: FastAPI 请求对象（读取配置 / 审计器 / 内存池）。

        Returns:
            强类型执行结果；配额不足且等待预算耗尽时 ``status == "QUEUED"``。

        Raises:
            AuditRejected: 高危命令（由处理器转 400）。
            PathEscapeError: 写入目标越界（由处理器转 422）。
            WorkspaceInvalidError: 工作区根目录非法（由处理器转 422）。
        """
        settings: BashShellSettings = request.app.state.settings
        audit: CommandAudit = request.app.state.audit
        pool: GlobalMemoryBudget = request.app.state.memory_pool
        logger.bind(
            workspace_id=payload.workspace_id,
            task_id=payload.task_id,
            step_id=payload.step_id,
        ).debug("收到 shell 执行请求：{}", payload.command)
        return await run_command(
            payload.command,
            workspace_root=payload.workspace_root,
            task_id=payload.task_id,
            step_id=payload.step_id,
            timeout_sec=payload.timeout_sec,
            queue_wait_sec=payload.queue_wait_sec,
            write_paths=payload.write_paths,
            settings=settings,
            audit=audit,
            pool=pool,
        )

    @application.exception_handler(AuditRejected)
    async def handle_audit_rejected(request: Request, exc: AuditRejected) -> JSONResponse:
        """将审计拒绝映射为 ``400`` + 结构化错误体。

        Args:
            request: FastAPI 请求对象。
            exc: 审计拒绝异常。

        Returns:
            HTTP 400 结构化错误响应。
        """
        logger.bind(rule=exc.rule, path=request.url.path).warning("命令被审计拒绝：{}", exc.reason)
        return JSONResponse(
            status_code=400,
            content=_structured_error("AUDIT_REJECTED", exc.reason, **exc.to_dict()),
        )

    @application.exception_handler(PathEscapeError)
    async def handle_path_escape(request: Request, exc: PathEscapeError) -> JSONResponse:
        """将路径越界映射为 ``422`` + 结构化错误体。

        Args:
            request: FastAPI 请求对象。
            exc: 路径越界异常。

        Returns:
            HTTP 422 结构化错误响应。
        """
        logger.bind(path=exc.path, root=exc.root).warning("写入目标越界：{}", exc)
        return JSONResponse(
            status_code=422,
            content=_structured_error("PATH_ESCAPE_DETECTED", str(exc), **exc.to_dict()),
        )

    @application.exception_handler(WorkspaceInvalidError)
    async def handle_workspace_invalid(
        request: Request, exc: WorkspaceInvalidError
    ) -> JSONResponse:
        """将工作区非法映射为 ``422`` + 结构化错误体。

        Args:
            request: FastAPI 请求对象。
            exc: 工作区非法异常。

        Returns:
            HTTP 422 结构化错误响应。
        """
        logger.bind(workspace_root=exc.workspace_root).warning("工作区非法：{}", exc)
        return JSONResponse(
            status_code=422,
            content=_structured_error("WORKSPACE_INVALID", str(exc), **exc.to_dict()),
        )

    return application


#: 供 ``uvicorn services.bash_shell.app:app`` 直接引用的应用实例
app = create_app()
