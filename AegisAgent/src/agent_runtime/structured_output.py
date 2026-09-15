"""结构化输出抽取（节点与研究子智能体共用的基础工具）。

**为什么单独成模块**：LLM 返回 JSON 是所有"结构化推理"路径的公共前置步骤——
`planner`（里程碑计划）、`evaluator`（验收结论）、研究子智能体（研究报告）都要用。
把它放在契约层附近，既避免各处重复实现，也避免 `research` 反向依赖图节点层
（依赖方向见 ``10_directory_structure.md`` §5）。

本模块**零 I/O、零业务依赖**，只有纯函数。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

__all__ = ["extract_json_object", "truncate_text"]


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出中稳健地抽出 JSON 对象。

    兼容三种最常见的污染：Markdown 代码围栏包裹、前后夹带解释性文字、空响应。

    Args:
        text: 模型原始输出。

    Returns:
        解析成功时返回字典；失败返回 ``None``（由调用方决定降级策略，不抛异常）。
    """
    if not text:
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        # 去掉 ```json ... ``` 包裹
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except (ValueError, TypeError):
        # 退一步：截取首个 '{' 到最后一个 '}' 之间的内容
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except (ValueError, TypeError):
            return None

    return parsed if isinstance(parsed, dict) else None


def truncate_text(text: str, limit: int) -> Tuple[str, bool]:
    """按字符上限截断文本。

    用于把不可信内容压进上下文预算。上限非正数时视为"不截断"，
    并在结尾追加显式标记，避免下游误以为拿到了全文。

    Args:
        text: 原始文本。
        limit: 字符上限（``<=0`` 表示不限制）。

    Returns:
        ``(文本, 是否发生截断)``。
    """
    if limit <= 0 or len(text) <= limit:
        return text, False

    marker = f"\n…[已截断，原文共 {len(text)} 字符]"
    keep = max(0, limit - len(marker))
    return text[:keep] + marker, True
