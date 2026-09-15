"""场景驱动与轨迹解析。

规范：documents/技术选型/evaluation.md 第 2.2 节

数据源：``AegisAgent/storage/traces/{task_id}.jsonl``（运行时由
``agent_runtime.observability.trajectory`` 落盘）。

解耦红线：本模块只做文件解析与指标汇总，**不 import** ``agent_runtime``，
因此轨迹格式升级时评测侧只需跟随字段约定演进，不会形成循环依赖。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .metrics import run_completed, run_error_recovery, run_step_count, summarize

__all__ = [
    "DEFAULT_TRACES_DIR",
    "load_trajectories",
    "main",
    "render_report",
    "run_benchmark",
]

#: 仓库内轨迹目录：``<AegisAgent>/storage/traces``。
DEFAULT_TRACES_DIR: Path = Path(__file__).resolve().parents[3] / "storage" / "traces"


def load_trajectories(traces_dir: str | Path) -> dict[str, list[dict[str, Any]]]:
    """读取目录下全部 ``*.jsonl`` 轨迹，按 ``task_id``（文件名）分组。

    Args:
        traces_dir: 轨迹目录，通常为 ``storage/traces``。

    Returns:
        ``{task_id: [记录, ...]}``；文件名（去掉 ``.jsonl``）即 ``task_id``，
        空行跳过，文件按文件名排序以保证结果可复现。

    Raises:
        FileNotFoundError: 目录不存在时抛出。
        ValueError: 某行不是合法 JSON 对象时抛出（附带文件与行号）。
    """
    directory = Path(traces_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"轨迹目录不存在：{directory}")

    runs: dict[str, list[dict[str, Any]]] = {}
    for trace_file in sorted(directory.glob("*.jsonl")):
        records: list[dict[str, Any]] = []
        for lineno, line in enumerate(
            trace_file.read_text(encoding="utf-8").splitlines(), start=1
        ):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"轨迹文件 {trace_file} 第 {lineno} 行不是合法 JSON：{exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError(f"轨迹文件 {trace_file} 第 {lineno} 行必须是 JSON 对象")
            records.append(payload)
        runs[trace_file.stem] = records
    return runs


def _task_detail(task_id: str, run: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """构造单任务的明细视图，供报告逐任务表格使用。

    Args:
        task_id: 任务标识。
        run: 该任务的轨迹记录序列。

    Returns:
        含 ``completed`` / ``steps`` / ``error_recovery`` 等字段的明细字典。
    """
    return {
        "task_id": task_id,
        "num_records": len(run),
        "completed": run_completed(run),
        "steps": run_step_count(run),
        "error_recovery": run_error_recovery(run),
        "has_artifact": any(
            isinstance(record.get("artifact_path"), str) and record["artifact_path"].strip()
            for record in run
        ),
    }


def run_benchmark(
    traces_dir: str | Path,
    baseline: dict[str, int] | None = None,
) -> dict[str, Any]:
    """驱动一次完整轨迹评测。

    Args:
        traces_dir: 轨迹目录。
        baseline: ``{task_id: 基准最优步数}``；``None`` 时跳过步骤效率对照。

    Returns:
        扁平汇总字典：``{"traces_dir", "num_tasks", ...指标..., "per_task": [...]}``，
        可直接交给 :func:`render_report` 渲染。
    """
    runs = load_trajectories(traces_dir)
    metrics = summarize(list(runs.values()), baseline)
    per_task = [_task_detail(task_id, run) for task_id, run in runs.items()]
    summary: dict[str, Any] = {
        "traces_dir": str(Path(traces_dir)),
        "num_tasks": len(runs),
        **metrics,
        "per_task": per_task,
    }
    return summary


def _format_ratio(value: Any, digits: int = 2) -> str:
    """格式化比值字段。

    Args:
        value: 任意数值。
        digits: 小数位。

    Returns:
        格式化文本；非数值时返回 ``"—"``。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "—"
    return f"{float(value):.{digits}f}"


