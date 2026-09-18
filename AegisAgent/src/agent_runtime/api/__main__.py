"""uvicorn 启动入口。

用法::

    PYTHONPATH=src .venv/bin/python -m agent_runtime.api

host / port 一律取自 ``config.toml`` 的 ``[server]`` 段；
``config.py`` 的 fail-closed 护栏会拒绝非回环地址，因此本服务默认只监听本机。
支持在控制台按下 [Q] 键或 [Ctrl+C] 触发全系统优雅退出。
"""

from __future__ import annotations

import asyncio
import os
import select
import sys
from typing import Optional

import uvicorn
from loguru import logger

from agent_runtime.api.app import create_app
from agent_runtime.config import get_config

__all__ = ["main", "serve_with_keyboard_listener"]


async def _listen_for_quit_key(server: uvicorn.Server) -> None:
    """在 TTY 终端下监听单字符按键，命中 [Q] 时通知 uvicorn 退出。"""
    if not sys.stdin.isatty():
        return

    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
    except Exception:
        return

    def _restore() -> None:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass

    loop = asyncio.get_running_loop()
    try:
        # 设置为 cbreak 模式：单字符直接读取，不需回车，同时保留 SIGINT (Ctrl+C)
        tty.setcbreak(fd)

        while not server.should_exit:
            # 异步非阻塞等待标准输入
            readable = await loop.run_in_executor(
                None, lambda: select.select([sys.stdin], [], [], 0.4)[0]
            )
            if readable and not server.should_exit:
                char = sys.stdin.read(1)
                if char in ("q", "Q", "\x03", "\x04"):  # q, Q, Ctrl+C, Ctrl+D
                    logger.info("⌨️  [Console] 接收到快捷指令 [Q]，正在通知全系统优雅退出...")
                    server.should_exit = True
                    break
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.debug(f"[Console] 键盘监听异常退出: {exc}")
    finally:
        _restore()


async def serve_with_keyboard_listener(server: uvicorn.Server) -> None:
    """运行 uvicorn 服务器并挂载键盘监听器。"""
    listener_task = asyncio.create_task(_listen_for_quit_key(server), name="quit-key-listener")
    try:
        await server.serve()
    finally:
        if not listener_task.done():
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass


def main() -> None:
    """按配置启动 HTTP 服务。"""
    config = get_config()
    app = create_app(config)

    server_config = uvicorn.Config(
        app,
        host=config.server.host,
        port=config.server.port,
        log_config=None,  # 统一交给 loguru，避免双份日志格式
        access_log=False,
    )
    server = uvicorn.Server(server_config)

    try:
        asyncio.run(serve_with_keyboard_listener(server))
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
