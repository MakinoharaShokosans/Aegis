"""
Aegis 系统全局强类型配置加载器 (config.py)

功能描述：
1. 基于 pydantic-settings 强类型解析与校验 config/config.toml 及 .env 环境变量；
2. 集中纳管物理预算指标、上下文滑窗阈值、本地持久化路径及双模型多端点降级列表；
3. 遵循安全架构设计：业务配置入版本库，敏感 API Key 统一由 .env 注入，代码内零硬编码。
"""

import os
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, Type
import tomllib

from loguru import logger
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


# ==============================================================================
# 1. 运行时物理安全守卫配置
# ==============================================================================

class GuardrailsConfig(BaseModel):
    """单任务运行时确定性物理安全守卫配置"""
    max_steps: int = Field(default=25, description="单任务最大执行步数上限")
    max_total_tokens: int = Field(default=200000, description="单任务累计消耗 Token 物理硬上限")
    max_wall_time_sec: float = Field(default=900.0, description="单任务物理挂钟运行时间上限 (秒)")
    consecutive_errors_limit: int = Field(default=3, description="连续工具报错强行回退重规划阈值")
    identical_fingerprint_limit: int = Field(default=3, description="相同参数 MD5 哈希连续出现次数上限 (防死循环)")


# ==============================================================================
# 2. 网络重试策略配置
# ==============================================================================

class RetryConfig(BaseModel):
    """API 弹性指数退避重试策略"""
    max_retries: int = Field(default=3, description="遭遇网络超时、429 限流或 5xx 时的最大重试次数")
    backoff_factor: float = Field(default=2.0, description="指数退避时间倍数因子 (秒)")


# ==============================================================================
# 3. 三层金字塔上下文治理配置
# ==============================================================================

class ContextConfig(BaseModel):
    """上下文与记忆滑动窗口治理配置"""
    session_token_limit: int = Field(default=32000, description="单会话活跃对话物理 Token 预算硬上限")
    compaction_high_watermark: float = Field(default=0.80, description="高水位触发线 (达到 80% 启动滚动压缩)")
    compaction_ratio: float = Field(default=0.40, description="目标压缩基准线 (对齐切出最古老约 40% 对话进行提炼)")
    active_window_turns: int = Field(default=3, description="保底保留的最少活跃对话轮数")
    compaction_trigger_turns: int = Field(default=8, description="未压缩轮数保底触发阈值")
    max_observation_tokens: int = Field(default=1500, description="单次工具输出触发本地落盘截断的 Token 阈值")
    observation_head_lines: int = Field(default=20, description="截断长输出时保留的头部关键行数")
    observation_tail_lines: int = Field(default=30, description="截断长输出时保留的尾部关键行数")


# ==============================================================================
# 4. 本地持久化路径配置
# ==============================================================================

class StorageConfig(BaseModel):
    """本地 SQLite 与日志产物文件持久化存储路径"""
    checkpoint_db_path: str = Field(default="storage/checkpoints/aegis_state.db", description="LangGraph 状态快照 SQLite 路径")
    metadata_db_path: str = Field(default="storage/aegis_meta.db", description="会话与认知记忆 SQLite 路径")
    traces_dir: str = Field(default="storage/traces", description="全量因果轨迹 JSONL 归档目录")
    artifacts_dir: str = Field(default="storage/artifacts", description="大体积工具日志离线落盘目录")


# ==============================================================================
# 5. 聚合运行时配置
# ==============================================================================

class RuntimeConfig(BaseModel):
    """系统综合运行时配置"""
    guardrails: GuardrailsConfig = Field(default_factory=GuardrailsConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)


# ==============================================================================
# 6. 大模型端点与双层降级列表
# ==============================================================================

class ModelEndpoint(BaseModel):
    """单个模型服务节点配置"""
    name: str = Field(description="节点可读标识")
    base_url: str = Field(description="兼容 OpenAI 协议的接口 Base URL")
    model: str = Field(description="目标模型代号")
    api_key_env: str = Field(description="引用自 .env 的 API Key 环境变量名称")
    timeout_sec: float = Field(default=60.0, description="单次请求网络超时时间 (秒)")

    def resolve_api_key(self) -> str:
        """从系统环境变量中解析真实的 API Key"""
        key = os.getenv(self.api_key_env, "").strip()
        if not key:
            logger.warning(f"环境变量 [{self.api_key_env}] 未设置或为空，节点 [{self.name}] 可能鉴权失败")
        return key


class ModelTierConfig(BaseModel):
    """单个模型层级配置 (包含温度与降级候选端点列表)"""
    temperature: float = Field(default=0.0, description="采样温度")
    endpoints: List[ModelEndpoint] = Field(default_factory=list, description="有序降级节点列表")


