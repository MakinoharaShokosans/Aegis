"""CommandAudit：高危命令正则黑名单前置拦截与路径越界校验。

职责（ADR §2.3 前置命令审计 / Path Escape Guard）：
1. **高危指令黑名单**：在命令派发前做纯正则语法拦截（确定性、零 LLM），覆盖
   ``rm -rf /``、``mkfs``、``dd of=/dev/*``、``shutdown``/``reboot``、fork bomb、
   对 ``/etc/passwd`` 等敏感系统路径的写操作、``chmod -R 777 /`` 等破坏性指令；
2. **路径越界校验**：``ensure_within_root`` 用 ``Path.resolve()`` 规范化（含符号链接）
   后判断目标是否位于工作区 ``root`` 子树内，越界即抛 ``PathEscapeError``；
3. **强类型错误**：``AuditRejected`` 携带 ``reason`` 等结构化字段，供 HTTP 层转 400。

本模块为纯函数式确定性逻辑，不做任何 I/O、不依赖配置，可离线单测。

规范：documents/技术选型/bash_shell.md 第 2.3 节；documents/agent_runtime/10_directory_structure.md 裁决项⑦
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "AuditRejected",
    "PathEscapeError",
    "CommandAudit",
    "ensure_within_root",
    "SAFE_WRITE_DEVICES",
]

# ==============================================================================
# 1. 异常契约
# ==============================================================================


class AuditRejected(Exception):
    """高危命令被前置审计拒绝。

    Attributes:
        reason: 人类可读的拒绝原因（供模型自我修正时理解）。
        rule: 命中的规则标识（如 ``RM_RF_ROOT``）。
        matched: 命中的命令片段（截断展示，便于定位）。
        command: 被审计的原始命令。
    """

    def __init__(
        self,
        reason: str,
        *,
        rule: str = "",
        matched: str = "",
        command: str = "",
    ) -> None:
        """初始化审计拒绝异常。

        Args:
            reason: 拒绝原因描述。
            rule: 命中的规则标识。
            matched: 命中的命令片段。
            command: 被审计的原始命令。
        """
        super().__init__(reason)
        self.reason = reason
        self.rule = rule
        self.matched = matched
        self.command = command

    def to_dict(self) -> Dict[str, Any]:
        """转换为结构化错误字典（HTTP 400 响应体载荷）。

        Returns:
            含 ``reason`` / ``rule`` / ``matched`` 的字典（``matched`` 截断至 200 字符）。
        """
        return {
            "reason": self.reason,
            "rule": self.rule,
            "matched": self.matched[:200],
        }


class PathEscapeError(ValueError):
    """路径越界：目标经规范化后落在工作区根目录子树之外。

    Attributes:
        path: 原始目标路径。
        root: 工作区根目录（已规范化）。
        resolved: 规范化后的绝对路径。
    """

    def __init__(self, path: str | Path, root: str | Path, *, resolved: Optional[Path] = None) -> None:
        """初始化路径越界异常。

        Args:
            path: 原始目标路径。
            root: 工作区根目录。
            resolved: 规范化后的绝对路径；为 ``None`` 时由 ``path`` 推导。
        """
        self.path = str(path)
        self.root = str(root)
        self.resolved = resolved if resolved is not None else Path(path).expanduser().resolve()
        super().__init__(
            f"路径越界：{self.path!r} 规范化后为 {self.resolved}，"
            f"不在工作区根 {self.root} 子树内（ADR §2.3 禁止逃逸到其他工作区或系统目录）"
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为结构化错误字典（HTTP 422 响应体载荷）。

        Returns:
            含 ``path`` / ``root`` / ``resolved`` 的字典。
        """
        return {"path": self.path, "root": self.root, "resolved": str(self.resolved)}


# ==============================================================================
# 2. 正则规则库（高危命令黑名单）
# ==============================================================================

