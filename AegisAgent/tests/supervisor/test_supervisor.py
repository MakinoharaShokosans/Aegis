"""Sidecar Supervisor 进程托管与生命周期单元测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agent_runtime.config import get_config
from agent_runtime.supervisor import (
    SidecarProcessInfo,
    SidecarSpec,
    SidecarSupervisor,
    build_default_supervisor,
)


def test_sidecar_spec_urls() -> None:
    spec = SidecarSpec(
        name="test_service",
        module="services.test",
        host="127.0.0.1",
        port=9999,
        health_path="/health",
        log_tag="Test:9999",
        log_color="green",
    )
    assert spec.url == "http://127.0.0.1:9999"
    assert spec.health_url == "http://127.0.0.1:9999/health"


def test_build_default_supervisor() -> None:
    cfg = get_config()
    sup = build_default_supervisor(cfg)
    assert len(sup._specs) == 2
    names = [s.name for s in sup._specs]
    assert "bash_shell" in names
    assert "web_search" in names


@pytest.mark.asyncio
async def test_supervisor_probe_health_unreachable() -> None:
    spec = SidecarSpec(
        name="dummy",
        module="dummy",
        host="127.0.0.1",
        port=59999,
        health_path="/health",
    )
    sup = SidecarSupervisor([spec], startup_timeout_sec=0.2)
    healthy = await sup.probe_health(spec, timeout_sec=0.2)
    assert healthy is False


@pytest.mark.asyncio
async def test_supervisor_attach_existing_external() -> None:
    spec = SidecarSpec(
        name="dummy",
        module="dummy",
        host="127.0.0.1",
        port=8002,
    )
    sup = SidecarSupervisor([spec], startup_timeout_sec=0.2)

    with patch.object(sup, "probe_health", AsyncMock(return_value=True)):
        statuses = await sup.start_all()
        assert "dummy" in statuses
        info = statuses["dummy"]
        assert info.is_external is True
        assert info.healthy is True
        assert info.process is None


@pytest.mark.asyncio
async def test_supervisor_spawn_and_stop_lifecycle() -> None:
    spec = SidecarSpec(
        name="test_worker",
        module="test_worker",
        host="127.0.0.1",
        port=59998,
        log_tag="Worker:59998",
        log_color="cyan",
    )
    sup = SidecarSupervisor([spec], startup_timeout_sec=0.5)

    from unittest.mock import MagicMock
    # 构造 mock 子进程
    mock_proc = AsyncMock()
    mock_proc.pid = 99881
    mock_proc.returncode = None
    mock_proc.send_signal = MagicMock()
    mock_proc.wait = AsyncMock(return_value=0)

    # 管道 mock
    mock_stdout = AsyncMock()
    mock_stdout.at_eof = MagicMock(side_effect=[False, False, True])
    mock_stdout.readline = AsyncMock(side_effect=[b"worker ready\n", b"worker running\n", b""])
    mock_proc.stdout = mock_stdout
    mock_proc.stderr = None

    # probe_health: 首次探针外部复用 False，随后健康探针轮询 True
    probe_results = [False, True]

    async def mock_probe(*args, **kwargs):
        if probe_results:
            return probe_results.pop(0)
        return True

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)), \
         patch.object(sup, "probe_health", side_effect=mock_probe):
        statuses = await sup.start_all()
        info = statuses["test_worker"]
        assert info.healthy is True
        assert info.pid == 99881
        assert info.is_external is False

        # 测试优雅退出 stop_all
        await sup.stop_all(grace_period_sec=0.5)
        mock_proc.send_signal.assert_called_once()
