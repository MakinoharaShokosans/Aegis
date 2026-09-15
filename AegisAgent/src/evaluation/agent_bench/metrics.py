"""Completion / ErrorRecovery / StepEfficiency / EvidenceProvenance。

规范：documents/技术选型/evaluation.md 第 2.2 节

输入是**已解析的 JSONL 记录列表**（``list[dict]``），本模块不 import 任何
运行期类，因此与 ``agent_runtime`` 完全解耦。

单条记录字段约定::

    {"task_id", "seq", "ts", "type", "node", "phase", "thought", "tool_name",
     "tool_args", "observation_summary", "artifact_path", "ok", "step_count",
     "total_tokens", "consecutive_errors"}

其中 ``type ∈ {"node", "tool", "guard", "final"}``；一条 run 即某任务的完整记录序列。
字段可能因版本演进缺失，本模块一律**容错读取**：缺失字段不抛异常，而是回退到
次优判据或视为"不适用"（详见各函数 docstring）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from statistics import fmean
from typing import Any

__all__ = [
    "error_recovery_rate",
    "evidence_provenance_ratio",
    "run_completed",
    "run_error_recovery",
    "run_step_count",
    "step_efficiency",
    "summarize",
    "task_completion_rate",
]

#: 终止原因中表示"已达成目标"的取值。
SUCCESS_TERMINATION_REASONS: frozenset[str] = frozenset(
    {
        "completed",
        "complete",
        "success",
        "succeeded",
        "successful",
        "done",
        "finished",
        "goal_achieved",
        "task_completed",
        "resolved",
    }
)

#: 终止原因 / 状态中表示"明确失败"的取值。
FAILURE_TERMINATION_REASONS: frozenset[str] = frozenset(
    {
        "failed",
        "failure",
        "error",
        "timeout",
        "timed_out",
        "cancelled",
        "canceled",
        "aborted",
        "budget_exhausted",
        "max_steps",
        "rejected",
    }
)

#: 兜底字段 ``status`` 中表示成功的取值。
SUCCESS_STATUSES: frozenset[str] = frozenset(
    {"completed", "complete", "success", "succeeded", "done", "finished"}
)

#: 性能类结论关键词（含中英文指标名与"数值 + 单位"模式）。
_PERFORMANCE_RE = re.compile(
    r"(?:\b(?:latency|throughput|bandwidth|speedup|qps|fps|p50|p95|p99)\b"
    r"|\d+(?:\.\d+)?\s*(?:ns|us|µs|ms|gb/s|mb/s|kb/s|ops/s)\b"
    r"|延迟|吞吐|带宽|加速比|性能|耗时|基准|纳秒|微秒|毫秒)",
    re.IGNORECASE,
)

#: 证据句柄模式（``artifact://`` 与 ``rag://``）。
_PROVENANCE_RE = re.compile(r"(?:artifact|rag)://", re.IGNORECASE)


def _normalize(value: Any) -> str:
    """把字段值规整为小写下划线的比较令牌。

    Args:
        value: 任意字段值。

    Returns:
        规整后的字符串；``None`` 返回空串。
    """
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _as_int(value: Any) -> int | None:
    """把字段值安全转为 ``int``。

    Args:
        value: 任意字段值。

    Returns:
        可转换时返回整数，否则返回 ``None``（不抛异常）。
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    """把字段值安全转为 ``bool``。

    Args:
        value: 任意字段值（``bool`` / ``"true"`` / ``"no"`` / ``1`` 等）。

    Returns:
        可判定时返回布尔值，否则返回 ``None``。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    token = _normalize(value)
    if token in {"true", "yes", "1", "y"}:
        return True
    if token in {"false", "no", "0", "n"}:
        return False
    return None


def _final_record_completed(record: Mapping[str, Any]) -> bool:
    """判定一条 ``type == "final"`` 记录是否表示任务达成。

    判据优先级：

    1. 显式 ``completed`` 布尔字段；
    2. ``termination_reason`` 是否落在成功/失败集合；
    3. 兜底字段 ``status`` / ``state``；
    4. 最后的退路 ``should_terminate`` 为真。

    Args:
        record: final 类型轨迹记录。

    Returns:
        判定为达成时返回 ``True``，否则 ``False``。
    """
    explicit = _as_bool(record.get("completed"))
    if explicit is not None:
        return explicit

    reason = _normalize(record.get("termination_reason"))
    if reason:
        if reason in SUCCESS_TERMINATION_REASONS:
            return True
        if reason in FAILURE_TERMINATION_REASONS:
            return False

    status = _normalize(record.get("status") or record.get("state"))
    if status:
        if status in SUCCESS_STATUSES:
            return True
        if status in FAILURE_TERMINATION_REASONS:
            return False

    return _as_bool(record.get("should_terminate")) is True


def run_completed(run: Sequence[Mapping[str, Any]]) -> bool:
    """判断单条 run 是否达成任务目标。

    Args:
        run: 单个任务的轨迹记录序列。

    Returns:
        存在 ``type == "final"`` 记录且其终止语义表示成功时返回 ``True``；
        完全没有 final 记录（任务被中断/崩溃）时返回 ``False``。
    """
    finals = [record for record in run if _normalize(record.get("type")) == "final"]
    if not finals:
        return False
    return _final_record_completed(finals[-1])


def run_step_count(run: Sequence[Mapping[str, Any]]) -> int | None:
    """提取单条 run 的实际执行步数。

    优先取记录中 ``step_count`` 的最大值（运行期计数器单调递增）；
    缺失时退化为 ``type == "tool"`` 的记录数；再缺失则退化为记录总条数。

    Args:
        run: 单个任务的轨迹记录序列。

    Returns:
        实际步数；空 run 返回 ``None``。
    """
    counters = [
        count for count in (_as_int(record.get("step_count")) for record in run) if count is not None
    ]
    if counters:
        return max(counters)
    tool_steps = sum(1 for record in run if _normalize(record.get("type")) == "tool")
    if tool_steps:
        return tool_steps
    return len(run) if run else None


def run_error_recovery(run: Sequence[Mapping[str, Any]]) -> bool | None:
    """判断单条 run 是否完成了故障自愈。

    自愈定义：``consecutive_errors`` 先出现 ``>= 1``，其后又回落（记录到 ``0``）。
    一旦自愈过即记为成功，即使后续再次报错。

    Args:
        run: 单个任务的轨迹记录序列。

    Returns:
        ``True`` 表示经历错误后成功恢复，``False`` 表示最终未能恢复，
        ``None`` 表示该 run 从未触发错误（不适用，不计入分母）。
    """
    sequence = [
        count
        for count in (_as_int(record.get("consecutive_errors")) for record in run)
        if count is not None
    ]
    if not any(count >= 1 for count in sequence):
        return None
    first_error = next(index for index, count in enumerate(sequence) if count >= 1)
    return any(count == 0 for count in sequence[first_error + 1 :])


def _recovery_counts(runs: Sequence[Sequence[Mapping[str, Any]]]) -> tuple[int, int]:
    """统计经历错误的 run 数与其中成功自愈的 run 数。

    Args:
        runs: 全部 run。

    Returns:
        ``(error_runs, recovered_runs)`` 二元组。
    """
    outcomes = [run_error_recovery(run) for run in runs]
    experienced = [outcome for outcome in outcomes if outcome is not None]
    return len(experienced), sum(1 for outcome in experienced if outcome)


def _run_task_id(run: Sequence[Mapping[str, Any]]) -> str | None:
    """从 run 中提取任务 ID。

    Args:
        run: 单个任务的轨迹记录序列。

    Returns:
        首个非空的 ``task_id``；缺失时返回 ``None``。
    """
    for record in run:
        task_id = record.get("task_id")
        if isinstance(task_id, str) and task_id.strip():
            return task_id
    return None


def _conclusion_records(run: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """抽取 run 中的"结论"记录，用于证据链合规率。

    取该 run 全部 ``type == "final"`` 记录；若一条都没有（任务中断），
    退化为该 run 的最后一条记录。

    Args:
        run: 单个任务的轨迹记录序列。

    Returns:
        结论记录列表；空 run 返回空列表。
    """
    finals = [record for record in run if _normalize(record.get("type")) == "final"]
    if finals:
        return finals
    return [run[-1]] if run else []


def _record_text(record: Mapping[str, Any]) -> str:
    """拼接记录中的自由文本字段。

    Args:
        record: 轨迹记录。

    Returns:
        以换行拼接的文本（仅保留字符串字段）。
    """
    parts = [
        record.get("thought"),
        record.get("observation_summary"),
        record.get("conclusion"),
        record.get("content"),
    ]
    return "\n".join(part for part in parts if isinstance(part, str))


def _is_performance_claim(text: str) -> bool:
    """判断文本是否包含性能类结论。

    Args:
        text: 待判定文本。

    Returns:
        命中性能关键词或"数值 + 单位"模式时返回 ``True``。
    """
    return bool(text) and _PERFORMANCE_RE.search(text) is not None


def _has_provenance(record: Mapping[str, Any], text: str) -> bool:
    """判断结论是否携带可溯源的证据句柄。

    Args:
        record: 结论记录。
        text: 该记录的自由文本。

    Returns:
        ``artifact_path`` 非空，或文本中出现 ``artifact://`` / ``rag://`` 时返回 ``True``。
    """
    artifact_path = record.get("artifact_path")
    if isinstance(artifact_path, str) and artifact_path.strip():
        return True
    return _PROVENANCE_RE.search(text) is not None


def _provenance_counts(runs: Sequence[Sequence[Mapping[str, Any]]]) -> tuple[int, int]:
    """统计性能类结论总数与其中带证据句柄的数量。

    Args:
        runs: 全部 run。

    Returns:
        ``(performance_conclusions, provenanced_conclusions)`` 二元组。
    """
    total = 0
    provenanced = 0
    for run in runs:
        for record in _conclusion_records(run):
            text = _record_text(record)
            if not _is_performance_claim(text):
                continue
            total += 1
            if _has_provenance(record, text):
                provenanced += 1
    return total, provenanced


def task_completion_rate(runs: list[list[dict[str, Any]]]) -> float:
    """计算任务完成率。

    完成判据见 :func:`run_completed`（以 ``type == "final"`` 记录的
    ``termination_reason`` 为准，缺失时按 ``status`` / ``should_terminate`` 兜底）。

    Args:
        runs: 全部 run（每个 run 是该任务的记录列表）。

    Returns:
        完成率 ``completed / total``；``runs`` 为空时返回 ``0.0``。
    """
    if not runs:
        return 0.0
    completed = sum(1 for run in runs if run_completed(run))
    return completed / len(runs)


def error_recovery_rate(runs: list[list[dict[str, Any]]]) -> float:
    """计算故障自愈率（核心指标）。

    分母是**经历过错误**的 run（``consecutive_errors`` 曾 ``>= 1``），
    分子是其中错误计数回落（记录到 ``0``）的 run。从未报错的 run 视为"不适用"，
    不计入分母；若全部 run 都未报错，返回 ``1.0``（无故障即无自愈失败）。

    Args:
        runs: 全部 run。

    Returns:
        自愈率 ``recovered / error_runs``；无错误 run 时返回 ``1.0``。
    """
    error_runs, recovered_runs = _recovery_counts(runs)
    if error_runs == 0:
        return 1.0
    return recovered_runs / error_runs


def step_efficiency(
    runs: list[list[dict[str, Any]]],
    baseline_steps: dict[str, int],
) -> float:
    """计算步骤效率（实际步数 / 基准最优步数）。

    只统计 ``task_id`` 同时出现在 ``baseline_steps`` 且步数可解析的 run，
    逐 run 计算比值后取算术平均。比值 ``1.0`` 表示与基准持平，越大越低效
    （对应 ADR 中"严防注意力漂移与无意义试错"的度量方向）。

    Args:
        runs: 全部 run。
        baseline_steps: ``{task_id: 基准最优步数}`` 映射。

    Returns:
        平均步骤比值；无任何可对照 run 时返回 ``0.0``。
    """
    if not baseline_steps:
        return 0.0
    ratios: list[float] = []
    for run in runs:
        task_id = _run_task_id(run)
        if task_id is None or task_id not in baseline_steps:
            continue
        baseline = _as_int(baseline_steps.get(task_id))
        actual = run_step_count(run)
        if baseline is None or baseline <= 0 or actual is None:
            continue
        ratios.append(actual / baseline)
    if not ratios:
        return 0.0
    return float(fmean(ratios))


def evidence_provenance_ratio(runs: list[list[dict[str, Any]]]) -> float:
    """计算证据链合规率（性能类结论中带证据句柄的占比）。

    结论取每个 run 的 ``type == "final"`` 记录（无 final 时退化取最后一条），
    文本命中性能关键词/数值单位模式即视为"性能类结论"；携带非空
    ``artifact_path`` 或文本含 ``artifact://`` / ``rag://`` 即视为合规。

    Args:
        runs: 全部 run。

    Returns:
        合规占比；完全没有性能类结论时返回 ``1.0``（无结论即无幻觉风险）。
    """
    total, provenanced = _provenance_counts(runs)
    if total == 0:
        return 1.0
    return provenanced / total


def summarize(
    runs: list[list[dict[str, Any]]],
    baseline_steps: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """汇总全部轨迹指标，附带分母计数便于报告交叉核对。

    Args:
        runs: 全部 run。
        baseline_steps: ``{task_id: 基准最优步数}`` 映射；``None`` 时步骤效率为 ``0.0``。

    Returns:
        扁平指标字典，键包括 ``num_runs`` / ``num_records`` /
        ``task_completion_rate`` / ``error_recovery_rate`` / ``step_efficiency`` /
        ``evidence_provenance_ratio`` 及对应的分子分母计数。
    """
    baseline = dict(baseline_steps or {})
    num_runs = len(runs)
    num_records = sum(len(run) for run in runs)

    completed_runs = sum(1 for run in runs if run_completed(run))
    error_runs, recovered_runs = _recovery_counts(runs)
    total_conclusions, provenanced = _provenance_counts(runs)

    ratios: list[float] = []
    actual_steps: list[int] = []
    baseline_values: list[int] = []
    for run in runs:
        task_id = _run_task_id(run)
        if task_id is None or task_id not in baseline:
            continue
        base = _as_int(baseline.get(task_id))
        actual = run_step_count(run)
        if base is None or base <= 0 or actual is None:
            continue
        ratios.append(actual / base)
        actual_steps.append(actual)
        baseline_values.append(base)

    return {
        "num_runs": num_runs,
        "num_records": num_records,
        "completed_runs": completed_runs,
        "task_completion_rate": (completed_runs / num_runs) if num_runs else 0.0,
        "error_runs": error_runs,
        "recovered_runs": recovered_runs,
        "error_recovery_rate": (recovered_runs / error_runs) if error_runs else 1.0,
        "efficiency_matched_runs": len(ratios),
        "step_efficiency": float(fmean(ratios)) if ratios else 0.0,
        "mean_actual_steps": float(fmean(actual_steps)) if actual_steps else 0.0,
        "mean_baseline_steps": float(fmean(baseline_values)) if baseline_values else 0.0,
        "performance_conclusions": total_conclusions,
        "provenanced_conclusions": provenanced,
        "evidence_provenance_ratio": (provenanced / total_conclusions) if total_conclusions else 1.0,
    }
