"""Aegis 领域异常体系。

设计原则：
1. **单一根异常**：所有业务异常继承 :class:`AgentError`，上层（节点 / API / 任务注册表）
   只需捕获一个基类即可统一兜底，避免散落的 ``except Exception``；
2. **结构化上下文**：异常携带 ``context`` 字典而非把变量拼进消息字符串，
   便于日志检索与 API 错误详情渲染；
3. **与传输层解耦**：领域层完全不知道 HTTP 的存在，错误码 → HTTP 状态码的映射
   集中在 :mod:`agent_runtime.api.errors`，保证领域逻辑可独立单测。
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class AgentError(Exception):
    """Aegis 领域异常基类。

    Attributes:
        code: 稳定的机器可读错误码（大写下划线），供 API 层做状态码映射与前端分流。
        message: 面向人类的可读描述。
        context: 结构化补充信息（如 workspace_id），不得包含任何密钥。
    """

    #: 子类必须覆盖为稳定的错误码
    code: str = "AGENT_ERROR"

    def __init__(self, message: str, *, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: Dict[str, Any] = dict(context or {})

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 API 错误体（不含 trace_id，由 API 层补齐）。"""
        return {"code": self.code, "message": self.message, "details": self.context}

    def __str__(self) -> str:
        if not self.context:
            return self.message
        detail = ", ".join(f"{key}={value!r}" for key, value in self.context.items())
        return f"{self.message} ({detail})"


# ==============================================================================
# 配置与启动期异常
# ==============================================================================

class ConfigError(AgentError):
    """配置缺失、非法或自相矛盾。"""

    code = "CONFIG_ERROR"


# ==============================================================================
# 资源查找类异常（对应 HTTP 404）
# ==============================================================================

class NotFoundError(AgentError):
    """资源不存在的基类。"""

    code = "NOT_FOUND"


class WorkspaceNotFoundError(NotFoundError):
    code = "WORKSPACE_NOT_FOUND"


class SessionNotFoundError(NotFoundError):
    code = "SESSION_NOT_FOUND"


class TaskNotFoundError(NotFoundError):
    code = "TASK_NOT_FOUND"


class ArtifactNotFoundError(NotFoundError):
    code = "ARTIFACT_NOT_FOUND"


class SkillNotFoundError(NotFoundError):
    code = "SKILL_NOT_FOUND"


# ==============================================================================
# 冲突类异常（对应 HTTP 409 / 422）
# ==============================================================================

class ConflictError(AgentError):
    """资源状态冲突的基类。"""

    code = "CONFLICT"


class WorkspacePathConflictError(ConflictError):
    """同一物理路径被另一个 workspace_id 占用（唯一索引冲突）。"""

    code = "WORKSPACE_PATH_CONFLICT"


class TaskAlreadyRunningError(ConflictError):
    """同一会话上已有任务在运行。"""

    code = "TASK_ALREADY_RUNNING"


class PathEscapeDetectedError(AgentError):
    """目标路径越出工作区 root_path（防目录穿越）。"""

    code = "PATH_ESCAPE_DETECTED"


# ==============================================================================
# 容量与依赖类异常（对应 HTTP 429 / 503）
# ==============================================================================

class TaskQueueFullError(AgentError):
    """并发任务数已达上限。"""

    code = "TASK_QUEUE_FULL"


class DependencyUnavailableError(AgentError):
    """下游 sidecar（RAG / Shell / Web）不可达或返回异常。"""

    code = "DEPENDENCY_UNAVAILABLE"


# ==============================================================================
# 执行期异常
# ==============================================================================

class ToolExecutionError(AgentError):
    """工具执行失败。

    注意：按 ``03_node_specification`` 的设计，**工具失败默认不抛出**，
    而是被包装为观察值交回模型自我修正；本异常仅用于工具框架自身的
    确定性错误（如工具未注册、Schema 非法）。
    """

    code = "TOOL_EXECUTION_ERROR"


class LLMUnavailableError(AgentError):
    """双模型链路（端点内退避 + 跨端点降级）全部耗尽。"""

    code = "LLM_UNAVAILABLE"


class BudgetExceededError(AgentError):
    """物理预算熔断（步数 / Token / 挂钟时间）。"""

    code = "BUDGET_EXCEEDED"


class LoopDetectedError(AgentError):
    """指纹死循环命中。"""

    code = "LOOP_DETECTED"


__all__ = [
    "AgentError",
    "ArtifactNotFoundError",
    "BudgetExceededError",
    "ConfigError",
    "ConflictError",
    "DependencyUnavailableError",
    "LLMUnavailableError",
    "LoopDetectedError",
    "NotFoundError",
    "PathEscapeDetectedError",
    "SessionNotFoundError",
    "SkillNotFoundError",
    "TaskAlreadyRunningError",
    "TaskNotFoundError",
    "TaskQueueFullError",
    "ToolExecutionError",
    "WorkspaceNotFoundError",
    "WorkspacePathConflictError",
]
