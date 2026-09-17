"""对外传输契约（DTO）。

**绝不直接外发 AgentState**。原因：它包含 LangChain 消息对象与随步数增长的内部结构。
本模块定义**稳定、JSON 安全、可演进**的对外形状，并负责内部模型 → DTO 的投影。

时间戳统一为 Unix 秒（浮点）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

__all__ = [
    "ArtifactDescriptor",
    "ContextPreview",
    "DependencyHealth",
    "ErrorBody",
    "ErrorDetail",
    "FailureCreate",
    "FactCreate",
    "HealthStatus",
    "MemoryView",
    "SessionCreate",
    "SessionOut",
    "TaskOut",
    "TaskSubmit",
    "TimelineItem",
    "TurnOut",
    "WorkspaceCreate",
    "WorkspaceOut",
    "ApprovalRequestOut",
    "ApproveRequest",
    "RejectRequest",
    "WorkspaceUpdate",
    "FileItem",
    "FileTreeResponse",
    "FileContentOut",
    "FileContentUpdate",
    "RagIngestRequest",
    "RagIngestResponse",
    "RagRetrieveRequest",
    "RagChunkResult",
    "RagRetrieveResponse",
]


# ==============================================================================
# 通用
# ==============================================================================

class ErrorDetail(BaseModel):
    """结构化错误详情。"""

    code: str = Field(description="稳定错误码")
    message: str = Field(description="人类可读描述")
    details: Dict[str, Any] = Field(default_factory=dict, description="补充上下文（不含密钥）")
    trace_id: str = Field(default="", description="链路追踪 ID")


class ErrorBody(BaseModel):
    """统一错误响应体。"""

    error: ErrorDetail


class PageMeta(BaseModel):
    """分页元信息。"""

    next_cursor: Optional[str] = Field(default=None, description="下一页游标；无更多数据时为 null")
    total: Optional[int] = Field(default=None, description="总数（若可廉价获得）")


# ==============================================================================
# 工作区
# ==============================================================================

class WorkspaceCreate(BaseModel):
    """创建工作区请求（按 root_path 幂等）。"""

    name: str = Field(description="工作区可读名称")
    root_path: str = Field(description="工程物理根目录绝对路径")
    description: str = Field(default="", description="工程背景说明")
    workspace_id: Optional[str] = Field(default=None, description="可选，指定工作区 ID")


class WorkspaceUpdate(BaseModel):
    """更新工作区元数据。"""

    name: Optional[str] = Field(default=None, description="新名称")
    description: Optional[str] = Field(default=None, description="新描述")


class WorkspaceOut(BaseModel):
    """工作区视图。"""

    workspace_id: str
    name: str
    root_path: str
    description: str = ""
    created_at: float
    updated_at: float


class FactCreate(BaseModel):
    """事实/规范上浮请求。"""

    fact: str = Field(description="要沉淀的技术事实")
    category: Literal["convention", "architecture"] = Field(
        default="architecture", description="类别：编码规范或架构定论"
    )


class FailureCreate(BaseModel):
    """全局避坑记录追加请求。"""

    action: str = Field(description="曾尝试的操作")
    failure_reason: str = Field(description="失败原因")
    conclusion: str = Field(description="避坑结论")


class MemoryView(BaseModel):
    """记忆视图（工作区级或会话级共用同一外形，未使用的字段留空）。"""

    scope: Literal["workspace", "session"] = Field(description="记忆作用域")
    updated_at: float = Field(default=0.0, description="最后更新时间")
    summary: str = Field(default="", description="已压缩摘要（会话级）")
    compacted_until_turn_id: int = Field(default=0, description="压缩水位线（会话级）")
    project_conventions: List[str] = Field(default_factory=list, description="项目规范（工作区级）")
    confirmed_architecture: List[str] = Field(default_factory=list, description="架构定论（工作区级）")
    confirmed_facts: List[str] = Field(default_factory=list, description="已确认事实")
    failed_attempts: List[Dict[str, Any]] = Field(default_factory=list, description="踩坑记录")
    last_action_target: Dict[str, List[str]] = Field(default_factory=dict, description="上轮操作实体")


# ==============================================================================
# 会话
# ==============================================================================

class SessionCreate(BaseModel):
    """创建会话请求。"""

    title: str = Field(default="", description="会话主题")


class SessionOut(BaseModel):
    """会话视图。"""

    session_id: str
    workspace_id: str
    title: str = ""
    created_at: float
    updated_at: float


class TurnOut(BaseModel):
    """对话轮次视图。"""

    id: int
    role: Literal["user", "assistant"]
    content: str
    token_count: int = 0
    timestamp: float


class ContextPreview(BaseModel):
    """上下文检视结果（前端展示"模型此刻看到了什么"）。"""

    workspace: Dict[str, Any] = Field(default_factory=dict)
    workspace_memory: Dict[str, Any] = Field(default_factory=dict)
    session_memory: Dict[str, Any] = Field(default_factory=dict)
    active_turns: List[TurnOut] = Field(default_factory=list)
    budget: Dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# 任务
# ==============================================================================

class TaskSubmit(BaseModel):
    """提交任务请求。"""

    task_goal: str = Field(description="任务目标（自然语言）")
    parent_task_id: Optional[str] = Field(default=None, description="可选，父任务 ID")
    permission_level: Optional[
        Literal["read_only", "workspace_write", "full_permissions"]
    ] = Field(default=None, description="可选，覆盖会话权限基线（缺省取服务端配置）")


class ApprovalRequestOut(BaseModel):
    """越级操作的待审批请求（人工审核卡片的数据源）。"""

    approval_id: str = Field(description="审批标识，提交 approve/reject 时回传")
    required_level: Literal["read_only", "workspace_write", "full_permissions"] = Field(
        description="该动作所需的最低权限级别"
    )
    current_level: Literal["read_only", "workspace_write", "full_permissions"] = Field(
        description="当前会话授权级别"
    )
    action_type: str = Field(description="动作类型：network_egress / global_env / privileged / unknown …")
    command: str = Field(default="", description="待执行动作摘要（含关键命令），供人工审阅")
    reason: str = Field(default="", description="越级判定原因")
    escalation_count: int = Field(default=1, description="本批越级动作总数")
    related_actions: List[str] = Field(default_factory=list, description="同批其它越级动作摘要")


class ApproveRequest(BaseModel):
    """批准越级操作。"""

    approval_id: Optional[str] = Field(default=None, description="回传审批标识（校验用）")
    decision: Literal["once", "always"] = Field(
        default="once", description="once=仅本次放行；always=加入当前会话白名单免审"
    )


class RejectRequest(BaseModel):
    """拒绝越级操作并反馈理由。"""

    approval_id: Optional[str] = Field(default=None, description="回传审批标识（校验用）")
    reason: str = Field(default="", description="拒绝理由，将作为观察值驱动模型重新规划")


class TimelineItem(BaseModel):
    """执行时间线条目（AgentState.messages 的投影）。"""

    seq: int
    type: Literal[
        "plan",
        "thought",
        "tool_call",
        "tool_result",
        "system_notice",
        "milestone",
        "guard_warning",
        "approval_request",
    ]
    role: str = ""
    summary: str = ""
    artifact_id: Optional[str] = None
    timestamp: float = 0.0


class ArtifactDescriptor(BaseModel):
    """产物描述。"""

    artifact_id: str
    task_id: str = ""
    size_bytes: int = 0
    created_at: float = 0.0
    preview: str = ""


class TaskOut(BaseModel):
    """任务状态快照（**不是** AgentState）。"""

    task_id: str
    session_id: str
    workspace_id: str
    task_goal: str
    status: Literal[
        "queued",
        "running",
        "waiting_for_approval",
        "succeeded",
        "failed",
        "cancelled",
        "terminated",
    ]
    permission_level: Literal["read_only", "workspace_write", "full_permissions"] = Field(
        default="workspace_write", description="会话权限基线"
    )
    approval_request: Optional[ApprovalRequestOut] = Field(
        default=None, description="处于 waiting_for_approval 时的待审批请求"
    )
    milestones: List[Dict[str, Any]] = Field(default_factory=list)
    current_milestone_idx: int = 0
    step_count: int = 0
    total_tokens: int = 0
    consecutive_errors: int = 0
    should_terminate: bool = False
    termination_reason: str = ""
    created_at: float = 0.0
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    artifact_count: int = 0


# ==============================================================================
# 健康检查
# ==============================================================================

class DependencyHealth(BaseModel):
    """单个下游依赖的健康状况。"""

    name: str
    reachable: bool
    detail: str = ""


class HealthStatus(BaseModel):
    """服务健康状态。"""

    status: Literal["ok", "degraded"]
    version: str = "0.1.0"
    uptime_sec: float = 0.0
    metadata_db_ok: bool = True
    checkpoint_ok: bool = True


# ==============================================================================
# 工作区文件树与内容
# ==============================================================================

class FileItem(BaseModel):
    """文件树节点。"""

    path: str = Field(description="相对工作区根路径的 Posix 相对路径")
    name: str = Field(description="文件名或目录名")
    type: Literal["file", "directory"] = Field(description="节点类型")
    size_bytes: int = Field(default=0, description="文件大小（字节）")
    updated_at: float = Field(default=0.0, description="最近修改时间戳")
    language: Optional[str] = Field(default=None, description="推断语言/格式标识")
    children: Optional[List[FileItem]] = Field(default=None, description="子目录节点列表（若为目录）")


class FileTreeResponse(BaseModel):
    """工作区文件树响应。"""

    workspace_id: str
    root_path: str
    items: List[FileItem]


class FileContentOut(BaseModel):
    """文件内容响应。"""

    workspace_id: str
    path: str
    content: str
    size_bytes: int
    language: str
    updated_at: float


class FileContentUpdate(BaseModel):
    """文件保存请求。"""

    path: str = Field(description="目标相对路径")
    content: str = Field(description="要写入的新文本内容")


# ==============================================================================
# RAG 知识检索与索引代理
# ==============================================================================

class RagIngestRequest(BaseModel):
    """RAG 索引触发请求。"""

    repo_name: Optional[str] = Field(default=None, description="仓库/知识库标识（缺省自动从工作区提取）")
    repo_root: Optional[str] = Field(default=None, description="物理根路径（缺省使用工作区根路径）")
    incremental: bool = Field(default=True, description="是否开启增量索引（按内容哈希比对）")


class RagIngestResponse(BaseModel):
    """RAG 索引统计响应。"""

    indexed: int = 0
    skipped: int = 0
    deleted: int = 0
    degraded_files: List[str] = Field(default_factory=list)
    duration_ms: int = 0


class RagRetrieveRequest(BaseModel):
    """RAG 检索请求。"""

    query: str = Field(description="查询问题或检索词")
    top_k: Optional[int] = Field(default=5, description="精排返回最大数量")
    mode: Literal["hybrid", "dense_only", "sparse_only", "hybrid_no_rerank"] = Field(
        default="hybrid", description="检索模式"
    )
    language: Optional[str] = Field(default=None, description="可选语言过滤")


class RagChunkResult(BaseModel):
    """RAG 召回切片。"""

    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    git_commit: Optional[str] = None
    enclosing_scope: Optional[str] = None
    score: float


class RagRetrieveResponse(BaseModel):
    """RAG 检索响应。"""

    results: List[RagChunkResult] = Field(default_factory=list)
    low_confidence: bool = False

