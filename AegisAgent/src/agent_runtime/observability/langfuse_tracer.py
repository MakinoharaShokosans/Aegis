"""Langfuse 平台可视化轨（可选旁路）。

**刻意做成"可失败旁路"**：Langfuse 未配置密钥、未启动服务、或 SDK 大版本 API 变更时，
本模块一律返回 ``None``，主流程完全不受影响。

之所以不做强绑定：Langfuse 的 Python SDK 在 2.x → 3.x → 4.x 之间回调挂载方式
发生过多次破坏性变更。把适配收敛在本文件内部，未来跟随版本调整只改这一处。
"""

from __future__ import annotations

import os
from typing import Any, Optional

from loguru import logger

__all__ = ["build_langfuse_handler", "is_langfuse_enabled"]


def is_langfuse_enabled() -> bool:
    """判断是否具备启用 Langfuse 的最小条件。

    Returns:
        公钥与私钥均已配置时为 ``True``。
    """
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY", "").strip() and os.getenv("LANGFUSE_SECRET_KEY", "").strip())


def build_langfuse_handler(*, task_id: str = "", session_id: str = "") -> Optional[Any]:
    """构造 LangGraph 可挂载的 Langfuse 回调。

    Args:
        task_id: 任务 ID，作为 Langfuse trace 的业务标识。
        session_id: 会话 ID，用于在平台上按会话聚合。

    Returns:
        回调处理器；未配置或构造失败时返回 ``None``（调用方应容忍 ``None``）。
    """
    if not is_langfuse_enabled():
        logger.debug("[Langfuse] 未配置密钥，跳过平台可视化轨")
        return None

    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler  # type: ignore[attr-defined]
    except ImportError:
        # SDK 大版本差异：优先尝试经典路径，失败则放弃（旁路不得影响主流程）
        try:
            from langfuse.callback import CallbackHandler  # type: ignore[no-redef]
        except ImportError as exc:
            logger.warning(f"[Langfuse] 当前 SDK 版本不提供 LangChain 回调，已跳过: {exc}")
            return None

    try:
        Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
        )
        metadata = {"task_id": task_id, "session_id": session_id}
        try:
            return CallbackHandler(metadata=metadata)  # type: ignore[call-arg]
        except TypeError:
            return CallbackHandler()  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001 - 观测旁路绝不影响主流程
        logger.warning(f"[Langfuse] 初始化失败，已跳过平台可视化轨: {exc}")
        return None
