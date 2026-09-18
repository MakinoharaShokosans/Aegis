"""
Aegis 记忆系统 SQLite 异步存储引擎 (sqlite_store.py)

功能描述：
1. 基于 aiosqlite 驱动操作本地 SQLite 数据库 (默认为 storage/aegis_meta.db)；
2. 强制开启 WAL (Write-Ahead Logging) 模式与高并发 busy_timeout，确保读写零死锁；
3. 严格遵循 ACID 事务，纳管四大核心表：
   - workspace_memories: 工作区跨会话全局共享长期记忆表
   - sessions: 会话元数据主表
   - session_turns: 人机对话轮次流水表 (带物理 token_count 缓存)
   - session_memories: 单会话已压缩情境记忆表 (带 compacted_until_turn_id 水位指针)
4. 支撑基于 Token 水位的活跃轮次切片，毫秒级计算会话活跃水位。
"""

import json
from pathlib import Path
import time
from typing import List, Optional
import aiosqlite
from loguru import logger

from agent_runtime.memory.models import (
    CompressedMemory,
    FailedAttempt,
    SessionMetadata,
    TurnRecord,
    TurnRole,
    Workspace,
    WorkspaceMemory,
)


class SqliteMemoryStore:
    """
    基于 SQLite 的异步会话与双层记忆持久化存储驱动
    """

    def __init__(self, db_path: str | Path):
        """
        初始化存储引擎
        
        Args:
            db_path: SQLite 数据库物理文件路径
        """
        self.db_path = Path(db_path)
        self._initialized = False

    async def initialize(self) -> None:
        """
        异步初始化底层 SQLite 数据库环境：
        1. 确保目标父级目录存在；
        2. 开启 WAL 高并发模式与外键约束；
        3. 自动建立五大核心表及索引 (workspaces, workspace_memories, sessions, session_turns, session_memories)。
        """
        if self._initialized:
            return

        # 确保存储目录物理存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            # 配置高性能与防死锁 PRAGMA 选项
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA busy_timeout=5000;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute("PRAGMA foreign_keys=ON;")

            # 0. 工作区实体主表 (一等公民: 多工作区独立管理)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            await db.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_root 
                ON workspaces(root_path);
                """
            )

            # 1. 工作区全局长期记忆表 (跨会话共享，级联从属工作区)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS workspace_memories (
                    workspace_id TEXT PRIMARY KEY,
                    user_profile TEXT DEFAULT '[]',
                    project_conventions TEXT DEFAULT '[]',
                    confirmed_architecture TEXT DEFAULT '[]',
                    global_failed_attempts TEXT DEFAULT '[]',
                    updated_at REAL NOT NULL,
                    FOREIGN KEY(workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE
                );
                """
            )
            # 兼容已有库的自动列追加
            try:
                await db.execute("ALTER TABLE workspace_memories ADD COLUMN user_profile TEXT DEFAULT '[]';")
            except Exception:
                pass

            # 2. 会话主表 (隶属于工作区，1:N 级联从属)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL DEFAULT 'default',
                    title TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY(workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE
                );
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_ws 
                ON sessions(workspace_id);
                """
            )

            # 3. 人机对话轮次流水表 (含 token_count 缓存，级联从属于会话)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS session_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    token_count INTEGER NOT NULL DEFAULT 0,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                """
            )
            # 建立索引加速活跃流水查询
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_session_turns_active 
                ON session_turns(session_id, id ASC);
                """
            )

            # 4. 单会话已压缩情境记忆表 (包含水位线指针，级联从属于会话)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS session_memories (
                    session_id TEXT PRIMARY KEY,
                    compacted_until_turn_id INTEGER DEFAULT 0,
                    summary TEXT DEFAULT '',
                    confirmed_facts TEXT DEFAULT '[]',
                    failed_attempts TEXT DEFAULT '[]',
                    last_action_target TEXT DEFAULT '{}',
                    updated_at REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                """
            )

            await db.commit()

        self._initialized = True
        logger.info(f"SQLite 记忆存储引擎初始化完成: {self.db_path}")

    async def _ensure_init(self) -> None:
        """内部防护：确保在任意数据操作前已完成 schema 准备"""
        if not self._initialized:
            await self.initialize()

    async def _ensure_workspace_exists(self, db: aiosqlite.Connection, workspace_id: str) -> None:
        """内部防护：确保外键引用的工作区存在，若不存在自动补齐默认记录"""
        async with db.execute("SELECT 1 FROM workspaces WHERE workspace_id = ?", (workspace_id,)) as cursor:
            if not await cursor.fetchone():
                now = time.time()
                await db.execute(
                    """
                    INSERT OR IGNORE INTO workspaces 
                    (workspace_id, name, root_path, description, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (workspace_id, f"Workspace_{workspace_id}", f"/workspaces/{workspace_id}", "自动生成的默认工作区", now, now),
                )

    # ==========================================================================
    # 0. 工作区实体管理接口 (Workspace Management CRUD)
    # ==========================================================================

    async def create_or_get_workspace(
        self,
        workspace_id: str,
        name: str,
        root_path: str,
        description: str = "",
    ) -> Workspace:
        """
        创建或获取工作区实体
        
        Args:
            workspace_id: 工作区唯一标识
            name: 工作区可读名称
            root_path: 工程物理根路径
            description: 项目描述
            
        Returns:
            Workspace: 工作区实体对象
        """
        await self._ensure_init()
        now = time.time()
        norm_path = str(Path(root_path).resolve())

        async with aiosqlite.connect(self.db_path) as db:
            # 1. 检查是否存在同 ID 或同路径的工作区
            async with db.execute(
                """
                SELECT workspace_id, name, root_path, description, created_at, updated_at
                FROM workspaces 
                WHERE workspace_id = ? OR root_path = ?
                """,
                (workspace_id, norm_path),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return Workspace(
                        workspace_id=row[0],
                        name=row[1],
                        root_path=row[2],
                        description=row[3],
                        created_at=row[4],
                        updated_at=row[5],
                    )

            # 2. 插入新工作区主记录
            await db.execute(
                """
                INSERT INTO workspaces (workspace_id, name, root_path, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (workspace_id, name, norm_path, description, now, now),
            )
            # 初始化工作区空白长期记忆
            await db.execute(
                """
                INSERT OR IGNORE INTO workspace_memories (workspace_id, project_conventions, confirmed_architecture, global_failed_attempts, updated_at)
                VALUES (?, '[]', '[]', '[]', ?)
                """,
                (workspace_id, now),
            )
            await db.commit()

        logger.info(f"已创建新工作区 [workspace_id={workspace_id}, name={name}, path={norm_path}]")
        return Workspace(
            workspace_id=workspace_id,
            name=name,
            root_path=norm_path,
            description=description,
            created_at=now,
            updated_at=now,
        )

    async def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """根据 ID 查询工作区"""
        await self._ensure_init()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT workspace_id, name, root_path, description, created_at, updated_at FROM workspaces WHERE workspace_id = ?",
                (workspace_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return Workspace(
                    workspace_id=row[0],
                    name=row[1],
                    root_path=row[2],
                    description=row[3],
                    created_at=row[4],
                    updated_at=row[5],
                )

    async def get_workspace_by_path(self, root_path: str) -> Optional[Workspace]:
        """根据工程物理根路径反查工作区"""
        await self._ensure_init()
        norm_path = str(Path(root_path).resolve())
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT workspace_id, name, root_path, description, created_at, updated_at FROM workspaces WHERE root_path = ?",
                (norm_path,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return Workspace(
                    workspace_id=row[0],
                    name=row[1],
                    root_path=row[2],
                    description=row[3],
                    created_at=row[4],
                    updated_at=row[5],
                )

    async def list_workspaces(self) -> List[Workspace]:
        """按最近活跃时间倒序列出所有工作区"""
        await self._ensure_init()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT workspace_id, name, root_path, description, created_at, updated_at FROM workspaces ORDER BY updated_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            Workspace(
                workspace_id=r[0],
                name=r[1],
                root_path=r[2],
                description=r[3],
                created_at=r[4],
                updated_at=r[5],
            )
            for r in rows
        ]

    async def update_workspace(
        self,
        workspace_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Workspace]:
        """更新工作区基础信息"""
        await self._ensure_init()
        ws = await self.get_workspace(workspace_id)
        if not ws:
            return None
        now = time.time()
        new_name = name if name is not None else ws.name
        new_desc = description if description is not None else ws.description

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE workspaces SET name = ?, description = ?, updated_at = ? WHERE workspace_id = ?",
                (new_name, new_desc, now, workspace_id),
            )
            await db.commit()

        ws.name = new_name
        ws.description = new_desc
        ws.updated_at = now
        return ws

    async def delete_workspace(self, workspace_id: str) -> bool:
        """
        物理删除工作区（依托外键 ON DELETE CASCADE 级联删除其下全部会话、记忆体与流水）
        """
        await self._ensure_init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            cursor = await db.execute(
                "DELETE FROM workspaces WHERE workspace_id = ?",
                (workspace_id,),
            )
            await db.commit()
            deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"已级联删除工作区及全部关联会话资产 [workspace_id={workspace_id}]")
        return deleted

    # ==========================================================================
    # 1. 工作区全局共享记忆接口 (Workspace Memory)
    # ==========================================================================

    async def get_workspace_memory(self, workspace_id: str = "default") -> WorkspaceMemory:
        """
        读取指定工作区的全局共享记忆 (跨会话共享)
        
        Args:
            workspace_id: 工作区标识
            
        Returns:
            WorkspaceMemory: 工作区记忆对象 (若不存在则返回默认空对象)
        """
        await self._ensure_init()

        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_workspace_exists(db, workspace_id)
            async with db.execute(
                """
                SELECT project_conventions, confirmed_architecture, global_failed_attempts, updated_at, user_profile 
                FROM workspace_memories 
                WHERE workspace_id = ?
                """,
                (workspace_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return WorkspaceMemory(workspace_id=workspace_id)

                convs_raw = row[0] or "[]"
                archs_raw = row[1] or "[]"
                fails_raw = row[2] or "[]"
                updated_at = row[3] or time.time()
                user_raw = (row[4] if len(row) > 4 else None) or "[]"

                try:
                    convs = json.loads(convs_raw)
                except Exception:
                    convs = []

                try:
                    archs = json.loads(archs_raw)
                except Exception:
                    archs = []

                try:
                    fails_data = json.loads(fails_raw)
                    fails = [FailedAttempt(**item) for item in fails_data if isinstance(item, dict)]
                except Exception:
                    fails = []

                try:
                    user_prof = json.loads(user_raw)
                except Exception:
                    user_prof = []

                return WorkspaceMemory(
                    workspace_id=workspace_id,
                    user_profile=user_prof,
                    project_conventions=convs,
                    confirmed_architecture=archs,
                    global_failed_attempts=fails,
                    updated_at=updated_at,
                )

    async def save_workspace_memory(self, memory: WorkspaceMemory) -> None:
        """
        持久化保存工作区全局共享记忆
        
        Args:
            memory: 待保存的工作区记忆对象
        """
        await self._ensure_init()
        now = time.time()
        memory.updated_at = now
        memory.deduplicate()

        user_json = json.dumps(memory.user_profile, ensure_ascii=False)
        conv_json = json.dumps(memory.project_conventions, ensure_ascii=False)
        arch_json = json.dumps(memory.confirmed_architecture, ensure_ascii=False)
        fails_json = json.dumps([f.model_dump() for f in memory.global_failed_attempts], ensure_ascii=False)

        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_workspace_exists(db, memory.workspace_id)
            await db.execute(
                """
                INSERT OR REPLACE INTO workspace_memories 
                (workspace_id, user_profile, project_conventions, confirmed_architecture, global_failed_attempts, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (memory.workspace_id, user_json, conv_json, arch_json, fails_json, now),
            )
            await db.commit()

        logger.debug(f"已更新工作区全局记忆 [ws={memory.workspace_id}, user_prof={len(memory.user_profile)}, convs={len(memory.project_conventions)}, archs={len(memory.confirmed_architecture)}]")

    # ==========================================================================
    # 2. 会话管理接口 (Session Management)
    # ==========================================================================

    async def create_or_get_session(
        self,
        session_id: str,
        workspace_id: str = "default",
        title: str = "",
    ) -> SessionMetadata:
        """
        创建或获取已有会话记录
        
        Args:
            session_id: 会话唯一标识 UUID
            workspace_id: 所属工作区标识
            title: 可选的会话初始标题
            
        Returns:
            SessionMetadata: 会话元数据对象
        """
        await self._ensure_init()
        now = time.time()

        async with aiosqlite.connect(self.db_path) as db:
            await self._ensure_workspace_exists(db, workspace_id)
            async with db.execute(
                "SELECT session_id, workspace_id, title, created_at, updated_at FROM sessions WHERE session_id = ?",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return SessionMetadata(
                        session_id=row[0],
                        workspace_id=row[1],
                        title=row[2],
                        created_at=row[3],
                        updated_at=row[4],
                    )

            # 会话不存在，插入会话主记录与默认情境记忆
            await db.execute(
                "INSERT INTO sessions (session_id, workspace_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, workspace_id, title, now, now),
            )
            await db.execute(
                """
                INSERT OR IGNORE INTO session_memories 
                (session_id, compacted_until_turn_id, summary, confirmed_facts, failed_attempts, last_action_target, updated_at)
                VALUES (?, 0, '', '[]', '[]', '{}', ?)
                """,
                (session_id, now),
            )
            await db.commit()

        logger.debug(f"已新建会话记录 [session_id={session_id}, workspace_id={workspace_id}]")
        return SessionMetadata(session_id=session_id, workspace_id=workspace_id, title=title, created_at=now, updated_at=now)

    async def list_sessions_by_workspace(self, workspace_id: str) -> List[SessionMetadata]:
        """查询指定工作区下的所有会话 (按最后活跃时间倒序)"""
        await self._ensure_init()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT session_id, workspace_id, title, created_at, updated_at 
                FROM sessions 
                WHERE workspace_id = ? 
                ORDER BY updated_at DESC
                """,
                (workspace_id,),
            ) as cursor:
                rows = await cursor.fetchall()

        return [
            SessionMetadata(
                session_id=r[0],
                workspace_id=r[1],
                title=r[2],
                created_at=r[3],
                updated_at=r[4],
            )
            for r in rows
        ]

    async def delete_session(self, session_id: str) -> bool:
        """删除指定会话（级联删除其下的流水和局部认知记忆）"""
        await self._ensure_init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            cursor = await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            await db.commit()
            deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"已级联删除会话及其关联流水与记忆 [session_id={session_id}]")
        return deleted

    # ==========================================================================
    # 3. 对话流水与 Token 水位查询 (Turns & Token Metrics)
    # ==========================================================================

    async def add_turn(
        self,
        session_id: str,
        role: TurnRole,
        content: str,
        token_count: int = 0,
    ) -> TurnRecord:
        """
        追加单轮人机对话记录 (带物理 Token 计数缓存)
        
        Args:
            session_id: 会话唯一标识
            role: 角色 ('user' 或 'assistant')
            content: 对话正文
            token_count: 该轮文本的真实 Token 数量
            
        Returns:
            TurnRecord: 附带主键与 Token 计数的完整记录
        """
        await self._ensure_init()
        now = time.time()

        # 确保会话存在
        await self.create_or_get_session(session_id)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO session_turns (session_id, role, content, token_count, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, token_count, now),
            )
            inserted_id = cursor.lastrowid
            await db.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            await db.commit()

        logger.debug(f"已追加对话轮次 [session_id={session_id}, turn_id={inserted_id}, role={role}, tokens={token_count}]")
        return TurnRecord(
            id=inserted_id,
            session_id=session_id,
            role=role,
            content=content,
            token_count=token_count,
            timestamp=now,
        )

    async def get_active_turns(self, session_id: str) -> List[TurnRecord]:
        """
        获取当前会话处于安全低水位线以上的全部活跃未压缩对话 (按时间正序排列)
        仅取 id > compacted_until_turn_id 的记录
        
        Args:
            session_id: 会话唯一标识
            
        Returns:
            List[TurnRecord]: 活跃对话记录列表 (最早 -> 最新)
        """
        await self._ensure_init()
        # 1. 读出当前已压缩到的 turn_id 水位线
        mem = await self.get_compressed_memory(session_id)
        cutoff_id = mem.compacted_until_turn_id

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, session_id, role, content, token_count, timestamp 
                FROM session_turns 
                WHERE session_id = ? AND id > ?
                ORDER BY id ASC
                """,
                (session_id, cutoff_id),
            ) as cursor:
                rows = await cursor.fetchall()

        return [
            TurnRecord(
                id=r[0],
                session_id=r[1],
                role=r[2],
                content=r[3],
                token_count=r[4],
                timestamp=r[5],
            )
            for r in rows
        ]

    async def get_active_turns_token_sum(self, session_id: str) -> int:
        """
        精准查询当前会话未压缩活跃对话的总物理 Token 累积量 (用于比对 80% 高水位线)
        
        Args:
            session_id: 会话唯一标识
            
        Returns:
            int: 活跃 Token 总数
        """
        await self._ensure_init()
        mem = await self.get_compressed_memory(session_id)
        cutoff_id = mem.compacted_until_turn_id

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT COALESCE(SUM(token_count), 0) 
                FROM session_turns 
                WHERE session_id = ? AND id > ?
                """,
                (session_id, cutoff_id),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_recent_turns(self, session_id: str, limit: int) -> List[TurnRecord]:
        """获取最近 N 轮对话 (保底接口)"""
        await self._ensure_init()
        if limit <= 0:
            return []

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, session_id, role, content, token_count, timestamp 
                FROM session_turns 
                WHERE session_id = ? 
                ORDER BY id DESC 
                LIMIT ?
                """,
                (session_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()

        turns = [
            TurnRecord(
                id=r[0],
                session_id=r[1],
                role=r[2],
                content=r[3],
                token_count=r[4],
                timestamp=r[5],
            )
            for r in rows
        ]
        turns.reverse()
        return turns

    async def get_total_turns_count(self, session_id: str) -> int:
        """查询指定会话的历史对话总轮数"""
        await self._ensure_init()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(1) FROM session_turns WHERE session_id = ?",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    # ==========================================================================
    # 4. 会话已压缩情境记忆接口 (Session Compressed Memory)
    # ==========================================================================

    async def get_compressed_memory(self, session_id: str) -> CompressedMemory:
        """
        读取当前会话的已压缩认知记忆体 (含水位指针)
        
        Args:
            session_id: 会话唯一标识
            
        Returns:
            CompressedMemory: 认知记忆对象
        """
        await self._ensure_init()

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT compacted_until_turn_id, summary, confirmed_facts, failed_attempts, last_action_target, updated_at 
                FROM session_memories 
                WHERE session_id = ?
                """,
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return CompressedMemory()

                compacted_until = row[0] or 0
                summary = row[1] or ""
                raw_facts = row[2] or "[]"
                raw_attempts = row[3] or "[]"
                raw_target = row[4] or "{}"
                updated_at = row[5] or time.time()

                try:
                    facts_list = json.loads(raw_facts)
                except Exception:
                    facts_list = []

                try:
                    attempts_data = json.loads(raw_attempts)
                    attempts_list = [FailedAttempt(**item) for item in attempts_data if isinstance(item, dict)]
                except Exception:
                    attempts_list = []

                try:
                    target_dict = json.loads(raw_target)
                except Exception:
                    target_dict = {}

                return CompressedMemory(
                    compacted_until_turn_id=compacted_until,
                    summary=summary,
                    confirmed_facts=facts_list,
                    failed_attempts=attempts_list,
                    last_action_target=target_dict,
                    updated_at=updated_at,
                )

    async def save_compressed_memory(self, session_id: str, memory: CompressedMemory) -> None:
        """
        原子更新单会话已压缩情境记忆 (并同步推进水位指针)
        
        Args:
            session_id: 会话唯一标识
            memory: 待持久化的认知记忆对象
        """
        await self._ensure_init()
        now = time.time()
        memory.updated_at = now
        memory.deduplicate_facts()

        facts_json = json.dumps(memory.confirmed_facts, ensure_ascii=False)
        attempts_json = json.dumps([a.model_dump() for a in memory.failed_attempts], ensure_ascii=False)
        target_json = json.dumps(memory.last_action_target, ensure_ascii=False)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO session_memories 
                (session_id, compacted_until_turn_id, summary, confirmed_facts, failed_attempts, last_action_target, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, memory.compacted_until_turn_id, memory.summary, facts_json, attempts_json, target_json, now),
            )
            await db.commit()

        logger.debug(
            f"已保存会话压缩记忆 [session_id={session_id}, 水位线ID={memory.compacted_until_turn_id}, "
            f"facts={len(memory.confirmed_facts)}, attempts={len(memory.failed_attempts)}]"
        )

    # ==========================================================================
    # 5. 只读查询接口（供 HTTP API 的 GET 语义使用）
    #    注意：与 create_or_get_session 的区别在于"不存在即返回 None"，
    #    不会因为一次读请求而在库里凭空创建会话。
    # ==========================================================================

    async def get_session(self, session_id: str) -> Optional[SessionMetadata]:
        """按 ID 查询会话元数据（不创建）。

        Args:
            session_id: 会话唯一标识。

        Returns:
            会话元数据；不存在时返回 ``None``。
        """
        await self._ensure_init()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT session_id, workspace_id, title, created_at, updated_at
                FROM sessions WHERE session_id = ?
                """,
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return SessionMetadata(
                    session_id=row[0],
                    workspace_id=row[1],
                    title=row[2],
                    created_at=row[3],
                    updated_at=row[4],
                )

    async def list_turns(
        self,
        session_id: str,
        limit: int = 50,
        before_id: Optional[int] = None,
    ) -> List[TurnRecord]:
        """按游标倒序分页查询对话流水。

        Args:
            session_id: 会话唯一标识。
            limit: 单页条数。
            before_id: 只取 ``id`` 小于该值的记录（向后翻页游标）。

        Returns:
            轮次列表（时间正序，便于前端直接渲染）。
        """
        await self._ensure_init()
        if limit <= 0:
            return []

        sql = (
            "SELECT id, session_id, role, content, token_count, timestamp "
            "FROM session_turns WHERE session_id = ?"
        )
        params: List[object] = [session_id]
        if before_id is not None:
            sql += " AND id < ?"
            params.append(before_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(sql, tuple(params)) as cursor:
                rows = await cursor.fetchall()

        turns = [
            TurnRecord(
                id=row[0],
                session_id=row[1],
                role=row[2],
                content=row[3],
                token_count=row[4],
                timestamp=row[5],
            )
            for row in rows
        ]
        turns.reverse()
        return turns
