"""双轨死循环防御（纯函数，零依赖）。

对应 ``documents/agent_runtime/05_guardrails_implementation.md`` §1。

模型在长周期自主排错中会陷入两种不同形态的死胡同，必须分别防御：

* **轨道 A —— 参数指纹（Fingerprint）**：模型"无脑重复"同一条命令。
  把 ``tool_name + 排序后的 args`` 序列化后取 MD5，连续 N 次完全一致即拦截。
* **轨道 B —— 连续错误计数（consecutive_errors）**：模型"微调参数反复试错"
  （如编译失败后依次换 ``-O1``/``-O2``/``-g``），指纹不同但仍在同一坑里打转。
  只要工具返回非零退出码就 +1，成功即清零，连续 N 次触发强制重规划。

本模块不依赖 LangChain，入参统一为 ``(工具名, 参数字典)`` 序列，便于离线单测。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

__all__ = [
    "build_replan_notice",
    "compute_fingerprint",
    "is_failure_observation",
    "is_fingerprint_loop",
    "register_fingerprints",
    "update_consecutive_errors",
]

#: 判定工具执行失败的观察值特征（小写匹配）
FAILURE_MARKERS: tuple[str, ...] = (
    "error",
    "failed",
    "exception",
    "fatal",
    "traceback",
    "cannot",
    "unable to",
    "not found",
    "segmentation fault",
    "timeout",
)


def compute_fingerprint(tool_name: str, args: Mapping[str, Any]) -> str:
    """计算一次工具调用的确定性指纹。

    Args:
        tool_name: 工具名。
        args: 工具入参。

    Returns:
        32 位十六进制 MD5。``args`` 经 ``sort_keys=True`` 规范化，
        因此字典插入顺序不影响结果。
    """
    payload = json.dumps(
        {"tool": tool_name, "args": args},
        sort_keys=True,
        ensure_ascii=False,
        default=str,  # 容忍不可 JSON 序列化的对象（如 Path），保证指纹计算永不抛错
    )
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def register_fingerprints(
    history: Sequence[str],
    calls: Sequence[tuple[str, Mapping[str, Any]]],
    keep_last: int = 5,
) -> list[str]:
    """把本批工具调用追加进指纹队列，并裁剪为定长滑动窗口。

    Args:
        history: 既有指纹队列（时间正序）。
        calls: 本批 ``(工具名, 入参)`` 序列。
        keep_last: 队列保留长度（默认 5）。

    Returns:
        追加并裁剪后的新队列（时间正序）。
    """
    merged = list(history) + [compute_fingerprint(name, args) for name, args in calls]
    return merged[-keep_last:] if keep_last > 0 else []


def is_fingerprint_loop(history: Sequence[str], limit: int) -> bool:
    """判断是否命中参数指纹死循环。

    Args:
        history: 指纹队列（时间正序，已含本批）。
        limit: 连续相同次数阈值（来自 ``config.toml`` 的 ``identical_fingerprint_limit``）。

    Returns:
        最近 ``limit`` 次指纹完全一致时为 ``True``。
    """
    if limit <= 0 or len(history) < limit:
        return False
    return len(set(history[-limit:])) == 1


def is_failure_observation(text: str) -> bool:
    """判断工具观察值是否表示失败。

    Args:
        text: 工具返回的文本。

    Returns:
        命中任一失败特征词时为 ``True``。
    """
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in FAILURE_MARKERS)


def update_consecutive_errors(current: int, failure_count: int) -> int:
    """按"成功清零、失败累加"规则推进连续错误计数。

    Args:
        current: 当前累计值。
        failure_count: 本批失败的工具数量。

    Returns:
        新的累计值；本批无失败时归零。
    """
    if failure_count <= 0:
        return 0
    return current + failure_count


def build_replan_notice(consecutive_errors: int, loop_detected: bool, limit: int) -> str:
    """构造强制重规划的提示文本（由 executor 包装成 SystemMessage 注入）。

    Args:
        consecutive_errors: 当前连续错误数。
        loop_detected: 是否命中指纹死循环。
        limit: 连续错误阈值。

    Returns:
        面向模型的纠偏指令文本。
    """
    lines = ["[系统护栏] 检测到执行受阻，请停止当前策略并重新规划："]
    if loop_detected:
        lines.append("- 你连续多次提交了**完全相同**的工具与参数，已被拦截。请更换工具或改变思路。")
    if consecutive_errors >= limit:
        lines.append(
            f"- 工具已连续 {consecutive_errors} 次返回失败（阈值 {limit}）。"
            "请分析根因（前置条件、路径、依赖、参数），而不是继续在同一处微调。"
        )
    lines.append("- 请在下一轮给出**不同的**行动方案，并说明你从失败中学到了什么。")
    return "\n".join(lines)
