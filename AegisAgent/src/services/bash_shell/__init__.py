"""受控 Bash 执行沙箱子系统（同工程 sidecar，独立进程，默认 ``127.0.0.1:8002``）。

模块分工：
- ``settings``：读取 ``config.toml`` 的 ``[bash_shell]`` 段（零硬编码）；
- ``audit``：高危命令黑名单与路径越界校验（确定性前置拦截）；
- ``memory_pool``：全局内存池配额与排队预估；
- ``sandbox``：``os.setsid`` + ``setrlimit`` + 两段式硬杀 + 输出蒸馏；
- ``app`` / ``__main__``：FastAPI 契约与 uvicorn 入口。

边界约束：本包**禁止 import ``agent_runtime`` / ``tool_layer`` / ``tools``**，
只允许依赖 ``services.settings``、标准库与 fastapi/uvicorn/pydantic/loguru。

规范：documents/技术选型/bash_shell.md；documents/agent_runtime/10_directory_structure.md §4 裁决项③⑦、§5
"""

from __future__ import annotations

__all__ = ["__version__"]

#: 子系统版本号（仅元数据，不参与任何阈值判定）
__version__ = "0.1.0"
