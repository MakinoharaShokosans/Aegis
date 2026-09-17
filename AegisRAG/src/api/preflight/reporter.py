"""体检报告排版与格式化渲染器。

提供终端富文本/ANSI 格式化排版器与机器可读的 JSON 导出器。
"""

from __future__ import annotations

import sys
from typing import List

from api.preflight.models import CheckStatus, DiagnosticCategory, DiagnosticItem, DiagnosticReport

__all__ = ["DiagnosticReporter"]

# ANSI 颜色码
_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_BLUE = "\033[94m"
_CYAN = "\033[96m"
_GRAY = "\033[90m"


class DiagnosticReporter:
    """体检报告渲染与导出工具类。"""

    @classmethod
    def format_console(cls, report: DiagnosticReport, *, verbose: bool = False) -> str:
        """生成面向控制台终端的格式化排版文本。

        Args:
            report: 全量体检报告数据。
            verbose: 是否输出扩展详情与耗时细节。

        Returns:
            带色彩与排版装饰的报告字符串。
        """
        use_color = sys.stdout.isatty()

        def c(text: str, color_code: str) -> str:
            return f"{color_code}{text}{_RESET}" if use_color else text

        lines: List[str] = []
        divider = "=" * 80
        sub_divider = "-" * 80

        lines.append("")
        lines.append(c(divider, _CYAN))
        lines.append(c("                     AegisRAG 启动前置体检报告 (Pre-flight Inspection)", _BOLD + _CYAN))
        lines.append(c(f"                     生成时间: {report.timestamp}", _GRAY))
        lines.append(c(divider, _CYAN))

        for idx, category in enumerate(report.categories, 1):
            cat_header = f"[{idx}. {category.category_name}]"
            duration_str = f"(耗时: {category.duration_ms:.1f}ms)"
            lines.append(f"{c(cat_header, _BOLD)} {c(duration_str, _GRAY)}")

            for item in category.items:
                status_icon, status_color = cls._status_badge(item.status)
                icon_str = c(f"  {status_icon}", status_color)
                name_str = c(f"{item.name:<26}", _BOLD)
                msg_str = item.message
                lines.append(f"{icon_str} {name_str} : {msg_str}")

                if item.remediation and item.status in (CheckStatus.FAIL, CheckStatus.WARN):
                    remed_str = c(f"     ↳ [排查修复] {item.remediation}", _YELLOW if item.status == CheckStatus.WARN else _RED)
                    lines.append(remed_str)

                if verbose and item.details:
                    details_str = c(f"     ↳ [详情] {item.details}", _GRAY)
                    lines.append(details_str)

            lines.append("")

        lines.append(c(sub_divider, _CYAN))

        # 统计概要
        summary_str = (
            f"体检统计: "
            f"{c(f'通过: {report.pass_count}', _GREEN)}, "
            f"{c(f'警告: {report.warn_count}', _YELLOW)}, "
            f"{c(f'阻断: {report.fail_count}', _RED)}, "
            f"跳过: {report.skip_count} "
            f"(总耗时: {report.total_duration_ms:.1f}ms)"
        )
        lines.append(summary_str)

        # 最终准入结论
        if report.is_launch_ready:
            ready_msg = "[✔ READY] 服务各系统检查通过，准许安全拉起！"
            lines.append(c(f"诊断结论: {ready_msg}", _BOLD + _GREEN))
        else:
            block_msg = f"[✘ BLOCKED] 发现 {report.fail_count} 项阻断性致命错误，禁止带病启动！请参照上述修复指引修正。"
            lines.append(c(f"诊断结论: {block_msg}", _BOLD + _RED))

        lines.append(c(divider, _CYAN))
        lines.append("")
        return "\n".join(lines)

    @classmethod
    def format_json(cls, report: DiagnosticReport) -> str:
        """导出为格式化 JSON 字符串。"""
        return report.model_dump_json(indent=2)

    @staticmethod
    def _status_badge(status: CheckStatus) -> tuple[str, str]:
        """返回状态对应的文本图标与颜色码。"""
        if status == CheckStatus.PASS:
            return "✔ PASS", _GREEN
        if status == CheckStatus.WARN:
            return "▲ WARN", _YELLOW
        if status == CheckStatus.FAIL:
            return "✘ FAIL", _RED
        return "○ SKIP", _GRAY
