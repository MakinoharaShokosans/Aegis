"""标注数据集加载与切片契约。

规范：documents/技术选型/evaluation.md 第 2.1 节

数据默认目录：``src/evaluation/rag_bench/datasets/``。

支持两种落盘格式：

- ``*.jsonl``：每行一个 ``EvalCase`` 对象（推荐，便于追加与 diff）；
- ``*.json``：顶层数组，或 ``{"cases": [...]}`` / ``{"queries": [...]}`` 包裹。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

__all__ = [
    "DEFAULT_DATASET_DIR",
    "EvalCase",
    "load_dataset",
    "resolve_dataset_path",
    "save_dataset",
]

#: 本包所在目录（``.../src/evaluation/rag_bench``）。
BENCH_DIR: Path = Path(__file__).resolve().parent

#: 标注数据集默认目录。
DEFAULT_DATASET_DIR: Path = BENCH_DIR / "datasets"


class EvalCase(BaseModel):
    """单条检索评测用例（查询 + 金标切片）。

    Attributes:
        case_id: 用例唯一标识，与 ``RetrievalResult.case_id`` 一一对应。
        query: 用户查询原文。
        gold_chunk_ids: 金标切片 ID 列表（相关文档集合）。
        metadata: 附加标注信息（难度、来源、场景标签等），不参与指标计算。
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    case_id: str = Field(..., description="用例唯一标识")
    query: str = Field(..., description="用户查询原文")
    gold_chunk_ids: list[str] = Field(default_factory=list, description="金标切片 ID 列表")
    metadata: dict[str, Any] = Field(default_factory=dict, description="附加标注信息")


def resolve_dataset_path(path: str | Path) -> Path:
    """解析数据集路径：支持绝对/相对路径与默认目录下的裸文件名。

    Args:
        path: 数据集路径，或 ``datasets/`` 目录下的文件名。

    Returns:
        实际存在的数据集文件路径。

    Raises:
        FileNotFoundError: 给定路径与默认目录回退均不存在时抛出。
    """
    candidate = Path(path)
    if candidate.is_file():
        return candidate
    fallback = DEFAULT_DATASET_DIR / candidate.name
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(f"数据集不存在：{candidate}（默认目录回退：{fallback}）")


def _extract_case_dicts(payload: Any, source: Path) -> list[dict[str, Any]]:
    """从已解析的 JSON 载荷中提取用例字典列表。

    Args:
        payload: ``json.loads`` 的结果。
        source: 来源路径，仅用于错误信息。

    Returns:
        用例字典列表。

    Raises:
        ValueError: 载荷结构无法识别时抛出。
    """
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        for key in ("cases", "queries", "data"):
            wrapped = payload.get(key)
            if isinstance(wrapped, list):
                raw_items = wrapped
                break
        else:
            raw_items = [payload]
    else:
        raise ValueError(f"数据集 {source} 顶层必须是数组或对象，实际为 {type(payload).__name__}")

    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise ValueError(
                f"数据集 {source} 第 {index} 条用例必须是对象，实际为 {type(item).__name__}"
            )
    return list(raw_items)


def _parse_jsonl(text: str, source: Path) -> list[dict[str, Any]]:
    """解析 JSONL 文本，空行跳过，非法行抛出带行号的错误。

    Args:
        text: 文件全文。
        source: 来源路径，仅用于错误信息。

    Returns:
        用例字典列表。

    Raises:
        ValueError: 某行不是合法 JSON 对象时抛出。
    """
    items: list[dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"数据集 {source} 第 {lineno} 行不是合法 JSON：{exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"数据集 {source} 第 {lineno} 行必须是 JSON 对象")
        items.append(obj)
    return items


def load_dataset(path: str | Path) -> list[EvalCase]:
    """加载标注数据集（自动识别 JSON / JSONL）。

    Args:
        path: 数据集路径；不存在时会回退到 ``DEFAULT_DATASET_DIR / <文件名>``。

    Returns:
        校验通过的 :class:`EvalCase` 列表（保持文件中的原始顺序）。

    Raises:
        FileNotFoundError: 数据集文件不存在。
        ValueError: 文件结构非法或某条用例字段校验失败。
    """
    source = resolve_dataset_path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() in {".jsonl", ".ndjson"}:
        raw_items = _parse_jsonl(text, source)
    else:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"数据集 {source} 不是合法 JSON：{exc}") from exc
        raw_items = _extract_case_dicts(payload, source)

    cases: list[EvalCase] = []
    for index, item in enumerate(raw_items):
        try:
            cases.append(EvalCase.model_validate(item))
        except ValidationError as exc:  # 附带字段级上下文后重新抛出，不静默吞掉
            raise ValueError(f"数据集 {source} 第 {index} 条用例校验失败：{exc}") from exc
    return cases


def save_dataset(cases: list[EvalCase], path: str | Path) -> Path:
    """将标注用例写盘（``.jsonl`` 逐行写，其它后缀写 JSON 数组）。

    Args:
        cases: 待写出的用例列表。
        path: 目标路径；父目录不存在时自动创建。

    Returns:
        实际写入的文件路径。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() in {".jsonl", ".ndjson"}:
        lines = [json.dumps(case.model_dump(), ensure_ascii=False) for case in cases]
        target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    else:
        payload = [case.model_dump() for case in cases]
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return target