class ModelsConfig(BaseModel):
    """思考模型与快速动作模型双层配置"""
    reasoning: ModelTierConfig = Field(default_factory=ModelTierConfig)
    fast: ModelTierConfig = Field(default_factory=ModelTierConfig)


# ==============================================================================
# 7. 外部基础设施微服务寻址配置
# ==============================================================================

class ServicesConfig(BaseModel):
    """独立微服务客户端寻址 (Sidecar 模式)"""
    rag_url: str = Field(default="http://127.0.0.1:8001", description="独立 RAG 检索微服务地址")
    shell_url: str = Field(default="http://127.0.0.1:8002", description="独立 Shell 容器服务地址")
    web_url: str = Field(default="http://127.0.0.1:8003", description="独立 Web 抓取服务地址")
    timeout_sec: float = Field(default=60.0, description="微服务 HTTP 调用超时上限 (秒)")


# ==============================================================================
# 8. Agent HTTP API 接入层配置（唯一用户入口）
#    契约：documents/agent_runtime/11_http_api.md
# ==============================================================================

class ServerConfig(BaseModel):
    """Agent HTTP API 接入层配置"""
    host: str = Field(default="127.0.0.1", description="监听地址（安全红线：仅允许回环）")
    port: int = Field(default=8000, description="监听端口")
    max_concurrent_tasks: int = Field(default=1, description="同时运行的任务上限，超出返回 429")
    cors_allow_origins: List[str] = Field(default_factory=list, description="CORS 白名单来源")
    sse_heartbeat_sec: float = Field(default=15.0, description="SSE 心跳间隔（秒）")
    sse_buffer_events: int = Field(default=1000, description="SSE 断线重连环形缓冲条数")
    artifact_preview_chars: int = Field(default=200, description="产物预览字符数")

    auth_enabled: bool = Field(
        default=True,
        description=(
            "接入层令牌校验总开关。默认开启：本 API 等价于对本机工程目录的读写与执行权限，"
            "而回环监听挡不住浏览器发起的跨站请求（CSRF / DNS rebinding）——"
            "用户浏览器里的任意页面都能 POST /approve 替用户批准高危操作。"
            "关闭后 Host 与 Origin 闸门仍然生效"
        ),
    )
    api_token_env: str = Field(
        default="AEGIS_API_TOKEN",
        description="令牌来源环境变量名（优先级最高；设置后不再读写令牌文件）",
    )
    api_token_file: str = Field(
        default="storage/api_token",
        description=(
            "令牌落盘路径（0600）。环境变量未设置时：已存在则复用（重启不失效），"
            "不存在则生成。该文件**绝不入版本库**（.gitignore 已排除），日志只打印路径不打印令牌"
        ),
    )
    allowed_hosts: List[str] = Field(
        default_factory=list,
        description=(
            "额外允许的 Host 主机名（防 DNS rebinding）。回环名称 127.0.0.1 / localhost / ::1 "
            "始终允许，仅在通过反向代理或自定义本地域名访问时才需要补充"
        ),
    )

    @model_validator(mode="after")
    def _guard_loopback(self) -> "ServerConfig":
        """
        安全护栏：拒绝非回环监听地址。
        本 API 的工具链包含受控命令执行能力，等价于对本机工程目录的读写与执行权限，
        对外暴露属于高危配置，因此在配置加载阶段即 fail-closed。
        """
        if self.host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(
                f"server.host 必须为回环地址，当前为 {self.host!r}。"
                "Aegis 工具链含受控命令执行能力，禁止对外暴露。"
            )
        return self


# ==============================================================================
# 9. MCP 外部扩展服务器配置
#    规范：documents/agent_runtime/09_mcp_integration_and_governance.md
# ==============================================================================

class MCPServerConfig(BaseModel):
    """单个 MCP 服务器配置"""
    name: str = Field(default="", description="服务器标识（由 servers 字典键回填）")
    enabled: bool = Field(default=False, description="是否启用（默认关闭：会拉起外部子进程）")
    transport: Literal["stdio", "sse"] = Field(default="stdio", description="传输模式")
    command: str = Field(default="", description="stdio 模式：可执行文件")
    args: List[str] = Field(default_factory=list, description="stdio 模式：启动参数")
    env: Dict[str, str] = Field(default_factory=dict, description='环境变量，敏感值以 "env:XXX" 引用 .env')
    url: str = Field(default="", description="sse 模式：服务地址")
    timeout_sec: float = Field(default=60.0, description="单次调用超时（秒）")


