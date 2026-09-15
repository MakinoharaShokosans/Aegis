"""uvicorn 启动入口。

用法::

    PYTHONPATH=src .venv/bin/python -m agent_runtime.api

host / port 一律取自 ``config.toml`` 的 ``[server]`` 段；
``config.py`` 的 fail-closed 护栏会拒绝非回环地址，因此本服务默认只监听本机。
"""

from __future__ import annotations

import uvicorn

from agent_runtime.api.app import create_app
from agent_runtime.config import get_config

__all__ = ["main"]


def main() -> None:
    """按配置启动 HTTP 服务。"""
    config = get_config()
    app = create_app(config)
    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_config=None,  # 统一交给 loguru，避免双份日志格式
        access_log=False,
    )


if __name__ == "__main__":
    main()
