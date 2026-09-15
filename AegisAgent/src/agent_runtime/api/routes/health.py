"""健康检查端点。

区分两类健康：

* ``/health``：**本进程**是否可用（元数据库 / 检查点）；
* ``/health/dependencies``：三个 sidecar 是否可达。**依赖不可用不返回 5xx**，
  只在响应体内标记——本进程仍然是健康的，只是能力降级。
"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter

from agent_runtime.api.deps import ConfigDep, RuntimeDep, StartedAtDep
from agent_runtime.api.schemas import DependencyHealth, HealthStatus

__all__ = ["router"]

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus, summary="进程健康检查")
async def health(runtime: RuntimeDep, started_at: StartedAtDep) -> HealthStatus:
    """报告本进程与本地存储的健康状态。

    Args:
        runtime: 进程级运行时。
        started_at: 进程启动时间戳。

    Returns:
        :class:`HealthStatus`。
    """
    checkpoint_ok = runtime.checkpoints.saver is not None
    metadata_ok = runtime.memory.store is not None
    return HealthStatus(
        status="ok" if (checkpoint_ok and metadata_ok) else "degraded",
        uptime_sec=max(0.0, time.time() - started_at),
        metadata_db_ok=metadata_ok,
        checkpoint_ok=checkpoint_ok,
    )


@router.get("/health/dependencies", response_model=list[DependencyHealth], summary="下游依赖连通性")
async def dependencies(config: ConfigDep) -> list[DependencyHealth]:
    """探测三个 sidecar 的连通性。

    探测失败**不影响本端点自身的 HTTP 状态码**，由调用方读取 ``reachable`` 字段。

    Args:
        config: 全局配置。

    Returns:
        各依赖的健康条目。
    """
    services = config.services
    targets = [
        ("rag", f"{services.rag_url}/api/v1/health"),
        ("shell", f"{services.shell_url}/api/v1/health"),
        ("web", f"{services.web_url}/api/v1/health"),
    ]

    results: list[DependencyHealth] = []
    timeout = httpx.Timeout(min(5.0, services.timeout_sec))
    async with httpx.AsyncClient(timeout=timeout) as client:
        for name, url in targets:
            try:
                response = await client.get(url)
                reachable = response.status_code < 500
                detail = f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                reachable = False
                detail = f"{type(exc).__name__}"
            results.append(DependencyHealth(name=name, reachable=reachable, detail=detail))
    return results
