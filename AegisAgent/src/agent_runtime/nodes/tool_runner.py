"""``tool_runner`` 节点：权限闸门 + 并发工具派发 + 预算冲销。

对应 ``documents/agent_runtime/03_node_specification.md`` §4.3、
``04_routing_and_control_flow.md`` §4.5（HITL）与
``13_subagent_delegation.md`` §4（子智能体预算对账）。

**为什么从 ``executor`` 拆出来**：LangGraph 的 ``interrupt()`` 恢复时会**重跑整个节点**。
把审批放在这里（而非紧随 fast 模型调用的 ``executor`` 内），
重跑代价只剩纯函数判定，不会重复调用 LLM、也不会出现
"用户批准的命令 ≠ 实际执行的命令"。

**执行顺序（不可乱）**：

1. 读取上一条 ``AIMessage`` 的 ``tool_calls``；
2. **权限闸门**：逐个判定所需级别；存在越级且未获会话白名单豁免时，
   调用 ``interrupt()`` 挂起任务等待人工审批；
3. 同步父任务已用量到预算账本，然后**串行准入**（预留）；
4. 指纹登记与死循环判定（命中则整批拦截）；
5. ``asyncio.gather`` 并发派发；
6. 观察值治理（超限落盘）与**原子对**组装（按信任级决定是否加不可信信封）；
7. 瞬态护栏：连续错误计数与强制重规划通知；
8. **预算冲销**：把子智能体实际消耗并入 ``total_tokens``。

**原子对铁律**：无论批准、拒绝、拦截还是失败，都必须为每个 ``tool_call``
生成配对 ``ToolMessage``，否则端点会因 ``tool_call_id`` 不匹配返回 400。

.. important::
   **预算冲销必须发生在审批闸门之后（第 8 步），这是不可调换的顺序。**
   ``interrupt()`` 挂起时本节点已产生的返回值会被整体丢弃，因此若在第 2 步之前
   记账，被丢弃的那一次记账就会永久丢失（账本是一次性结算的）。
   当前顺序下：挂起发生在派发之前，而子智能体的消耗只可能发生在派发期间，
   所以"挂起 ⇒ 本次无消耗可记"，不存在丢失。
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Mapping, Optional, Set

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.types import interrupt
from loguru import logger

from agent_runtime.envelope import observation
from agent_runtime.guardrails.authority import TaskAuthority
from agent_runtime.guardrails.budget_ledger import BudgetLedger
from agent_runtime.guardrails.loop_detector import (
    build_replan_notice,
    is_fingerprint_loop,
    register_fingerprints,
    update_consecutive_errors,
)
from agent_runtime.guardrails.observation_pruner import ObservationPruner
from agent_runtime.guardrails.permission import action_signature, check_permission
from agent_runtime.nodes.base import NodeFn, is_failure_result, latest_ai_message, to_tool_call_specs
from agent_runtime.observability.trajectory import TrajectoryRecorder
from tools.core.dispatcher import DispatchedResult, ToolDispatcher
from tools.core.protocol import ToolResult

__all__ = ["build_tool_runner_node"]

#: 指纹队列保留长度
FINGERPRINT_WINDOW = 5

#: 命中死循环时的拦截说明（仍要回填成 ToolMessage 以保持原子对完整）
_LOOP_BLOCK_NOTICE = "已拦截：相同工具与参数连续重复，请更换策略后重试。"

#: 越级且未被批准时的观察值前缀
_REJECT_PREFIX = "已被人工审核拒绝"


def build_tool_runner_node(
    dispatcher: ToolDispatcher,
    pruner: ObservationPruner,
    guardrails_config: Any,
    permissions_config: Any,
    *,
    ledger: Optional[BudgetLedger] = None,
    authority: Optional[TaskAuthority] = None,
    approval_allowlist: Optional[Set[str]] = None,
    recorder: Optional[TrajectoryRecorder] = None,
) -> NodeFn:
    """构造 ``tool_runner`` 节点。

    Args:
        dispatcher: 并发派发器。
        pruner: 观察值裁剪器。
        guardrails_config: ``config.runtime.guardrails``（指纹与错误阈值）。
        permissions_config: ``config.permissions``（三级权限分类表）。
        ledger: **子智能体预算账本**（父级记账方）。为 ``None`` 时不启用预算冲销
            （如单测直接构造节点时）。
        authority: **任务授权窗口**（父级权限级别的权威推送点）。为 ``None`` 时
            不推送——此时叶子工具只能使用其初始级别。
        approval_allowlist: **会话级"永久放行"指纹集合**（可变引用）。
            由 ``TaskRegistry`` 持有，跨 ``resume`` 存活；为 ``None`` 时不启用豁免。
        recorder: 轨迹记录器（可选旁路）。

    Returns:
        节点函数。
    """

    async def tool_runner(state: Mapping[str, Any]) -> Dict[str, Any]:
        """执行已生成的工具调用（含越级审批闸门与预算冲销）。

        Args:
            state: ``AgentState``（只读）。

        Returns:
            工具消息、连续错误、指纹队列、产物句柄与 Token 增量。
        """
        step_index = int(state.get("step_count", 0))
        task_id = str(state.get("task_id", "unknown"))
        current_level = state.get("permission_level") or "workspace_write"
        base_tokens = int(state.get("total_tokens", 0))

        assistant = latest_ai_message(list(state.get("messages") or []))
        specs = to_tool_call_specs(getattr(assistant, "tool_calls", None) or [])
        if not specs:
            logger.debug("[ToolRunner] 无待执行工具，跳过")
            return {}

        # ------------------------------------------------------------------
        # 1. 权限闸门：逐项判定越级
        # ------------------------------------------------------------------
        allowlist: Set[str] = approval_allowlist if approval_allowlist is not None else set()
        escalations: List[tuple[str, str, Mapping[str, Any], Any]] = []

        for call_id, name, args in specs:
            decision = check_permission(current_level, name, args, permissions_config)
            if decision.allowed:
                continue
            if action_signature(name, args) in allowlist:
                logger.debug(f"[ToolRunner] {name} 已获会话白名单豁免，直接执行")
                continue
            escalations.append((call_id, name, args, decision))

        blocked_reasons: Dict[str, str] = {}
        if escalations:
            blocked_reasons = await _resolve_escalations(
                escalations, current_level, task_id, step_index, allowlist, recorder
            )

        # ------------------------------------------------------------------
        # 2. 预算账本：同步父任务已用量 → 串行准入（必须在并发派发之前）
        #    准入无 await，因而原子；若挪到 gather 之后，并发子任务会各自
        #    读到同一份余额并全额预留，造成超额分配。
        # ------------------------------------------------------------------
        consumed_before = 0
        if ledger is not None:
            ledger.sync_parent_usage(base_tokens)
            consumed_before = ledger.consumed
        if authority is not None:
            # 把 State 中的权威级别推送给叶子工具（工具看不到 State）
            authority.bind(current_level)

        # ------------------------------------------------------------------
        # 3. 指纹登记与死循环判定
        # ------------------------------------------------------------------
        fingerprint_history = register_fingerprints(
            state.get("fingerprint_history") or [],
            [(name, args) for _, name, args in specs],
            keep_last=FINGERPRINT_WINDOW,
        )
        loop_detected = is_fingerprint_loop(
            fingerprint_history, int(guardrails_config.identical_fingerprint_limit)
        )
        if loop_detected:
            logger.warning("[ToolRunner] 指纹死循环命中，拦截本次派发")

        # ------------------------------------------------------------------
        # 4. 并发派发（被拒绝/被拦截的调用不派发，改为合成观察值）
        # ------------------------------------------------------------------
        if loop_detected:
            results: List[DispatchedResult] = [
                DispatchedResult(
                    tool_call_id=call_id, tool_name=name, result=ToolResult.failure(_LOOP_BLOCK_NOTICE)
                )
                for call_id, name, _ in specs
            ]
        else:
            dispatchable = [
                (call_id, name, args) for call_id, name, args in specs if call_id not in blocked_reasons
            ]
            dispatched = await dispatcher.dispatch(dispatchable)
            by_id = {item.tool_call_id: item for item in dispatched}
            results = [
                by_id.get(
                    call_id,
                    DispatchedResult(
                        tool_call_id=call_id,
                        tool_name=name,
                        result=ToolResult.failure(
                            f"{_REJECT_PREFIX}：{blocked_reasons.get(call_id, '用户未批准该操作')}，请改用合规方案（如仅生成本地补丁而不推送远端）"
                        ),
                    ),
                )
                for call_id, name, _ in specs
            ]

        # ------------------------------------------------------------------
        # 5. 观察值治理 + 原子对组装（信任级决定是否加不可信信封）
        # ------------------------------------------------------------------
        tool_messages: List[ToolMessage] = []
        artifacts: Dict[str, str] = dict(state.get("artifacts") or {})
        failure_count = 0

        for dispatched in results:
            failed = is_failure_result(dispatched.result)
            if failed:
                failure_count += 1

            pruned = await pruner.prune(
                dispatched.result.content,
                task_id=task_id,
                step_id=step_index,
                tool_name=dispatched.tool_name,
            )
            if pruned.artifact_path and pruned.artifact_id:
                artifacts[pruned.artifact_id] = pruned.artifact_path

            tool_messages.append(
                ToolMessage(
                    content=observation(dispatched.tool_name, dispatched.trust, pruned.summary),
                    tool_call_id=dispatched.tool_call_id,
                )
            )

            if recorder is not None:
                await recorder.record(
                    record_type="tool",
                    node="tool_runner",
                    phase="executing",
                    tool_name=dispatched.tool_name,
                    observation_summary=pruned.summary[:1000],
                    artifact_path=pruned.artifact_path or "",
                    ok=not failed,
                    step_count=step_index,
                    total_tokens=base_tokens,
                )

        # ------------------------------------------------------------------
        # 6. 瞬态护栏：成功清零、失败累加，必要时注入重规划通知
        # ------------------------------------------------------------------
        consecutive_errors = update_consecutive_errors(
            int(state.get("consecutive_errors", 0)), failure_count
        )

        if consecutive_errors >= int(guardrails_config.consecutive_errors_limit) or loop_detected:
            notice = build_replan_notice(
                consecutive_errors,
                loop_detected,
                int(guardrails_config.consecutive_errors_limit),
            )
            tool_messages.append(SystemMessage(content=notice))
            if recorder is not None:
                await recorder.record(
                    record_type="guard",
                    node="tool_runner",
                    phase="reflecting",
                    thought=notice[:500],
                    ok=False,
                    step_count=step_index,
                    consecutive_errors=consecutive_errors,
                )

        # ------------------------------------------------------------------
        # 7. 预算冲销：把本次派发期间子智能体**已结算**的消耗并入父任务计量
        #    用"增量"而非"绝对值"：账本随任务重建，而 total_tokens 已由
        #    Checkpoint 持久化，增量语义在 resume 场景下天然正确。
        # ------------------------------------------------------------------
        child_tokens = 0
        if ledger is not None:
            child_tokens = max(0, ledger.consumed - consumed_before)

        logger.info(
            f"[ToolRunner] 执行 {len(specs)} 个工具（拒绝 {len(blocked_reasons)} 个），"
            f"失败 {failure_count} 个，连续错误={consecutive_errors}，死循环={loop_detected}，"
            f"子智能体消耗={child_tokens}"
        )

        updates: Dict[str, Any] = {
            "messages": tool_messages,
            "consecutive_errors": consecutive_errors,
            "fingerprint_history": fingerprint_history,
            "artifacts": artifacts,
        }
        if child_tokens:
            updates["total_tokens"] = base_tokens + child_tokens
        return updates

    return tool_runner


async def _resolve_escalations(
    escalations: List[tuple[str, str, Mapping[str, Any], Any]],
    current_level: str,
    task_id: str,
    step_index: int,
    allowlist: Set[str],
    recorder: Optional[TrajectoryRecorder],
) -> Set[str]:
    """就一批越级操作请求人工审批。

    ``interrupt()`` 会挂起图执行；恢复时本节点从头重跑，
    该调用返回 ``/approve`` 或 ``/reject`` 传入的决策字典。

    Args:
        escalations: ``(tool_call_id, 工具名, 入参, 判定结果)`` 列表。
        current_level: 当前权限级别。
        task_id: 任务 ID（仅用于轨迹）。
        step_index: 步序号（仅用于轨迹）。
        allowlist: 会话白名单（``always`` 决策时写入）。
        recorder: 轨迹记录器。

    Returns:
        被拒绝、不允许执行的 ``tool_call_id -> 拒绝原因`` 字典（空字典表示全部放行）。
    """
    primary = escalations[0]
    decision = primary[3]

    payload: Dict[str, Any] = {
        "approval_id": f"appr_{uuid.uuid4().hex[:12]}",
        "required_level": decision.required_level,
        "current_level": current_level,
        "action_type": decision.action_type,
        "command": decision.action_summary,
        "reason": decision.reason,
        "escalation_count": len(escalations),
        "related_actions": [item[3].action_summary for item in escalations[1:5]],
    }

    logger.warning(
        f"[ToolRunner] 检测到越级操作，挂起等待人工审批："
        f"approval_id={payload['approval_id']} "
        f"{decision.current_level} → {decision.required_level} [{decision.action_type}] "
        f"{decision.action_summary}"
    )

    # 挂起：恢复时返回 API 层传入的决策（{"approved": bool, "scope": ..., "reason": ...}）
    resume_value = interrupt(payload)
    verdict = dict(resume_value) if isinstance(resume_value, Mapping) else {}

    if recorder is not None:
        await recorder.record(
            record_type="guard",
            node="tool_runner",
            phase="reflecting",
            thought=(
                f"[HITL] approval_id={payload['approval_id']} "
                f"approved={bool(verdict.get('approved'))} "
                f"scope={verdict.get('scope') or '-'} "
                f"reason={verdict.get('reason') or '-'}"
            ),
            ok=bool(verdict.get("approved")),
            step_count=step_index,
        )

    if verdict.get("approved") is not True:
        reason = str(verdict.get("reason") or "用户未批准该操作")
        logger.warning(f"[ToolRunner] 审批被拒绝：{reason}")
        return {call_id: reason for call_id, _, _, _ in escalations}

    if str(verdict.get("scope") or "once") == "always":
        for _, name, args, _ in escalations:
            allowlist.add(action_signature(name, args))
        logger.info(f"[ToolRunner] 已加入会话白名单（{len(escalations)} 项），后续同类操作免审")

    return {}
