"""``executor`` 节点：把决策指令翻译成具体工具调用（fast 层）。

对应 ``documents/agent_runtime/03_node_specification.md`` §4.3。

**职责单一化（HITL 引入后的调整）**：本节点**只**做三件事——

1. 调用 fast 模型，把 planner 的自然语言指令翻译成 ``tool_calls``；
2. 做 Canary Token 泄露检测（提示词窃取 / 工具外带注入的熔断点）；
3. 产出携带 ``tool_calls`` 的 ``AIMessage``，交给 ``tool_runner`` 执行。

**为什么把"派发"拆到 ``tool_runner``**：LangGraph 的 ``interrupt()`` 在恢复时会
**从头重跑整个节点**。若把权限审批放在本节点内（紧邻派发），审批通过后重跑会
让本次 fast 模型调用**再发生一次**——既重复计费，又可能因采样差异产生不同的
``tool_calls``，导致"用户批准的命令"与"实际执行的命令"不一致。
拆分后审批发生在 ``tool_runner``（纯判定、无 LLM 调用），重跑代价可忽略。
"""

from __future__ import annotations

import time
from typing import Any, Dict, Mapping, Optional

from langchain_core.messages import AIMessage
from loguru import logger

from agent_runtime.context import ContextManager
from agent_runtime.errors import LLMUnavailableError
from agent_runtime.guardrails.canary import detect_canary_leak
from agent_runtime.llm.client import LLMGateway, to_openai_messages
from agent_runtime.nodes.base import NodeFn, to_tool_call_specs
from agent_runtime.observability.event_bus import TaskEventBus
from agent_runtime.observability.trajectory import TrajectoryRecorder
from agent_runtime.prompt_loader import PromptLibrary
from tools.core.registry import ToolRegistry

__all__ = ["build_executor_node"]


def build_executor_node(
    gateway: LLMGateway,
    registry: ToolRegistry,
    prompts: PromptLibrary,
    context: ContextManager,
    recorder: Optional[TrajectoryRecorder] = None,
    event_bus: Optional[TaskEventBus] = None,
) -> NodeFn:
    """构造 ``executor`` 节点。

    Args:
        gateway: 双模型网关。
        registry: 工具注册表（用于导出 function calling Schema）。
        prompts: 提示词库。
        context: 上下文装配器。
        recorder: 轨迹记录器（可选旁路）。
        event_bus: 事件总线（可选旁路）。

    Returns:
        节点函数。
    """

    async def executor(state: Mapping[str, Any]) -> Dict[str, Any]:
        """生成工具调用（不执行）。

        Args:
            state: ``AgentState``（只读）。

        Returns:
            消息、步数与 Token 增量；LLM 全链路不可用或检测到金丝雀泄露时置位熔断。
        """
        base_tokens = int(state.get("total_tokens", 0))
        step_index = int(state.get("step_count", 0)) + 1

        messages = context.assemble(state, node_instruction=prompts.load("executor"))
        tool_schemas = registry.to_openai_tools()

        t0 = time.time()
        try:
            response = await gateway.invoke("fast", messages, tools=tool_schemas)
        except LLMUnavailableError as exc:
            logger.error(f"[Executor] LLM 全链路不可用: {exc}")
            if event_bus is not None:
                await event_bus.emit({
                    "event": "llm.call",
                    "id": f"llm-executor-{step_index}-{time.time()}",
                    "node": "executor",
                    "step": step_index,
                    "tier": "fast",
                    "model": "fast-model",
                    "messages": to_openai_messages(messages),
                    "tools": tool_schemas,
                    "response": {"content": "", "tool_calls": [], "finish_reason": "error"},
                    "tokens": 0,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "error": str(exc),
                })
            return {"should_terminate": True, "termination_reason": f"LLM 不可用: {exc}"}

        duration_ms = int((time.time() - t0) * 1000)
        if event_bus is not None:
            await event_bus.emit({
                "event": "llm.call",
                "id": f"llm-executor-{step_index}-{time.time()}",
                "node": "executor",
                "step": step_index,
                "tier": "fast",
                "model": response.endpoint_name or "gpt-5.6-luna",
                "messages": to_openai_messages(messages),
                "tools": tool_schemas,
                "response": {
                    "content": response.content,
                    "tool_calls": response.tool_calls,
                    "finish_reason": response.finish_reason or "stop",
                },
                "tokens": response.total_tokens,
                "duration_ms": duration_ms,
            })

        tokens_after_llm = base_tokens + response.total_tokens

        # ------------------------------------------------------------------
        # 安全防御：Canary Token 泄露检测（提示词窃取 / 工具外带注入熔断）
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

        specs = to_tool_call_specs(response.tool_calls)
        if not specs:
            logger.info("[Executor] 本轮未产生工具调用")
            return {
                "messages": [AIMessage(content=response.content or "")],
                "step_count": step_index,
                "total_tokens": tokens_after_llm,
            }

        # 携带 tool_calls 的 AIMessage 是 tool_runner 的输入，
        # 也是与其后 ToolMessage 构成原子对的必要前提
        assistant_message = AIMessage(
            content=response.content or "",
            tool_calls=[
                {"id": call_id, "name": name, "args": dict(args), "type": "tool_call"}
                for call_id, name, args in specs
            ],
        )

        logger.info(f"[Executor] 已生成 {len(specs)} 个工具调用，交由 tool_runner 执行")

        return {
            "messages": [assistant_message],
            "step_count": step_index,
            "total_tokens": tokens_after_llm,
        }

    return executor
