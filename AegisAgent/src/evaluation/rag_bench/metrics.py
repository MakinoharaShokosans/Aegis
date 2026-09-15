"""HitRate@K / MRR@K / NDCG@K（numpy 离线计算）。

规范：documents/技术选型/evaluation.md 第 2.1 节

设计要点：

1. 全部为**纯函数**：无 I/O、无全局可变状态、不触发任何 LLM 调用，
   数百个用例可在毫秒级内以 100% 确定性完成（有别于 LLM-as-a-judge）；
2. **二值相关性**假设：文档 ID 命中 ``gold_ids`` 记为相关（增益 = 1），否则为 0；
3. **边界安全**：金标为空、检索结果为空、``k <= 0`` 一律返回 ``0.0``，不抛异常，
   便于消融实验中某一路召回完全缺失时仍能出表。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

__all__ = [
    "aggregate",
    "hit_rate_at_k",
    "ndcg_at_k",
    "reciprocal_rank_at_k",
]


def _top_k_list(ranked_ids: Sequence[str], k: int) -> list[str]:
    """截取检索结果的前 ``k`` 项。

    Args:
        ranked_ids: 检索服务返回的有序文档 ID 序列。
        k: 截断深度。

    Returns:
        前 ``k`` 项组成的列表；``k <= 0`` 时返回空列表，序列不足 ``k`` 项时返回全部。
    """
    if k <= 0:
        return []
    return list(ranked_ids)[:k]


def _relevance_mask(ranked_ids: Sequence[str], gold_ids: Sequence[str], k: int) -> np.ndarray:
    """构造 top-k 的二值相关性掩码。

    所有 ID 均按字符串比较，因此传入 int 型 chunk id 也不会误判。

    Args:
        ranked_ids: 有序检索结果 ID。
        gold_ids: 金标（标准答案）ID 集合。
        k: 截断深度。

    Returns:
        一维 ``bool`` 数组，长度为 ``min(len(ranked_ids), max(k, 0))``；
        金标为空或 ``k <= 0`` 时返回长度为 0 的空数组。
    """
    if k <= 0:
        return np.zeros(0, dtype=bool)
    gold = {str(g) for g in gold_ids}
    if not gold:
        return np.zeros(0, dtype=bool)
    top = _top_k_list(ranked_ids, k)
    return np.fromiter((str(doc_id) in gold for doc_id in top), dtype=bool, count=len(top))


def hit_rate_at_k(ranked_ids: Sequence[str], gold_ids: Sequence[str], k: int) -> float:
    """计算单个查询的 HitRate@K（top-k 内是否至少命中一条金标）。

    Args:
        ranked_ids: 检索服务返回的有序文档 ID。
        gold_ids: 金标文档 ID 集合。
        k: 截断深度。

    Returns:
        命中返回 ``1.0``，否则返回 ``0.0``；金标为空、检索结果为空或 ``k <= 0``
        时安全返回 ``0.0``。
    """
    mask = _relevance_mask(ranked_ids, gold_ids, k)
    return float(mask.any())


def reciprocal_rank_at_k(ranked_ids: Sequence[str], gold_ids: Sequence[str], k: int) -> float:
    """计算单个查询的 MRR@K（第一个命中位置的倒数排名）。

    Args:
        ranked_ids: 检索服务返回的有序文档 ID。
        gold_ids: 金标文档 ID 集合。
        k: 截断深度。

    Returns:
        命中时返回 ``1 / rank``（rank 从 1 开始）；未命中、金标为空、
        检索结果为空或 ``k <= 0`` 时返回 ``0.0``。
    """
    mask = _relevance_mask(ranked_ids, gold_ids, k)
    hit_positions = np.flatnonzero(mask)
    if hit_positions.size == 0:
        return 0.0
    return float(1.0 / (int(hit_positions[0]) + 1))


def ndcg_at_k(ranked_ids: Sequence[str], gold_ids: Sequence[str], k: int) -> float:
    """计算单个查询的 NDCG@K（二值相关性 + log2 折损）。

    公式（位置从 1 开始）：

    .. math::

        \\mathrm{DCG@k} = \\sum_{i=1}^{k} \\frac{rel_i}{\\log_2(i + 1)},
        \\qquad
        \\mathrm{NDCG@k} = \\frac{\\mathrm{DCG@k}}{\\mathrm{IDCG@k}}

    IDCG 为理想排序（全部金标排在最前）的 DCG，其有效长度取
    ``min(len(gold_ids), k)``，因此**完美排序恒等于 1.0**。

    Args:
        ranked_ids: 检索服务返回的有序文档 ID。
        gold_ids: 金标文档 ID 集合。
        k: 截断深度。

    Returns:
        ``[0.0, 1.0]`` 区间的增益比值；金标为空、检索结果为空或 ``k <= 0``
        时安全返回 ``0.0``。
    """
    mask = _relevance_mask(ranked_ids, gold_ids, k)
    if mask.size == 0:
        return 0.0
    positions = np.arange(1, mask.size + 1, dtype=np.float64)
    discounts = 1.0 / np.log2(positions + 1.0)
    dcg = float(np.sum(mask.astype(np.float64) * discounts))

    n_ideal = min(len({str(g) for g in gold_ids}), k)
    if n_ideal <= 0:
        return 0.0
    ideal_positions = np.arange(1, n_ideal + 1, dtype=np.float64)
    idcg = float(np.sum(1.0 / np.log2(ideal_positions + 1.0)))
    if idcg <= 0.0:
        return 0.0
    return dcg / idcg


#: 指标名 → 单查询计算函数的固定映射，供 :func:`aggregate` 统一调度。
_METRIC_FUNCS: tuple[tuple[str, Callable[[Sequence[str], Sequence[str], int], float]], ...] = (
    ("hit_rate", hit_rate_at_k),
    ("mrr", reciprocal_rank_at_k),
    ("ndcg", ndcg_at_k),
)


def _safe_mean(values: Sequence[float]) -> float:
    """对一组标量求均值，空序列返回 ``0.0``。

    Args:
        values: 待求均值的标量序列。

    Returns:
        算术平均值；``values`` 为空时返回 ``0.0``。
    """
    if not values:
        return 0.0
    return float(np.mean(np.asarray(values, dtype=np.float64)))


def _coerce_float(value: Any) -> float:
    """将外部传入的预计算指标值安全转为 ``float``。

    Args:
        value: 任意标量（``None`` / 数字 / 数字字符串）。

    Returns:
        可转换时返回其浮点值，否则返回 ``0.0``。
    """
    if isinstance(value, bool) or value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def aggregate(per_query: list[dict[str, Any]], k_values: Sequence[int]) -> dict[str, Any]:
    """汇总逐查询结果，输出各 K 值下的均值指标。

    每条 ``per_query`` 记录支持两种形态：

    1. ``{"case_id": str, "ranked_ids": [...], "gold_ids": [...]}``
       —— 由本函数重新计算全部指标（推荐形态）；
    2. 仅携带预计算标量 ``{"hit_rate@5": 1.0, "mrr@5": 0.5, "ndcg@5": 0.7}``
       —— 直接取用已有数值，缺失字段按 ``0.0`` 计入。

    Args:
        per_query: 逐查询记录列表。
        k_values: 需要汇总的 K 值（截断深度）列表。

    Returns:
        形如 ``{"num_queries": int, "k_values": [int], "hit_rate": {k: float},
        "mrr": {k: float}, "ndcg": {k: float}}`` 的汇总字典；
        ``per_query`` 为空时所有均值为 ``0.0``。

    Raises:
        TypeError: ``per_query`` 中存在非 ``dict`` 元素。
    """
    ks = [int(k) for k in k_values]
    buckets: dict[str, dict[int, list[float]]] = {
        name: {k: [] for k in ks} for name, _ in _METRIC_FUNCS
    }

    for index, row in enumerate(per_query):
        if not isinstance(row, dict):
            raise TypeError(f"per_query[{index}] 必须是 dict，实际为 {type(row).__name__}")
        ranked_ids = row.get("ranked_ids")
        gold_ids = row.get("gold_ids")
        recompute = (
            isinstance(ranked_ids, Sequence)
            and isinstance(gold_ids, Sequence)
            and not isinstance(ranked_ids, (str, bytes))
            and not isinstance(gold_ids, (str, bytes))
        )
        for k in ks:
            for name, func in _METRIC_FUNCS:
                if recompute:
                    value = func(ranked_ids, gold_ids, k)  # type: ignore[arg-type]
                else:
                    value = _coerce_float(row.get(f"{name}@{k}"))
                buckets[name][k].append(value)

    summary: dict[str, Any] = {"num_queries": len(per_query), "k_values": ks}
    for name, per_k in buckets.items():
        summary[name] = {k: _safe_mean(values) for k, values in per_k.items()}
    return summary
