"""Token 计量工具单元测试。"""

import pytest

from agent_runtime.tokenizer import (
    count_tokens,
    get_encoder,
    set_encoder_for_testing,
)


@pytest.fixture(autouse=True)
def restore_encoder():
    """保存并还原原始编码器状态，保证测试隔离。"""
    original = get_encoder()
    yield
    set_encoder_for_testing(original)


def test_count_tokens_empty_and_normal():
    """测试空串与正常文本的 Token 计量。"""
    assert count_tokens("") == 0

    text = "Hello, world! This is an Aegis test."
    tokens = count_tokens(text)
    assert tokens > 0
    # 正常英文句子应该在 5~15 tokens 之间
    assert 5 <= tokens <= 15


def test_count_tokens_chinese_and_special_chars():
    """测试中文字符及特殊控制字符计量。"""
    text = "构建一个完整的自主 Agent 框架"
    tokens = count_tokens(text)
    assert tokens > 0


def test_count_tokens_fallback_to_heuristic():
    """测试当 tiktoken 编码器不可用时，优雅降级为字符粗算。"""
    # 强制将编码器设置为 None（模拟 tiktoken 缺失或加载失败）
    set_encoder_for_testing(None)

    raw_text = "12345678"
    # 保底粗算逻辑：len(text) // 2 -> 4
    assert count_tokens(raw_text) == 4

    short_text = "a"
    # max(1, len(text) // 2) -> 1
    assert count_tokens(short_text) == 1
