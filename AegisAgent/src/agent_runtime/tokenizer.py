"""统一的分词计量工具（本地 tiktoken，零网络、零外部依赖）。

**为什么独立成模块**：Token 是 Aegis "物理预算"体系的基础度量单位，被记忆压缩、
观察值裁剪、上下文装配、预算守卫等多处复用。集中一处可保证全系统口径一致，
避免出现"同一个字符串在不同模块算出不同 Token 数"这类难以定位的隐性 bug。

**降级策略**：若 tiktoken 因特殊字符抛错或编码表不可用，回退为
``len(text) // 2`` 的字符粗算，并只记录一次 warning，绝不阻断主流程
（对齐 ``06_memory_and_context_management`` §8 的优雅降级要求）。
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

__all__ = ["count_tokens", "get_encoder", "set_encoder_for_testing"]

#: 默认编码表。cl100k_base 覆盖 GPT-4 / DeepSeek 等主流模型的词表口径
_DEFAULT_ENCODING = "cl100k_base"

_encoder: Optional[object] = None
_encoder_initialized = False
_encoder_failed_warned = False


def get_encoder() -> Optional[object]:
    """懒加载并缓存 tiktoken 编码器。

    Returns:
        编码器实例；初始化失败时返回 ``None``（调用方需自行降级）。
    """
    global _encoder, _encoder_initialized, _encoder_failed_warned

    if not _encoder_initialized:
        _encoder_initialized = True
        try:
            import tiktoken

            _encoder = tiktoken.get_encoding(_DEFAULT_ENCODING)
        except Exception as exc:  # noqa: BLE001 - 任何失败都必须降级而非中断
            _encoder = None
            logger.warning(f"tiktoken 编码器初始化失败，将采用字符粗算降级: {exc}")
            _encoder_failed_warned = True

    return _encoder


def set_encoder_for_testing(encoder: Optional[object]) -> None:
    """注入自定义编码器（仅用于测试替身）。

    Args:
        encoder: 实现了 ``encode(text, disallowed_special=())`` 的对象；传 ``None`` 表示强制降级。
    """
    global _encoder, _encoder_initialized
    _encoder = encoder
    _encoder_initialized = True


def count_tokens(text: str) -> int:
    """精确计量文本的物理 Token 数。

    Args:
        text: 待计量文本。

    Returns:
        Token 数；空串返回 0。编码器不可用或编码异常时返回字符粗算值。
    """
    global _encoder_failed_warned

    if not text:
        return 0

    encoder = get_encoder()
    if encoder is not None:
        try:
            # disallowed_special=() 关闭特殊 token 报错，允许任意用户文本
            return len(encoder.encode(text, disallowed_special=()))  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - 单次编码失败不应影响主流程
            if not _encoder_failed_warned:
                logger.warning(f"tiktoken 编码异常，本次改用字符粗算: {exc}")
                _encoder_failed_warned = True

    # 保底粗算：中文约 1 字 1 Token、英文约 2 字符 1 Token，折中取 2 字符
    return max(1, len(text) // 2)
