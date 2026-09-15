"""Loguru 结构化日志装配。

**双 sink 设计**：
1. **控制台 sink**：人类可读的彩色文本，只到 INFO；
2. **文件 sink**：``serialize=True`` 的 JSON Lines，含全量 DEBUG 与结构化字段，
   供离线评测脚本直接解析（评测 harness 需要按 ``task_id`` 聚合统计）。

``enqueue=True`` 让日志写入走后台线程，避免磁盘抖动阻塞事件循环。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

__all__ = ["setup_logging"]

_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


def setup_logging(
    log_dir: str | Path = "storage/logs",
    *,
    level: str = "INFO",
    json_filename: str = "aegis.jsonl",
    enable_console: bool = True,
) -> Optional[Path]:
    """装配全局日志。

    幂等：重复调用会先移除既有 sink，避免日志重复输出。

    Args:
        log_dir: JSONL 日志落盘目录。
        level: 控制台最低级别。
        json_filename: JSONL 文件名。
        enable_console: 是否启用控制台 sink。

    Returns:
        JSONL 日志文件的绝对路径；文件 sink 创建失败时返回 ``None``。
    """
    logger.remove()

    if enable_console:
        logger.add(sys.stderr, level=level, format=_CONSOLE_FORMAT, colorize=True)

    try:
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        json_path = (directory / json_filename).resolve()
        logger.add(
            json_path,
            level="DEBUG",
            serialize=True,          # JSON Lines，供评测脚本解析
            enqueue=True,            # 后台线程写入，不阻塞事件循环
            rotation="20 MB",
            retention=10,
            encoding="utf-8",
            backtrace=True,
            diagnose=False,          # 不打印局部变量，避免密钥等敏感值进日志
        )
    except OSError as exc:
        logger.error(f"JSONL 日志 sink 创建失败，仅保留控制台输出: {exc}")
        return None

    logger.debug(f"日志系统就绪: 控制台={enable_console} JSONL={json_path}")
    return json_path
