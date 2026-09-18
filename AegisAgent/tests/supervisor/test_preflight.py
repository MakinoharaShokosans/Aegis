"""启动前自检与看板渲染单元测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_runtime.config import get_config
from agent_runtime.preflight import (
    CheckItem,
    CheckStatus,
    PreflightReport,
    render_startup_dashboard,
    run_preflight_checks,
)
from agent_runtime.supervisor import SidecarProcessInfo, SidecarSpec


def test_preflight_report_properties() -> None:
    report = PreflightReport()
    report.items.append(CheckItem("Cat", "Item1", CheckStatus.OK, "detail1"))
    assert report.all_ok is True
    assert report.has_errors is False
    assert report.has_warnings is False

    report.items.append(CheckItem("Cat", "Item2", CheckStatus.WARN, "detail2"))
    assert report.all_ok is True
    assert report.has_warnings is True

    report.items.append(CheckItem("Cat", "Item3", CheckStatus.ERROR, "detail3"))
    assert report.all_ok is False
    assert report.has_errors is True


def test_run_preflight_checks_standard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = get_config()
    monkeypatch.setenv("TERRA_KEY", "test_terra_key_secret_123")
    monkeypatch.setenv("LUNA_KEY", "test_luna_key_secret_456")

    report = run_preflight_checks(cfg)
    assert len(report.items) > 0
    assert not report.has_errors

    # 检查 LLM 环境变量项
    key_items = [it for it in report.items if it.category == "LLM Endpoints"]
    assert any("TERRA_KEY" in it.name and it.status == CheckStatus.OK for it in key_items)
    assert any("LUNA_KEY" in it.name and it.status == CheckStatus.OK for it in key_items)


def test_run_preflight_checks_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = get_config()
    monkeypatch.delenv("TERRA_KEY", raising=False)
    monkeypatch.delenv("LUNA_KEY", raising=False)

    report = run_preflight_checks(cfg)
    key_items = [it for it in report.items if it.category == "LLM Endpoints"]
    assert any("TERRA_KEY" in it.name and it.status == CheckStatus.WARN for it in key_items)


def test_render_startup_dashboard() -> None:
    cfg = get_config()
    report = run_preflight_checks(cfg)

    spec = SidecarSpec(
        name="bash_shell",
        module="services.bash_shell",
        host="127.0.0.1",
        port=8002,
        log_tag="Bash:8002",
        log_color="yellow",
    )
    statuses = {
        "bash_shell": SidecarProcessInfo(
            spec=spec,
            pid=12345,
            is_external=False,
            healthy=True,
        )
    }

    banner = render_startup_dashboard(
        report=report,
        config=cfg,
        sidecar_statuses=statuses,
        rag_reachable=True,
        token_hint="token_demo",
    )

    assert "AEGIS AGENT RUNTIME SYSTEM READY" in banner
    assert "[1. System Pre-flight Checks]" in banner
    assert "[2. Managed Sidecars (Physical Sandboxes)]" in banner
    assert "[3. External Dependencies]" in banner
    assert "[4. Agent HTTP API Gateway]" in banner
    assert "Bash:8002" in banner
    assert "12345" in banner
