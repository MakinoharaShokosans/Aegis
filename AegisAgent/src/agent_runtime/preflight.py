"""AegisAgent 启动前环境自检与终端启动看板（Pre-flight Checks & Startup Dashboard）。

包含：
1. **环境变量与 LLM 密钥预检**：检查 reasoning / fast 模型链所需的环境变量是否已配置；
2. **存储与持久化目录就绪检查**：验证 checkpoints、traces、artifacts、logs 目录权限及 SQLite 读写；
3. **安全闸门与网络合规检查**：验证 Host 回环限制与 API Token 凭据状态；
4. **技能库与 MCP 自检**：扫描技能包与 MCP 服务器状态；
5. **结构化启动看板渲染**：以结构化、美观的控制台视图展示系统拓扑与就绪状态。
"""

from __future__ import annotations

import enum
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from agent_runtime.config import AegisConfig
from agent_runtime.supervisor import SidecarProcessInfo

__all__ = [
    "CheckStatus",
    "CheckItem",
    "PreflightReport",
    "run_preflight_checks",
    "render_startup_dashboard",
]


class CheckStatus(str, enum.Enum):
    """自检单项状态。"""

    OK = "OK"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass(slots=True)
class CheckItem:
    """单个自检项的结果。"""

    category: str
    name: str
    status: CheckStatus
    detail: str


@dataclass
class PreflightReport:
    """系统启动自检汇总报告。"""

    items: List[CheckItem] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """是否存在阻断性错误。"""
        return any(item.status == CheckStatus.ERROR for item in self.items)

    @property
    def has_warnings(self) -> bool:
        """是否存在告警提示。"""
        return any(item.status == CheckStatus.WARN for item in self.items)

    @property
    def all_ok(self) -> bool:
        """是否全项通过且无阻断错误。"""
        return not self.has_errors


