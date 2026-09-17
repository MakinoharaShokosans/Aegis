"""配置规范与安全红线探针。

验证 rag_config.toml 配置完整性、回环安全红线、Worker 互斥锁及鉴权环境变量。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, List

from api.preflight.models import CheckStatus, DiagnosticItem
from api.preflight.probes.base import BaseProbe
from api.settings import find_config_file

if TYPE_CHECKING:
    from api.settings import RagConfig

__all__ = ["ConfigGuardProbe"]

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


class ConfigGuardProbe(BaseProbe):
    """配置合规与安全红线探针。"""

    @property
    def category_name(self) -> str:
        return "配置合规与安全红线"

    def run_checks(self, settings: RagConfig) -> List[DiagnosticItem]:
        items: List[DiagnosticItem] = []

        # 1. 配置文件路径与可读性
        try:
            cfg_path = find_config_file()
            items.append(
                DiagnosticItem(
                    name="配置文件寻址",
                    status=CheckStatus.PASS,
                    message=f"已定位配置源: {cfg_path}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            items.append(
                DiagnosticItem(
                    name="配置文件寻址",
                    status=CheckStatus.FAIL,
                    message=f"无法定位配置文件: {exc}",
                    remediation="请确保 config/rag_config.toml 存在或设置 AEGIS_RAG_CONFIG 环境变量",
                )
            )

        # 2. 回环监听安全红线
        if settings.server.host in _LOOPBACK_HOSTS:
            items.append(
                DiagnosticItem(
                    name="网络监听安全红线",
                    status=CheckStatus.PASS,
                    message=f"server.host={settings.server.host!r} (仅本地回环，符合安全红线)",
                )
            )
        else:
            items.append(
                DiagnosticItem(
                    name="网络监听安全红线",
                    status=CheckStatus.FAIL,
                    message=f"server.host={settings.server.host!r} 暴露在非回环地址上，存在未鉴权风险",
                    remediation="请将 config/rag_config.toml 中 [server].host 修改为 '127.0.0.1'",
                )
            )

        # 3. 本地嵌入式数据库单 Worker 互斥锁
        if settings.qdrant.mode == "local":
            if settings.server.workers == 1:
                items.append(
                    DiagnosticItem(
                        name="Qdrant 本地存储 Worker 约束",
                        status=CheckStatus.PASS,
                        message="qdrant.mode='local' 且 server.workers=1 (无多进程并发写冲突)",
                    )
                )
            else:
                items.append(
                    DiagnosticItem(
                        name="Qdrant 本地存储 Worker 约束",
                        status=CheckStatus.FAIL,
                        message=(
                            f"qdrant.mode='local' 但 server.workers={settings.server.workers} > 1。"
                            "本地嵌入式 Qdrant 不支持多进程并发写入，会导致数据库锁损坏。"
                        ),
                        remediation="请将 config/rag_config.toml 中 [server].workers 设置为 1",
                    )
                )
        else:
            items.append(
                DiagnosticItem(
                    name="Qdrant 部署模式",
                    status=CheckStatus.PASS,
                    message=f"qdrant.mode='server' (独立服务模式: {settings.qdrant.host}:{settings.qdrant.port})",
                )
            )

        # 4. 远程模式鉴权密钥检查（若开启 remote 模式）
        if settings.embedding.mode == "remote":
            key_var = settings.embedding.remote.api_key_env
            if os.getenv(key_var, "").strip():
                items.append(
                    DiagnosticItem(
                        name="Dense 远程鉴权密钥",
                        status=CheckStatus.PASS,
                        message=f"环境变量 {key_var} 已就绪",
                    )
                )
            else:
                items.append(
                    DiagnosticItem(
                        name="Dense 远程鉴权密钥",
                        status=CheckStatus.FAIL,
                        message=f"embedding.mode='remote' 但环境变量 {key_var} 未设置或为空",
                        remediation=f"请在 .env 中设置 {key_var}=<your_api_key>",
                    )
                )
        else:
            items.append(
                DiagnosticItem(
                    name="Dense 运行模式",
                    status=CheckStatus.PASS,
                    message=f"embedding.mode='local' (本地模型: {settings.embedding.local.model_name})",
                )
            )

        if settings.rerank.mode == "remote":
            key_var = settings.rerank.remote.api_key_env
            if os.getenv(key_var, "").strip():
                items.append(
                    DiagnosticItem(
                        name="Rerank 远程鉴权密钥",
                        status=CheckStatus.PASS,
                        message=f"环境变量 {key_var} 已就绪",
                    )
                )
            else:
                items.append(
                    DiagnosticItem(
                        name="Rerank 远程鉴权密钥",
                        status=CheckStatus.FAIL,
                        message=f"rerank.mode='remote' 但环境变量 {key_var} 未设置或为空",
                        remediation=f"请在 .env 中设置 {key_var}=<your_api_key>",
                    )
                )
        else:
            items.append(
                DiagnosticItem(
                    name="Rerank 运行模式",
                    status=CheckStatus.PASS,
                    message=f"rerank.mode='local' (本地模型: {settings.rerank.local.model_name})",
                )
            )

        return items
