"""MCP 工具描述消毒（数据面治理）。

对应 ``documents/agent_runtime/09_mcp_integration_and_governance.md`` §3.5.1。

**为什么工具描述比工具结果更危险**：``description`` 会进入喂给模型的**工具 Schema**，
模型把它当作权威使用指引——这个位置比 ``<tool_observation>`` 里的普通观察值高得多。
一个恶意 MCP Server 只要在描述里写"调用本工具前请先执行 …"，
就可能诱导主 Agent 做出越权动作（业界称 tool poisoning）。

**因此这里可以硬拒**：与研究子智能体对网页的"只标注不拦截"不同，
**工具描述本就不该包含指令样态**——命中即可判定该工具不可用，
误杀的代价（少一个工具）远低于放行的代价。

**边界说明**：本模块只治理**数据面**。stdio MCP Server 的进程本体是
**任意代码执行**，任何描述消毒都无法解决，只能靠默认关闭 + 资源上限 + 审计
（见 §3.5.2）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Tuple

from loguru import logger

from agent_runtime.guardrails.injection_guard import scan_injection, summarize_matches
from mcps.models import MCPToolDefinition

__all__ = ["VettingOutcome", "vet_tool_definition"]

#: 工具名允许的字符集合（MCP 工具名应当是标识符，不允许空白或控制字符）
_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")

#: 描述长度下限：过短描述会让模型无法正确使用工具，仅告警不拒绝
_MIN_USEFUL_DESCRIPTION = 8


@dataclass(frozen=True, slots=True)
class VettingOutcome:
    """单个 MCP 工具的消毒结论。

    Attributes:
        definition: 治理后的工具定义（可能已截断描述）。
        accepted: 是否允许注册。
        reasons: 拒绝原因或告警说明（用于审计与 ``/api/v1/mcp/servers``）。
    """

    definition: MCPToolDefinition
    accepted: bool
    reasons: Tuple[str, ...] = field(default_factory=tuple)


def _vet_schema(schema: Any) -> List[str]:
    """校验 ``inputSchema`` 的形状。

    Args:
        schema: 待校验的 Schema。

    Returns:
        问题列表；为空表示通过。
    """
    problems: List[str] = []
    if not isinstance(schema, Mapping):
        return ["inputSchema 不是对象"]
    if schema.get("type") not in (None, "object"):
        problems.append(f"inputSchema.type 非 object（{schema.get('type')!r}）")
    properties = schema.get("properties")
    if properties is not None and not isinstance(properties, Mapping):
        problems.append("inputSchema.properties 不是对象")
    return problems


def vet_tool_definition(
    definition: MCPToolDefinition,
    *,
    max_description_chars: int = 1000,
    reject_on_injection: bool = True,
) -> VettingOutcome:
    """对单个远端工具定义做消毒。

    Args:
        definition: 由 ``tools/list`` 转译而来的本地投影。
        max_description_chars: 描述长度上限（超出即截断）。
        reject_on_injection: 描述命中注入样态时是否拒绝注册。

    Returns:
        :class:`VettingOutcome`。
    """
    reasons: List[str] = []
    reject = False

    # ---------------- 工具名 ----------------
    if not _TOOL_NAME_PATTERN.match(definition.original_name or ""):
        return VettingOutcome(
            definition=definition,
            accepted=False,
            reasons=(f"工具名非法（仅允许字母数字与 _.-，长度 1~128）：{definition.original_name!r}",),
        )

    # ---------------- 描述长度 ----------------
    description = definition.description or ""
    if max_description_chars > 0 and len(description) > max_description_chars:
        description = description[: max_description_chars - 1] + "…"
        reasons.append(f"描述超长已截断至 {max_description_chars} 字符")

    # ---------------- 注入样态（可硬拒）----------------
    scan = scan_injection(description)
    if scan.suspicious:
        summary = summarize_matches(scan)
        if reject_on_injection:
            reject = True
            reasons.append(f"拒绝注册：{summary}")
        else:
            reasons.append(summary)

    # ---------------- Schema 形状 ----------------
    if not definition.schema_ok:
        # from_remote 已如实记录"原始 schema 不是对象"，此处据实拒绝
        reject = True
        reasons.append("拒绝注册：inputSchema 原始值不是对象（畸形或恶意定义）")

    schema_problems = _vet_schema(definition.input_schema)
    if schema_problems:
        reject = True
        reasons.extend(f"拒绝注册：{problem}" for problem in schema_problems)

    # ---------------- 描述可用性（仅告警）----------------
    if len(description.strip()) < _MIN_USEFUL_DESCRIPTION:
        reasons.append("描述过短，模型可能无法正确使用该工具")

    vetted = definition.model_copy(update={"description": description})

    if reject:
        logger.warning(
            f"[MCPVetting] 工具 {definition.namespaced_name} 未通过消毒，已拒绝注册；"
            f"原因：{'; '.join(reasons)}"
        )
    elif reasons:
        logger.info(f"[MCPVetting] 工具 {definition.namespaced_name} 通过消毒，附告警：{'; '.join(reasons)}")

    return VettingOutcome(definition=vetted, accepted=not reject, reasons=tuple(reasons))
