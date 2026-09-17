"""AegisRAG 启动前置体检与自检数据模型。

规范：定义强类型的检查状态、单项诊断结果、领域分类容器及顶层全局体检报告。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CheckStatus",
    "DiagnosticItem",
    "DiagnosticCategory",
    "DiagnosticReport",
]


class CheckStatus(str, Enum):
    """单项检查状态枚举。"""

    PASS = "PASS"    #: 检查通过，运行正常
    WARN = "WARN"    #: 存在警告/次要隐患，但允许降级或继续运行
    FAIL = "FAIL"    #: 存在致命阻断性错误，禁止带病启动
    SKIP = "SKIP"    #: 预置跳过（如因前置条件不满足或被显式忽略）


class DiagnosticItem(BaseModel):
    """单项诊断结果数据结构。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str = Field(description="检查项名称")
    status: CheckStatus = Field(description="检查结果状态")
    message: str = Field(description="诊断结果描述或指标信息")
    latency_ms: Optional[float] = Field(default=None, description="探测耗时（毫秒）")
    details: Optional[Dict[str, Any]] = Field(default=None, description="附加结构化详情")
    remediation: Optional[str] = Field(default=None, description="失败/警告时的修复排查建议")


class DiagnosticCategory(BaseModel):
    """领域诊断分类容器（如系统环境、存储检查、模型探针等）。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    category_name: str = Field(description="领域分类名称")
    items: List[DiagnosticItem] = Field(default_factory=list, description="该分类下的所有诊断项")
    duration_ms: float = Field(default=0.0, description="该分类所有探针执行总耗时（毫秒）")

    @property
    def has_failures(self) -> bool:
        """该分类下是否存在阻断性致命错误。"""
        return any(item.status == CheckStatus.FAIL for item in self.items)

    @property
    def has_warnings(self) -> bool:
        """该分类下是否存在警告项。"""
        return any(item.status == CheckStatus.WARN for item in self.items)


class DiagnosticReport(BaseModel):
    """AegisRAG 全局启动前置体检报告。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="体检生成时刻 (ISO 8601 UTC)",
    )
    categories: List[DiagnosticCategory] = Field(
        default_factory=list, description="各领域分类诊断结果"
    )
    total_duration_ms: float = Field(default=0.0, description="全量体检总耗时（毫秒）")

    @property
    def is_launch_ready(self) -> bool:
        """服务是否具备安全启动条件（当且仅当无任何 FAIL 阻断项）。"""
        return not self.has_failures

    @property
    def has_failures(self) -> bool:
        """全量报告中是否存在任意 FAIL 阻断项。"""
        return any(cat.has_failures for cat in self.categories)

    @property
    def has_warnings(self) -> bool:
        """全量报告中是否存在 WARN 警告项。"""
        return any(cat.has_warnings for cat in self.categories)

    @property
    def pass_count(self) -> int:
        """通过检查项总数。"""
        return sum(
            1
            for cat in self.categories
            for item in cat.items
            if item.status == CheckStatus.PASS
        )

    @property
    def warn_count(self) -> int:
        """警告检查项总数。"""
        return sum(
            1
            for cat in self.categories
            for item in cat.items
            if item.status == CheckStatus.WARN
        )

    @property
    def fail_count(self) -> int:
        """失败阻断检查项总数。"""
        return sum(
            1
            for cat in self.categories
            for item in cat.items
            if item.status == CheckStatus.FAIL
        )

    @property
    def skip_count(self) -> int:
        """跳过检查项总数。"""
        return sum(
            1
            for cat in self.categories
            for item in cat.items
            if item.status == CheckStatus.SKIP
        )

    def to_summary_dict(self) -> Dict[str, Any]:
        """输出精简摘要字典（供日志或健康接口快照）。"""
        return {
            "timestamp": self.timestamp,
            "is_launch_ready": self.is_launch_ready,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "skip_count": self.skip_count,
            "total_duration_ms": round(self.total_duration_ms, 2),
        }
