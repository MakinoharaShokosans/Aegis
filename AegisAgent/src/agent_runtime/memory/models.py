"""
Aegis 记忆系统强类型数据模型 (models.py)

功能描述：
定义会话元数据、人机对话流水轮次、已压缩认知记忆、工作区全局共享记忆与踩坑禁区的数据契约。
采用 Pydantic v2 强类型约束，确保数据在 SQLite 存取、Token 物理计算及 LLM 组装过程中的零类型泄露。
"""

import time
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# 会话角色字面量类型定义
TurnRole = Literal["user", "assistant"]


class TurnRecord(BaseModel):
    """
    单轮人机真实交互对话记录
    
    属性说明：
        id: 自增流水主键 (从数据库读取时赋值)
        session_id: 所属会话唯一标识 UUID
        role: 角色 ('user' 或 'assistant')
        content: 对话正文内容
        token_count: 该轮次正文的物理 Token 数 (通过 tiktoken 精准计量并缓存)
        timestamp: 记录生成时间戳 (秒)
    """
    id: Optional[int] = Field(default=None, description="自增流水主键")
    session_id: str = Field(description="会话唯一标识 UUID")
    role: TurnRole = Field(description="对话角色")
    content: str = Field(description="对话正文内容")
    token_count: int = Field(default=0, description="物理 Token 计数缓存")
    timestamp: float = Field(default_factory=time.time, description="创建时间戳")


class FailedAttempt(BaseModel):
    """
    踩坑反思记忆项 (负向经验，防止 Agent 原地打转或重复尝试无效方案)
    
    属性说明：
        action: 曾尝试的具体操作 (如编译参数、修改指令)
        failure_reason: 导致失败的核心报错摘要
        conclusion: 沉淀的技术禁区结论 (严禁再犯)
    """
    action: str = Field(description="曾尝试的具体操作描述")
    failure_reason: str = Field(description="错误或异常的关键信息")
    conclusion: str = Field(description="经检验得出的避坑结论")


class CompressedMemory(BaseModel):
    """
    单会话已压缩情境认知记忆体 (每个 Session 维持单条聚合记录，就地滚动更新)
    
    属性说明：
        compacted_until_turn_id: 标记当前已压缩到的最高 turn_id (此 ID 及之前的对话已纳入压缩)
        summary: 历史已压缩轮次的全局事实与进展摘要
        confirmed_facts: 本会话探索出的已确认客观事实列表
        failed_attempts: 本会话探索出的踩坑禁区清单
        last_action_target: 上一轮任务核心修改的实体对象 (如文件、函数符号等)
        updated_at: 记忆最后刷新时间戳
    """
    compacted_until_turn_id: int = Field(default=0, description="已压缩到的最新 turn_id 水位线")
    summary: str = Field(default="", description="已压缩历史的全局背景摘要")
    confirmed_facts: List[str] = Field(default_factory=list, description="本会话确认的客观事实列表")
    failed_attempts: List[FailedAttempt] = Field(default_factory=list, description="本会话踩坑禁区清单")
    last_action_target: Dict[str, List[str]] = Field(default_factory=dict, description="上一轮操作的核心实体与产物句柄")
    updated_at: float = Field(default_factory=time.time, description="最后更新时间戳")

    def deduplicate_facts(self) -> None:
        """对已确认事实进行顺序保留的唯一性去重"""
        seen = set()
        deduped: List[str] = []
        for fact in self.confirmed_facts:
            clean_fact = fact.strip()
            if clean_fact and clean_fact not in seen:
                seen.add(clean_fact)
                deduped.append(clean_fact)
        self.confirmed_facts = deduped


class WorkspaceMemory(BaseModel):
    """
    工作区全局长期记忆体 (跨会话共享，持久有效)
    
    属性说明：
        workspace_id: 工作区唯一标识 (如项目绝对路径哈希或代号)
        project_conventions: 项目全局代码风格、构建规范与用户偏好 (跨会话有效)
        confirmed_architecture: 已探明的核心系统架构定论与代码入口 (跨会话有效)
        global_failed_attempts: 全局避坑黑名单 (跨会话有效，避免新会话再犯)
        updated_at: 记忆最后更新时间戳
    """
    workspace_id: str = Field(default="default", description="工作区唯一标识")
    project_conventions: List[str] = Field(default_factory=list, description="项目全局编码规范与用户习惯")
    confirmed_architecture: List[str] = Field(default_factory=list, description="核心架构定论与关键入口")
    global_failed_attempts: List[FailedAttempt] = Field(default_factory=list, description="全局避坑黑名单")
    updated_at: float = Field(default_factory=time.time, description="最后更新时间戳")

    def deduplicate(self) -> None:
        """对规范与架构事实进行顺序保留的唯一性去重"""
        seen_conv = set()
        dedup_conv: List[str] = []
        for c in self.project_conventions:
            clean_c = c.strip()
            if clean_c and clean_c not in seen_conv:
                seen_conv.add(clean_c)
                dedup_conv.append(clean_c)
        self.project_conventions = dedup_conv

        seen_arch = set()
        dedup_arch: List[str] = []
        for a in self.confirmed_architecture:
            clean_a = a.strip()
            if clean_a and clean_a not in seen_arch:
                seen_arch.add(clean_a)
                dedup_arch.append(clean_a)
        self.confirmed_architecture = dedup_arch



class Workspace(BaseModel):
    """
    工作区实体数据模型 (一等公民：支持开辟多个独立工作区，每个工作区下挂载多个独立会话)
    
    属性说明：
        workspace_id: 工作区全局唯一标识 (UUID 或物理路径规范化哈希)
        name: 工作区可读名称 (如 "Aegis Core", "Linux 6.1 Kernel")
        root_path: 工作区对应的物理工程根目录绝对路径 (作为工具执行的 CWD 基准)
        description: 工作区工程描述与技术背景
        created_at: 工作区创建时间戳
        updated_at: 工作区最后活跃时间戳
    """
    workspace_id: str = Field(description="工作区唯一标识 (UUID 或路径哈希)")
    name: str = Field(description="工作区可读名称")
    root_path: str = Field(description="物理工程根目录绝对路径")
    description: str = Field(default="", description="工作区项目描述与背景说明")
    created_at: float = Field(default_factory=time.time, description="创建时间戳")
    updated_at: float = Field(default_factory=time.time, description="最后活跃时间戳")


class SessionMetadata(BaseModel):
    """
    会话元数据概览 (隶属于特定工作区，1:N 从属关系)
    
    属性说明：
        session_id: 会话唯一标识 UUID
        workspace_id: 所属工作区唯一标识
        title: 会话主题或首问简述
        created_at: 会话创建时间戳
        updated_at: 会话最后活跃时间戳
    """
    session_id: str = Field(description="会话唯一标识 UUID")
    workspace_id: str = Field(default="default", description="所属工作区唯一标识")
    title: str = Field(default="", description="会话摘要标题")
    created_at: float = Field(default_factory=time.time, description="创建时间戳")
    updated_at: float = Field(default_factory=time.time, description="最后活跃时间戳")