#: ``rm`` 的递归 + 强制组合标志（-rf / -fr / -r -f / --recursive --force）
_RM_RECURSIVE_FORCE = re.compile(
    r"\brm\b(?=[^\n;&|]*\s-{1,2}[A-Za-z-]*(?:r[A-Za-z]*f|f[A-Za-z]*r)[A-Za-z]*)",
    re.IGNORECASE,
)
#: 危险根目标：命令段落的独立 ``/`` 或 ``/*`` 参数
_ROOT_TARGET = re.compile(r"(?:^|\s)(?:--\s+)?/(?:\*)?(?=\s|$|[;&|])")
#: 敏感系统路径（写操作即拒绝）
_SENSITIVE_PATH = re.compile(
    r"/(?:etc/(?:passwd|shadow|gshadow|group|sudoers|fstab|hosts|resolv\.conf)"
    r"|boot(?:/|$)|sys(?:/|$)|proc/(?:sys|kallsyms|mem)"
    r"|dev/(?:sd[a-z]|nvme\d|vd[a-z]|hd[a-z]|mmcblk\d|loop\d))",
)
#: 写操作指示符（重定向、tee、原地编辑、权限/属主变更、搬运删除等）
_WRITE_OPERATION = re.compile(
    r"(?:>>?"
    r"|\btee\b"
    r"|\bsed\s+-i\b"
    r"|\bperl\s+-i\b"
    r"|\btruncate\b"
    r"|\bchmod\b|\bchown\b|\bchgrp\b"
    r"|\bmv\b|\bcp\b|\brm\b|\bln\b|\binstall\b"
    r"|\bdd\b|\bmkfs\b|\bmkdir\b|\btouch\b|\btee\b)"
)
#: 递归放开全部权限（chmod -R 777 / chown -R ...）
_RECURSIVE_PERMISSION = re.compile(
    r"\bch(?:mod|own|grp)\b[^\n;&|]*\s-[A-Za-z-]*R[A-Za-z-]*",
    re.IGNORECASE,
)
#: 777 / a+rwx 全开放权限字面量
_FULL_PERMISSION = re.compile(r"\b(?:0?777|a\+rwx)\b")

#: ``mkfs`` / ``mkfs.ext4`` 等格式化指令
_MKFS = re.compile(r"\bmkfs(?:\.[A-Za-z0-9]+)?\b")
#: ``dd of=/dev/*`` 裸设备写入
_DD_TO_DEVICE = re.compile(r"\bdd\b[^\n;&|]*\bof\s*=\s*/dev/")
#: 关机/重启类指令
_POWER_CONTROL = re.compile(
    r"\b(?:shutdown|reboot|halt|poweroff)\b"
    r"|\binit\s+[06]\b"
    r"|\bsystemctl\s+(?:reboot|poweroff|halt)\b"
)
#: Shell fork bomb（``:(){ :|:& };:``）
_FORK_BOMB = re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;?\s*:")

#: 重定向目标提取（``> file`` / ``>> file`` / ``2> file`` / ``2>&1``）
_REDIRECT_TARGET = re.compile(r"(?:\d?)>>?\s*(&?[^\s;&|<>()]+)")
#: ``tee`` 目标提取（含 ``-a`` 等选项）
_TEE_TARGET = re.compile(r"\btee\b(?:\s+-{1,2}[A-Za-z-]+)*\s+([^\s;&|<>()]+)")
#: ``dd of=`` 目标提取
_DD_TARGET = re.compile(r"\bof\s*=\s*([^\s;&|<>()]+)")

#: 允许写入的安全设备/伪文件（并非工作区内的真实文件，放行以避免误杀）
SAFE_WRITE_DEVICES = frozenset(
    {
        "/dev/null",
        "/dev/zero",
        "/dev/full",
        "/dev/tty",
        "/dev/stdout",
        "/dev/stderr",
        "/dev/stdin",
        "/dev/random",
        "/dev/urandom",
    }
)


@dataclass(frozen=True)
class _Rule:
    """单条黑名单规则。

    Attributes:
        rule_id: 规则标识（返回给调用方的稳定枚举值）。
        description: 拒绝原因描述。
        detector: 检测函数；命中返回命中片段，未命中返回 ``None``。
    """

    rule_id: str
    description: str
    detector: Callable[[str], Optional[str]]


def _match(pattern: re.Pattern[str], text: str) -> Optional[str]:
    """在文本中查找正则命中片段。

    Args:
        pattern: 已编译的正则。
        text: 待检测文本。

    Returns:
        命中片段字符串；未命中返回 ``None``。
    """
    found = pattern.search(text)
    return found.group(0) if found else None


