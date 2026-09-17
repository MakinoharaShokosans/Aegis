"""网络端口与连接性探针。

验证 AegisRAG 服务端口 (127.0.0.1:8001) 是否被占用，探测远端 Qdrant 端口连通性。
"""

from __future__ import annotations

import errno
import socket
from typing import TYPE_CHECKING, List, Optional

from api.preflight.models import CheckStatus, DiagnosticItem
from api.preflight.probes.base import BaseProbe

if TYPE_CHECKING:
    from api.settings import RagConfig

__all__ = ["NetworkProbe"]


class NetworkProbe(BaseProbe):
    """网络端口与服务连通性探针。"""

    @property
    def category_name(self) -> str:
        return "网络端口与服务连通性"

    def run_checks(self, settings: RagConfig) -> List[DiagnosticItem]:
        items: List[DiagnosticItem] = []

        # 1. 探测 AegisRAG 服务监听端口可用性 (127.0.0.1:8001)
        host = settings.server.host
        port = settings.server.port

        port_available, error_msg = self._check_port_bindable(host, port)
        if port_available:
            items.append(
                DiagnosticItem(
                    name="HTTP 服务端口可用性",
                    status=CheckStatus.PASS,
                    message=f"端口 {host}:{port} 空闲可用，允许绑定",
                )
            )
        else:
            items.append(
                DiagnosticItem(
                    name="HTTP 服务端口可用性",
                    status=CheckStatus.FAIL,
                    message=f"端口 {host}:{port} 已被占用或无法绑定 ({error_msg})",
                    remediation=(
                        f"请检查是否有残留的 AegisRAG / uvicorn 实例在运行，"
                        f"可使用命令 `lsof -i :{port}` 或 `fuser {port}/tcp` 查找并终止冲突进程"
                    ),
                )
            )

        # 2. 若 Qdrant 为独立容器 server 模式，探测远端 TCP 连通性
        if settings.qdrant.mode == "server":
            q_host = settings.qdrant.host
            q_port = settings.qdrant.port
            is_connectable, conn_msg = self._check_tcp_connectable(q_host, q_port, timeout_sec=2.0)
            if is_connectable:
                items.append(
                    DiagnosticItem(
                        name="Qdrant Server 连通性",
                        status=CheckStatus.PASS,
                        message=f"成功连通 Qdrant 服务端: {q_host}:{q_port}",
                    )
                )
            else:
                items.append(
                    DiagnosticItem(
                        name="Qdrant Server 连通性",
                        status=CheckStatus.FAIL,
                        message=f"无法连接到 Qdrant 服务端 {q_host}:{q_port} ({conn_msg})",
                        remediation="请确认独立 Qdrant 容器/服务已正常启动并在该端口监听",
                    )
                )
        else:
            items.append(
                DiagnosticItem(
                    name="Qdrant 部署模式",
                    status=CheckStatus.PASS,
                    message="qdrant.mode='local' (嵌入式直接读写文件系统，无需外部网络端口)",
                )
            )

        return items

    def _check_port_bindable(self, host: str, port: int) -> tuple[bool, Optional[str]]:
        """尝试在指定 host:port 临时绑定以检测端口冲突。"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return True, None
        except socket.error as exc:
            if exc.errno == errno.EADDRINUSE:
                return False, "Address already in use (端口已被占用)"
            return False, str(exc)
        finally:
            sock.close()

    def _check_tcp_connectable(self, host: str, port: int, timeout_sec: float) -> tuple[bool, Optional[str]]:
        """尝试建立 TCP 握手。"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_sec)
        try:
            sock.connect((host, port))
            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        finally:
            sock.close()
