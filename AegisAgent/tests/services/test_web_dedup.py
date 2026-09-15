"""Web 搜索结果去重 (Content Deduplication) 单元测试。"""

from services.web_search.dedup import (
    content_fingerprint,
    dedupe,
    normalize_text,
    url_fingerprint,
)
from services.web_search.providers import SearchHit


def test_normalize_text():
    """测试文本 NFKC 归一化与空白折叠。"""
    raw = "  Hello   WORLD \t\n \u3000 Foo  "
    normalized = normalize_text(raw)
    assert normalized == "hello world foo"

    # 空文本处理
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_fingerprints():
    """测试内容指纹与 URL 指纹稳定性（8位 MD5）。"""
    fp1 = content_fingerprint("Title A", "Snippet text content")
    fp2 = content_fingerprint("title a", "  snippet   text content ")
    # 经归一化后指纹应完全相同
    assert fp1 == fp2
    assert len(fp1) == 8

    url_fp = url_fingerprint("https://example.com/page1?a=1")
    assert len(url_fp) == 8


def test_dedupe_preserves_order_and_filters_duplicates():
    """测试 dedupe 函数去除同标题同内容的重复项并保留首次出现顺序。"""
    hits = [
        SearchHit(title="Doc 1", url="https://a.com/1", snippet="Original text"),
        SearchHit(title="Doc 2", url="https://b.com/2", snippet="Different text"),
        # 与 Doc 1 内容完全相同的镜像站点（不同 URL）
        SearchHit(title="doc 1", url="https://mirror.com/1", snippet="original   text"),
        SearchHit(title="Doc 3", url="https://c.com/3", snippet="Third text"),
    ]

    deduped = dedupe(hits)
    assert len(deduped) == 3

    assert deduped[0].url == "https://a.com/1"
    assert deduped[1].url == "https://b.com/2"
    assert deduped[2].url == "https://c.com/3"
