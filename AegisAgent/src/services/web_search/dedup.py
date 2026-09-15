"""搜索结果去重：基于"标题 + 正文/摘要"的 MD5 内容指纹。

设计依据 ``documents/技术选型/web_search.md`` §2.1：镜像站与转载站点会把同一篇
内容以不同 URL 反复返回，直接喂给模型既浪费 Token 又污染证据链。因此对每条结果
计算内容指纹并保留**首次出现**的顺序（首次出现通常是原始来源，排序更靠前）。

归一化策略：Unicode NFKC + 空白折叠 + 大小写折叠，抑制排版差异导致的漏判。

解耦红线：本模块只依赖标准库与 :mod:`services.web_search.providers` 的数据契约。
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from typing import Final

from services.web_search.providers import SearchHit

__all__ = ["normalize_text", "content_fingerprint", "url_fingerprint", "dedupe"]

#: 连续空白（含换行/制表）折叠为单个空格，消除排版差异
_WHITESPACE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\s+")

#: 指纹保留长度：ADR §2.1 明确采用 "MD5 哈希前 8 位"
_FINGERPRINT_LENGTH: Final[int] = 8


def normalize_text(text: str) -> str:
    """归一化文本，用于内容指纹计算。

    Args:
        text: 原始文本（标题或正文/摘要），可为空。

    Returns:
        经 NFKC 归一化、空白折叠并转小写后的文本；空输入返回空串。
    """
    if not text:
        return ""
    return _WHITESPACE_PATTERN.sub(" ", unicodedata.normalize("NFKC", text)).strip().lower()


def _hash8(payload: str) -> str:
    """计算字符串的 MD5 并截取前 8 位。

    Args:
        payload: 待哈希内容（调用方已归一化）。

    Returns:
        8 位十六进制指纹字符串。
    """
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:_FINGERPRINT_LENGTH]


def content_fingerprint(title: str, text: str) -> str:
    """计算"标题 + 正文"的内容指纹。

    Args:
        title: 结果标题或网页标题。
        text: 正文（清洗后的 Markdown）或搜索结果摘要。

    Returns:
        8 位十六进制 MD5 指纹；标题与正文均为空时退化为空串内容的指纹。
    """
    payload = f"{normalize_text(title)}\n{normalize_text(text)}"
    return _hash8(payload)


def url_fingerprint(url: str) -> str:
    """计算 URL 指纹，用于离线落盘文件名（``web_{hash}.md``）。

    Args:
        url: 页面地址。

    Returns:
        8 位十六进制 MD5 指纹。
    """
    return _hash8((url or "").strip())


def dedupe(hits: Iterable[SearchHit]) -> list[SearchHit]:
    """按内容指纹去重，保留首次出现的顺序。

    标题与摘要都为空的结果无法用内容判定重复，改用 URL 指纹兜底，避免把所有
    空摘要结果错误地折叠成一条。

    Args:
        hits: 待去重的搜索结果序列。

    Returns:
        去重后的搜索结果列表，保持输入中的首次出现顺序。
    """
    seen: set[str] = set()
    unique: list[SearchHit] = []

    for hit in hits:
        title_key = normalize_text(hit.title)
        text_key = normalize_text(hit.snippet)
        if not title_key and not text_key:
            fingerprint = f"url:{url_fingerprint(hit.url)}"
        else:
            fingerprint = content_fingerprint(hit.title, hit.snippet)

        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique.append(hit)

    return unique
