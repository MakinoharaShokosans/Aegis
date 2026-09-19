"""``planner`` 节点：宏观规划与反思重规划（reasoning 层）。

对应 ``documents/agent_runtime/03_node_specification.md`` §4.1。

**关键设计**：planner **不产出 ``tool_calls``**。它只输出"要做什么"的自然语言决策指令
与里程碑状态变更；"具体调用哪个工具的哪些参数"下沉给 fast 层的 ``executor``。
这样 reasoning 模型专注高价值判断，便宜快速的模型承担格式化的动作翻译。

**结构化输出**：为了能确定性更新里程碑，本节点强制 JSON 输出::

    {"thought": "...", "milestone_updates": [{"id": 1, "status": "completed"}], "next_step": "..."}

解析失败时**优雅降级**：把原始文本当作决策指令，不改动里程碑（不因格式问题中断任务）。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

from langchain_core.messages import AIMessage
from loguru import logger

from agent_runtime.context import ContextManager
from agent_runtime.errors import LLMUnavailableError
from agent_runtime.guardrails.canary import detect_canary_leak
from agent_runtime.llm.client import LLMGateway, to_openai_messages
from agent_runtime.nodes.base import (
    NodeFn,
    apply_milestone_updates,
    coerce_milestones,
    extract_json_object,
)
from agent_runtime.observability.event_bus import TaskEventBus
from agent_runtime.observability.trajectory import TrajectoryRecorder
from agent_runtime.prompt_loader import PromptLibrary
from agent_runtime.state import Milestone

__all__ = ["build_planner_node", "format_structured_verdict_to_markdown"]


def format_structured_verdict_to_markdown(verdict: Dict[str, Any]) -> Optional[str]:
    """若模型产出了自定义的结构化分析/总结字典而非标准 direct_response 纯文本，
    防御性地自动将其转换为结构清晰、排版优美的 Markdown 交付文本。

    Args:
        verdict: 模型返回并提取出的 JSON 字典。

    Returns:
        转换后的 Markdown 文本字符串；若无需转换或不符合数据结构特征则返回 None。
    """
    if not isinstance(verdict, dict) or not verdict:
        return None

    # 如果有显式直接文本字段且不是裸 JSON 字符串，优先使用
    direct = (
        verdict.get("direct_response")
        or verdict.get("reply")
        or verdict.get("answer")
        or verdict.get("direct_answer")
    )
    if direct and isinstance(direct, str):
        trimmed = direct.strip()
        if not (trimmed.startswith("{") and trimmed.endswith("}")):
            return trimmed

    # 检查是否包含自定义结构化业务结果字段
    known_keys = {
        "topic", "summary", "result", "findings", "sources", "limitations",
        "notes", "data", "details", "content", "file", "verified",
    }
    present_keys = set(verdict.keys()) & known_keys
    if not present_keys:
        return None

    parts: List[str] = []

    # 1. 标题 / 主题
    topic = verdict.get("topic") or verdict.get("title")
    if topic and isinstance(topic, str):
        parts.append(f"### {topic.strip()}\n")

    # 2. 核心结论 / 摘要
    summary = verdict.get("summary") or verdict.get("result") or verdict.get("findings")
    if isinstance(summary, dict):
        for k, v in summary.items():
            k_clean = str(k).replace("_", " ").capitalize()
            parts.append(f"- **{k_clean}**：{v}")
    elif isinstance(summary, list):
        for item in summary:
            parts.append(f"- {item}")
    elif summary and isinstance(summary, str):
        parts.append(summary.strip())

    # 3. 详细数据 / 文件信息
    if "file" in verdict or "path" in verdict or "verified" in verdict:
        file_info = []
        if verdict.get("file"):
            file_info.append(f"- **目标文件**：`{verdict['file']}`")
        if verdict.get("path"):
            file_info.append(f"- **绝对路径**：`{verdict['path']}`")
        if verdict.get("verified"):
            file_info.append(f"- **校验状态**：{verdict['verified']}")
        if file_info:
            parts.append("\n**文件操作详情**：")
            parts.extend(file_info)

    details = verdict.get("details") or verdict.get("data")
    if isinstance(details, dict):
        parts.append("\n**详细数据**：")
        for k, v in details.items():
            k_clean = str(k).replace("_", " ").capitalize()
            parts.append(f"- **{k_clean}**：{v}")
    elif isinstance(details, list):
        parts.append("\n**详细列表**：")
        for item in details:
            parts.append(f"- {item}")
    elif details and isinstance(details, str):
        parts.append(f"\n{details.strip()}")

    # 4. 来源引用
    sources = verdict.get("sources") or verdict.get("references")
    if isinstance(sources, list) and sources:
        parts.append("\n**参考来源**：")
        for s in sources:
            parts.append(f"- {s}")

    # 5. 局限性 / 补充说明
    limitations = verdict.get("limitations") or verdict.get("notes")
    if isinstance(limitations, list) and limitations:
        parts.append("\n**补充说明与局限性**：")
        for l in limitations:
            parts.append(f"- {l}")

    formatted = "\n".join(parts).strip()
    return formatted if formatted else None


def build_planner_node(
    gateway: LLMGateway,
    context: ContextManager,
    prompts: PromptLibrary,
    recorder: Optional[TrajectoryRecorder] = None,
    event_bus: Optional[TaskEventBus] = None,
) -> NodeFn:
    """构造 ``planner`` 节点。

    Args:
        gateway: 双模型网关。
        context: 上下文装配器。
        prompts: 提示词库。
        recorder: 轨迹记录器（可选旁路）。
        event_bus: 事件总线（可选旁路）。

    Returns:
        节点函数。
    """

    async def planner(state: Mapping[str, Any]) -> Dict[str, Any]:
        """产出下一步决策指令并更新里程碑状态。

        Args:
            state: ``AgentState``（只读）。

        Returns:
            消息、里程碑与 Token 计数增量；LLM 全链路不可用时置位熔断。
        """
        messages = context.assemble(state, node_instruction=prompts.load("planner"))
        step_num = int(state.get("step_count", 0))

        t0 = time.time()
        try:
            response = await gateway.invoke("reasoning", messages, force_json=True)
        except LLMUnavailableError as exc:
            logger.error(f"[Planner] LLM 全链路不可用: {exc}")
            if event_bus is not None:
                await event_bus.emit({
                    "event": "llm.call",
                    "id": f"llm-planner-{step_num}-{time.time()}",
                    "node": "planner",
                    "step": step_num,
                    "tier": "reasoning",
                    "model": "reasoning-model",
                    "messages": to_openai_messages(messages),
                    "tools": None,
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
                "id": f"llm-planner-{step_num}-{time.time()}",
                "node": "planner",
                "step": step_num,
                "tier": "reasoning",
                "model": response.endpoint_name or "gpt-5.6-terra",
                "messages": to_openai_messages(messages),
                "tools": None,
                "response": {
                    "content": response.content,
                    "tool_calls": response.tool_calls,
                    "finish_reason": response.finish_reason or "stop",
                },
                "tokens": response.total_tokens,
                "duration_ms": duration_ms,
            })

        tokens_after = int(state.get("total_tokens", 0)) + response.total_tokens

        # ------------------------------------------------------------------
        # 安全防御：Canary Token 泄露检测
        # ------------------------------------------------------------------
        canary_token = str(state.get("canary_token") or "")
        if canary_token and detect_canary_leak(response.content, canary_token):
            logger.critical("[Planner] 安全熔断：检测到 Canary Token 泄露！")
            if recorder is not None:
                await recorder.record(
                    record_type="guard",
                    node="planner",
                    phase="planning",
                    thought="[SECURITY] Canary Token leak detected in planner response",
                    ok=False,
                    step_count=int(state.get("step_count", 0)),
                    total_tokens=tokens_after,
                )
            return {
                "should_terminate": True,
                "termination_reason": "[SECURITY] Prompt leak detected via canary token",
                "total_tokens": tokens_after,
            }

        verdict = extract_json_object(response.content) or {}
        if not verdict and response.content:
            logger.warning("[Planner] 未能解析结构化输出，降级为纯文本指令")

        raw_thought = verdict.get("thought") or response.content or ""
        direct_response = format_structured_verdict_to_markdown(verdict)
        raw_directive = direct_response or verdict.get("next_step") or verdict.get("message") or verdict.get("directive") or raw_thought

        thought = str(raw_thought).strip()
        directive = str(raw_directive).strip()

        # 防御性清洗：若模型把结果封装在 {"message": ...} 或 {"thought": ...} 字符串内，提取并格式化纯文本
        if thought.startswith("{") and thought.endswith("}"):
            inner = extract_json_object(thought)
            if inner:
                thought = (
                    format_structured_verdict_to_markdown(inner)
                    or str(inner.get("thought") or inner.get("direct_response") or inner.get("message") or inner.get("reply") or inner.get("next_step") or thought).strip()
                )
        if directive.startswith("{") and directive.endswith("}"):
            inner = extract_json_object(directive)
            if inner:
                directive = (
                    format_structured_verdict_to_markdown(inner)
                    or str(inner.get("direct_response") or inner.get("next_step") or inner.get("message") or inner.get("reply") or inner.get("thought") or directive).strip()
                )

        # 首次规划：由 planner 产出完整里程碑计划；后续轮次只做状态增量更新。
        # 这样"里程碑"是模型自主分解的产物，而不是硬编码的固定流程。
        existing = coerce_milestones(list(state.get("milestones") or []))
        if not existing and verdict.get("milestones"):
            milestones = coerce_milestones(verdict["milestones"])
        elif existing:
            milestones = apply_milestone_updates(existing, verdict.get("milestone_updates"))
        else:
            milestones = []

        is_completed = bool(
            direct_response
            or verdict.get("is_completed")
            or verdict.get("all_completed")
            or str(verdict.get("status", "")).lower() == "completed"
        )
        if is_completed:
            if milestones:
                milestones = [m.model_copy(update={"status": "completed"}) for m in milestones]
            else:
                milestones = [Milestone(id=1, title="响应用户咨询与交付任务", status="completed")]

        logger.info(f"[Planner] 决策指令已生成（tokens={response.total_tokens}）")

        if recorder is not None:
            await recorder.record(
                record_type="node",
                node="planner",
                phase="planning",
                thought=thought[:1000],
                step_count=int(state.get("step_count", 0)),
                total_tokens=int(state.get("total_tokens", 0)) + response.total_tokens,
                consecutive_errors=int(state.get("consecutive_errors", 0)),
            )

        return {
            "messages": [AIMessage(content=directive or "继续推进当前里程碑。")],
            "milestones": milestones,
            "total_tokens": int(state.get("total_tokens", 0)) + response.total_tokens,
        }

    return planner
