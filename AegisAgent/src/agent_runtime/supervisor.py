"""AegisAgent 内置 Sidecar 托管引擎（Process Supervisor & Log Stream Aggregator）。

职责：
1. **自动拉起**：在 Agent 启动时，自动异步拉起同工程的 ``bash_shell`` (:8002) 与 ``web_search`` (:8003) 独立子进程；
2. **智能复用**：若端口已被外部实例（Docker 容器或独立调试终端）占用且通过健康检查，则自动复用（Attach），不重复拉起；
3. **日志管道聚合**：捕获子进程的 ``stdout`` 与 ``stderr``，经由主 Agent 的统一 Loguru 日志引擎打标着色输出与落盘；
4. **两段式优雅退出**：Agent 退出时，向托管子进程级联发送 ``SIGTERM``，超时后兜底 ``SIGKILL``，防止孤儿进程与端口残留。
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

from agent_runtime.config import AegisConfig, ServicesConfig

__all__ = [
    "SidecarSpec",
    "SidecarProcessInfo",
    "SidecarSupervisor",
    "build_default_supervisor",
]


@dataclass(slots=True)
class SidecarSpec:
    """单个 Sidecar 子服务的规格定义。

    Attributes:
        name: 服务名称（如 ``"bash_shell"``、``"web_search"``）。
        module: Python 启动模块名（如 ``"services.bash_shell"``）。
        host: 监听主机。
        port: 监听端口。
        health_path: 健康检查端点相对路径。
        log_tag: 日志输出标签（如 ``"Bash:8002"``）。
        log_color: 控制台着色颜色（如 ``"yellow"``、``"cyan"``）。
    """

    name: str
    module: str
    host: str
    port: int
    health_path: str = "/api/v1/health"
    log_tag: str = ""
    log_color: str = "cyan"

    @property
    def url(self) -> str:
        """服务的 HTTP Base URL。"""
        return f"http://{self.host}:{self.port}"

    @property
    def health_url(self) -> str:
        """服务的健康检查完整 URL。"""
        return f"{self.url}{self.health_path}"


@dataclass
class SidecarProcessInfo:
    """托管子进程的运行状态。"""

    spec: SidecarSpec
    pid: Optional[int] = None
    process: Optional[asyncio.subprocess.Process] = None
    is_external: bool = False
    healthy: bool = False
    error: Optional[str] = None
    tasks: List[asyncio.Task[Any]] = field(default_factory=list)


class SidecarSupervisor:
    """Sidecar 子进程生命周期与日志聚合管理器。"""

    def __init__(
        self,
        specs: Optional[List[SidecarSpec]] = None,
        *,
        startup_timeout_sec: float = 10.0,
        src_root: Optional[Path] = None,
    ) -> None:
        self._specs = specs or []
        self._startup_timeout_sec = startup_timeout_sec
        self._src_root = src_root or Path(__file__).resolve().parents[1]
        self._statuses: Dict[str, SidecarProcessInfo] = {}
        self._stopping: bool = False

    @property
    def statuses(self) -> Dict[str, SidecarProcessInfo]:
        """获取所有 Sidecar 的当前状态只读视图。"""
        return dict(self._statuses)

    async def probe_health(self, spec: SidecarSpec, timeout_sec: float = 1.0) -> bool:
        """探测指定 Sidecar 的健康状态。"""
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                resp = await client.get(spec.health_url)
                return resp.status_code < 500
        except Exception:
            return False

    async def start_all(self) -> Dict[str, SidecarProcessInfo]:
        """启动并等待所有配置的 Sidecar 服务就绪。

        Returns:
            各 Sidecar 的状态字典。
        """
        self._stopping = False
        logger.info(f"[Supervisor] 开始启动/探测 {len(self._specs)} 个 Sidecar 服务...")

        for spec in self._specs:
            info = await self._start_single(spec)
            self._statuses[spec.name] = info

        return self._statuses

    async def _start_single(self, spec: SidecarSpec) -> SidecarProcessInfo:
        """启动或复用单个 Sidecar。"""
        tag = spec.log_tag or f"{spec.name}:{spec.port}"

        # 1. 检查是否已经有健康的实例在运行（外部复用）
        if await self.probe_health(spec, timeout_sec=0.5):
            logger.info(f"[Supervisor] 探测到现存外部实例健康，直接复用: {tag} ({spec.url})")
            return SidecarProcessInfo(
                spec=spec,
                pid=None,
                process=None,
                is_external=True,
                healthy=True,
            )

        # 2. 构造环境变量与启动命令
        env = os.environ.copy()
        current_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{self._src_root}:{current_pp}" if current_pp else str(self._src_root)
        # 强制 Python 无缓冲输出，确保实时流式转发
        env["PYTHONUNBUFFERED"] = "1"

        cmd = [sys.executable, "-m", spec.module]
        logger.info(f"[Supervisor] 拉起子进程 [{tag}]: {' '.join(cmd)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._src_root.parent),
                env=env,
            )
        except Exception as exc:
            logger.error(f"[Supervisor] 拉起子进程 [{tag}] 失败: {exc}")
            return SidecarProcessInfo(
                spec=spec,
                pid=None,
                process=None,
                is_external=False,
                healthy=False,
                error=str(exc),
            )

        info = SidecarProcessInfo(
            spec=spec,
            pid=proc.pid,
            process=proc,
            is_external=False,
            healthy=False,
        )

        # 3. 启动后台日志管道读取协程
        if proc.stdout:
            info.tasks.append(
                asyncio.create_task(
                    self._forward_stream(proc.stdout, tag=tag, color=spec.log_color, is_stderr=False),
                    name=f"log-{spec.name}-stdout",
                )
            )
        if proc.stderr:
            info.tasks.append(
                asyncio.create_task(
                    self._forward_stream(proc.stderr, tag=tag, color=spec.log_color, is_stderr=True),
                    name=f"log-{spec.name}-stderr",
                )
            )

        # 4. 轮询等待健康检查通过
        healthy = await self._wait_for_health(spec, proc)
        info.healthy = healthy
        if healthy:
            logger.info(f"[Supervisor] Sidecar [{tag}] 启动就绪 (PID: {proc.pid})")
        else:
            info.error = f"服务在 {self._startup_timeout_sec}s 内未通过就绪性探针"
            logger.warning(f"[Supervisor] Sidecar [{tag}] 未就绪: {info.error}")

        return info

    async def _wait_for_health(self, spec: SidecarSpec, proc: asyncio.subprocess.Process) -> bool:
        """带超时的健康状态轮询。"""
        deadline = asyncio.get_running_loop().time() + self._startup_timeout_sec
        interval = 0.1

        while asyncio.get_running_loop().time() < deadline:
            # 检查子进程是否已异常提前退出
            if proc.returncode is not None:
                logger.error(f"[Supervisor] 子进程 [{spec.name}] 异常提前退出，退出码: {proc.returncode}")
                return False

            if await self.probe_health(spec, timeout_sec=0.4):
                return True

            await asyncio.sleep(interval)
            interval = min(interval * 1.5, 0.5)

        return False

    async def _forward_stream(
        self,
        reader: asyncio.StreamReader,
        *,
        tag: str,
        color: str,
        is_stderr: bool,
    ) -> None:
        """异步逐行读取管道并将日志注入主 Agent 的 Loguru 引擎。"""
        try:
            while not reader.at_eof() and not self._stopping:
                line_bytes = await reader.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue

                # 格式化前缀并输出至统一日志流
                colored_tag = f"<{color}>[{tag}]</{color}>"
                if is_stderr and ("error" in line.lower() or "exception" in line.lower() or "traceback" in line.lower()):
                    logger.opt(colors=True).error(f"{colored_tag} {line}")
                elif "warn" in line.lower():
                    logger.opt(colors=True).warning(f"{colored_tag} {line}")
                else:
                    logger.opt(colors=True).info(f"{colored_tag} {line}")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if not self._stopping:
                logger.debug(f"[Supervisor] 管道读取异常 [{tag}]: {exc}")

    async def stop_all(self, grace_period_sec: float = 3.0) -> None:
        """两段式优雅终止所有由本 Supervisor 管理拉起的子进程。"""
        self._stopping = True
        logger.info("[Supervisor] 开始释放所有托管 Sidecar 子进程...")

        managed = [info for info in self._statuses.values() if not info.is_external and info.process is not None]

        # 第一阶段：向所有子进程发送 SIGTERM
        for info in managed:
            proc = info.process
            if proc and proc.returncode is None:
                tag = info.spec.log_tag or info.spec.name
                logger.info(f"[Supervisor] 发送 SIGTERM -> [{tag}] (PID: {proc.pid})")
                try:
                    proc.send_signal(signal.SIGTERM)
                except ProcessLookupError:
                    pass

        # 等待子进程退出
        if managed:
            for info in managed:
                proc = info.process
                if proc and proc.returncode is None:
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=grace_period_sec)
                    except asyncio.TimeoutError:
                        tag = info.spec.log_tag or info.spec.name
                        logger.warning(f"[Supervisor] [{tag}] 未在 {grace_period_sec}s 内退出，发送 SIGKILL 强制回收")
                        try:
                            proc.kill()
                            await proc.wait()
                        except ProcessLookupError:
                            pass

        # 取消日志转发后台任务
        for info in self._statuses.values():
            for task in info.tasks:
                if not task.done():
                    task.cancel()

        logger.info("[Supervisor] 所有 Sidecar 子进程已清理完成")


def build_default_supervisor(config: AegisConfig) -> SidecarSupervisor:
    """根据全局配置构造标准的 SidecarSupervisor 实例。"""
    services = config.services

    # 解析 bash_shell 端口与主机
    shell_parsed = urlparse(services.shell_url)
    shell_host = shell_parsed.hostname or "127.0.0.1"
    shell_port = shell_parsed.port or 8002

    # 解析 web_search 端口与主机
    web_parsed = urlparse(services.web_url)
    web_host = web_parsed.hostname or "127.0.0.1"
    web_port = web_parsed.port or 8003

    specs = [
        SidecarSpec(
            name="bash_shell",
            module="services.bash_shell",
            host=shell_host,
            port=shell_port,
            health_path="/api/v1/health",
            log_tag="Bash:8002",
            log_color="yellow",
        ),
        SidecarSpec(
            name="web_search",
            module="services.web_search",
            host=web_host,
            port=web_port,
            health_path="/api/v1/health",
            log_tag="Search:8003",
            log_color="cyan",
        ),
    ]

    return SidecarSupervisor(
        specs=specs,
        startup_timeout_sec=services.sidecar_startup_timeout_sec,
    )
