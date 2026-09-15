"""工具契约：统一入参/出参与工具抽象基类。

**统一返回契约的意义**：Executor 节点需要对"成功/失败/是否被截断/产物句柄"
做出确定性判断，而不是靠解析自由文本。所有工具（基础工具、MCP 转译工具）
一律返回 :class:`ToolResult`，让编排层无需关心工具的实现细节。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping, Optional

from pydantic import BaseModel, Field

__all__ = ["AegisTool", "ToolResult"]


class ToolResult(BaseModel):
    """工具执行结果（统一契约）。"""

    ok: bool = Field(description="是否成功")
    content: str = Field(default="", description="供模型阅读的观察值（已蒸馏）")
    exit_code: Optional[int] = Field(default=None, description="子进程退出码（非进程类工具为 None）")
    artifact_id: Optional[str] = Field(default=None, description="产物句柄标识")
    artifact_path: Optional[str] = Field(default=None, description="产物绝对路径")
    is_truncated: bool = Field(default=False, description="观察值是否被裁剪/离线卸载")
    duration_ms: int = Field(default=0, description="耗时（毫秒）")
    error: Optional[str] = Field(default=None, description="失败原因摘要")
    meta: Dict[str, Any] = Field(default_factory=dict, description="工具特有的结构化附加信息")

    @classmethod
    def failure(cls, message: str, **meta: Any) -> "ToolResult":
        """构造失败结果（工具失败不抛异常，而是交回模型自我修正）。

        Args:
            message: 失败原因摘要。
            **meta: 附加结构化信息。

        Returns:
            失败态的 :class:`ToolResult`。
        """
        return cls(ok=False, content=f"工具执行失败: {message}", error=message, meta=dict(meta))


class AegisTool(ABC):
    """所有工具的抽象基类。

    子类必须声明 ``name`` / ``description`` / ``parameters``，并实现 :meth:`invoke`。

    Attributes:
        name: 工具唯一名（注入模型 function calling 的 ``name``）。
        description: 给模型看的能力描述，直接影响调用准确率。
        parameters: JSON Schema 形式的入参定义。
        timeout_sec: 单次调用硬超时。
    """

    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {"type": "object", "properties": {}}
    timeout_sec: float = 60.0

    @abstractmethod
    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        """执行工具。

        Args:
            args: 模型给出的入参（已按 ``parameters`` 生成）。

        Returns:
            :class:`ToolResult`。实现方**不得**因业务失败而抛异常，
            应返回 ``ToolResult.failure(...)``；只有框架级错误才抛 :class:`AgentError`。
        """

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<{type(self).__name__} name={self.name!r}>"
