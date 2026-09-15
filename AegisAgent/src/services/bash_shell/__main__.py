"""uvicorn 启动入口（默认 ``127.0.0.1:8002``，host/port 取自 ``[bash_shell]`` 配置）。

启动方式（任选其一，均自动把 ``src`` 挂到 ``sys.path``）::

    python -m services.bash_shell            # cwd = AegisAgent/src
    python -m src.services.bash_shell        # cwd = AegisAgent

规范：documents/技术选型/bash_shell.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

__all__ = ["main"]


def _bootstrap_sys_path() -> None:
    """确保 ``src`` 目录位于 ``sys.path`` 首位。

    子系统内部使用 ``services.xxx`` 绝对导入（与仓库其它模块一致），
    因此从 ``AegisAgent/`` 根目录以 ``python -m src.services.bash_shell`` 启动时
    需要补上 ``src``，避免依赖调用方的 cwd。
    """
    src_root = Path(__file__).resolve().parents[2]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))


def main() -> None:
    """读取配置并启动 uvicorn 服务。

    Raises:
        RuntimeError: ``config.toml`` 缺少 ``[bash_shell]`` 段时抛出。
        pydantic.ValidationError: 配置字段缺失或非法时抛出。
    """
    _bootstrap_sys_path()

    from services.bash_shell.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "services.bash_shell.app:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
