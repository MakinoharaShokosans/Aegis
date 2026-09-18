"""LangGraph 状态快照的生命周期管理（SQLite / WAL）。

对应 ``documents/agent_runtime/04_routing_and_control_flow.md`` §4。

**为什么要单独一个模块**：``AsyncSqliteSaver`` 需要一个**长生命周期**的
``aiosqlite`` 连接，且必须由创建它的同一个事件循环任务负责关闭。
把"连接怎么开、表怎么建、怎么关"收在一处，``workflow.py`` 才能保持只关心编排。

**依赖说明**：``AsyncSqliteSaver`` 来自独立包 ``langgraph-checkpoint-sqlite``，
已在本工程声明并锁定（见 ``pyproject.toml``）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import aiosqlite
from loguru import logger

__all__ = ["SqliteCheckpointStore"]


class SqliteCheckpointStore:
    """SQLite 检查点存储的持有者。

    Args:
        db_path: 检查点数据库路径。
    """

    __slots__ = ("db_path", "_connection", "_saver")

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._connection: Optional[aiosqlite.Connection] = None
        self._saver: Optional[object] = None

    @property
    def saver(self) -> Optional[object]:
        """底层 saver 实例（供 ``graph.compile(checkpointer=...)`` 使用）。"""
        return self._saver

    async def open(self) -> None:
        """建立连接、开启 WAL 并确保检查点表存在。

        Raises:
            RuntimeError: 依赖包缺失（提示安装 ``langgraph-checkpoint-sqlite``）。
        """
        if self._saver is not None:
            return

        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
        except ImportError as exc:  # pragma: no cover - 依赖已在 pyproject 声明
            raise RuntimeError(
                "缺少 langgraph-checkpoint-sqlite，请执行 uv add \"langgraph-checkpoint-sqlite\""
            ) from exc

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.db_path)
        await self._connection.execute("PRAGMA journal_mode=WAL;")
        await self._connection.execute("PRAGMA busy_timeout=5000;")
        await self._connection.commit()

        serde = JsonPlusSerializer(
            allowed_msgpack_modules=[
                ("agent_runtime.state", "Milestone"),
                ("agent_runtime.state", "FailedAttempt"),
            ]
        )
        self._saver = AsyncSqliteSaver(self._connection, serde=serde)
        # 显式建表，避免首次调用时才懒建表导致的偶发并发竞争
        setup = getattr(self._saver, "setup", None)
        if callable(setup):
            await setup()
        logger.info(f"[Checkpoint] SQLite 检查点存储就绪: {self.db_path}")

    async def close(self) -> None:
        """关闭连接（应由应用 lifespan 在关闭阶段调用）。"""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._saver = None
            logger.info("[Checkpoint] 检查点连接已关闭")