def _detect_rm_rf_root(command: str) -> Optional[str]:
    """检测递归强制删除根目录（``rm -rf /`` 及其变体）。

    Args:
        command: 待检测命令。

    Returns:
        命中片段；未命中返回 ``None``。
    """
    if _RM_RECURSIVE_FORCE.search(command):
        return _match(_ROOT_TARGET, command)
    return None


def _detect_mkfs(command: str) -> Optional[str]:
    """检测文件系统格式化指令（``mkfs`` / ``mkfs.ext4``）。

    Args:
        command: 待检测命令。

    Returns:
        命中片段；未命中返回 ``None``。
    """
    return _match(_MKFS, command)


def _detect_dd_to_device(command: str) -> Optional[str]:
    """检测裸设备写入（``dd of=/dev/sda`` 等）。

    Args:
        command: 待检测命令。

    Returns:
        命中片段；未命中返回 ``None``。
    """
    return _match(_DD_TO_DEVICE, command)


def _detect_power_control(command: str) -> Optional[str]:
    """检测关机/重启类指令（``shutdown`` / ``reboot`` / ``systemctl reboot``）。

    Args:
        command: 待检测命令。

    Returns:
        命中片段；未命中返回 ``None``。
    """
    return _match(_POWER_CONTROL, command)


def _detect_fork_bomb(command: str) -> Optional[str]:
    """检测 Shell fork bomb（``:(){ :|:& };:`` 及其空白变体）。

    Args:
        command: 待检测命令。

    Returns:
        命中片段；未命中返回 ``None``。
    """
    return _match(_FORK_BOMB, command)


def _detect_sensitive_write(command: str) -> Optional[str]:
    """检测对敏感系统路径的写操作。

    采用「敏感路径 ∧ 写操作」双条件，避免把 ``cat /etc/passwd`` 之类的只读指令误杀。

    Args:
        command: 待检测命令。

    Returns:
        命中片段；未命中返回 ``None``。
    """
    if not _SENSITIVE_PATH.search(command):
        return None
    return _match(_WRITE_OPERATION, command)


def _detect_recursive_root_permission(command: str) -> Optional[str]:
    """检测对根目录递归放开权限（``chmod -R 777 /`` / ``chown -R``）。

    Args:
        command: 待检测命令。

    Returns:
        命中片段；未命中返回 ``None``。
    """
    if _RECURSIVE_PERMISSION.search(command) and _ROOT_TARGET.search(command):
        return _match(_ROOT_TARGET, command)
    if _FULL_PERMISSION.search(command) and _ROOT_TARGET.search(command):
        return _match(_FULL_PERMISSION, command)
    return None


#: 黑名单规则表（顺序即匹配顺序，先命中先拒绝）
_RULES: Tuple[_Rule, ...] = (
    _Rule("RM_RF_ROOT", "禁止递归强制删除根目录（rm -rf /）", _detect_rm_rf_root),
    _Rule("MKFS", "禁止格式化文件系统（mkfs）", _detect_mkfs),
    _Rule("DD_TO_DEVICE", "禁止向裸设备写入（dd of=/dev/*）", _detect_dd_to_device),
    _Rule("POWER_CONTROL", "禁止关机/重启宿主机（shutdown/reboot）", _detect_power_control),
    _Rule("FORK_BOMB", "禁止 Shell fork bomb", _detect_fork_bomb),
    _Rule("SENSITIVE_SYSTEM_WRITE", "禁止写入敏感系统路径（如 /etc/passwd）", _detect_sensitive_write),
    _Rule(
        "RECURSIVE_ROOT_PERMISSION",
        "禁止对根目录递归放开权限（chmod -R 777 /）",
        _detect_recursive_root_permission,
    ),
)


# ==============================================================================
# 3. 路径越界校验
# ==============================================================================


