"""``bash`` 基础工具：受控命令执行。

**职责边界**：本工具**不做**任何沙箱与配额控制——那属于 ``services/bash_shell``
子系统（独立进程、setrlimit 配额、两段式硬杀）。Agent 侧只负责参数组装与结果转译，
这样"安全边界"永远只存在于一个地方，不会因为调用方不同而失效。
"""

from __future__ import annotations

import itertools
from typing import Any, Mapping

from loguru import logger

from agent_runtime.errors import DependencyUnavailableError
from tools.core.http_client import ServiceClient
from tools.core.protocol import AegisTool, ToolResult

__all__ = ["BashTool"]


class BashTool(AegisTool):
    """执行 Shell 命令的基础工具。

    Args:
        client: 指向 ``bash_shell`` 子系统的 HTTP 客户端。
        workspace_id: 工作区标识（服务端据此校验 ``workspace_root``）。
        workspace_root: 工作区物理根路径（作为子进程 cwd）。
        task_id: 当前任务 ID（决定产物落盘目录）。
        default_timeout_sec: 默认命令超时。
    """

    name = "bash"
    description = (
        "在目标工程目录中执行 Shell 命令（编译、测试、git、查看文件等）。"
        "命令以工作区根目录为工作目录执行；超长输出会自动落盘，只返回摘要与句柄。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的完整 Shell 命令"},
            "timeout_sec": {
                "type": "number",
                "description": "可选，本次命令超时秒数；不填则使用系统默认值",
            },
        },
        "required": ["command"],
    }

    def __init__(
        self,
        client: ServiceClient,
        *,
        workspace_id: str,
        workspace_root: str,
        task_id: str,
        default_timeout_sec: float = 60.0,
    ) -> None:
        self._client = client
        self._workspace_id = workspace_id
        self._workspace_root = workspace_root
        self._task_id = task_id
        self.timeout_sec = default_timeout_sec
        #: 本任务内 bash 调用序号，用于产物命名（step_id 由工具自身单调维护，
        #: 避免把编排层的步号概念泄漏给模型）
        self._counter = itertools.count(1)

    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        """提交命令到 bash_shell 子系统执行。

        Args:
            args: ``{"command": str, "timeout_sec"?: float}``。

        Returns:
            :class:`ToolResult`；退出码非零时 ``ok=False`` 但观察值仍然可用。
        """
        command = str(args.get("command", "")).strip()
        if not command:
            return ToolResult.failure("缺少 command 参数")

        try:
            timeout = float(args.get("timeout_sec") or self.timeout_sec)
        except (TypeError, ValueError):
            timeout = self.timeout_sec

        payload = {
            "workspace_id": self._workspace_id,
            "workspace_root": self._workspace_root,
            "task_id": self._task_id,
            "step_id": next(self._counter),
            "command": command,
            "timeout_sec": timeout,
        }

        try:
            data = await self._client.request_json("POST", "/api/v1/shell/execute", payload=payload)
        except DependencyUnavailableError as exc:
            logger.error(f"[BashTool] shell 子系统不可用: {exc}")
            return ToolResult.failure(str(exc), tool=self.name)

        exit_code = data.get("exit_code")
        status = str(data.get("status") or "")
        if status == "QUEUED":
            return ToolResult(
                ok=True,
                content="命令已进入等待队列（当前并发配额已满），请稍后重试或减少并行命令。",
                meta={"queued": True},
            )

        stdout = str(data.get("distilled_stdout") or "")
        stderr = str(data.get("distilled_stderr") or "")
        artifact_path = str(data.get("artifact_path") or "")
        sections = [section for section in (stdout, stderr) if section.strip()]
        content = "\n".join(sections) or "（无输出）"

        return ToolResult(
            ok=exit_code == 0,
            content=content,
            exit_code=int(exit_code) if isinstance(exit_code, int) else None,
            artifact_path=artifact_path or None,
            artifact_id=(artifact_path.rsplit("/", 1)[-1] if artifact_path else None),
            is_truncated=bool(data.get("is_truncated")),
            meta={"execution_time_ms": data.get("execution_time_ms")},
        )
