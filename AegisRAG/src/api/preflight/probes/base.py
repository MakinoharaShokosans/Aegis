"""探针基类与抽象接口定义。"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List

from api.preflight.models import DiagnosticCategory, DiagnosticItem

if TYPE_CHECKING:
    from api.settings import RagConfig

__all__ = ["BaseProbe"]


class BaseProbe(ABC):
    """前置体检探针抽象基类。"""

    @property
    @abstractmethod
    def category_name(self) -> str:
        """所属领域分类名称（如 '系统环境与依赖', '配置与安全红线'）。"""

    @abstractmethod
    def run_checks(self, settings: RagConfig) -> List[DiagnosticItem]:
        """执行该领域下的所有具体检查项。

        Args:
            settings: AegisRAG 全量配置实例。

        Returns:
            诊断项列表。
        """

    def probe(self, settings: RagConfig) -> DiagnosticCategory:
        """执行该探针并封装为分类诊断结果（自动统计耗时）。

        Args:
            settings: AegisRAG 全量配置实例。

        Returns:
            领域分类诊断结果。
        """
        start_time = time.perf_counter()
        items = self.run_checks(settings)
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return DiagnosticCategory(
            category_name=self.category_name,
            items=items,
            duration_ms=duration_ms,
        )