def ensure_within_root(path: str | Path, root: str | Path, *, base: Optional[str | Path] = None) -> Path:
    """校验并规范化目标路径，确保其位于工作区根目录子树内。

    规范化使用 ``Path.resolve()``（同时解析 ``..`` 与符号链接），因此
    ``/workspace/../etc/passwd`` 与指向外部的软链接都会被识别为越界。

    Args:
        path: 待校验的目标路径（绝对路径或相对路径）。
        root: 工作区根目录（越界边界）。
        base: 相对路径的解析基准；默认与 ``root`` 相同（命令的 cwd 即工作区根）。

    Returns:
        规范化后的绝对路径。

    Raises:
        PathEscapeError: 目标规范化后不在 ``root`` 子树内（含 ``root`` 自身）。
    """
    root_resolved = Path(root).expanduser().resolve()
    target = Path(path).expanduser()
    if not target.is_absolute():
        anchor = Path(base).expanduser().resolve() if base is not None else root_resolved
        target = anchor / target
    resolved = target.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise PathEscapeError(path, root_resolved, resolved=resolved)
    return resolved


# ==============================================================================
# 4. 审计器
# ==============================================================================


class CommandAudit:
    """命令审计器：黑名单拦截 + 写目标越界校验。

    Attributes:
        _extra_patterns: 调用方追加的额外拒绝正则（如按工作区策略注入）。
    """

    def __init__(self, extra_deny_patterns: Sequence[str] = ()) -> None:
        """初始化审计器。

        Args:
            extra_deny_patterns: 追加的高危正则（可为空）。

        Raises:
            re.error: 追加正则语法非法时抛出。
        """
        self._extra_patterns: Tuple[re.Pattern[str], ...] = tuple(
            re.compile(pattern) for pattern in extra_deny_patterns
        )

    def audit(self, command: str) -> None:
        """对命令做前置黑名单审计，命中即拒绝。

        Args:
            command: 待执行命令原文。

        Raises:
            AuditRejected: 命令为空或命中任一黑名单规则时抛出。
        """
        stripped = command.strip()
        if not stripped:
            raise AuditRejected("命令为空，拒绝派发", rule="EMPTY_COMMAND", command=command)

        for rule in _RULES:
            matched = rule.detector(stripped)
            if matched:
                raise AuditRejected(
                    rule.description,
                    rule=rule.rule_id,
                    matched=matched,
                    command=stripped,
                )

        for pattern in self._extra_patterns:
            found = pattern.search(stripped)
            if found:
                raise AuditRejected(
                    "命令命中工作区自定义高危规则",
                    rule="CUSTOM_DENY",
                    matched=found.group(0),
                    command=stripped,
                )

    def extract_write_targets(self, command: str) -> List[str]:
        """从命令中提取显式写入目标（重定向 / tee / dd of=）。

        Args:
            command: 待解析命令。

        Returns:
            去重后的写入目标列表（保序）；安全设备（如 ``/dev/null``）已剔除。
        """
        targets: List[str] = []
        for pattern in (_REDIRECT_TARGET, _TEE_TARGET, _DD_TARGET):
            for found in pattern.finditer(command):
                candidate = found.group(1).strip().strip("\"'")
                if not candidate or candidate in SAFE_WRITE_DEVICES:
                    continue
                if candidate.startswith("&") or candidate.startswith("$"):
                    continue
                if candidate not in targets:
                    targets.append(candidate)
        return targets

    def audit_write_targets(self, command: str, root: str | Path) -> List[Path]:
        """校验命令中所有显式写入目标均落在工作区内。

        Args:
            command: 待执行命令。
            root: 工作区根目录。

        Returns:
            规范化后的写入目标绝对路径列表。

        Raises:
            PathEscapeError: 任一写入目标越界时抛出。
        """
        resolved: List[Path] = []
        for target in self.extract_write_targets(command):
            resolved.append(ensure_within_root(target, root, base=root))
        return resolved

    def audit_explicit_paths(self, paths: Iterable[str | Path], root: str | Path) -> List[Path]:
        """校验调用方显式声明的写入/删除目标均落在工作区内。

        Args:
            paths: 显式目标路径集合。
            root: 工作区根目录。

        Returns:
            规范化后的绝对路径列表。

        Raises:
            PathEscapeError: 任一目标越界时抛出。
        """
        return [ensure_within_root(path, root, base=root) for path in paths]
