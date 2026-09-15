"""检索评测驱动脚本（含四组消融实验）。

规范：documents/技术选型/evaluation.md 第 2.1 节

用法::

    cd AegisAgent
    .venv/bin/python -m evaluation.rag_bench.evaluate_retrieval \
        --dataset src/evaluation/rag_bench/datasets/retrieval_eval.jsonl \
        --results src/evaluation/rag_bench/reports/retrieval_results.json \
        --out src/evaluation/rag_bench/reports/benchmark_report.md

契约：

- ``RetrievalResult`` = ``{"case_id": str, "ranked_ids": [str, ...]}``，
  即检索服务返回的**有序**结果；可选 ``group``（别名 ``config``）标注消融分组，
  可选 ``latency_ms`` 记录单次检索耗时；
- ``results`` 可以是 ``{分组名: [结果, ...]}``（推荐，四组消融一次跑完），
  也可以是 ``[结果, ...]``（此时按每条记录的 ``group`` 字段分组）。

报告渲染使用纯字符串拼接，**不依赖 tabulate**，避免引入额外耦合。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from .dataset import DEFAULT_DATASET_DIR, EvalCase, load_dataset
from .metrics import aggregate

__all__ = [
    "ABLATION_GROUPS",
    "ABLATION_LEGEND",
    "DEFAULT_REPORT_PATH",
    "RetrievalResult",
    "evaluate",
    "load_results",
    "main",
    "render_report",
]

#: 本包所在目录（``.../src/evaluation/rag_bench``）。
BENCH_DIR: Path = Path(__file__).resolve().parent

#: 评测报告默认输出路径。
DEFAULT_REPORT_PATH: Path = BENCH_DIR / "reports" / "benchmark_report.md"

#: 四组消融配置名（顺序即报告中的展示顺序）。
ABLATION_GROUPS: tuple[str, ...] = (
    "dense_only",
    "sparse_only",
    "hybrid_rrf",
    "hybrid_rerank",
)

#: 消融配置的中文释义，仅用于报告可读性。
ABLATION_LEGEND: dict[str, str] = {
    "dense_only": "纯语义向量召回（Dense）",
    "sparse_only": "纯 BM25 词法召回（Sparse）",
    "hybrid_rrf": "双路召回 + RRF 倒排融合",
    "hybrid_rerank": "融合结果 + Cross-Encoder 重排精选",
}


class RetrievalResult(BaseModel):
    """单条检索结果契约（检索服务返回的顺序结果）。

    Attributes:
        case_id: 对应用例 ID。
        ranked_ids: 按相关性降序排列的切片 ID 列表。
        group: 消融分组标签（可由 ``config`` 字段提供），缺省为 ``"default"``。
        latency_ms: 该次检索耗时（毫秒），可选，缺失时不计入平均延迟。
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    case_id: str = Field(..., description="对应用例 ID")
    ranked_ids: list[str] = Field(default_factory=list, description="有序切片 ID 列表")
    group: str = Field(
        default="default",
        validation_alias=AliasChoices("group", "config"),
        description="消融分组标签",
    )
    latency_ms: float | None = Field(default=None, description="单次检索耗时（毫秒）")


def _coerce_result(item: RetrievalResult | Mapping[str, Any], source: str, index: int) -> RetrievalResult:
    """将原始记录规整为 :class:`RetrievalResult`。

    Args:
        item: 已构造的模型实例或原始字典。
        source: 来源描述，仅用于错误信息。
        index: 记录下标，仅用于错误信息。

    Returns:
        校验通过的检索结果对象。

    Raises:
        TypeError: 元素既不是模型也不是映射时抛出。
        pydantic.ValidationError: 字段缺失或类型非法时向上抛出。
    """
    if isinstance(item, RetrievalResult):
        return item
    if isinstance(item, Mapping):
        return RetrievalResult.model_validate(dict(item))
    raise TypeError(f"{source} 第 {index} 条结果必须是 dict 或 RetrievalResult，实际为 {type(item).__name__}")