class MCPConfig(BaseModel):
    """MCP 集成总配置"""
    enabled: bool = Field(default=True, description="MCP 总开关（关闭后忽略全部 servers）")
    connection_timeout_sec: float = Field(default=30.0, description="连接握手超时（秒）")
    call_timeout_sec: float = Field(default=60.0, description="单次调用超时上限（秒）")
    servers: Dict[str, MCPServerConfig] = Field(default_factory=dict, description="服务器注册表")

    # ---- 数据面治理：工具描述消毒（描述会进工具 Schema，位置高于普通观察值）----
    max_description_chars: int = Field(default=1000, description="工具描述长度上限")
    reject_on_injection: bool = Field(default=True, description="描述命中注入样态时拒绝注册该工具")

    # ---- 控制面治理：stdio 子进程资源上限（Linux）----
    rlimit_as_mb: int = Field(default=1024, description="stdio 子进程虚拟内存上限（MB）")
    rlimit_fsize_mb: int = Field(default=50, description="stdio 子进程单文件大小上限（MB）")
    rlimit_cpu_sec: int = Field(default=300, description="stdio 子进程纯 CPU 时间上限（秒）")

    @model_validator(mode="after")
    def _fill_server_names(self) -> "MCPConfig":
        """以字典键回填服务器名，避免在 TOML 中重复书写 name 字段"""
        for key, server in self.servers.items():
            if not server.name:
                server.name = key
        return self


# ==============================================================================
# 11. 研究子智能体配置（外部不可信数据隔离区）
#     规范：documents/agent_runtime/12_research_subagent.md
# ==============================================================================

class ResearchConfig(BaseModel):
    """
    研究子智能体预算与契约上限。

    这里的每一项都是**硬上限**：它们共同保证子智能体不会失控地消耗
    Token、时间与上下文，也不会把过长的不可信文本带回主 Agent。
    """
    enabled: bool = Field(default=True, description="总开关；关闭后主 Agent 无任何外部信息能力")
    model_tier: Literal["reasoning", "fast"] = Field(default="fast", description="子智能体使用的模型层级")
    max_rounds: int = Field(default=3, description="内部检索轮数上限")
    max_sources: int = Field(default=5, description="单轮最多来源数")
    max_source_chars: int = Field(default=6000, description="单源正文入子上下文的截断上限")
    max_wall_time_sec: float = Field(default=45.0, description="子智能体挂钟上限（秒）")
    max_total_tokens: int = Field(default=20000, description="子智能体 Token 上限")
    max_findings: int = Field(default=8, description="结论条目上限")
    max_answer_chars: int = Field(default=500, description="单条结论长度上限")
    max_code_examples: int = Field(default=5, description="代码示例条数上限")
    max_code_chars: int = Field(default=2000, description="单个代码块长度上限")
    max_report_chars: int = Field(default=4000, description="渲染后注入主上下文的上限")


# ==============================================================================
# 11b. 代码检索子智能体配置（源码深度探索与证据提炼）
# ==============================================================================

class CodeSearchConfig(BaseModel):
    """
    代码检索子智能体（``delegate_code_search``）预算与契约上限。
    """
    enabled: bool = Field(default=True, description="总开关；关闭后主 Agent 仅具备单次 rag_search 能力")
    model_tier: Literal["reasoning", "fast"] = Field(default="fast", description="代码检索子智能体使用的模型层级")
    max_rounds: int = Field(default=3, description="内部检索与判别重试轮数上限")
    max_chunks_per_round: int = Field(default=5, description="单轮检索最多召回切片数")
    max_source_chars: int = Field(default=6000, description="单切片正文进入子上下文的截断上限")
    max_wall_time_sec: float = Field(default=45.0, description="子智能体挂钟上限（秒）")
    max_total_tokens: int = Field(default=20000, description="子智能体 Token 上限")
    max_findings: int = Field(default=6, description="结论条目上限")
    max_answer_chars: int = Field(default=500, description="单条结论长度上限")
    max_code_snippets: int = Field(default=5, description="代码片段条目上限")
    max_code_chars: int = Field(default=2000, description="单个代码片段长度上限")
    max_report_chars: int = Field(default=4000, description="渲染后注入主上下文的上限")


# ==============================================================================
# 12. 动态子智能体委派配置（能力衰减 + 预算切片）
#     规范：documents/agent_runtime/13_subagent_delegation.md
# ==============================================================================

