"""体检执行编排器。

负责调度 7 大探针、汇总分类报告、计算全局耗时并评估准入条件。
"""

from __future__ import annotations

import time
from typing import List, Optional

from api.preflight.models import DiagnosticCategory, DiagnosticReport
from api.preflight.probes.base import BaseProbe
from api.preflight.probes.config_guard import ConfigGuardProbe
from api.preflight.probes.environment import EnvironmentProbe
from api.preflight.probes.model import ModelProbe
from api.preflight.probes.network import NetworkProbe
from api.preflight.probes.parser import ParserProbe
from api.preflight.probes.smoke import SmokeProbe
from api.preflight.probes.storage import StorageProbe
from api.settings import RagConfig, get_settings

__all__ = ["PreflightRunner"]


class PreflightRunner:
    """启动前置体检调度器。

    Args:
        custom_probes: 可选自定义探针列表；默认使用标准 7 大领域探针。
    """

    def __init__(self, custom_probes: Optional[List[BaseProbe]] = None) -> None:
        self._probes = custom_probes

    def run(
        self,
        settings: Optional[RagConfig] = None,
        *,
        skip_smoke: bool = False,
    ) -> DiagnosticReport:
        """执行完整前置体检流程。

        Args:
            settings: 可选传入配置对象；默认通过 ``get_settings()`` 自动获取。
            skip_smoke: 是否跳过端到端内存沙箱冒烟测试。

        Returns:
            生成的完整全局体检报告。
        """
        if settings is None:
            settings = get_settings()

        probes: List[BaseProbe]
        if self._probes is not None:
            probes = self._probes
        else:
            probes = [
                EnvironmentProbe(),
                ConfigGuardProbe(),
                StorageProbe(),
                ModelProbe(),
                NetworkProbe(),
                ParserProbe(),
            ]
            if not skip_smoke:
                probes.append(SmokeProbe())

        start_time = time.perf_counter()
        categories: List[DiagnosticCategory] = []

        for probe in probes:
            category = probe.probe(settings)
            categories.append(category)

        total_duration_ms = (time.perf_counter() - start_time) * 1000.0

        return DiagnosticReport(
            categories=categories,
            total_duration_ms=total_duration_ms,
        )
