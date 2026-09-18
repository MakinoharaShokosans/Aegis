"""控制台键盘 Q 优雅退出单元测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import uvicorn

from agent_runtime.api.__main__ import _listen_for_quit_key, serve_with_keyboard_listener


@pytest.mark.asyncio
async def test_listen_for_quit_key_non_tty() -> None:
    server = MagicMock()
    server.should_exit = False

    with patch("sys.stdin.isatty", return_value=False):
        await _listen_for_quit_key(server)
        assert server.should_exit is False


@pytest.mark.asyncio
async def test_listen_for_quit_key_detects_q() -> None:
    server = MagicMock()
    server.should_exit = False

    with patch("sys.stdin.isatty", return_value=True), \
         patch("sys.stdin.fileno", return_value=0), \
         patch("termios.tcgetattr", return_value=[]), \
         patch("termios.tcsetattr", return_value=None), \
         patch("tty.setcbreak", return_value=None), \
         patch("select.select", return_value=([True], [], [])), \
         patch("sys.stdin.read", return_value="q"):
        await _listen_for_quit_key(server)
        assert server.should_exit is True


@pytest.mark.asyncio
async def test_serve_with_keyboard_listener() -> None:
    server = MagicMock()
    server.serve = AsyncMock(return_value=None)

    with patch("agent_runtime.api.__main__._listen_for_quit_key", AsyncMock()):
        await serve_with_keyboard_listener(server)
        server.serve.assert_called_once()
