"""
Aegis 记忆系统顶层管理器 (manager.py)

功能描述：
1. 充当记忆子系统的统一门面类 (Facade)，统筹 SqliteMemoryStore 与 MemoryCompactor；
2. 调度双层作用域记忆：
   - 跨会话全局共享的工作区长期记忆 (WorkspaceMemory)；
   - 单会话专属的情境认知记忆 (CompressedMemory)；
3. 驱动高低水位对话对齐动态压缩算法：
   - 基于 tiktoken 进行精确物理分词计算；
   - 达到 80% Token 高水位硬指标时自动触发；
   - 严格按完整人机对话单元对齐，切除最古老约 40% 对话进行提炼，安全恢复至低水位；
4. 为上层 ContextManager 提供极简异步 API。
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Literal, Optional, Tuple
from loguru import logger

from agent_runtime.config import AegisConfig, get_config
from agent_runtime.memory.compactor import MemoryCompactor, select_turns_for_compaction
from agent_runtime.memory.models import (
    CompressedMemory,
    FailedAttempt,
    SessionMetadata,
    TurnRecord,
    Workspace,
    WorkspaceMemory,
)
from agent_runtime.memory.sqlite_store import SqliteMemoryStore
from agent_runtime.tokenizer import count_tokens as _count_tokens


class MemoryManager:
    """
    会话与工作区双层记忆统筹管理器
    """

    def __init__(
        self,
        store: Optional[SqliteMemoryStore] = None,
        compactor: Optional[MemoryCompactor] = None,
        session_token_limit: Optional[int] = None,
        compaction_high_watermark: Optional[float] = None,
        compaction_ratio: Optional[float] = None,
        active_window_turns: Optional[int] = None,
    ):
        """
        初始化记忆管理器
        
        Args:
            store: 自定义存储驱动 (若为 None 则根据 config.toml 中的 metadata_db_path 初始化)
            compactor: 自定义压缩器 (若为 None 则使用默认 Fast 模型压缩器)
            session_token_limit: 单会话 Token 物理硬上限 (默认读取配置)
            compaction_high_watermark: 高水位触发线比例 (默认读取配置, 0.80)
            compaction_ratio: 目标压缩切片比例 (默认读取配置, 0.40)
            active_window_turns: 保底保留的最少未压缩对话轮数 (默认读取配置)
        """
        cfg = get_config()

        # 1. 注入存储引擎
        if store is not None:
            self.store = store
        else:
            db_path = cfg.runtime.storage.metadata_db_path
            self.store = SqliteMemoryStore(db_path)

        # 2. 注入压缩引擎
        self.compactor = compactor or MemoryCompactor()

        # 3. 注入动态物理阈值 (零魔法数字)
        ctx_cfg = cfg.runtime.context
        self.session_token_limit = (
            session_token_limit if session_token_limit is not None else ctx_cfg.session_token_limit
        )
        self.compaction_high_watermark = (
            compaction_high_watermark
            if compaction_high_watermark is not None
            else ctx_cfg.compaction_high_watermark
        )
        self.compaction_ratio = (
            compaction_ratio if compaction_ratio is not None else ctx_cfg.compaction_ratio
        )
        self.active_window_turns = (
            active_window_turns if active_window_turns is not None else ctx_cfg.active_window_turns
        )

        logger.debug(
            f"MemoryManager 初始化就绪: Token上限={self.session_token_limit}, "
            f"高水位触发线={int(self.compaction_high_watermark * 100)}%, "
            f"目标压缩率={int(self.compaction_ratio * 100)}%"
        )

    @classmethod
    def from_config(
        cls,
        cfg: AegisConfig,
        store: Optional[SqliteMemoryStore] = None,
        compactor: Optional[MemoryCompactor] = None,
    ) -> MemoryManager:
        """根据配置对象构造 MemoryManager，确保存储与阈值与 cfg 完全对齐。"""
        return cls(
            store=store or SqliteMemoryStore(cfg.runtime.storage.metadata_db_path),
            compactor=compactor,
            session_token_limit=cfg.runtime.context.session_token_limit,
            compaction_high_watermark=cfg.runtime.context.compaction_high_watermark,
            compaction_ratio=cfg.runtime.context.compaction_ratio,
            active_window_turns=cfg.runtime.context.active_window_turns,
        )

    def count_tokens(self, text: str) -> int:
        """
        计量输入文本的物理 Token 数量。

        委托给 :mod:`agent_runtime.tokenizer` 的统一实现，保证全系统
        （记忆压缩 / 观察值裁剪 / 上下文装配 / 预算守卫）使用**同一分词口径**，
        避免同一个字符串在不同模块算出不同 Token 数。

        Args:
            text: 目标文本

        Returns:
            int: 物理 Token 数
        """
        return _count_tokens(text)

    async def initialize(self) -> None:
        """初始化底层存储环境"""
        await self.store.initialize()

    # ==========================================================================
    # 0. 工作区与多会话生命周期管理 (Workspace & Sessions Lifecycle)
    # ==========================================================================

    async def create_workspace(
        self,
        name: str,
        root_path: str,
        description: str = "",
        workspace_id: Optional[str] = None,
    ) -> Workspace:
        """
        创建新工作区 (绑定工程根路径)
        """
        await self.store.initialize()
        ws_id = workspace_id or str(uuid.uuid4())
        return await self.store.create_or_get_workspace(
            workspace_id=ws_id,
            name=name,
            root_path=root_path,
            description=description,
        )

    async def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """获取工作区元数据"""
        await self.store.initialize()
        return await self.store.get_workspace(workspace_id)

    async def get_workspace_by_path(self, root_path: str) -> Optional[Workspace]:
        """按物理根目录路径反查工作区"""
        await self.store.initialize()
        return await self.store.get_workspace_by_path(root_path)

    async def list_workspaces(self) -> List[Workspace]:
        """枚举全部纳管的工作区列表"""
        await self.store.initialize()
        return await self.store.list_workspaces()

    async def delete_workspace(self, workspace_id: str) -> bool:
        """物理级联删除工作区及其所有会话资产"""
        await self.store.initialize()
        return await self.store.delete_workspace(workspace_id)

    async def create_session(
        self,
        workspace_id: str,
        title: str = "",
        session_id: Optional[str] = None,
    ) -> SessionMetadata:
        """在指定工作区下创建新会话"""
        await self.store.initialize()
        sid = session_id or str(uuid.uuid4())
        return await self.store.create_or_get_session(
            session_id=sid,
            workspace_id=workspace_id,
            title=title,
        )

    async def list_sessions(self, workspace_id: str) -> List[SessionMetadata]:
        """获取指定工作区下的所有会话列表"""
        await self.store.initialize()
        return await self.store.list_sessions_by_workspace(workspace_id)

    async def delete_session(self, session_id: str) -> bool:
        """删除指定会话及关联流水与记忆"""
        await self.store.initialize()
        return await self.store.delete_session(session_id)

    # ==========================================================================
    # 1. 上下文装配读取 (Context Ingestion)
    # ==========================================================================

    async def load_session_context(
        self,
        session_id: str,
        workspace_id: str = "default",
    ) -> Tuple[Workspace, WorkspaceMemory, CompressedMemory, List[TurnRecord]]:
        """
        任务启动阶段调用：一键读取四层工作区与记忆资产供 Prompt 装配器使用
        
        Args:
            session_id: 当前会话 UUID
            workspace_id: 当前工作区唯一标识
            
        Returns:
            Tuple[Workspace, WorkspaceMemory, CompressedMemory, List[TurnRecord]]:
                1. 工作区实体元数据 (包含 root_path, name)
                2. 工作区全局长期记忆 (跨会话共享)
                3. 当前会话已压缩情境记忆
                4. 安全低水位线以上的全部活跃未压缩对话对 (时间正序)
        """
        await self.store.initialize()

        # 确保会话存在并获取其实际归属的 workspace_id
        session_meta = await self.store.create_or_get_session(session_id, workspace_id=workspace_id)
        actual_ws_id = session_meta.workspace_id or workspace_id

        # 读取工作区元数据 (若尚未显式创建则补齐默认元数据)
        workspace = await self.store.get_workspace(actual_ws_id)
        if not workspace:
            workspace = await self.store.create_or_get_workspace(
                workspace_id=actual_ws_id,
                name=f"Workspace_{actual_ws_id}",
                root_path=f"/workspaces/{actual_ws_id}",
            )

        # 读取工作区共享记忆、会话已压缩记忆与活跃未压缩流水
        workspace_mem = await self.store.get_workspace_memory(actual_ws_id)
        session_mem = await self.store.get_compressed_memory(session_id)
        active_turns = await self.store.get_active_turns(session_id)

        # 保底防护：若活跃轮数少于 active_window_turns，尝试拉取最近 N 轮
        if len(active_turns) < self.active_window_turns:
            active_turns = await self.store.get_recent_turns(session_id, limit=self.active_window_turns)

        logger.debug(
            f"加载工作区多层记忆成功 [session_id={session_id}, ws={actual_ws_id}]: "
            f"工作区根路径={workspace.root_path}, "
            f"工作区架构事实={len(workspace_mem.confirmed_architecture)}, "
            f"会话局部事实={len(session_mem.confirmed_facts)}, 活跃轮数={len(active_turns)}"
        )
        return workspace, workspace_mem, session_mem, active_turns


    # ==========================================================================
    # 2. 交互交付与动态高低水位压缩 (Delivery & Watermark Compaction)
    # ==========================================================================

    async def record_turn_and_maybe_compact(
        self,
        session_id: str,
        user_query: str,
        agent_delivery: str,
        last_action_target: Optional[Dict[str, List[str]]] = None,
        workspace_id: str = "default",
    ) -> None:
        """
        任务完成交付阶段调用：
        1. 物理计量用户提问与 Agent 答复的 Token 数量并持久化；
        2. 更新上一轮操作实体 (last_action_target)；
        3. 检测活跃未压缩 Token 总量是否触达 80% 高水位线；
        4. 若触达，则按对话对齐切出最古老约 40% 的对话进行提炼，安全恢复至低水位。
        
        Args:
            session_id: 会话唯一标识
            user_query: 用户本轮提问
            agent_delivery: Agent 本轮交付结论
            last_action_target: 本轮涉及的核心修改实体 (文件/符号等)
            workspace_id: 所属工作区标识
        """
        await self.store.initialize()

        # 1. 物理计量 Token 消耗
        tokens_user = self.count_tokens(user_query)
        tokens_agent = self.count_tokens(agent_delivery)

        # 2. 持久化记录到对话流水表
        await self.store.add_turn(session_id, "user", user_query, tokens_user)
        await self.store.add_turn(session_id, "assistant", agent_delivery, tokens_agent)

        # 3. 关联更新会话情境记忆元数据
        current_memory = await self.store.get_compressed_memory(session_id)
        if last_action_target:
            current_memory.last_action_target = last_action_target
            await self.store.save_compressed_memory(session_id, current_memory)

        # 4. 高低水位检测：计算当前活跃未压缩对话的总物理 Token
        active_tokens = await self.store.get_active_turns_token_sum(session_id)
        trigger_threshold = int(self.session_token_limit * self.compaction_high_watermark)

        logger.debug(
            f"会话水位监测 [session_id={session_id}]: "
            f"当前活跃Token={active_tokens} / 触发上限={trigger_threshold} ({self.compaction_high_watermark:.0%})"
        )

        # 5. 触达 80% 高水位，触发基于对话完整性对齐的动态压缩
        if active_tokens >= trigger_threshold:
            target_compact_tokens = int(self.session_token_limit * self.compaction_ratio)
            active_turns = await self.store.get_active_turns(session_id)

            overflow_turns, remaining_turns = select_turns_for_compaction(
                active_turns=active_turns,
                target_compact_tokens=target_compact_tokens,
            )

            if overflow_turns:
                logger.info(
                    f"触发高水位压缩! 当前活跃={active_tokens} >= {trigger_threshold}, "
                    f"切出最古老约 {target_compact_tokens} Token (实际切出 {len(overflow_turns)} 轮对话)"
                )

                # 调度 Fast 模型执行提炼并更新水位指针
                new_memory = await self.compactor.compact(current_memory, overflow_turns)
                new_memory.compacted_until_turn_id = overflow_turns[-1].id or current_memory.compacted_until_turn_id
                
                # 持久化更新后的会话记忆
                await self.store.save_compressed_memory(session_id, new_memory)

                # 计算压缩后的安全低水位
                new_active_tokens = sum(t.token_count for t in remaining_turns)
                logger.info(
                    f"会话高低水位压缩成功完成! 新水位线ID={new_memory.compacted_until_turn_id}, "
                    f"活跃Token由 {active_tokens} 降至 {new_active_tokens} (占比 {new_active_tokens / self.session_token_limit:.1%})"
                )

    # ==========================================================================
    # 3. 工作区跨会话共享接口 (Workspace Sharing Operations)
    # ==========================================================================

    async def get_workspace_memory(self, workspace_id: str = "default") -> WorkspaceMemory:
        """读取工作区全局共享记忆"""
        return await self.store.get_workspace_memory(workspace_id)

    async def promote_fact_to_workspace(
        self,
        workspace_id: str,
        fact: str,
        category: Literal[
            "convention",
            "architecture",
            "user_profile",
            "knowledge",
            "project_conventions",
            "confirmed_architecture",
        ] = "architecture",
    ) -> None:
        """
        将单会话或外部录入的全局性结论/用户画像上浮沉淀到工作区共享库 (所有会话可见)
        
        Args:
            workspace_id: 工作区标识
            fact: 确凿的知识事实、画像偏好或规范
            category: 类别 ('user_profile', 'convention' / 'project_conventions', 'architecture' / 'confirmed_architecture')
        """
        ws_mem = await self.store.get_workspace_memory(workspace_id)
        if category in ("user_profile",):
            ws_mem.user_profile.append(fact)
        elif category in ("convention", "project_conventions"):
            ws_mem.project_conventions.append(fact)
        else:
            ws_mem.confirmed_architecture.append(fact)
        ws_mem.deduplicate()
        await self.store.save_workspace_memory(ws_mem)
        logger.info(f"已上浮全局记忆至工作区 [{workspace_id}]: [{category}] {fact}")

    async def record_global_failure(
        self,
        workspace_id: str,
        failed_attempt: FailedAttempt,
    ) -> None:
        """沉淀跨会话有效的全局避坑黑名单"""
        ws_mem = await self.store.get_workspace_memory(workspace_id)
        ws_mem.global_failed_attempts.append(failed_attempt)
        await self.store.save_workspace_memory(ws_mem)
        logger.info(f"已追加全局避坑禁区至工作区 [{workspace_id}]: {failed_attempt.action}")

    async def get_session_info(self, session_id: str) -> SessionMetadata:
        """获取会话元数据基础信息"""
        return await self.store.create_or_get_session(session_id)

    # ==========================================================================
    # 4. 只读与更新接口（供 HTTP API 使用）
    # ==========================================================================

    async def get_session(self, session_id: str) -> Optional[SessionMetadata]:
        """按 ID 查询会话（不创建）。

        Args:
            session_id: 会话唯一标识。

        Returns:
            会话元数据；不存在时返回 ``None``。
        """
        return await self.store.get_session(session_id)

    async def list_turns(
        self,
        session_id: str,
        limit: int = 50,
        before_id: Optional[int] = None,
    ):
        """分页查询会话对话流水。

        Args:
            session_id: 会话唯一标识。
            limit: 单页条数。
            before_id: 向后翻页游标。

        Returns:
            轮次列表（时间正序）。
        """
        return await self.store.list_turns(session_id, limit=limit, before_id=before_id)

    async def update_workspace(
        self,
        workspace_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Workspace]:
        """更新工作区元数据。

        Args:
            workspace_id: 工作区标识。
            name: 新名称。
            description: 新描述。

        Returns:
            更新后的工作区；不存在时返回 ``None``。
        """
        return await self.store.update_workspace(workspace_id, name=name, description=description)

    async def get_session_context(
        self,
        session_id: str,
        workspace_id: str = "default",
    ):
        """读取上下文装配所需的四层资产（供 ``/context`` 检视端点使用）。

        Args:
            session_id: 会话唯一标识。
            workspace_id: 工作区标识。

        Returns:
            ``(workspace, workspace_memory, session_memory, active_turns)``。
        """
        return await self.load_session_context(session_id, workspace_id=workspace_id)
