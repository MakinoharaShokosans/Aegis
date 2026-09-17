"""动态子智能体的**有界执行循环**。

对应 ``documents/agent_runtime/13_subagent_delegation.md`` §5–§8。

## 为什么不是 LangGraph 子图

与 ``research/runner.py`` 同一理由（``10_directory_structure.md`` 裁决⑯）：
子图共享父图的 ``messages`` 与 Checkpoint，被隔离的中间内容会被**持久化进主任务快照**，
恢复时重新喂回主上下文——隔离形同虚设。

本模块用一条自带预算的朴素异步循环，把中间内容的生命周期**关在一次函数调用内**：
循环结束，中间观察值即被丢弃，只有 :class:`~agent_runtime.subagent.contracts.SubagentReport`
会离开本函数。

## 三道收窄在本模块的落点

收窄的主要工作在 :mod:`agent_runtime.subagent.tool`（派发前一次性定死）。
本模块只承担**第二层**、也是无法在派发前判定的那一层：

* **工具集**已在派发前收窄 → 这里只按收窄后的工具表导出 Schema；
* **权限级别**在派发前确定为 ``≤ 父级``，但"同一工具、不同入参"的级别差异
  （典型是 ``bash`` 的命令分类）只能在这里逐次判定 → 用
  :func:`~agent_runtime.guardrails.permission.check_permission` 判定，
  **越级即失败，绝不调用 ``interrupt()``**；
* **深度**由工具表剔除 ``spawn_subagent`` 实现，本模块无须感知。

## 为什么子智能体不得请求人工审批（技术理由，非policy）

``interrupt()`` 在恢复时会**重跑整个节点**。子智能体运行在 ``tool_runner`` 内部，
一旦它在内部挂起，恢复时**整个子循环从头重跑**：已花掉的模型调用重复计费，
已产生副作用的工具调用**执行两次**。这不是策略选择，是框架语义决定的，
无法通过谨慎编码绕开。因此本模块**不 import ``interrupt``**。

## 有界性

不设指纹死循环检测：子智能体没有"重规划"回路，唯一的循环由 ``max_steps``
与 Token/挂钟预算三重封顶，最坏情况是有限的重复调用而非无限打转。
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from loguru import logger

from agent_runtime.envelope import observation
from agent_runtime.guardrails.budget_ledger import ChildBudget
from agent_runtime.guardrails.permission import check_permission
from agent_runtime.llm.client import LLMGateway
from agent_runtime.nodes.base import to_tool_call_specs
from agent_runtime.observability.event_bus import TaskEventBus
from agent_runtime.prompt_loader import PromptLibrary
from agent_runtime.structured_output import extract_json_object, truncate_text
from agent_runtime.subagent.contracts import (
    SubagentReport,
    SubagentRequest,
    build_report,
    collect_accessed_refs,
    describe_tool,
    render_system_message,
)
from tools.core.dispatcher import ToolDispatcher
from tools.core.registry import ToolRegistry

__all__ = ["SubagentRunner"]

#: 子智能体收到任务后的开场指令（真正的目标在系统消息的数据块里）
_KICKOFF = "请按 <subagent_protocol> 执行上述子任务。需要工具时直接发起调用；任务完成后只输出契约要求的 JSON。"

#: 收尾提炼指令（forced JSON 模式下的用户消息）
_DISTILL = (
    "## 收尾：输出结构化结论\n"
    "停止调用工具，只输出一个 JSON 对象，字段与协议第五节完全一致：\n"
    '{"status": "...", "findings": [{"statement": "...", "citations": [{"kind": "...", "ref": "...", "note": "..."}]}], '
    '"unresolved": [...], "warnings": [...]}\n'
    "注意：citations 里的 ref 必须是你**本次真正访问过**的资源，否则会被系统丢弃；"
    "没有证据支撑的内容请写进 unresolved，不要写成结论。"
)


class SubagentRunner:
    """有界子智能体循环。

    Args:
        gateway: 双模型网关（使用 ``config.model_tier`` 指定的层级）。
        tools: **已收窄**的子智能体工具表。
        dispatcher: 并发派发器（复用主循环同一个实现，拿到超时与异常降级语义）。
        prompts: 提示词库（读取固定协议 ``subagent``）。
        permissions_config: ``config.permissions``（三级权限分类表）。
        config: ``SubagentConfig``（各项硬上限）。
        event_bus: 任务事件总线（可选）。中间步骤对节点级流式不可见，
            因此由子智能体主动向总线发 ``subagent.*`` 事件（见 `11` §6）。
    """

    __slots__ = (
        "_gateway",
        "_tools",
        "_dispatcher",
        "_prompts",
        "_permissions_config",
        "_config",
        "_protocol",
        "_bus",
    )

    def __init__(
        self,
        *,
        gateway: LLMGateway,
        tools: ToolRegistry,
        dispatcher: ToolDispatcher,
        prompts: PromptLibrary,
        permissions_config: Any,
        config: Any,
        event_bus: Optional[TaskEventBus] = None,
    ) -> None:
        self._gateway = gateway
        self._tools = tools
        self._dispatcher = dispatcher
        self._prompts = prompts
        self._permissions_config = permissions_config
        self._config = config
        self._protocol = prompts.load("subagent")
        self._bus = event_bus

    # ==========================================================================
    # 对外入口
    # ==========================================================================

    async def run(self, request: SubagentRequest, budget: ChildBudget) -> SubagentReport:
        """执行一次委派子任务。

        Args:
            request: **已收窄**的委派请求。
            budget: 子级预算计数器（由调用方持有，以便在被取消时仍能结算）。

        Returns:
            :class:`SubagentReport`。**任何阶段失败都不抛异常**，
            而是返回带 ``warnings`` 的报告（可能是空报告），
            绝不把中间观察值或异常原文透传给主 Agent。
        """
        warnings: List[str] = []
        accessed: Set[str] = set()
        steps_used = 0
        tool_call_count = 0
        messages = self._initial_messages(request)

        await self._emit(
            {
                "event": "subagent.started",
                "role": request.role,
                "depth": request.depth,
                "assigned_tools": list(request.assigned_tools),
                "token_budget": budget.max_tokens,
                "max_steps": request.max_steps,
            }
        )

        for _ in range(max(1, int(request.max_steps))):
            if budget.exhausted:
                warnings.append(budget.reason())
                break

            try:
                response = await self._gateway.invoke(
                    self._config.model_tier, messages, tools=self._tools.to_openai_tools()
                )
            except Exception as exc:  # noqa: BLE001 - 隔离区失败必须降级而非上抛
                logger.error(f"[Subagent] 模型调用失败，提前收尾: {exc}")
                warnings.append(f"子智能体模型调用失败：{type(exc).__name__}")
                break

            budget.add_tokens(response.total_tokens)
            steps_used += 1

            specs = to_tool_call_specs(response.tool_calls)
            messages.append(_assistant_message(response.content, specs))
            if not specs:
                logger.debug("[Subagent] 本轮未产生工具调用，转入收尾")
                break

            tool_call_count += len(specs)
            await self._emit(
                {
                    "event": "subagent.step",
                    "step": steps_used,
                    "tools": [name for _, name, _ in specs],
                }
            )
            messages.extend(
                await self._execute(specs, request.permission_level, accessed, warnings, steps_used)
            )

        raw = await self._distill(messages, budget, warnings)

        report = build_report(
            raw,
            role=request.role,
            goal=request.goal,
            accessed=accessed,
            steps_used=steps_used,
            tool_calls=tool_call_count,
            total_tokens=budget.tokens,
            elapsed_sec=budget.elapsed,
            config=self._config,
        )
        if warnings:
            report.warnings = [*warnings, *report.warnings]

        logger.info(
            f"[Subagent] 完成 role={request.role} 步数={steps_used} "
            f"工具调用={tool_call_count} tokens={budget.tokens} "
            f"耗时={budget.elapsed:.1f}s 结论={len(report.findings)} "
            f"已验证={sum(1 for item in report.findings if item.verified)}"
        )
        await self._emit(
            {
                "event": "subagent.finished",
                "role": request.role,
                "status": report.status,
                "steps_used": steps_used,
                "tool_calls": tool_call_count,
                "tokens": budget.tokens,
                "findings": len(report.findings),
                "verified_findings": sum(1 for item in report.findings if item.verified),
                "elapsed_sec": round(budget.elapsed, 2),
            }
        )
        return report

    # ==========================================================================
    # 内部阶段
    # ==========================================================================

    def _initial_messages(self, request: SubagentRequest) -> List[BaseMessage]:
        """构造子智能体的初始上下文（目标与角色作为**数据块**注入）。"""
        tool_lines: List[str] = []
        for name in request.assigned_tools:
            tool = self._tools.get(name)
            if tool is not None:
                tool_lines.append(describe_tool(tool))

        return [
            SystemMessage(
                content=render_system_message(
                    request=request, protocol=self._protocol, tool_lines=tool_lines
                )
            ),
            HumanMessage(content=_KICKOFF),
        ]

    async def _execute(
        self,
        specs: Sequence[tuple[str, str, Mapping[str, Any]]],
        permission_level: str,
        accessed: Set[str],
        warnings: List[str],
        step_index: int,
    ) -> List[ToolMessage]:
        """执行一轮工具调用（权限二次判定 → 并发派发 → 组装原子对）。

        越级调用**不挂起、不审批**，直接合成一条失败观察值——
        这是"能力在派发前已衰减"在子级内部的体现。

        Args:
            specs: ``(tool_call_id, 工具名, 入参)`` 序列。
            permission_level: 子级权限级别。
            accessed: **原地累加**的实际访问资源集合（引用白名单来源）。
            warnings: **原地累加**的护栏标注。
            step_index: 当前轮次（用于事件与轨迹）。

        Returns:
            与 ``specs`` 等长、顺序一致的 :class:`ToolMessage` 列表。
        """
        allowed: List[tuple[str, str, Mapping[str, Any]]] = []
        rejected: Dict[str, str] = {}

        for call_id, name, args in specs:
            decision = check_permission(permission_level, name, args, self._permissions_config)
            if decision.allowed:
                allowed.append((call_id, name, args))
                continue
            rejected[call_id] = (
                f"该能力未授予此子智能体（需要 {decision.required_level}，当前 {permission_level}），"
                "且子智能体不能发起人工审批。请改用合规方案，或如实报告无法完成。"
            )
            warnings.append(f"子智能体越级调用被拒绝：{decision.action_summary}")
            logger.warning(
                f"[Subagent] 越级调用被拒绝 tool={name} "
                f"{decision.current_level}→{decision.required_level} [{decision.action_type}]"
            )
            # 越级被拒是**用户最需要看见**的事件：它解释了子智能体为何"做不成某件事"
            await self._emit(
                {
                    "event": "subagent.blocked",
                    "step": step_index,
                    "tool": name,
                    "required_level": decision.required_level,
                    "current_level": decision.current_level,
                    "action_type": decision.action_type,
                    "reason": decision.action_summary,
                }
            )

        dispatched = await self._dispatcher.dispatch(allowed)
        by_id = {item.tool_call_id: item for item in dispatched}

        max_observation_chars = int(getattr(self._config, "max_observation_chars", 4000))
        messages: List[ToolMessage] = []
        for call_id, name, args in specs:
            item = by_id.get(call_id)
            if item is None:
                # 被拒绝的调用：框架自带文本，按可信内容出信封（不加不可信警示）
                messages.append(
                    ToolMessage(
                        content=observation(name, "trusted", rejected.get(call_id, "未执行")),
                        tool_call_id=call_id,
                    )
                )
                continue

            accessed |= collect_accessed_refs(name, args, item.result)
            content, _ = truncate_text(item.result.content, max_observation_chars)
            messages.append(
                ToolMessage(content=observation(name, item.trust, content), tool_call_id=call_id)
            )
            # 事件流只带**已裁剪摘要**（总线还会强制限长到 300 字符）；
            # 原始正文仍不进入主状态、主 Checkpoint 与事件流
            await self._emit(
                {
                    "event": "subagent.tool",
                    "step": step_index,
                    "tool": name,
                    "ok": bool(item.result.ok),
                    "duration_ms": int(item.result.duration_ms),
                    "untrusted": item.trust == "untrusted",
                    "summary": item.result.content,
                }
            )

        return messages

    async def _emit(self, event: Mapping[str, Any]) -> None:
        """向任务事件总线发送一条事件（未装配总线时为空操作）。

        Args:
            event: 事件字典，必须含 ``event`` 键。
        """
        if self._bus is None:
            return
        await self._bus.emit(event)

    async def _distill(
        self,
        messages: Sequence[BaseMessage],
        budget: ChildBudget,
        warnings: List[str],
    ) -> Mapping[str, Any]:
        """收尾提炼：把已积累的对话压成契约 JSON。

        Args:
            messages: 本次子任务的完整消息序列（**只在本函数内使用，不离开隔离区**）。
            budget: 子级预算计数器。
            warnings: **原地累加**的降级说明。

        Returns:
            原始 JSON 对象；解析失败时返回空字典（由 :func:`build_report` 归一为 failed）。
        """
        try:
            response = await self._gateway.invoke(
                self._config.model_tier,
                [*messages, HumanMessage(content=_DISTILL)],
                force_json=True,
            )
        except Exception as exc:  # noqa: BLE001 - 提炼失败也要给出可解释的报告
            logger.error(f"[Subagent] 收尾提炼失败: {exc}")
            warnings.append(f"子智能体收尾提炼失败：{type(exc).__name__}")
            return {}

        budget.add_tokens(response.total_tokens)
        parsed = extract_json_object(response.content)
        if parsed is None:
            logger.warning("[Subagent] 提炼输出不是合法 JSON，返回空报告")
            warnings.append("子智能体未按契约输出 JSON")
            return {}
        return parsed


def _assistant_message(
    content: str, specs: Sequence[tuple[str, str, Mapping[str, Any]]]
) -> AIMessage:
    """构造子级 AIMessage（携带 tool_calls 才能与其后的 ToolMessage 构成合法原子对）。"""
    if not specs:
        return AIMessage(content=content or "")
    return AIMessage(
        content=content or "",
        tool_calls=[
            {"id": call_id, "name": name, "args": dict(args), "type": "tool_call"}
            for call_id, name, args in specs
        ],
    )
