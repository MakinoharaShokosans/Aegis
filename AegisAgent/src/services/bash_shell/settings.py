"""bash_shell 子系统配置：`config/config.toml` → 强类型 Pydantic 模型。

设计要点：
1. **零硬编码**：端口、超时、rlimit 配额、内存池总量、产物目录一律取自
   ``[bash_shell]`` 配置段；段内缺失的调优项（蒸馏行数等）在模型里给出可被
   TOML 覆盖的兜底值，代码中不存在散落的魔法数字。
2. **fail-closed**：关键项（host/port/timeout/rlimit/pool/artifacts_dir）无默认值，
   配置段缺失或缺键时在服务启动阶段直接抛校验错误，而不是悄悄降级。
3. **sidecar 边界**：本模块只依赖 ``services.settings``（纯标准库 TOML 读取），
   绝不 import ``agent_runtime``（见 ``10_directory_structure.md`` §5 依赖方向矩阵）。

规范：documents/技术选型/bash_shell.md；documents/agent_runtime/10_directory_structure.md §4 裁决项③⑦
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.settings import find_config_file, load_section

__all__ = ["BashShellSettings", "get_settings", "project_root"]

#: 本子系统在 config.toml 中对应的段落名
_SECTION = "bash_shell"

#: 安全红线：允许监听的地址白名单（与 `ServerConfig._guard_loopback` 保持一致）
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def project_root() -> Path:
    """定位 AegisAgent 工程根目录。

    以 ``config/config.toml`` 的位置反推：``<root>/config/config.toml`` ⇒ 根目录为其父目录。
    用于把配置中的相对路径（如 ``storage/artifacts``）解析为绝对路径，
    避免依赖进程启动时的当前工作目录。

    Returns:
        工程根目录绝对路径。

    Raises:
        FileNotFoundError: 未找到 ``config/config.toml`` 时抛出（由 ``find_config_file`` 透传）。
    """
    return find_config_file().resolve().parent.parent


class BashShellSettings(BaseModel):
    """``[bash_shell]`` 段的强类型视图。

    Attributes:
        host: HTTP 监听地址（仅允许回环地址）。
        port: HTTP 监听端口（默认契约 ``127.0.0.1:8002``）。
        timeout_sec: 单命令默认硬超时（秒），请求体可用 ``timeout_sec`` 覆盖。
        sigterm_grace_sec: 两段式硬杀中 SIGTERM → SIGKILL 之间的宽限期（秒）。
        rlimit_as_mb: RLIMIT_AS 虚拟内存上限（MB）。
        rlimit_fsize_mb: RLIMIT_FSIZE 单文件大小上限（MB）。
        rlimit_cpu_sec: RLIMIT_CPU 纯 CPU 时间上限（秒）。
        memory_pool_mb: 全局内存池总量（MB），用于并发配额排队。
        max_concurrent: 并发执行上限（并发槽位数）。
        artifacts_dir: 全量日志离线落盘根目录（相对路径按工程根解析）。
        stream_chunk_bytes: 管道流式读取分块大小（字节），防止大日志驻留内存。
        distill_head_lines: 成功输出保留的头部行数。
        distill_tail_lines: 成功输出保留的尾部行数。
        distill_max_keyword_lines: 失败输出保留的关键字命中行上限。
        structured_sniff_max_bytes: 结构化（JSON/YAML）完整性嗅探缓冲上限（字节）。
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    # ---- 必填：来自 config.toml [bash_shell]，缺失即启动失败（fail-closed） ----
    host: str = Field(description="HTTP 监听地址（安全红线：仅允许回环）")
    port: int = Field(ge=1, le=65535, description="HTTP 监听端口")
    timeout_sec: float = Field(gt=0, description="单命令默认硬超时（秒）")
    sigterm_grace_sec: float = Field(gt=0, description="SIGTERM→SIGKILL 宽限期（秒）")
    rlimit_as_mb: int = Field(gt=0, description="RLIMIT_AS 虚拟内存上限（MB）")
    rlimit_fsize_mb: int = Field(gt=0, description="RLIMIT_FSIZE 单文件上限（MB）")
    rlimit_cpu_sec: int = Field(gt=0, description="RLIMIT_CPU 纯 CPU 时间上限（秒）")
    memory_pool_mb: int = Field(gt=0, description="全局内存池总量（MB）")
    max_concurrent: int = Field(gt=0, description="并发执行上限")
    artifacts_dir: str = Field(min_length=1, description="全量日志落盘根目录")

    # ---- 可选调优项：TOML 未提供时使用下列兜底值（可被 [bash_shell] 覆盖） ----
    stream_chunk_bytes: int = Field(
        default=65536, gt=0, description="管道流式读取分块大小（字节）"
    )
    distill_head_lines: int = Field(
        default=20, ge=0, description="成功输出保留的头部行数（ADR §2.4：Head 20 行）"
    )
    distill_tail_lines: int = Field(
        default=30, ge=0, description="成功输出保留的尾部行数（ADR §2.4：Tail 30 行）"
    )
    distill_max_keyword_lines: int = Field(
        default=200, gt=0, description="失败输出关键字命中行上限（防关键字刷屏）"
    )
    structured_sniff_max_bytes: int = Field(
        default=262144, gt=0, description="结构化输出完整性嗅探缓冲上限（字节）"
    )

    @model_validator(mode="after")
    def _guard_loopback(self) -> "BashShellSettings":
        """安全护栏：拒绝非回环监听地址。

        本服务具备在宿主工作区执行任意命令的能力，对外暴露等价于交出本机执行权限，
        因此与 ``agent_runtime.config.ServerConfig`` 一致，在配置加载阶段 fail-closed。

        Returns:
            校验通过的自身实例。

        Raises:
            ValueError: ``host`` 不在回环地址白名单内时抛出。
        """
        if self.host not in _LOOPBACK_HOSTS:
            raise ValueError(
                f"bash_shell.host 必须为回环地址，当前为 {self.host!r}。"
                "该服务具备命令执行能力，禁止对外暴露。"
            )
        return self

    @property
    def artifacts_root(self) -> Path:
        """产物落盘根目录的绝对路径。

        相对路径（如 ``storage/artifacts``）以工程根为基准解析，
        保证服务从任意工作目录启动时落盘位置一致（ADR §2.3「产物落盘隔离」）。

        Returns:
            已展开用户目录的绝对路径（不保证目录已存在）。
        """
        raw = Path(self.artifacts_dir).expanduser()
        return raw if raw.is_absolute() else (project_root() / raw)


@lru_cache(maxsize=1)
def get_settings() -> BashShellSettings:
    """读取并缓存 ``[bash_shell]`` 配置（进程内单例）。

    Returns:
        进程内唯一的配置实例（``lru_cache`` 保证只解析一次）。

    Raises:
        RuntimeError: ``config.toml`` 中缺少 ``[bash_shell]`` 段时抛出。
        pydantic.ValidationError: 段落存在但字段缺失或非法时抛出。
    """
    section = load_section(_SECTION)
    if not section:
        raise RuntimeError(
            f"config.toml 缺少 [{_SECTION}] 配置段，bash_shell 子服务无法启动"
        )
    return BashShellSettings.model_validate(section)
