"""HTTP 路由集合。

路由只做**协议转换**：解析入参 → 调用领域能力 → 投影为 DTO。
任何编排决策、SQL、文件 I/O 都不应出现在本层。
"""

from agent_runtime.api.routes import (
    artifacts,
    health,
    introspection,
    sessions,
    tasks,
    workspaces,
)

__all__ = ["artifacts", "health", "introspection", "sessions", "tasks", "workspaces"]