class SubagentConfig(BaseModel):
    """
    动态子智能体（``spawn_subagent``）的授权与预算上限。

    **这里的每一项都是可以被代码强制执行的硬约束**，不是提示词建议——
    凡只写在工具描述里的"上限"都不构成上限（见规范 §6）。

    与 :class:`ResearchConfig` 的分工：研究子智能体是**强类型输出**的专用通道，
    本段配置的是**通用但弱保证**的通道，两者刻意并存、不互相折叠。
    """
    enabled: bool = Field(default=True, description="总开关；关闭后主 Agent 不具备动态委派能力")
    model_tier: Literal["reasoning", "fast"] = Field(default="fast", description="子智能体使用的模型层级")
    max_depth: int = Field(default=1, description="最大委派深度；1 表示只允许主 Agent 分叉一级")
    max_steps: int = Field(default=8, description="子智能体内部交互轮数硬上限（代码内 clamp）")
    max_total_tokens: int = Field(default=30000, description="单次派发的名义 Token 上限（实际额度受父级余额收窄）")
    min_token_budget: int = Field(default=2000, description="最小可授予额度；余额低于此值直接拒绝派发")
    max_wall_time_sec: float = Field(default=90.0, description="单次派发挂钟上限（秒）")
    max_spawns_per_task: int = Field(default=4, description="单任务派发次数上限：约束'委派意愿'的物理旋钮")
    max_assigned_tools: int = Field(default=6, description="单次派发可授权的工具条数上限")
    max_findings: int = Field(default=6, description="回流的结论条目上限")
    max_observation_chars: int = Field(
        default=4000,
        description=(
            "子智能体单条工具观察值的字符上限（**内存截断，不落盘**）。"
            "刻意不复用主循环的 ObservationPruner：后者会把超长内容写成 artifact，"
            "而子智能体的中间观察值不应污染主任务的产物登记表"
        ),
    )
    max_answer_chars: int = Field(default=400, description="单条结论长度上限")
    max_citations: int = Field(default=8, description="单条结论可携带的引用数上限")
    max_report_chars: int = Field(default=3000, description="渲染后注入主上下文的上限")
    denied_tools: List[str] = Field(
        default_factory=lambda: ["spawn_subagent", "delegate_research", "delegate_code_search"],
        description=(
            "禁止下发给子智能体的工具（硬黑名单，与'白名单取交集'叠加）。"
            "默认剔除委派类工具：前者防套娃，后者防止在子智能体内再嵌一层模型循环"
            "（等价于深度 +1，却绕过了深度计数）"
        ),
    )


# ==============================================================================
# 13. 技能信任与治理配置
#     规范：documents/agent_runtime/08_skills_management.md 第 4.1-4.3 节
# ==============================================================================

class SkillsConfig(BaseModel):
    """
    技能来源信任分级与元数据治理。

    技能内容会进入**系统提示词**，信任位置高于工具输出，因此必须按来源分级；
    其中工作区覆盖来自"被指向的仓库"，属于不可信来源，默认拒绝。
    """
    allow_builtin: bool = Field(default=True, description="是否加载内置技能包（可信）")
    allow_global: bool = Field(default=True, description="是否加载用户全局技能库（可信）")
    allow_workspace: bool = Field(default=False, description="是否加载工作区技能覆盖（不可信，默认拒绝）")
    max_description_chars: int = Field(default=200, description="清单中单条描述的长度上限")
    max_triggers: int = Field(default=12, description="单技能触发词条数上限")
    high_privilege_tools: List[str] = Field(
        default_factory=lambda: ["bash", "write_file"],
        description="高风险工具名单：技能声明依赖它们时会被显式标注（仅标注，不拦截）",
    )


# ==============================================================================
# 14. 三级权限分级配置（HITL 越级人工审核）
#     规范：documents/技术选型/bash_shell.md §2.3、agent_runtime/04 §4.5
# ==============================================================================

