"""web_search 子系统进程入口（uvicorn，默认 ``127.0.0.1:8003``）。

用法::

    # 方式一：从 AegisAgent/ 根目录以包模块启动（需 src 在 PYTHONPATH）
    PYTHONPATH=src .venv/bin/python -m services.web_search

    # 方式二：直接执行本文件（脚本会把 src/ 注入 sys.path，可省略 PYTHONPATH）
    .venv/bin/python src/services/web_search/__main__.py

监听地址与端口全部来自 ``config/config.toml`` 的 ``[web_search]`` 段（零硬编码）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

import uvicorn

#: ``src/`` 目录（本文件位于 src/services/web_search/__main__.py，向上三级）
_SRC_DIR: Final[Path] = Path(__file__).resolve().parents[2]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from services.web_search.app import app  # noqa: E402  (须在 sys.path 修补之后导入)
from services.web_search.settings import get_settings  # noqa: E402


def main() -> None:
    """读取配置并启动 uvicorn 服务。

    Raises:
        RuntimeError: ``[web_search]`` 配置段缺失。
        pydantic.ValidationError: 配置项缺失或取值越界。
    """
    settings = get_settings()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
