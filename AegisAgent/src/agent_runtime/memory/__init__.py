"""
Aegis 记忆子系统 (memory)

对外统一暴露的类与模型：
- MemoryManager: 记忆管理顶层门面
- SqliteMemoryStore: SQLite 异步存储引擎
- MemoryCompactor: 滚动压缩与事实提炼器
- CompressedMemory: 认知记忆体模型
- FailedAttempt: 踩坑禁区数据模型
- TurnRecord: 对话轮次模型
- SessionMetadata: 会话元数据模型
"""

from agent_runtime.memory.compactor import MemoryCompactor, select_turns_for_compaction
from agent_runtime.memory.manager import MemoryManager
from agent_runtime.memory.models import (
    CompressedMemory,
    FailedAttempt,
    SessionMetadata,
    TurnRecord,
    TurnRole,
    Workspace,
    WorkspaceMemory,
)
from agent_runtime.memory.sqlite_store import SqliteMemoryStore

__all__ = [
    "MemoryManager",
    "SqliteMemoryStore",
    "MemoryCompactor",
    "select_turns_for_compaction",
    "CompressedMemory",
    "Workspace",
    "WorkspaceMemory",
    "FailedAttempt",
    "TurnRecord",
    "TurnRole",
    "SessionMetadata",
]


