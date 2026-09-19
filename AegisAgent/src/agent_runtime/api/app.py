"""FastAPI 应用装配（lifespan + 中间件 + 路由挂载）。

**启动顺序即依赖顺序**（见 ``11_http_api.md`` §7）：
日志 → 访问令牌 → 运行时（配置/记忆/网关/检查点）→ 任务注册表 → 暴露路由。
关闭时**逆序**释放：先停任务，再关 MCP 与检查点，避免"任务还在跑但连接已断"。

**中间件嵌套顺序（不可随意调整）**：本文件先注册安全闸门、后注册 CORS。
Starlette 后注册的中间件在外层，因此 CORS 包住安全闸门——
这样 401/403 响应也能带上 CORS 头（否则浏览器里只会看到一个语焉不详的网络错误，
而不是我们的错误体）。
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

import httpx
from agent_runtime.api.auth import SecurityGateMiddleware
from agent_runtime.api.errors import install_exception_handlers
from agent_runtime.api.routes import (
    artifacts,
    files,
    health,
    introspection,
    rag,
    sessions,
    tasks,
    workspaces,
)
from agent_runtime.api.task_registry import TaskRegistry
from agent_runtime.config import AegisConfig, get_config
from agent_runtime.observability.logging import setup_logging
from agent_runtime.preflight import render_startup_dashboard, run_preflight_checks
from agent_runtime.supervisor import SidecarSupervisor, build_default_supervisor
from agent_runtime.workflow import build_runtime, close_runtime

__all__ = ["create_app"]

API_PREFIX = "/api/v1"


def create_app(config: Optional[AegisConfig] = None) -> FastAPI:
    """构造 Agent HTTP API 应用。

    Args:
        config: 全局配置；缺省从 ``config.toml`` 加载。

    Returns:
        可直接交给 uvicorn 运行的 :class:`FastAPI` 实例。
    """
    cfg = config or get_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """管理进程级资源的生命周期。"""
        setup_logging(log_dir=Path(cfg.runtime.storage.metadata_db_path).parent / "logs")
        logger.info(f"[API] 启动 Agent HTTP API on {cfg.server.host}:{cfg.server.port}")

        # 1. 运行启动前环境与持久化自检
        app.state.api_token = None
        preflight_report = run_preflight_checks(cfg)

        # 2. 连带拉起托管的 Sidecar 子进程（若开启）
        supervisor: Optional[SidecarSupervisor] = None
        sidecar_statuses = None
        if cfg.services.auto_start_sidecars:
            supervisor = build_default_supervisor(cfg)
            app.state.supervisor = supervisor
            sidecar_statuses = await supervisor.start_all()

        # 3. 探测外部依赖微服务（如 AegisRAG）
        rag_reachable: Optional[bool] = None
        try:
            async with httpx.AsyncClient(timeout=0.6) as client:
                resp = await client.get(f"{cfg.services.rag_url}/api/v1/health")
                rag_reachable = resp.status_code < 500
        except Exception:
            rag_reachable = False

        # 4. 装配核心 Agent 运行时
        runtime = await build_runtime(cfg)
        app.state.runtime = runtime
        app.state.started_at = time.time()
        app.state.task_registry = TaskRegistry(
            max_concurrent=cfg.server.max_concurrent_tasks,
            buffer_size=cfg.server.sse_buffer_events,
        )

        # 5. 打印结构化终端启动就绪看板
        dashboard_banner = render_startup_dashboard(
            report=preflight_report,
            config=cfg,
            sidecar_statuses=sidecar_statuses,
            rag_reachable=rag_reachable,
        )
        logger.info(f"\n{dashboard_banner}")

        try:
            yield
        finally:
            logger.info("[API] 开始关闭 Agent HTTP API")
            await app.state.task_registry.shutdown()
            await close_runtime(runtime)
            if supervisor:
                await supervisor.stop_all()


    app = FastAPI(
        title="Aegis Agent Runtime API",
        description="工程研究智能体的唯一用户入口：工作区/会话/任务 + SSE 执行事件流。",
        version="0.1.0",
        lifespan=lifespan,
    )

    # 安全闸门（先注册 → 在内层）：Host → Origin，见 api/auth.py。
    app.add_middleware(
        SecurityGateMiddleware,
        allowed_hosts=list(cfg.server.allowed_hosts),
        allow_origins=list(cfg.server.cors_allow_origins),
    )

    # CORS（后注册 → 在外层）：默认拒绝，只放行配置白名单（前端开发服务器）。
    # 注意：本服务内含受控命令执行能力，禁止把 host 设为 0.0.0.0（config.py 已 fail-closed）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.server.cors_allow_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Trace-ID", "Last-Event-ID", "Authorization", "X-API-Token"],
        expose_headers=["X-Trace-ID"],
    )

    install_exception_handlers(app)

    for module in (health, workspaces, sessions, tasks, artifacts, introspection, files, rag):
        app.include_router(module.router, prefix=API_PREFIX)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, Any]:
        """根路径：给出契约文档位置与鉴权要求，避免暴露内部结构。"""
        return {
            "service": "aegis-agent",
            "api_prefix": API_PREFIX,
            "docs": "/docs",
            "contract": "documents/agent_runtime/11_http_api.md",
            "auth_required": bool(cfg.server.auth_enabled),
            "auth_hint": (
                "Authorization: Bearer <token> / X-API-Token / ?token= ；"
                f"令牌见 {cfg.server.api_token_file} 或环境变量 {cfg.server.api_token_env}"
                if cfg.server.auth_enabled
                else "未启用令牌校验（Host 与 Origin 闸门仍生效）"
            ),
        }

    return app