def run_preflight_checks(config: AegisConfig) -> PreflightReport:
    """执行全面的启动前自检。

    Args:
        config: 全局运行时配置。

    Returns:
        包含各项检测结果的 :class:`PreflightReport`。
    """
    report = PreflightReport()

    # 1. 检查 LLM API 密钥环境变量
    checked_envs: set[str] = set()
    all_endpoints = (
        list(config.models.reasoning.endpoints) + list(config.models.fast.endpoints)
    )
    for ep in all_endpoints:
        env_name = ep.api_key_env
        if not env_name or env_name in checked_envs:
            continue
        checked_envs.add(env_name)
        val = os.getenv(env_name, "").strip()
        if val:
            report.items.append(
                CheckItem(
                    category="LLM Endpoints",
                    name=f"Key: {env_name}",
                    status=CheckStatus.OK,
                    detail=f"已设置 (长度 {len(val)} 字符，用于 {ep.model})",
                )
            )
        else:
            report.items.append(
                CheckItem(
                    category="LLM Endpoints",
                    name=f"Key: {env_name}",
                    status=CheckStatus.WARN,
                    detail=f"未设置环境变量 {env_name} (真实调用时将鉴权失败)",
                )
            )

    # 2. 检查本地存储与 SQLite 目录
    storage = config.runtime.storage
    target_dirs = [
        ("Checkpoints Dir", Path(storage.checkpoint_db_path).parent),
        ("Metadata DB Dir", Path(storage.metadata_db_path).parent),
        ("Traces Dir", Path(storage.traces_dir)),
        ("Artifacts Dir", Path(storage.artifacts_dir)),
        ("Logs Dir", Path(storage.metadata_db_path).parent / "logs"),
    ]
    for name, directory in target_dirs:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            # 测试写入探针文件
            probe_file = directory / ".write_test"
            probe_file.write_text("ok", encoding="utf-8")
            probe_file.unlink(missing_ok=True)
            report.items.append(
                CheckItem(
                    category="Storage & Databases",
                    name=name,
                    status=CheckStatus.OK,
                    detail=f"可读写: {directory.resolve()}",
                )
            )
        except Exception as exc:
            report.items.append(
                CheckItem(
                    category="Storage & Databases",
                    name=name,
                    status=CheckStatus.ERROR,
                    detail=f"目录无法创建或写入: {exc}",
                )
            )

    # 3. 检查 SQLite Checkpoint 数据库连接
    try:
        db_path = Path(storage.checkpoint_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute("SELECT 1;")
        conn.close()
        report.items.append(
            CheckItem(
                category="Storage & Databases",
                name="SQLite Checkpoint DB",
                status=CheckStatus.OK,
                detail=f"连接正常: {db_path.name}",
            )
        )
    except Exception as exc:
        report.items.append(
            CheckItem(
                category="Storage & Databases",
                name="SQLite Checkpoint DB",
                status=CheckStatus.ERROR,
                detail=f"SQLite 打开失败: {exc}",
            )
        )

    # 4. 安全闸门与回环配置
    server = config.server
    if server.host in ("127.0.0.1", "localhost", "::1"):
        report.items.append(
            CheckItem(
                category="Security & Network",
                name="Host Gate",
                status=CheckStatus.OK,
                detail=f"回环隔离生效 ({server.host})",
            )
        )
    else:
        report.items.append(
            CheckItem(
                category="Security & Network",
                name="Host Gate",
                status=CheckStatus.ERROR,
                detail=f"非回环地址违规 ({server.host})",
            )
        )

    if server.auth_enabled:
        report.items.append(
            CheckItem(
                category="Security & Network",
                name="API Token Gate",
                status=CheckStatus.OK,
                detail=f"已启用 (来源: {server.api_token_file} / env:{server.api_token_env})",
            )
        )
    else:
        report.items.append(
            CheckItem(
                category="Security & Network",
                name="API Token Gate",
                status=CheckStatus.WARN,
                detail="未启用令牌鉴权 (仅 Host 与 Origin 闸门生效)",
            )
        )

    # 5. 技能包与 MCP 状态
    builtin_skills_dir = Path(__file__).resolve().parents[1] / "skills"
    if builtin_skills_dir.is_dir():
        skill_count = len([p for p in builtin_skills_dir.iterdir() if p.is_dir() and not p.name.startswith(".")])
        report.items.append(
            CheckItem(
                category="Skills & MCP",
                name="Builtin Skills",
                status=CheckStatus.OK,
                detail=f"已就绪 ({skill_count} 个内置技能)",
            )
        )

    enabled_mcps = [k for k, v in config.mcp.servers.items() if v.enabled]
    if config.mcp.enabled:
        report.items.append(
            CheckItem(
                category="Skills & MCP",
                name="MCP Extension Servers",
                status=CheckStatus.OK,
                detail=f"MCP 已开启 ({len(enabled_mcps)} 个活跃服务器)",
            )
        )
    else:
        report.items.append(
            CheckItem(
                category="Skills & MCP",
                name="MCP Extension Servers",
                status=CheckStatus.OK,
                detail="MCP 总开关关闭",
            )
        )

    return report


def render_startup_dashboard(
    report: PreflightReport,
    config: AegisConfig,
    *,
    sidecar_statuses: Optional[Dict[str, SidecarProcessInfo]] = None,
    rag_reachable: Optional[bool] = None,
    token_hint: Optional[str] = None,
) -> str:
    """生成结构化终端启动就绪看板字符串。

    Args:
        report: 启动自检报告。
        config: 全局配置。
        sidecar_statuses: 托管 Sidecar 状态字典。
        rag_reachable: 外部 RAG 服务连通性。
        token_hint: 令牌提示文案。

    Returns:
        看板格式化字符串。
    """
    server = config.server
    lines: List[str] = []
    width = 78

    lines.append("=" * width)
    lines.append("🛡️   AEGIS AGENT RUNTIME SYSTEM READY".center(width))
    lines.append("=" * width)

    # 1. 启动自检项
    lines.append("\n  [1. System Pre-flight Checks]")
    for item in report.items:
        sym = "✓" if item.status == CheckStatus.OK else ("!" if item.status == CheckStatus.WARN else "✗")
        tag = f"[{item.status.value}]"
        line = f"    {sym} {item.name:<24}: {item.detail}"
        lines.append(line)

    # 2. 托管 Sidecars 状态
    lines.append("\n  [2. Managed Sidecars (Physical Sandboxes)]")
    if sidecar_statuses:
        for name, info in sidecar_statuses.items():
            status_text = "Health OK" if info.healthy else (f"Error: {info.error}" if info.error else "Degraded")
            mode = "Attached External" if info.is_external else f"Auto-Spawned (PID: {info.pid})"
            sym = "✓" if info.healthy else "✗"
            lines.append(f"    {sym} {info.spec.log_tag or name:<24}: {info.spec.url} [{mode}, {status_text}]")
    else:
        lines.append("    - (Sidecar auto-start disabled)")

    # 3. 外部依赖微服务
    lines.append("\n  [3. External Dependencies]")
    rag_sym = "✓" if rag_reachable else ("?" if rag_reachable is None else "✗")
    rag_detail = "Reachable OK" if rag_reachable else ("Unchecked" if rag_reachable is None else "Unreachable (Degraded Mode)")
    lines.append(f"    {rag_sym} {'AegisRAG Service':<24}: {config.services.rag_url} [{rag_detail}]")

    # 4. API 网关访问入口
    lines.append("\n  [4. Agent HTTP API Gateway]")
    lines.append(f"    🚀 Endpoint Listening      : http://{server.host}:{server.port}")
    lines.append(f"    📄 Swagger Docs            : http://{server.host}:{server.port}/docs")
    lines.append(f"    🪵 Unified JSONL Log Sink  : {config.runtime.storage.metadata_db_path.replace('aegis_meta.db', 'logs/aegis.jsonl')}")
    if token_hint:
        lines.append(f"    🔑 Authentication          : {token_hint}")
    lines.append("    ⌨️  Quick Control           : 按 [Q] 或 [Ctrl+C] 优雅关闭所有服务并退出")

    lines.append("=" * width)
    return "\n".join(lines)
