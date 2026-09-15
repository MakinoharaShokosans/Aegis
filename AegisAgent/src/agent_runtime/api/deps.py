"""FastAPI 依赖注入。

**原则**：路由函数不自己 new 任何东西，一律通过依赖声明所需能力。
这样每个路由都只表达"我需要什么"，而不关心"它从哪来、怎么构造"。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from agent_runtime.api.task_registry import TaskRegistry
from agent_runtime.config import AegisConfig
from agent_runtime.memory.manager import MemoryManager
from agent_runtime.workflow import RuntimeDeps

__all__ = [
    "ConfigDep",
    "MemoryDep",
    "RegistryDep",
    "RuntimeDep",
    "get_config_dep",
    "get_memory",
    "get_registry",
    "get_runtime",
    "get_started_at",
]


def get_runtime(request: Request) -> RuntimeDeps:
    """取进程级运行时容器（由 lifespan 写入 ``app.state``）。

    Args:
        request: FastAPI 请求对象。

    Returns:
        :class:`RuntimeDeps`。
    """
    return request.app.state.runtime


def get_registry(request: Request) -> TaskRegistry:
    """取任务注册表。"""
    return request.app.state.task_registry


def get_memory(request: Request) -> MemoryManager:
    """取记忆管理器。"""
    return request.app.state.runtime.memory


def get_config_dep(request: Request) -> AegisConfig:
    """取全局配置。"""
    return request.app.state.runtime.config


def get_started_at(request: Request) -> float:
    """取进程启动时间戳（用于健康检查计算 uptime）。"""
    return float(request.app.state.started_at)


RuntimeDep = Annotated[RuntimeDeps, Depends(get_runtime)]
RegistryDep = Annotated[TaskRegistry, Depends(get_registry)]
MemoryDep = Annotated[MemoryManager, Depends(get_memory)]
ConfigDep = Annotated[AegisConfig, Depends(get_config_dep)]
StartedAtDep = Annotated[float, Depends(get_started_at)]
