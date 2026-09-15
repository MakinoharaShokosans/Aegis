"""
Aegis 系统全局强类型配置加载器 (config.py)

功能描述：
1. 基于 pydantic-settings 强类型解析与校验 config/config.toml 及 .env 环境变量；
2. 集中纳管物理预算指标、上下文滑窗阈值、本地持久化路径及双模型多端点降级列表；
3. 遵循安全架构设计：业务配置入版本库，敏感 API Key 统一由 .env 注入，代码内零硬编码。
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple, Type
import tomllib

from loguru import logger
from pydantic import BaseModel, Field
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
# 8. 全局配置根对象 (AegisConfig)
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
