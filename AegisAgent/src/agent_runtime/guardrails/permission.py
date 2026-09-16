"""三级权限分级与越级判定（纯函数，零 I/O、零 LLM）。

对应 ``documents/技术选型/bash_shell.md`` §2.3 与
``documents/agent_runtime/04_routing_and_control_flow.md`` §4.5。

## 三级语义

======================  ==========================================================
级别                     允许自动执行的范围
======================  ==========================================================
``read_only``            只读探测（查看文件、检索、读日志）
``workspace_write``      工作区内读写、编译、测试、本地 git 操作
``full_permissions``     网络外联、依赖安装、git 推送、全局环境变更
======================  ==========================================================

## 为什么放在 ``guardrails/``

判定必须**确定性**且**可离线单测**：它决定"要不要打断人去审批"，
一旦引入模型判断就会出现"有时拦有时不拦"的不可解释行为。
因此本模块只有纯函数与配置表，不依赖 LangGraph、不依赖工具实现。

## 为什么"未知工具"按最高级别处理

无法静态推理其副作用的工具（第三方 MCP 工具是典型）默认要求最高权限，
即"在工作区写入级别下会触发人工审批"。这与技能包的"不可信来源默认拒绝"
是同一取向：**默认保守，放宽需要显式配置**。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Pattern, Sequence, Tuple

from loguru import logger

__all__ = [
    "LEVEL_ORDER",
    "PermissionDecision",
    "action_signature",
    "check_permission",
    "normalize_level",
    "required_level_for",
]

#: 权限级别偏序（数值越大权限越高）
LEVEL_ORDER: dict[str, int] = {
    "read_only": 0,
    "workspace_write": 1,
    "full_permissions": 2,
}

_DEFAULT_LEVEL = "workspace_write"

#: 动作类型标签（稳定值，供前端做图标与文案映射）
ACTION_READ = "read"
ACTION_WORKSPACE_WRITE = "workspace_write"
ACTION_NETWORK_EGRESS = "network_egress"
ACTION_GLOBAL_ENV = "global_env"
ACTION_PRIVILEGED = "privileged"
ACTION_UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    """一次工具调用的权限判定结论。

    Attributes:
        allowed: 在当前授权级别下是否可**直接执行**（False 即需要人工审批）。
        required_level: 该动作所需的最低级别。
        current_level: 当前会话授权级别。
        action_type: 动作类型标签（网络外联 / 全局环境变更 / 特权 …）。
        action_summary: 面向审批人的一句话动作摘要（含关键命令）。
        reason: 判定原因（用于审批卡片与日志）。
    """

    allowed: bool
    required_level: str
    current_level: str
    action_type: str
    action_summary: str
    reason: str


def normalize_level(level: Any) -> str:
    """把任意输入归一为合法级别（未知值回落到默认级别）。

    Args:
        level: 待归一的值。

    Returns:
        ``read_only`` / ``workspace_write`` / ``full_permissions`` 之一。
    """
    text = str(level or "").strip().lower()
    return text if text in LEVEL_ORDER else _DEFAULT_LEVEL


def _compile(patterns: Sequence[str]) -> List[Pattern[str]]:
    """把配置中的正则字符串编译为 Pattern（编译失败的条目跳过并告警）。"""
    compiled: List[Pattern[str]] = []
    for pattern in patterns or []:
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error as exc:
            logger.error(f"[Permission] 忽略非法的权限正则 {pattern!r}: {exc}")
    return compiled


def _summarize(tool_name: str, args: Mapping[str, Any], limit: int = 200) -> str:
    """生成面向审批人的动作摘要。"""
    if tool_name == "bash":
        command = str(args.get("command") or "").strip()
        return command[:limit] if command else "(空命令)"
    if not args:
        return tool_name
    rendered = ", ".join(f"{key}={str(value)[:60]}" for key, value in list(args.items())[:4])
    return f"{tool_name}({rendered})"[:limit]


def _classify_bash(
    command: str,
    full_patterns: Sequence[str],
    write_patterns: Sequence[str],
) -> Tuple[str, str, str]:
    """对 bash 命令做三分类。

    Args:
        command: 命令原文。
        full_patterns: 需要 ``full_permissions`` 的模式（网络外联 / 全局环境）。
        write_patterns: 需要 ``workspace_write`` 的模式（写文件 / 编译 / 本地 git）。

    Returns:
        ``(级别, 动作类型, 原因)``。
    """
    for pattern in _compile(full_patterns):
        if pattern.search(command):
            action_type = (
                ACTION_NETWORK_EGRESS
                if re.search(r"\b(git\s+push|curl|wget|ssh|scp|nc|telnet)\b", command, re.IGNORECASE)
                else ACTION_GLOBAL_ENV
            )
            return "full_permissions", action_type, f"命令匹配高权限模式 {pattern.pattern!r}"

    for pattern in _compile(write_patterns):
        if pattern.search(command):
            return "workspace_write", ACTION_WORKSPACE_WRITE, f"命令匹配写入模式 {pattern.pattern!r}"

    return "read_only", ACTION_READ, "命令未匹配任何写入或外联模式，按只读处理"


def required_level_for(
    tool_name: str,
    args: Mapping[str, Any],
    config: Any,
) -> Tuple[str, str, str]:
    """推导一次工具调用所需的权限级别。

    判定顺序：**显式工具名单 → bash 命令分类 → 未知工具兜底**。

    Args:
        tool_name: 工具名。
        args: 工具入参。
        config: ``PermissionsConfig``。

    Returns:
        ``(级别, 动作类型, 原因)``。
    """
    name = str(tool_name or "")

    if name in set(getattr(config, "full_permission_tools", []) or []):
        return "full_permissions", ACTION_PRIVILEGED, "该工具被配置为需要全权限"

    if name in set(getattr(config, "workspace_write_tools", []) or []):
        return "workspace_write", ACTION_WORKSPACE_WRITE, "该工具被配置为工作区写入类"

    if name in set(getattr(config, "read_only_tools", []) or []):
        return "read_only", ACTION_READ, "该工具被配置为只读类"

    bash_tools = set(getattr(config, "bash_tools", []) or ["bash"])
    if name in bash_tools:
        command = str(args.get("command") or "")
        return _classify_bash(
            command,
            getattr(config, "full_permission_patterns", []) or [],
            getattr(config, "workspace_write_patterns", []) or [],
        )

    level = normalize_level(getattr(config, "unknown_tool_level", "full_permissions"))
    return level, ACTION_UNKNOWN, f"未知工具 {name}，按配置的保守级别处理"


def check_permission(
    current_level: Any,
    tool_name: str,
    args: Mapping[str, Any],
    config: Any,
) -> PermissionDecision:
    """判定一次工具调用是否越级。

    Args:
        current_level: 当前会话授权级别。
        tool_name: 工具名。
        args: 工具入参。
        config: ``PermissionsConfig``。

    Returns:
        :class:`PermissionDecision`；``allowed=False`` 表示需要人工审批。
    """
    current = normalize_level(current_level)
    required, action_type, reason = required_level_for(tool_name, args, config)
    allowed = LEVEL_ORDER[required] <= LEVEL_ORDER[current]

    return PermissionDecision(
        allowed=allowed,
        required_level=required,
        current_level=current,
        action_type=action_type,
        action_summary=_summarize(tool_name, args),
        reason=reason if allowed else f"{reason}；所需级别 {required} 高于当前级别 {current}",
    )


def action_signature(tool_name: str, args: Mapping[str, Any]) -> str:
    """计算"会话内永久放行"用的动作指纹。

    与死循环检测的指纹同构（工具名 + 规范化参数），但**用途不同**：
    这里代表"用户已批准过这一类动作"。

    Args:
        tool_name: 工具名。
        args: 工具入参。

    Returns:
        16 位十六进制摘要。
    """
    import json

    payload = json.dumps(
        {"tool": str(tool_name), "args": args}, sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:16]
