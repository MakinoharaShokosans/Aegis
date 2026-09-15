"""同工程子系统的配置读写（**不依赖 agent_runtime**）。

为什么单独一份而不复用 ``agent_runtime.config``：
``bash_shell`` 与 ``web_search`` 是**独立进程**的 sidecar。一旦它们 import
``agent_runtime``，就同时把 LangGraph / LangChain / OpenAI SDK 等一大串依赖拖进
服务进程，破坏"崩溃隔离 + 秒级冷启动"的设计前提（见 ``01_architecture_overview`` §3）。

因此本模块只做一件事：把 ``config/config.toml`` 里的指定段落读成普通 dict，
由各子系统用自己的 Pydantic 模型做校验。零第三方依赖，只用标准库 ``tomllib``。
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Dict

__all__ = ["load_section", "find_config_file"]

#: 配置文件的候选相对路径（按优先级），兼容从项目根或子目录启动
_CANDIDATE_PATHS = (
    Path("config/config.toml"),
    Path("AegisAgent/config/config.toml"),
    Path(__file__).resolve().parent.parent.parent / "config" / "config.toml",
)


def find_config_file() -> Path:
    """定位 ``config.toml`` 的绝对路径。

    Returns:
        首个存在的候选路径。

    Raises:
        FileNotFoundError: 所有候选路径均不存在时抛出。
    """
    override = os.getenv("AEGIS_CONFIG", "").strip()
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"AEGIS_CONFIG 指向的文件不存在: {candidate}")

    for candidate in _CANDIDATE_PATHS:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("未找到 config/config.toml，请从项目根目录启动或设置 AEGIS_CONFIG")


def load_section(section: str) -> Dict[str, Any]:
    """读取 TOML 中的指定段落。

    支持点号分隔的嵌套键（如 ``"mcp.servers"``）。

    Args:
        section: 段落名，例如 ``"bash_shell"``。

    Returns:
        该段落的键值字典；段落不存在时返回空字典（由调用方决定默认值）。
    """
    with find_config_file().open("rb") as handle:
        data: Dict[str, Any] = tomllib.load(handle)

    node: Any = data
    for part in section.split("."):
        if not isinstance(node, dict) or part not in node:
            return {}
        node = node[part]
    return dict(node) if isinstance(node, dict) else {}
