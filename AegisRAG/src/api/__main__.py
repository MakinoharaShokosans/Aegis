"""uvicorn 启动入口（默认 ``127.0.0.1:8001``，host/port/workers 取自 ``[server]`` 配置）。

启动方式（任选其一，均自动把 ``src`` 挂到 ``sys.path``）::

    python -m api            # cwd = AegisRAG/src
    python -m src.api        # cwd = AegisRAG
    ./start service          # cwd = AegisRAG

规范：documents/技术选型/rag_retrieval.md
"""

from __future__ import annotations

import asyncio
import select
import sys
from pathlib import Path

import uvicorn
from loguru import logger

__all__ = ["main", "serve_with_keyboard_listener"]


def _bootstrap_sys_path() -> None:
    """确保 ``src`` 目录位于 ``sys.path`` 首位。"""
    src_root = Path(__file__).resolve().parents[1]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))


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
        tty.setcbreak(fd)
        while not server.should_exit:
            readable = await loop.run_in_executor(
                None, lambda: select.select([sys.stdin], [], [], 0.4)[0]
            )
            if readable and not server.should_exit:
                char = sys.stdin.read(1)
                if char in ("q", "Q", "\x03", "\x04"):
                    logger.info("⌨️  [Console] 接收到快捷指令 [Q]，正在关闭 AegisRAG 检索微服务...")
                    server.should_exit = True
                    break
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.debug(f"[Console] 键盘监听异常: {exc}")
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
    """读取配置、执行启动前置体检并安全拉起 uvicorn 服务。"""
    _bootstrap_sys_path()

    from api.app import app
    from api.preflight import DiagnosticReporter, PreflightRunner
    from api.settings import get_settings

    settings = get_settings()

    # 1. 启动前置体检与自检门禁
    runner = PreflightRunner()
    report = runner.run(settings)
    print(DiagnosticReporter.format_console(report))

    if not report.is_launch_ready:
        print("\n[✘ 启动中止] 前置自检发现致命错误，拒绝带病启动服务！\n", file=sys.stderr)
        sys.exit(1)

    # 2. 安全拉起服务
    print(f"[🚀 AegisRAG] 正在拉起 HTTP 检索服务: http://{settings.server.host}:{settings.server.port}")
    print("  ⌨️  Quick Control : 按 [Q] 或 [Ctrl+C] 优雅关闭微服务并退出\n")

    server_config = uvicorn.Config(
        app,
        host=settings.server.host,
        port=settings.server.port,
        log_level="info",
    )
    server = uvicorn.Server(server_config)

    try:
        asyncio.run(serve_with_keyboard_listener(server))
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
