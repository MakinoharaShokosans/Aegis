"""注入样态扫描（纯函数，零 I/O、零 LLM）。

> **定位声明（务必不要误读）**：本模块是**纵深防御与审计手段，不是安全边界**。
> 真正的边界是权限分离——见 ``documents/agent_runtime/12_research_subagent.md``。
>
> 它拦不住任何有创造力的攻击者，也**不允许**被用来宣称"已防住提示注入"。
> 它做两件事：① 给可疑内容打标并写进 ``warnings``，让主 Agent 与人类看到；
> ② 把注入尝试写进轨迹，供离线评测统计频率。

**为什么做成通用纯函数**：外部不可信内容不止网页一种。
后续 MCP 工具输出、工作区技能包正文都需要同一套标注，
因此它属于 ``guardrails/``（确定性策略层）而不是 ``research/`` 内部实现。

**误报代价极低**（多一行 warning），因此宁可宽扫。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Pattern, Tuple

__all__ = [
    "INJECTION_PATTERNS",
    "InjectionMatch",
    "InjectionScan",
    "redact_injection",
    "scan_injection",
    "summarize_matches",
]

#: 命中片段在报告中保留的上下文字符数
_EXCERPT_PAD = 40

#: 单个文本最多报告几处命中（防止超长正文刷屏）
_MAX_MATCHES_PER_TEXT = 12

#: 注入样态库：``(标签, 编译后的正则)``。
#: 正则刻意保持简单（无嵌套量词），避免灾难性回溯。
INJECTION_PATTERNS: Tuple[Tuple[str, Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instruction|prompt|rule|context)",
            re.IGNORECASE,
        ),
    ),
    (
        "instruction_override_zh",
        re.compile(r"(忽略|无视|忘记)(之前|以上|上述|前面|先前)的?(所有)?(指令|提示|规则|要求)"),
    ),
    (
        "system_override",
        re.compile(
            r"(system\s+override|new\s+instructions?\s*[:：]|override\s+the\s+system|"
            r"覆盖系统|新指令\s*[:：])",
            re.IGNORECASE,
        ),
    ),
    (
        "role_switch",
        re.compile(r"(you\s+are\s+now\s+(a|an|the)\b|从现在(起)?你是|接下来你扮演)", re.IGNORECASE),
    ),
    (
        "secrecy",
        re.compile(
            r"((do\s+not|don'?t)\s+(tell|inform|mention|reveal\s+to)\s+(the\s+)?(user|human)|"
            r"不要(告诉|告知|提及|透露给)用户|别让用户(知道|看到))",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_exfiltration",
        re.compile(
            r"((reveal|print|output|show|repeat)\s+(me\s+)?(your\s+)?(system\s+prompt|instructions|rules)|"
            r"(输出|打印|显示|重复)(你的)?(系统提示|系统指令|规则))",
            re.IGNORECASE,
        ),
    ),
    (
        "command_injection",
        re.compile(
            r"((run|execute)\s+(the\s+)?(following|this|below)\s+(command|script|code)|"
            r"(请|立即)?执行(以下|下面|如下)(这条|这些)?(命令|脚本|代码))",
            re.IGNORECASE,
        ),
    ),
    (
        "destructive_intent",
        re.compile(
            r"(rm\s+-rf\s+/|mkfs|dd\s+of=/dev/|:\(\)\s*\{\s*:\|:&\s*\};:|"
            r"格式化(磁盘|硬盘)|删除(全部|所有)文件)",
            re.IGNORECASE,
        ),
    ),
    (
        "credential_access",
        re.compile(
            r"((read|cat|print|send|upload|exfiltrate)\s+\S*\s*(\.env|id_rsa|credential|api[_-]?key|token)|"
            r"(读取|导出|上传|发送)(.{0,10})?(密钥|凭据|私钥|访问令牌))",
            re.IGNORECASE,
        ),
    ),
    (
        "authority_claim",
        re.compile(
            r"((as\s+the\s+(system|administrator|developer|operator)|作为(系统|管理员|开发者|运维))"
            r"[^\n]{0,40}(must|must\s+be|required|必须|立即|务必))",
            re.IGNORECASE,
        ),
    ),
    (
        "hidden_markup",
        re.compile(r"<!--[\s\S]{0,200}?(ignore|system|instruction|overrid|指令)", re.IGNORECASE),
    ),
)


@dataclass(frozen=True, slots=True)
class InjectionMatch:
    """单处命中。

    Attributes:
        label: 命中的样态标签（稳定，可被评测脚本统计）。
        excerpt: 命中位置附近的片段（已压平换行）。
    """

    label: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class InjectionScan:
    """一次扫描的结论。

    Attributes:
        matches: 命中列表（同标签可能多处于命中，已按上限裁剪）。
        suspicious: 是否命中任一可疑样态。
    """

    matches: Tuple[InjectionMatch, ...] = field(default_factory=tuple)
    suspicious: bool = False

    @property
    def labels(self) -> List[str]:
        """去重后的标签列表（保持首次出现顺序）。"""
        seen: List[str] = []
        for match in self.matches:
            if match.label not in seen:
                seen.append(match.label)
        return seen


def _excerpt(text: str, start: int, end: int) -> str:
    """截取命中位置附近的片段并压平换行。"""
    left = max(0, start - _EXCERPT_PAD)
    right = min(len(text), end + _EXCERPT_PAD)
    return text[left:right].replace("\n", " ").strip()


def scan_injection(text: str) -> InjectionScan:
    """扫描文本中的指令样态。

    Args:
        text: 待扫描文本（网页正文、工具输出、技能正文等）。

    Returns:
        :class:`InjectionScan`。空文本返回空结论；永不抛异常。
    """
    if not text:
        return InjectionScan()

    matches: List[InjectionMatch] = []
    try:
        for label, pattern in INJECTION_PATTERNS:
            for found in pattern.finditer(text):
                matches.append(InjectionMatch(label=label, excerpt=_excerpt(text, found.start(), found.end())))
                if len(matches) >= _MAX_MATCHES_PER_TEXT:
                    break
            if len(matches) >= _MAX_MATCHES_PER_TEXT:
                break
    except Exception:  # noqa: BLE001 - 标注功能绝不允许影响主流程
        return InjectionScan()

    return InjectionScan(matches=tuple(matches), suspicious=bool(matches))


def redact_injection(text: str, scan: InjectionScan) -> str:
    """把命中的样态替换为显式标记。

    默认**不启用**（只标注不篡改，便于审计原始内容）；当需要把内容直接喂给
    子智能体时，可选择启用作为额外一层降噪。

    Args:
        text: 原始文本。
        scan: 先前的扫描结论。

    Returns:
        替换后的文本；无命中时原样返回。
    """
    if not scan.suspicious:
        return text

    redacted = text
    for label, pattern in INJECTION_PATTERNS:
        if label in scan.labels:
            redacted = pattern.sub(f"[已移除可疑指令片段:{label}]", redacted)
    return redacted


def summarize_matches(scan: InjectionScan) -> str:
    """生成可直接写入 ``warnings`` 的一行摘要。

    Args:
        scan: 扫描结论。

    Returns:
        摘要文本；无命中时返回空串。
    """
    if not scan.suspicious:
        return ""
    labels = ", ".join(scan.labels)
    return f"检测到 {len(scan.matches)} 处疑似注入指令样态（{labels}），已标注为不可信内容"
