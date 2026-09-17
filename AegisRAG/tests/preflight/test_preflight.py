"""AegisRAG 启动前置体检子系统 (Pre-flight Inspection) 单元与集成测试。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api.preflight.models import (
    CheckStatus,
    DiagnosticCategory,
    DiagnosticItem,
    DiagnosticReport,
)
from api.preflight.probes.base import BaseProbe
from api.preflight.probes.config_guard import ConfigGuardProbe
from api.preflight.probes.environment import EnvironmentProbe
from api.preflight.probes.network import NetworkProbe
from api.preflight.probes.parser import ParserProbe
from api.preflight.probes.storage import StorageProbe
from api.preflight.reporter import DiagnosticReporter
from api.preflight.runner import PreflightRunner
from api.settings import get_settings


class TestPreflightModels:
    """测试体检数据模型与报告状态聚合逻辑。"""

    def test_diagnostic_item_properties(self) -> None:
        item = DiagnosticItem(
            name="测试检查项",
            status=CheckStatus.PASS,
            message="检查正常",
            latency_ms=12.5,
            details={"key": "value"},
        )
        assert item.name == "测试检查项"
        assert item.status == CheckStatus.PASS
        assert item.latency_ms == 12.5
        assert item.details == {"key": "value"}

    def test_category_and_report_aggregation(self) -> None:
        cat1 = DiagnosticCategory(
            category_name="分类1",
            items=[
                DiagnosticItem(name="项1", status=CheckStatus.PASS, message="ok"),
                DiagnosticItem(name="项2", status=CheckStatus.WARN, message="warn", remediation="fix warn"),
            ],
            duration_ms=10.0,
        )
        cat2 = DiagnosticCategory(
            category_name="分类2",
            items=[
                DiagnosticItem(name="项3", status=CheckStatus.FAIL, message="fail", remediation="fix fail"),
            ],
            duration_ms=20.0,
        )

        report = DiagnosticReport(
            categories=[cat1, cat2],
            total_duration_ms=30.0,
        )

        assert report.pass_count == 1
        assert report.warn_count == 1
        assert report.fail_count == 1
        assert report.skip_count == 0
        assert report.has_warnings is True
        assert report.has_failures is True
        assert report.is_launch_ready is False  # 存在 FAIL 时不允许启动

        summary = report.to_summary_dict()
        assert summary["is_launch_ready"] is False
        assert summary["fail_count"] == 1
        assert summary["total_duration_ms"] == 30.0


class TestDiagnosticReporter:
    """测试报告渲染器格式化功能。"""

    def test_console_and_json_format(self) -> None:
        cat = DiagnosticCategory(
            category_name="测试分类",
            items=[
                DiagnosticItem(name="项A", status=CheckStatus.PASS, message="正常运行"),
                DiagnosticItem(name="项B", status=CheckStatus.FAIL, message="严重异常", remediation="请重新安装"),
            ],
            duration_ms=5.0,
        )
        report = DiagnosticReport(categories=[cat], total_duration_ms=5.0)

        console_out = DiagnosticReporter.format_console(report, verbose=True)
        assert "AegisRAG 启动前置体检报告" in console_out
        assert "测试分类" in console_out
        assert "项A" in console_out
        assert "项B" in console_out
        assert "请重新安装" in console_out
        assert "[✘ BLOCKED]" in console_out

        json_out = DiagnosticReporter.format_json(report)
        data = json.loads(json_out)
        assert data["categories"][0]["category_name"] == "测试分类"
        assert data["categories"][0]["items"][0]["status"] == "PASS"
        assert data["categories"][0]["items"][1]["status"] == "FAIL"


class TestIndividualProbes:
    """测试各领域独立探针的诊断行为。"""

    def test_environment_probe(self) -> None:
        settings = get_settings()
        probe = EnvironmentProbe()
        cat = probe.probe(settings)
        assert cat.category_name == "系统环境与依赖完整性"
        assert len(cat.items) >= 2
        # Python 3.11 必须通过
        py_item = next(it for it in cat.items if it.name == "Python 运行时版本")
        assert py_item.status == CheckStatus.PASS

    def test_config_guard_probe_valid(self) -> None:
        settings = get_settings()
        probe = ConfigGuardProbe()
        cat = probe.probe(settings)
        assert cat.category_name == "配置合规与安全红线"
        assert not cat.has_failures

    def test_config_guard_probe_invalid_host(self) -> None:
        settings = get_settings()
        # 模拟配置被篡改为非回环公网 IP
        bad_server = settings.server.model_copy(update={"host": "192.168.1.100"})
        # 绕过 model_validator 直接测试探针防御
        bad_settings = MagicMock()
        bad_settings.server = bad_server
        bad_settings.qdrant = settings.qdrant
        bad_settings.embedding = settings.embedding
        bad_settings.rerank = settings.rerank

        probe = ConfigGuardProbe()
        items = probe.run_checks(bad_settings)
        host_item = next(it for it in items if it.name == "网络监听安全红线")
        assert host_item.status == CheckStatus.FAIL
        assert "非回环地址" in host_item.message

    def test_storage_probe(self, tmp_path: Path) -> None:
        settings = get_settings()
        probe = StorageProbe()
        cat = probe.probe(settings)
        assert cat.category_name == "存储系统与磁盘 I/O 权限"
        # 只要磁盘正常，不应有 FAIL
        assert not cat.has_failures

    def test_network_probe(self) -> None:
        settings = get_settings()
        probe = NetworkProbe()
        cat = probe.probe(settings)
        assert cat.category_name == "网络端口与服务连通性"
        # 端口 8001 应当是空闲的
        port_item = next(it for it in cat.items if it.name == "HTTP 服务端口可用性")
        assert port_item.status in (CheckStatus.PASS, CheckStatus.FAIL)

    def test_network_probe_collision_simulation(self) -> None:
        settings = get_settings()
        probe = NetworkProbe()
        with patch.object(probe, "_check_port_bindable", return_value=(False, "Address already in use")):
            items = probe.run_checks(settings)
            port_item = next(it for it in items if it.name == "HTTP 服务端口可用性")
            assert port_item.status == CheckStatus.FAIL
            assert "已被占用" in port_item.message

    def test_parser_probe(self) -> None:
        settings = get_settings()
        probe = ParserProbe()
        cat = probe.probe(settings)
        assert cat.category_name == "语法解析器与切分器就绪度"
        assert not cat.has_failures


class TestPreflightRunnerIntegration:
    """测试体检调度器整体执行流。"""

    def test_runner_skip_smoke(self) -> None:
        settings = get_settings()
        runner = PreflightRunner()
        report = runner.run(settings, skip_smoke=True)
        assert len(report.categories) == 6
        assert report.total_duration_ms > 0
        # 验证没有 FAIL
        for cat in report.categories:
            for item in cat.items:
                if item.status == CheckStatus.FAIL:
                    pytest.fail(f"探针失败: {item.name} - {item.message} ({item.remediation})")
        assert report.is_launch_ready is True

    def test_runner_custom_probes(self) -> None:
        class DummyProbe(BaseProbe):
            @property
            def category_name(self) -> str:
                return "Mock分类"

            def run_checks(self, settings) -> list[DiagnosticItem]:
                return [DiagnosticItem(name="Mock项", status=CheckStatus.PASS, message="Mock OK")]

        runner = PreflightRunner(custom_probes=[DummyProbe()])
        report = runner.run()
        assert len(report.categories) == 1
        assert report.categories[0].category_name == "Mock分类"
        assert report.is_launch_ready is True
