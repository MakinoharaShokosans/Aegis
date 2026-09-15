"""``executor`` 节点：动作生成与并发工具派发（fast 层）。

对应 ``documents/agent_runtime/03_node_specification.md`` §4.3。

五件事，顺序不可乱：

1. 把 planner 的决策指令翻译成**具体 ``tool_calls``**（fast 模型 + function calling）；
2. **指纹登记 + 死循环判定**（命中则拦截派发，但仍必须补齐配对消息）；
3. ``asyncio.gather`` **并发派发**；
4. **观察值治理**：超限输出离线落盘，只把摘要与句柄带回上下文；
5. **瞬态护栏**：更新连续错误计数，必要时注入强制重规划通知。

**原子对铁律**：无论成功、失败还是被拦截，都必须为原 ``AIMessage`` 的每个
``tool_call`` 生成配对 ``ToolMessage``；否则端点会因 ``tool_call_id`` 不匹配返回 400。
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from loguru import logger

from agent_runtime.context import ContextManager
from agent_runtime.errors import LLMUnavailableError
from agent_runtime.guardrails.canary import detect_canary_leak
from agent_runtime.guardrails.loop_detector import (
    build_replan_notice,
    is_fingerprint_loop,
    register_fingerprints,
    update_consecutive_errors,
)
from agent_runtime.guardrails.observation_pruner import ObservationPruner
from agent_runtime.llm.client import LLMGateway
from agent_runtime.nodes.base import NodeFn, is_failure_result, to_tool_call_specs
from agent_runtime.observability.trajectory import TrajectoryRecorder
from agent_runtime.prompt_loader import PromptLibrary
from tools.core.dispatcher import DispatchedResult, ToolDispatcher
from tools.core.protocol import ToolResult
from tools.core.registry import ToolRegistry

__all__ = ["build_executor_node"]

#: 指纹队列保留长度
FINGERPRINT_WINDOW = 5

#: 命中死循环时的拦截说明（仍要回填成 ToolMessage 以保持原子对完整）
_LOOP_BLOCK_NOTICE = "已拦截：相同工具与参数连续重复，请更换策略后重试。"


def build_executor_node(
    gateway: LLMGateway,
    registry: ToolRegistry,
    dispatcher: ToolDispatcher,
    pruner: ObservationPruner,
    prompts: PromptLibrary,
    context: ContextManager,
    guardrails_config: Any,
    recorder: Optional[TrajectoryRecorder] = None,
) -> NodeFn:
    """构造 ``executor`` 节点。

    Args:
        gateway: 双模型网关。
        registry: 工具注册表（含 MCP 转译工具）。
        dispatcher: 并发派发器。
        pruner: 观察值裁剪器。
        prompts: 提示词库。
        context: 上下文装配器。
        guardrails_config: ``config.runtime.guardrails``（提供阈值）。
        recorder: 轨迹记录器（可选旁路）。

    Returns:
        节点函数。
    """

    async def executor(state: Mapping[str, Any]) -> Dict[str, Any]:
        """生成并执行工具调用。

        Args:
            state: ``AgentState``（只读）。

        Returns:
            消息、步数、Token、连续错误、指纹队列与产物句柄增量。
        """
        base_tokens = int(state.get("total_tokens", 0))
        step_index = int(state.get("step_count", 0)) + 1

        # ------------------------------------------------------------------
        # 1. fast 层：把决策指令翻译成具体工具调用
        # ------------------------------------------------------------------
        messages = context.assemble(state, node_instruction=prompts.load("executor"))
        tool_schemas = registry.to_openai_tools()

        try:
            response = await gateway.invoke("fast", messages, tools=tool_schemas)
        except LLMUnavailableError as exc:
            logger.error(f"[Executor] LLM 全链路不可用: {exc}")
            return {"should_terminate": True, "termination_reason": f"LLM 不可用: {exc}"}

        specs = to_tool_call_specs(response.tool_calls)
        tokens_after_llm = base_tokens + response.total_tokens

        # ------------------------------------------------------------------
        # 安全防御：Canary Token 泄露检测（阻断任何提示词窃取或工具外带注入）
        # ------------------------------------------------------------------
        canary_token = str(state.get("canary_token") or "")
        if canary_token:
            leak_in_content = detect_canary_leak(response.content, canary_token)
            leak_in_tools = detect_canary_leak(response.tool_calls, canary_token)
            if leak_in_content or leak_in_tools:
                logger.critical(
                    f"[Executor] 安全熔断：检测到 Canary Token 泄露！"
                    f"（content_leak={leak_in_content}, tools_leak={leak_in_tools}）"
                )
                if recorder is not None:
                    await recorder.record(
                        record_type="guard",
                        node="executor",
                        phase="executing",
                        thought="[SECURITY] Canary Token leak detected in LLM response or tool calls",
                        ok=False,
                        step_count=step_index,
                        total_tokens=tokens_after_llm,
                    )
                return {
                    "should_terminate": True,
                    "termination_reason": "[SECURITY] Prompt leak detected via canary token",
                    "total_tokens": tokens_after_llm,
                }

        # 没有工具调用：记录 planner 指令的落地文字即可，不计为错误
        if not specs:
            logger.info("[Executor] 本轮未产生工具调用")
            return {
                "messages": [AIMessage(content=response.content or "")],
                "step_count": step_index,
                "total_tokens": tokens_after_llm,
            }

        # ------------------------------------------------------------------
        # 2. 指纹登记与死循环判定
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
            logger.warning("[Executor] 指纹死循环命中，拦截本次派发")

        # ------------------------------------------------------------------
        # 3. 并发派发
        # ------------------------------------------------------------------
        if loop_detected:
            results: List[DispatchedResult] = [
                DispatchedResult(tool_call_id=call_id, tool_name=name, result=ToolResult.failure(_LOOP_BLOCK_NOTICE))
                for call_id, name, _ in specs
            ]
        else:
            results = await dispatcher.dispatch(specs)

        # ------------------------------------------------------------------
        # 4. 观察值治理 + 原子对组装
        # ------------------------------------------------------------------
        tool_messages: List[ToolMessage] = []
        artifacts: Dict[str, str] = dict(state.get("artifacts") or {})
        failure_count = 0

        for dispatched in results:
            if is_failure_result(dispatched.result):
                failure_count += 1

            pruned = await pruner.prune(
                dispatched.result.content,
                task_id=str(state.get("task_id", "unknown")),
                step_id=step_index,
                tool_name=dispatched.tool_name,
            )
            if pruned.artifact_path and pruned.artifact_id:
                artifacts[pruned.artifact_id] = pruned.artifact_path

            wrapped_observation = (
                f"<tool_observation tool=\"{dispatched.tool_name}\">\n"
                f"{pruned.summary}\n"
                f"</tool_observation>"
            )
            tool_messages.append(
                ToolMessage(content=wrapped_observation, tool_call_id=dispatched.tool_call_id)
            )

            if recorder is not None:
                await recorder.record(
                    record_type="tool",
                    node="executor",
                    phase="executing",
                    tool_name=dispatched.tool_name,
                    observation_summary=pruned.summary[:1000],
                    artifact_path=pruned.artifact_path or "",
                    ok=not is_failure_result(dispatched.result),
                    step_count=step_index,
                    total_tokens=tokens_after_llm,
                )

        # ------------------------------------------------------------------
        # 5. 瞬态护栏：成功清零、失败累加，必要时注入重规划通知
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
                    node="executor",
                    phase="reflecting",
                    thought=notice[:500],
                    ok=False,
                    step_count=step_index,
                    consecutive_errors=consecutive_errors,
                )

        # AIMessage 必须携带 tool_calls，才能与其后的 ToolMessage 构成合法原子对
        assistant_message = AIMessage(
            content=response.content or "",
            tool_calls=[
                {"id": call_id, "name": name, "args": dict(args), "type": "tool_call"}
                for call_id, name, args in specs
            ],
        )

        logger.info(
            f"[Executor] 派发 {len(specs)} 个工具，失败 {failure_count} 个，"
            f"连续错误={consecutive_errors}，死循环={loop_detected}"
        )

        return {
            "messages": [assistant_message, *tool_messages],
            "step_count": step_index,
            "total_tokens": tokens_after_llm,
            "consecutive_errors": consecutive_errors,
            "fingerprint_history": fingerprint_history,
            "artifacts": artifacts,
        }

    return executor