class PermissionsConfig(BaseModel):
    """
    工具调用的权限分级与越级判定配置。

    判定逻辑本身是确定性纯函数（``guardrails/permission.py``），
    本配置只提供**分类表与正则模式**，便于按团队习惯调整而不改代码。
    """
    default_level: Literal["read_only", "workspace_write", "full_permissions"] = Field(
        default="workspace_write", description="新任务的默认权限基线"
    )
    read_only_tools: List[str] = Field(
        default_factory=lambda: [
            "view_file",
            "rag_search",
            "load_skill",
            "delegate_research",
            "delegate_code_search",
            "spawn_subagent",
        ],
        description=(
            "只读类工具（免审批）。``spawn_subagent`` 归此类的理由：它**不直接产生副作用**，"
            "其内部每一次子调用都会按父级权限重新判定（能力在派发前已衰减），"
            "因此委派动作本身不需要构成一道审批；需要审批的是子智能体实际执行的具体动作"
        ),
    )
    workspace_write_tools: List[str] = Field(
        default_factory=lambda: ["write_file"],
        description="工作区写入类工具",
    )
    full_permission_tools: List[str] = Field(
        default_factory=list,
        description="显式要求全权限的工具",
    )
    unknown_tool_level: Literal["read_only", "workspace_write", "full_permissions"] = Field(
        default="full_permissions",
        description=(
            "未知工具（如第三方 MCP 工具）的保守级别。"
            "默认 full_permissions：无法静态推理副作用时一律要求人工审批；"
            "信任某类工具时可下调或在 workspace_write_tools 中显式列出。"
        ),
    )
    bash_tools: List[str] = Field(
        default_factory=lambda: ["bash"],
        description="需要按命令内容做三分类的工具名",
    )
    # ---- 命令分类正则 ----
    # 注意：这里的默认值必须与 config.toml 的 [permissions] 保持一致且**非空**。
    # 若默认给空列表，任何"程序化构造配置"的场景（单测、嵌入式调用）都会得到
    # 一个"永远不触发升级"的权限系统——这是不安全默认值，故内置一份保守集合。
    full_permission_patterns: List[str] = Field(
        default_factory=lambda: [
            r"\bgit\s+push\b",
            r"\b(curl|wget)\b",
            r"\b(ssh|scp|rsync)\b",
            r"\bpip3?\s+install\b",
            r"\bnpm\s+(install|i|ci)\b",
            r"\b(yarn|pnpm)\s+(add|install)\b",
            r"\b(apt|apt-get|yum|dnf|apk)\s+(install|upgrade|remove)\b",
            r"\bsudo\b",
            r"\b(docker|docker-compose|kubectl|helm)\b",
        ],
        description="命中即需全权限的命令正则（网络外联、依赖安装、全局环境变更）",
    )
    workspace_write_patterns: List[str] = Field(
        default_factory=lambda: [
            r">>?\s*\S",
            r"\b(rm|mv|cp|mkdir|rmdir|touch|ln)\b",
            r"\b(sed|perl)\s+-i\b",
            r"\b(chmod|chown)\b",
            r"\bgit\s+(add|commit|checkout|switch|merge|rebase|reset|stash|tag|clean)\b",
            r"\b(make|cmake|ninja)\b",
            r"\b(gcc|g\+\+|clang|clang\+\+|rustc|cargo|go\s+(build|test))\b",
            r"\b(pytest|python\s+-m\s+pytest)\b",
            r"\b(npm|yarn|pnpm)\s+(run|test)\b",
            r"\btee\b",
        ],
        description="命中即需工作区写入权限的命令正则",
    )


# ==============================================================================
# 15. 全局配置根对象 (AegisConfig)
# ==============================================================================

class AegisConfig(BaseSettings):
    """
    Aegis 全局统一配置管理器
    支持从 config/config.toml 读取结构化业务参数，并结合 .env 环境变量完成装配
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    services: ServicesConfig = Field(default_factory=ServicesConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    code_search: CodeSearchConfig = Field(default_factory=CodeSearchConfig)
    subagent: SubagentConfig = Field(default_factory=SubagentConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """
        定制配置优先级：
        1. 实例化显式入参 (最高)
        2. TOML 配置文件 (config/config.toml)
        3. 系统环境变量
        4. .env 文件 (最低保底)
        """
        # 寻找配置文件绝对路径
        possible_paths = [
            Path("config/config.toml"),
            Path("AegisAgent/config/config.toml"),
            Path(__file__).resolve().parent.parent.parent / "config" / "config.toml",
        ]
        toml_path = next((p for p in possible_paths if p.is_file()), None)

        sources: list[PydanticBaseSettingsSource] = [init_settings]
        if toml_path:
            sources.append(TomlConfigSettingsSource(settings_cls, toml_file=toml_path))
        sources.extend([env_settings, dotenv_settings, file_secret_settings])

        return tuple(sources)


# 全局单例配置缓存
_GLOBAL_CONFIG: Optional[AegisConfig] = None


def get_config(reload: bool = False) -> AegisConfig:
    """
    获取全局统一配置单例对象
    
    Args:
        reload: 若为 True 则强制重新加载配置文件
        
    Returns:
        AegisConfig: 强类型配置实例
    """
    global _GLOBAL_CONFIG
    if _GLOBAL_CONFIG is None or reload:
        _GLOBAL_CONFIG = AegisConfig()
        logger.info("已成功加载 Aegis 系统全局配置")
    return _GLOBAL_CONFIG
