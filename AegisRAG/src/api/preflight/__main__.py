"""AegisRAG 独立体检诊断 CLI 命令入口。

执行方式::

    python -m api.preflight               # 标准体检 (控制台排版)
    python -m api.preflight --verbose     # 详细体检 (输出扩展细节)
    python -m api.preflight --json        # 输出 JSON 格式
    python -m api.preflight --skip-smoke  # 跳过内存沙箱冒烟
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 确保 src 目录在 sys.path 首位
_src_root = Path(__file__).resolve().parents[2]
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))

from api.preflight.reporter import DiagnosticReporter
from api.preflight.runner import PreflightRunner
from api.settings import get_settings


def main() -> None:
    """CLI 入口点。"""
    parser = argparse.ArgumentParser(
        prog="python -m api.preflight",
        description="AegisRAG 启动前置系统自检与体检工具",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以标准 JSON 格式输出体检报告",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出详细诊断信息与耗时指标",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="跳过端到端内存沙箱冒烟测试（加快纯静态检查速度）",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：存在任何 WARN 警告项时也将退出码置为 2",
    )

    args = parser.parse_args()

    try:
        settings = get_settings()
    except Exception as exc:  # noqa: BLE001
        print(f"\n[✘ 致命错误] 读取/解析配置文件失败: {exc}\n", file=sys.stderr)
        sys.exit(1)

    runner = PreflightRunner()
    report = runner.run(settings, skip_smoke=args.skip_smoke)

    if args.json:
        print(DiagnosticReporter.format_json(report))
    else:
        print(DiagnosticReporter.format_console(report, verbose=args.verbose))

    if not report.is_launch_ready:
        sys.exit(1)
    if args.strict and report.has_warnings:
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