def _format_percent(value: Any) -> str:
    """把 0~1 的比率格式化为百分比。

    Args:
        value: 任意数值。

    Returns:
        形如 ``"85.71%"`` 的文本；非数值时返回 ``"—"``。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "—"
    return f"{float(value) * 100:.2f}%"


def _format_bool(value: Any) -> str:
    """格式化布尔字段（``None`` 表示不适用）。

    Args:
        value: 布尔值或 ``None``。

    Returns:
        ``"✅"`` / ``"❌"`` / ``"—"``。
    """
    if value is None:
        return "—"
    return "✅" if value else "❌"


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    """把二维数据渲染为 Markdown 表格行（纯字符串拼接，无 tabulate 依赖）。

    Args:
        headers: 表头文本。
        rows: 数据行。

    Returns:
        Markdown 表格文本行列表。
    """
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join([":---"] + [":---:"] * (len(headers) - 1)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def render_report(summary: Mapping[str, Any]) -> str:
    """把评测汇总渲染为 Markdown 文本。

    Args:
        summary: :func:`run_benchmark` 的返回值（亦可手工构造同构字典）。

    Returns:
        完整 Markdown 文本，含总体指标表与逐任务明细表。
    """
    num_records = int(summary.get("num_records", 0) or 0)
    completed_runs = int(summary.get("completed_runs", 0) or 0)
    num_tasks = int(summary.get("num_tasks", summary.get("num_runs", 0)) or 0)
    error_runs = int(summary.get("error_runs", 0) or 0)
    recovered_runs = int(summary.get("recovered_runs", 0) or 0)
    matched_runs = int(summary.get("efficiency_matched_runs", 0) or 0)
    total_conclusions = int(summary.get("performance_conclusions", 0) or 0)
    provenanced = int(summary.get("provenanced_conclusions", 0) or 0)

    lines: list[str] = ["# Agent 轨迹评测报告", ""]
    lines.append(f"- 轨迹目录：`{summary.get('traces_dir', '—')}`")
    lines.append(f"- 任务数：{num_tasks}")
    lines.append(f"- 轨迹记录数：{num_records}")
    lines.append("")
    lines.append("## 总体指标")
    lines.append("")
    metric_rows = [
        ["任务完成率", _format_percent(summary.get("task_completion_rate")), f"完成 {completed_runs}/{num_tasks}"],
        [
            "故障自愈率",
            _format_percent(summary.get("error_recovery_rate")),
            f"自愈 {recovered_runs}/{error_runs} 个报错任务",
        ],
        [
            "步骤效率（实际/基准）",
            _format_ratio(summary.get("step_efficiency")),
            f"可对照 {matched_runs} 个任务，均值 实际 {_format_ratio(summary.get('mean_actual_steps'))} / 基准 {_format_ratio(summary.get('mean_baseline_steps'))}",
        ],
        [
            "证据链合规率",
            _format_percent(summary.get("evidence_provenance_ratio")),
            f"合规 {provenanced}/{total_conclusions} 条性能结论",
        ],
    ]
    lines.extend(_markdown_table(["指标", "值", "明细"], metric_rows))
    lines.append("")

    per_task = summary.get("per_task") or []
    lines.append("## 逐任务明细")
    lines.append("")
    if per_task:
        task_rows = [
            [
                item.get("task_id", "—"),
                int(item.get("num_records", 0) or 0),
                _format_bool(item.get("completed")),
                _format_bool(item.get("error_recovery")),
                _format_ratio(item.get("steps"), digits=0),
                _format_bool(item.get("has_artifact")),
            ]
            for item in per_task
        ]
        lines.extend(
            _markdown_table(
                ["任务 ID", "记录数", "完成", "错误自愈", "实际步数", "有产物"],
                task_rows,
            )
        )
    else:
        lines.append("（无轨迹文件）")
    lines.append("")
    lines.append("> 指标口径：完成率以 final 记录的终止语义判定；自愈率分母为曾出现")
    lines.append("> `consecutive_errors >= 1` 的任务；步骤效率为实际步数 / 基准最优步数；")
    lines.append("> 证据链合规率统计性能类结论中携带 `artifact_path` 或 `artifact://`/`rag://` 的占比。")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：解析轨迹 → 汇总指标 → 渲染（可选写出报告）。

    Args:
        argv: 命令行参数（不含程序名）；``None`` 时取 ``sys.argv[1:]``。

    Returns:
        进程退出码，成功为 ``0``。
    """
    parser = argparse.ArgumentParser(
        prog="agent_bench",
        description="Agent 轨迹离线评测：完成率 / 故障自愈率 / 步骤效率 / 证据链合规率",
    )
    parser.add_argument(
        "--traces",
        default=str(DEFAULT_TRACES_DIR),
        help=f"轨迹目录（默认 {DEFAULT_TRACES_DIR}）",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help="基准最优步数 JSON 文件，内容为 {task_id: steps}",
    )
    parser.add_argument("--out", default=None, help="Markdown 报告输出路径；缺省仅打印到 stdout")
    args = parser.parse_args(argv)

    baseline: dict[str, int] | None = None
    if args.baseline:
        baseline_path = Path(args.baseline)
        if not baseline_path.is_file():
            raise FileNotFoundError(f"基准文件不存在：{baseline_path}")
        payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"基准文件 {baseline_path} 顶层必须是对象：{{task_id: steps}}")
        baseline = {str(key): int(value) for key, value in payload.items()}

    summary = run_benchmark(args.traces, baseline)
    text = render_report(summary)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"[agent_bench] 报告已写入 {out_path}")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