def _normalize_results(
    results: (
        Mapping[str, Sequence[RetrievalResult | Mapping[str, Any]]]
        | Sequence[RetrievalResult | Mapping[str, Any]]
    ),
) -> dict[str, list[RetrievalResult]]:
    """把两种入参形态统一为 ``{分组名: [RetrievalResult, ...]}``。

    Args:
        results: 分组映射形态或扁平序列形态的检索结果。

    Returns:
        分组后的检索结果字典。

    Raises:
        TypeError: 入参类型或元素类型非法。
    """
    grouped: dict[str, list[RetrievalResult]] = {}
    if isinstance(results, Mapping):
        for name, items in results.items():
            key = str(name)
            if isinstance(items, (RetrievalResult, Mapping)):
                normalized = [_coerce_result(items, key, 0)]
            elif isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
                normalized = [
                    _coerce_result(item, key, index) for index, item in enumerate(items)
                ]
            else:
                raise TypeError(f"分组 {key} 的值必须是结果序列，实际为 {type(items).__name__}")
            grouped.setdefault(key, []).extend(normalized)
        return grouped

    if isinstance(results, Sequence) and not isinstance(results, (str, bytes)):
        for index, item in enumerate(results):
            result = _coerce_result(item, "results", index)
            grouped.setdefault(result.group, []).append(result)
        return grouped

    raise TypeError(f"results 必须是映射或序列，实际为 {type(results).__name__}")


def load_results(
    path: str | Path,
) -> dict[str, list[RetrievalResult]]:
    """加载检索结果文件（自动识别 JSON / JSONL）。

    支持的 JSON 结构：

    - ``{"groups": {分组名: [结果, ...]}}``；
    - ``{分组名: [结果, ...]}``；
    - ``[结果, ...]``（按每条记录的 ``group`` / ``config`` 分组）；
    - 单个结果对象。

    JSONL 每行一个结果对象，分组取该行的 ``group`` / ``config`` 字段。

    Args:
        path: 结果文件路径。

    Returns:
        ``{分组名: [RetrievalResult, ...]}``。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 文件结构非法或存在非法 JSON 行。
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"检索结果文件不存在：{source}")
    text = source.read_text(encoding="utf-8")

    if source.suffix.lower() in {".jsonl", ".ndjson"}:
        items: list[dict[str, Any]] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"检索结果 {source} 第 {lineno} 行不是合法 JSON：{exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"检索结果 {source} 第 {lineno} 行必须是 JSON 对象")
            items.append(obj)
        return _normalize_results(items)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"检索结果 {source} 不是合法 JSON：{exc}") from exc

    if isinstance(payload, dict) and isinstance(payload.get("groups"), Mapping):
        return _normalize_results(payload["groups"])
    if isinstance(payload, (list, dict)):
        return _normalize_results(payload)
    raise ValueError(f"检索结果 {source} 顶层必须是数组或对象，实际为 {type(payload).__name__}")


def evaluate(
    results: (
        Mapping[str, Sequence[RetrievalResult | Mapping[str, Any]]]
        | Sequence[RetrievalResult | Mapping[str, Any]]
    ),
    cases: Sequence[EvalCase],
    k_values: Sequence[int],
) -> dict[str, Any]:
    """对四组消融配置分别汇总检索指标。

    只有同时出现在 ``cases`` 与 ``results`` 中的 ``case_id`` 参与计算；
    缺失/多余的 case 会被记录在报告里，便于发现数据集与结果不同步。

    Args:
        results: 检索结果（分组映射或扁平序列，见 :func:`_normalize_results`）。
        cases: 标注用例列表（提供金标 ``gold_chunk_ids``）。
        k_values: 需要统计的 K 值列表。

    Returns:
        形如 ``{"num_cases": int, "num_results": int, "k_values": [int],
        "groups": {分组名: 汇总字典}, "missing_case_ids": [...],
        "unknown_case_ids": [...]}`` 的报告字典。四组消融始终占据
        ``groups`` 的前四个键，未提供数据的组 ``num_queries == 0``。

    Raises:
        TypeError: ``results`` 结构非法。
        pydantic.ValidationError: 结果记录字段非法。
    """
    grouped = _normalize_results(results)
    cases_by_id: dict[str, EvalCase] = {case.case_id: case for case in cases}
    ks = [int(k) for k in k_values]

    order: list[str] = list(ABLATION_GROUPS)
    order.extend(name for name in grouped if name not in order)

    observed_ids: set[str] = set()
    group_reports: dict[str, dict[str, Any]] = {}
    for name in order:
        items = grouped.get(name, [])
        rows: list[dict[str, Any]] = []
        latencies: list[float] = []
        for result in items:
            observed_ids.add(result.case_id)
            if result.latency_ms is not None:
                latencies.append(float(result.latency_ms))
            case = cases_by_id.get(result.case_id)
            if case is None:
                continue
            rows.append(
                {
                    "case_id": result.case_id,
                    "ranked_ids": list(result.ranked_ids),
                    "gold_ids": list(case.gold_chunk_ids),
                }
            )
        entry = aggregate(rows, ks)
        entry["group"] = name
        entry["num_results"] = len(items)
        entry["avg_latency_ms"] = statistics.fmean(latencies) if latencies else None
        group_reports[name] = entry

    missing_case_ids = [case.case_id for case in cases if case.case_id not in observed_ids]
    unknown_case_ids = sorted(observed_ids - set(cases_by_id))
    return {
        "num_cases": len(cases),
        "num_results": sum(len(items) for items in grouped.values()),
        "k_values": ks,
        "groups": group_reports,
        "missing_case_ids": missing_case_ids,
        "unknown_case_ids": unknown_case_ids,
    }


def _metric_value(entry: Mapping[str, Any], metric: str, k: int) -> float:
    """读取某分组的单个指标值（兼容 int / str 两种 K 键）。

    Args:
        entry: 分组汇总字典。
        metric: 指标名（``hit_rate`` / ``mrr`` / ``ndcg``）。
        k: 截断深度。

    Returns:
        指标值；缺失时返回 ``0.0``。
    """
    table = entry.get(metric)
    if not isinstance(table, Mapping):
        return 0.0
    if k in table:
        return float(table[k])
    value = table.get(str(k), 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_metric(value: float, best: float | None) -> str:
    """格式化指标单元格，并列最优加粗。

    Args:
        value: 指标值。
        best: 该列最优值；``None`` 表示无有效对照。

    Returns:
        Markdown 单元格文本。
    """
    text = f"{value:.4f}"
    if best is not None and value >= best - 1e-12:
        return f"**{text}**"
    return text


def _format_latency(value: float | None, best: float | None) -> str:
    """格式化延迟单元格（越小越优），并列最优加粗。

    Args:
        value: 平均延迟（毫秒），``None`` 表示无数据。
        best: 该列最小延迟；``None`` 表示无有效对照。

    Returns:
        Markdown 单元格文本。
    """
    if value is None:
        return "—"
    text = f"{value:.2f}"
    if best is not None and value <= best + 1e-12:
        return f"**{text}**"
    return text


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    """把二维数据渲染为 Markdown 表格行。

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


