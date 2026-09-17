"""节点的公共契约与纯辅助函数。

这些函数刻意做成**无状态纯函数**：节点实现的复杂度只能来自"编排"，
不该来自"字符串处理"。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage
from loguru import logger

from agent_runtime.state import FailedAttempt, Milestone
from agent_runtime.structured_output import extract_json_object
from tools.core.protocol import ToolResult

__all__ = [
    "NodeFn",
    "apply_milestone_updates",
    "coerce_failed_attempts",
    "extract_json_object",
    "is_failure_result",
    "latest_ai_message",
    "merge_unique",
    "to_tool_call_specs",
]

#: 节点函数签名：只读状态 → 增量更新字典
NodeFn = Callable[[Mapping[str, Any]], Awaitable[Dict[str, Any]]]


def latest_ai_message(messages: Sequence[BaseMessage]) -> Optional[AIMessage]:
    """取最近一条 AIMessage。

    Args:
        messages: 消息序列。

    Returns:
        最近的 ``AIMessage``；不存在时返回 ``None``。
    """
    for message in reversed(list(messages)):
        if isinstance(message, AIMessage):
            return message
    return None


def to_tool_call_specs(tool_calls: Sequence[Mapping[str, Any]]) -> List[tuple[str, str, Mapping[str, Any]]]:
    """把网关返回的工具调用规范化为派发器需要的三元组。

    Args:
        tool_calls: ``[{"id","name","args"}]``。

    Returns:
        ``(tool_call_id, tool_name, args)`` 列表。
    """
    specs: List[tuple[str, str, Mapping[str, Any]]] = []
    for index, call in enumerate(tool_calls):
        name = str(call.get("name") or "")
        if not name:
            logger.warning(f"[Node] 忽略缺少 name 的工具调用: {call}")
            continue
        specs.append((str(call.get("id") or f"call_{index}"), name, call.get("args") or {}))
    return specs


def is_failure_result(result: ToolResult) -> bool:
    """判定工具结果是否应计入连续错误。

    判定顺序（确定性优先，启发式兜底）：

    1. ``ok is False`` → 失败；
    2. 有 ``exit_code`` 且非 0 → 失败；
    3. 无退出码时，才回退到观察值关键字启发式。

    Args:
        result: 工具结果。

    Returns:
        应计为失败时为 ``True``。
    """
    from agent_runtime.guardrails.loop_detector import is_failure_observation

    if not result.ok:
        return True
    if result.exit_code is not None:
        return result.exit_code != 0
    return is_failure_observation(result.content)


def merge_unique(existing: Sequence[str], new_items: Sequence[str]) -> List[str]:
    """顺序保留的唯一性合并（用于 confirmed_facts 累积）。

    Args:
        existing: 既有条目。
        new_items: 新增条目。

    Returns:
        去重后的列表，保持首次出现顺序。
    """
    seen: set[str] = set()
    merged: List[str] = []
    for item in list(existing) + list(new_items):
        clean = str(item).strip()
        if clean and clean not in seen:
            seen.add(clean)
            merged.append(clean)
    return merged


def coerce_failed_attempts(raw: Any) -> List[FailedAttempt]:
    """把模型给出的踩坑记录稳健地转成契约模型。

    Args:
        raw: 期望是 ``[{"action","failure_reason","conclusion"}]``；容错处理脏数据。

    Returns:
        合法的 :class:`FailedAttempt` 列表（丢弃不合法项）。
    """
    if not isinstance(raw, list):
        return []
    attempts: List[FailedAttempt] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        try:
            attempts.append(
                FailedAttempt(
                    action=str(item.get("action", "")).strip(),
                    failure_reason=str(item.get("failure_reason", "")).strip(),
                    conclusion=str(item.get("conclusion", "")).strip(),
                )
            )
        except Exception as exc:  # noqa: BLE001 - 单条脏数据不应影响整轮
            logger.warning(f"[Node] 跳过非法的 failed_attempts 条目: {exc}")
    return [attempt for attempt in attempts if attempt.action or attempt.conclusion]


def apply_milestone_updates(milestones: Sequence[Any], updates: Any) -> List[Milestone]:
    """按模型给出的状态更新里程碑（只允许合法状态值）。

    Args:
        milestones: 既有里程碑列表（可能包含 Milestone 对象或从 checkpoint 反序列化的 dict）。
        updates: 期望是 ``[{"id":1,"status":"completed"}]``。

    Returns:
        更新后的里程碑列表（原地构造新对象，不修改入参）。
    """
    normalized = coerce_milestones(list(milestones))
    if not isinstance(updates, list):
        return normalized

    valid_status = {"pending", "in_progress", "completed", "failed"}
    by_id = {m.id: m for m in normalized}

    for update in updates:
        if not isinstance(update, Mapping):
            continue
        try:
            milestone_id = int(update.get("id"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        status = str(update.get("status", ""))
        if status not in valid_status or milestone_id not in by_id:
            logger.warning(f"[Node] 忽略非法里程碑更新: {update}")
            continue
        current = by_id[milestone_id]
        by_id[milestone_id] = current.model_copy(update={"status": status})

    return [by_id[m.id] for m in normalized]


def coerce_milestones(raw: Any, *, max_items: int = 8) -> List[Milestone]:
    """把模型给出的里程碑计划稳健地转成契约模型。

    只做"形状校验"，不判断计划质量——计划好坏由 evaluator 与实际执行检验。

    Args:
        raw: 期望是 ``[{"id","title","description"}]`` 或已有的 ``Milestone`` 序列。
        max_items: 上限，防止模型输出超长计划把状态撑爆。

    Returns:
        合法的 :class:`Milestone` 列表；全部非法时返回空列表。
    """
    if not isinstance(raw, list):
        return []

    milestones: List[Milestone] = []
    for index, item in enumerate(raw[:max_items], start=1):
        if isinstance(item, Milestone):
            milestones.append(item)
            continue
        if isinstance(item, Mapping):
            title = str(item.get("title", "")).strip() or f"阶段 {index}"
            try:
                milestone_id = int(item.get("id", index))
            except (TypeError, ValueError):
                milestone_id = index
            status_val = str(item.get("status") or "pending")
            desc = str(item.get("description", "")).strip()
        elif hasattr(item, "status"):
            title = getattr(item, "title", "") or f"阶段 {index}"
            milestone_id = getattr(item, "id", index)
            try:
                milestone_id = int(milestone_id)
            except (TypeError, ValueError):
                milestone_id = index
            status_val = str(getattr(item, "status", "pending"))
            desc = str(getattr(item, "description", "")).strip()
        else:
            continue

        status = status_val if status_val in {"pending", "in_progress", "completed", "failed"} else "pending"
        milestones.append(
            Milestone(
                id=milestone_id,
                title=title,
                description=desc,
                status=status,
            )
        )
    return milestones
