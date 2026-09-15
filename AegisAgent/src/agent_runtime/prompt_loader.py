"""提示词加载器（内容与代码分离的读取侧）。

**设计取舍**：提示词以 Markdown 存放于 ``agent_runtime/prompts/``，属于**可热改内容**
而非代码——改措辞不该触发逻辑回归。代码侧只负责按名读取与缓存。

**路径解析双策略**：优先按包内相对路径定位（安装为 wheel 后依然有效），
失败再回退到项目根相对路径（源码直跑场景）。**禁止**在业务代码里写死相对路径。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from loguru import logger

__all__ = ["PromptLibrary"]


class PromptLibrary:
    """提示词库（按名读取 + 进程内缓存）。

    Args:
        prompts_dir: 提示词目录；缺省为包内 ``prompts/``。
    """

    __slots__ = ("_dir", "_cache")

    def __init__(self, prompts_dir: Optional[str | Path] = None) -> None:
        self._dir = Path(prompts_dir) if prompts_dir else self._resolve_default_dir()
        self._cache: Dict[str, str] = {}

    @staticmethod
    def _resolve_default_dir() -> Path:
        """解析提示词目录（包内优先，项目根回退）。"""
        candidates = [
            Path(__file__).resolve().parent / "prompts",
            Path("src/agent_runtime/prompts"),
            Path("AegisAgent/src/agent_runtime/prompts"),
        ]
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
        logger.warning("未找到 prompts 目录，提示词将全部走内置保底文本")
        return candidates[0]

    @property
    def directory(self) -> Path:
        """提示词目录路径。"""
        return self._dir

    def load(self, name: str, default: str = "") -> str:
        """按名读取提示词（不含 ``.md`` 后缀）。

        Args:
            name: 提示词名，如 ``"planner"``。
            default: 文件缺失或读取失败时返回的保底文本。

        Returns:
            提示词全文；命中缓存时直接返回。
        """
        if name in self._cache:
            return self._cache[name]

        path = self._dir / f"{name}.md"
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            logger.warning(f"提示词缺失，使用保底文本: {path}")
            content = default

        self._cache[name] = content
        return content

    def reload(self) -> None:
        """清空缓存（供开发期热改提示词使用）。"""
        self._cache.clear()
        logger.debug("提示词缓存已清空")
