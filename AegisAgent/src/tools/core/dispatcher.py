"""并发工具派发器。

对应 ``documents/agent_runtime/01_architecture_overview.md`` 中 ToolLayer 的
"Async Concurrent Dispatcher"：单轮多个 ``tool_calls`` 用 ``asyncio.gather``
并发执行，把总耗时从 ``Σtᵢ`` 压缩到 ``max(tᵢ)``。

**关键纪律**：
1. 每个工具调用都有独立硬超时（``asyncio.wait_for``），单个卡死不影响其它；
2. 工具业务失败**不抛异常**，一律包装为 :class:`ToolResult`，
   由 Executor 依据结果更新 ``consecutive_errors``；
3. 派发结果保留原始 ``tool_call_id``，供上层组装**原子配对**的 ``ToolMessage``。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from loguru import logger

from tools.core.protocol import ToolResult, ToolTrust
from tools.core.registry import ToolRegistry

__all__ = ["DispatchedResult", "ToolDispatcher"]

#: 工具调用三元组：(tool_call_id, 工具名, 入参)
ToolCallSpec = tuple[str, str, Mapping[str, Any]]


@dataclass(slots=True)
class DispatchedResult:
    """一次工具派发的结果。

    Attributes:
        tool_call_id: 原始调用 ID（用于配对 ToolMessage）。
        tool_name: 工具名。
        result: 统一结果契约。
        trust: **本次调用**生效的信任级。解析规则：``result.trust``（调用期覆盖）
            优先，否则回退工具类静态声明；未知工具取最保守值 ``untrusted``。
            编排层只读这一个字段，不必自行拼装解析逻辑。
    """

    tool_call_id: str
    tool_name: str
    result: ToolResult
    trust: ToolTrust = "trusted"


class ToolDispatcher:
    """并发工具派发器。

    Args:
        registry: 工具注册表。
    """

    __slots__ = ("_registry",)

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def dispatch(self, calls: Sequence[ToolCallSpec]) -> list[DispatchedResult]:
        """并发执行一批工具调用。

        Args:
            calls: ``(tool_call_id, 工具名, 入参)`` 序列。

        Returns:
            与入参等长、顺序一致的结果列表（顺序一致便于与 tool_calls 配对）。
        """
        if not calls:
            return []
        gathered = await asyncio.gather(*(self._dispatch_one(*call) for call in calls))
        return list(gathered)

    async def _dispatch_one(
        self,
        tool_call_id: str,
        tool_name: str,
        args: Mapping[str, Any],
    ) -> DispatchedResult:
        """执行单个工具（含超时与未知工具的降级处理）。"""
        started = time.perf_counter()
        tool = self._registry.get(tool_name)

        if tool is None:
            logger.warning(f"[Dispatcher] 未知工具 {tool_name}，已封装为失败观察值")
            return DispatchedResult(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                result=ToolResult.failure(f"未知工具: {tool_name}"),
                # 未知工具的副作用不可静态推理，信任级取最保守值
                trust="untrusted",
            )

        try:
            result = await asyncio.wait_for(tool.invoke(args), timeout=tool.timeout_sec)
        except asyncio.TimeoutError:
            logger.error(f"[Dispatcher] 工具 {tool_name} 执行超时（>{tool.timeout_sec}s）")
            result = ToolResult.failure(f"工具执行超时（>{tool.timeout_sec}s）")
        except Exception as exc:  # noqa: BLE001 - 工具异常必须降级为观察值，不得中断主循环
            logger.exception(f"[Dispatcher] 工具 {tool_name} 抛出未预期异常")
            result = ToolResult.failure(f"{type(exc).__name__}: {exc}")

        if result.duration_ms == 0:
            result.duration_ms = int((time.perf_counter() - started) * 1000)
        return DispatchedResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            result=result,
            trust=_resolve_trust(result, tool),
        )


def _resolve_trust(result: ToolResult, tool: Any) -> ToolTrust:
    """解析本次调用生效的信任级。

    优先级：**调用期覆盖 > 工具类静态声明 > 最保守值**。
    之所以允许调用期覆盖：像动态子智能体这类工具，其输出信任级取决于
    **本次被授予了哪些工具**，静态类属性表达不了这种依赖。

    Args:
        result: 工具返回的结果。
        tool: 工具实例。

    Returns:
        ``"trusted"`` 或 ``"untrusted"``。
    """
    if result.trust in ("trusted", "untrusted"):
        return result.trust  # type: ignore[return-value]
    declared = getattr(tool, "trust", None)
    return "trusted" if declared == "trusted" else "untrusted"