def _preview_ids(ids: Sequence[str], limit: int = 5) -> str:
    """生成 ID 列表的简短预览。

    Args:
        ids: ID 序列。
        limit: 最多展示的条数。

    Returns:
        形如 ``"（a, b, …）"`` 的预览串；``ids`` 为空时返回空串。
    """
    if not ids:
        return ""
    shown = ", ".join(ids[:limit])
    suffix = "…" if len(ids) > limit else ""
    return f"（{shown}{suffix}）"


def render_report(report: Mapping[str, Any]) -> str:
    """把评测报告渲染为 Markdown 文本（纯字符串拼接，零额外依赖）。

    Args:
        report: :func:`evaluate` 的返回值。

    Returns:
        完整 Markdown 文本，可直接写入
        ``src/evaluation/rag_bench/reports/benchmark_report.md``。
    """
    k_values = [int(k) for k in report.get("k_values", [])]
    groups = report.get("groups")
    group_map: Mapping[str, Mapping[str, Any]] = groups if isinstance(groups, Mapping) else {}

    order = [name for name in ABLATION_GROUPS if name in group_map]
    order.extend(name for name in group_map if name not in order)

    lines: list[str] = ["# RAG 检索评测报告", ""]
    lines.append(f"- 用例总数：{int(report.get('num_cases', 0) or 0)}")
    lines.append(f"- 结果条数：{int(report.get('num_results', 0) or 0)}")
    lines.append(f"- K 值：{'/'.join(str(k) for k in k_values) if k_values else '（未指定）'}")
    missing_ids = [str(cid) for cid in (report.get("missing_case_ids") or [])]
    lines.append(f"- 缺失检索结果的用例：{len(missing_ids)}{_preview_ids(missing_ids)}")
    unknown_ids = [str(cid) for cid in (report.get("unknown_case_ids") or [])]
    if unknown_ids:
        lines.append(f"- 无对应用例的检索结果：{len(unknown_ids)}{_preview_ids(unknown_ids)}")
    lines.append("")

    raw_rows: list[dict[str, Any]] = []
    for name in order:
        entry = group_map.get(name) or {}
        cells: list[float] = []
        for k in k_values:
            cells.extend(
                [
                    _metric_value(entry, "hit_rate", k),
                    _metric_value(entry, "mrr", k),
                    _metric_value(entry, "ndcg", k),
                ]
            )
        latency = entry.get("avg_latency_ms")
        raw_rows.append(
            {
                "name": name,
                "num_queries": int(entry.get("num_queries", 0) or 0),
                "cells": cells,
                "latency": float(latency) if isinstance(latency, (int, float)) else None,
            }
        )

    column_bests: list[float | None] = []
    for column in range(len(k_values) * 3):
        candidates = [row["cells"][column] for row in raw_rows if row["num_queries"] > 0]
        column_bests.append(max(candidates) if candidates else None)
    latency_candidates = [
        row["latency"]
        for row in raw_rows
        if row["num_queries"] > 0 and row["latency"] is not None
    ]
    latency_best = min(latency_candidates) if latency_candidates else None

    lines.append("## 四组消融对比")
    lines.append("")
    headers = ["配置"]
    for k in k_values:
        headers.extend([f"HitRate@{k}", f"MRR@{k}", f"NDCG@{k}"])
    headers.append("平均延迟(ms)")

    table_rows: list[list[Any]] = []
    for row in raw_rows:
        label = f"{row['name']} (n={row['num_queries']})"
        if row["num_queries"] <= 0:
            cells = [label] + ["—"] * (len(k_values) * 3) + ["—"]
        else:
            cells = [label]
            cells.extend(
                _format_metric(value, column_bests[column])
                for column, value in enumerate(row["cells"])
            )
            cells.append(_format_latency(row["latency"], latency_best))
        table_rows.append(cells)
    lines.extend(_markdown_table(headers, table_rows))
    lines.append("")

    lines.append("## 消融配置说明")
    lines.append("")
    legend_rows = [
        [name, ABLATION_LEGEND.get(name, "（自定义分组）")]
        for name in order
    ]
    lines.extend(_markdown_table(["配置", "含义"], legend_rows))
    lines.append("")
    lines.append("> 全部指标由 numpy 离线计算，零 LLM 消耗，结果 100% 可复现。")
    lines.append("")
    return "\n".join(lines)


