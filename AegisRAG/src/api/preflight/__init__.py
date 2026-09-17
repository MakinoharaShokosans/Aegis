"""AegisRAG 启动前置体检与自检子系统。

提供系统级 7 维前置诊断矩阵、结构化报告输出与服务启动安全门禁。
"""

from __future__ import annotations

from api.preflight.models import (
    CheckStatus,
    DiagnosticCategory,
    DiagnosticItem,
    DiagnosticReport,
)
from api.preflight.reporter import DiagnosticReporter
from api.preflight.runner import PreflightRunner

__all__ = [
    "CheckStatus",
    "DiagnosticItem",
    "DiagnosticCategory",
    "DiagnosticReport",
    "DiagnosticReporter",
    "PreflightRunner",
]
