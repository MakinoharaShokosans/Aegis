"""FastAPI 应用装配（lifespan + 中间件 + 路由挂载）。

**启动顺序即依赖顺序**（见 ``11_http_api.md`` §7）：
日志 → 运行时（配置/记忆/网关/检查点）→ 任务注册表 → 暴露路由。
关闭时**逆序**释放：先停任务，再关 MCP 与检查点，避免"任务还在跑但连接已断"。
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from agent_runtime.api.errors import install_exception_handlers
from agent_runtime.api.routes import (
    artifacts,
    health,
    introspection,
    sessions,
    tasks,
    workspaces,
)
from agent_runtime.api.task_registry import TaskRegistry
from agent_runtime.config import AegisConfig, get_config
from agent_runtime.observability.logging import setup_logging
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

        runtime = await build_runtime(cfg)
        app.state.runtime = runtime
        app.state.started_at = time.time()
        app.state.task_registry = TaskRegistry(
            max_concurrent=cfg.server.max_concurrent_tasks,
            buffer_size=cfg.server.sse_buffer_events,
        )
        try:
            yield
        finally:
            logger.info("[API] 开始关闭 Agent HTTP API")
            await app.state.task_registry.shutdown()
            await close_runtime(runtime)

    app = FastAPI(
        title="Aegis Agent Runtime API",
        description="工程研究智能体的唯一用户入口：工作区/会话/任务 + SSE 执行事件流。",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS 默认拒绝：只放行配置白名单（前端开发服务器）。
    # 注意：本服务内含受控命令执行能力，禁止把 host 设为 0.0.0.0（config.py 已 fail-closed）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.server.cors_allow_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Trace-ID", "Last-Event-ID"],
        expose_headers=["X-Trace-ID"],
    )

    install_exception_handlers(app)

    for module in (health, workspaces, sessions, tasks, artifacts, introspection):
        app.include_router(module.router, prefix=API_PREFIX)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, Any]:
        """根路径：给出契约文档位置，避免暴露内部结构。"""
        return {
            "service": "aegis-agent",
            "api_prefix": API_PREFIX,
            "docs": "/docs",
            "contract": "documents/agent_runtime/11_http_api.md",
        }

    return app