def _parse_k_values(raw: str) -> list[int]:
    """解析逗号分隔的 K 值参数。

    Args:
        raw: 形如 ``"1,3,5,10"`` 的字符串。

    Returns:
        去重并升序排列的正整数 K 值列表。

    Raises:
        ValueError: 不含任何合法正整数时抛出。
    """
    values: list[int] = []
    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            continue
        values.append(int(token))
    values = sorted({value for value in values if value > 0})
    if not values:
        raise ValueError(f"--k 至少需要一个正整数，实际收到：{raw!r}")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：加载数据集与结果 → 汇总 → 渲染并写出报告。

    Args:
        argv: 命令行参数（不含程序名）；``None`` 时取 ``sys.argv[1:]``。

    Returns:
        进程退出码，成功为 ``0``。
    """
    parser = argparse.ArgumentParser(
        prog="evaluate_retrieval",
        description="RAG 检索离线评测：HitRate@K / MRR@K / NDCG@K + 四组消融（零 LLM 消耗）",
    )
    parser.add_argument("--dataset", required=True, help="标注数据集路径（.json / .jsonl）")
    parser.add_argument("--results", required=True, help="检索结果路径（.json / .jsonl）")
    parser.add_argument(
        "--out",
        default=str(DEFAULT_REPORT_PATH),
        help=f"Markdown 报告输出路径（默认 {DEFAULT_REPORT_PATH}）",
    )
    parser.add_argument("--k", default="1,3,5,10", help="逗号分隔的 K 值列表（默认 1,3,5,10）")
    args = parser.parse_args(argv)

    k_values = _parse_k_values(args.k)
    cases = load_dataset(args.dataset)
    grouped = load_results(args.results)
    report = evaluate(grouped, cases, k_values)
    text = render_report(report)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(text)
    print(f"[rag_bench] 报告已写入 {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
