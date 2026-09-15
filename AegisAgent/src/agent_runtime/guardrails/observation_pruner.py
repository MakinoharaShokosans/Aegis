"""观察值离线卸载与蒸馏（Observation Pruner）。

对应 ``documents/agent_runtime/05_guardrails_implementation.md`` §4 与
``07_execution_context_management.md`` §3。

**要解决的问题**：``cat`` 大文件、编译内核模块、跑压力测试会产生上万行输出。
直接塞进上下文会造成 Token 爆炸与"中间迷失（Lost in the Middle）"。

**策略**：两头保留 + 离线落盘 + 结构化感知。

1. **全量落盘**：原始输出无损写入 ``{artifacts_dir}/{task_id}/``，只把句柄带回上下文；
2. **结构化感知**：
   - 输出是合法 JSON 时，**不做字符截断**（会把语法切碎），而是生成保持 JSON 合法性的
     "结构轮廓"（键名 + 类型 + 数组长度 + 标量预览）；
   - 纯文本时按 Head + 关键字行 + Tail 提取，并标注省略行数。

**解耦设计**：Token 计数以 ``token_counter`` 注入，本模块不直接依赖 tiktoken；
因此可在单测中注入假计数器，也便于未来替换分词口径。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

__all__ = ["ObservationPruner", "PrunedObservation"]

#: 失败输出的关键字特征（失败时优先保留这些行）
ERROR_KEYWORDS: tuple[str, ...] = (
    "error",
    "fatal",
    "warning",
    "failed",
    "undefined reference",
    "segmentation fault",
    "traceback",
    "exception",
    "assert",
)

#: 结构化轮廓中单个标量值的最大预览长度
_SCALAR_PREVIEW = 120


@dataclass(slots=True)
class PrunedObservation:
    """蒸馏后的观察值。

    Attributes:
        summary: 注入上下文用的紧凑摘要。
        artifact_id: 产物句柄标识（未落盘时为 ``None``）。
        artifact_path: 全量输出的磁盘绝对路径（未落盘时为 ``None``）。
        is_truncated: 是否发生了裁剪/卸载。
        original_tokens: 原始观察值的 Token 数。
        original_chars: 原始观察值的字符数。
    """

    summary: str
    artifact_id: Optional[str] = None
    artifact_path: Optional[str] = None
    is_truncated: bool = False
    original_tokens: int = 0
    original_chars: int = 0


def _preview_scalar(value: Any) -> Any:
    """把标量裁剪为可读预览；容器类型保留结构提示。"""
    if isinstance(value, str):
        return value if len(value) <= _SCALAR_PREVIEW else value[:_SCALAR_PREVIEW] + "…"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return f"<list len={len(value)}>"
    if isinstance(value, dict):
        return f"<object keys={list(value)[:8]}>"
    return f"<{type(value).__name__}>"


def json_outline(obj: Any, depth: int = 0, max_depth: int = 3) -> Any:
    """生成保持 JSON 合法性的结构轮廓。

    Args:
        obj: 已解析的 JSON 对象。
        depth: 当前递归深度。
        max_depth: 最大递归深度，超出后仅保留类型提示。

    Returns:
        与入参同构、但体积大幅缩小的对象。
    """
    if depth >= max_depth:
        return _preview_scalar(obj)
    if isinstance(obj, dict):
        return {str(key): json_outline(value, depth + 1, max_depth) for key, value in obj.items()}
    if isinstance(obj, list):
        # 只展开前若干元素，其余用长度提示代替，避免大数组撑爆上下文
        head = [json_outline(item, depth + 1, max_depth) for item in obj[:5]]
        if len(obj) > 5:
            head.append(f"<... 其余 {len(obj) - 5} 项省略>")
        return head
    return _preview_scalar(obj)


def distill_text(raw: str, head_lines: int, tail_lines: int, keyword_limit: int = 30) -> str:
    """对纯文本执行 Head + 关键字行 + Tail 提取。

    Args:
        raw: 原始文本。
        head_lines: 保留头部行数。
        tail_lines: 保留尾部行数。
        keyword_limit: 中间关键字行最多保留条数。

    Returns:
        带省略标注的蒸馏文本。
    """
    lines = raw.splitlines()
    total = len(lines)

    # 短文本无需蒸馏
    if total <= head_lines + tail_lines:
        return raw

    head = lines[:head_lines]
    tail = lines[-tail_lines:]
    middle = lines[head_lines : total - tail_lines]

    keyword_hits = [
        line for line in middle if any(keyword in line.lower() for keyword in ERROR_KEYWORDS)
    ][:keyword_limit]

    sections: list[str] = list(head)
    if keyword_hits:
        sections.append(f"... [中间省略 {len(middle) - len(keyword_hits)} 行，以下为关键行] ...")
        sections.extend(keyword_hits)
    else:
        sections.append(f"... [中间省略 {len(middle)} 行] ...")
    sections.extend(tail)
    return "\n".join(sections)


class ObservationPruner:
    """观察值裁剪器。

    Args:
        token_counter: 文本 → Token 数的计量函数（注入以避免直接依赖 tiktoken）。
        max_tokens: 触发蒸馏的 Token 阈值。
        head_lines: 蒸馏时保留的头部行数。
        tail_lines: 蒸馏时保留的尾部行数。
        artifacts_dir: 全量输出落盘根目录。
    """

    __slots__ = ("_count_tokens", "max_tokens", "head_lines", "tail_lines", "artifacts_dir")

    def __init__(
        self,
        token_counter: Callable[[str], int],
        max_tokens: int,
        head_lines: int,
        tail_lines: int,
        artifacts_dir: str | Path,
    ) -> None:
        self._count_tokens = token_counter
        self.max_tokens = max_tokens
        self.head_lines = head_lines
        self.tail_lines = tail_lines
        self.artifacts_dir = Path(artifacts_dir)

    @classmethod
    def from_config(
        cls,
        context_config: Any,
        artifacts_dir: str | Path,
        token_counter: Callable[[str], int],
    ) -> "ObservationPruner":
        """从 ``config.runtime.context`` 构造裁剪器。

        Args:
            context_config: ``config.runtime.context``（Pydantic 模型）。
            artifacts_dir: ``config.runtime.storage.artifacts_dir``。
            token_counter: 分词计量函数。

        Returns:
            裁剪器实例。
        """
        return cls(
            token_counter=token_counter,
            max_tokens=context_config.max_observation_tokens,
            head_lines=context_config.observation_head_lines,
            tail_lines=context_config.observation_tail_lines,
            artifacts_dir=artifacts_dir,
        )

    def build_summary(self, raw: str) -> str:
        """构造紧凑摘要（结构化优先，失败降级为文本蒸馏）。

        Args:
            raw: 原始观察值。

        Returns:
            摘要文本。
        """
        stripped = raw.strip()
        if stripped.startswith(("{", "[")):
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                # 解析失败说明不是合法 JSON，降级为文本蒸馏
                pass
            else:
                outline = json.dumps(json_outline(parsed), ensure_ascii=False, indent=2)
                return f"[结构化输出轮廓，已保持 JSON 合法性]\n{outline}"
        return distill_text(raw, self.head_lines, self.tail_lines)

    async def prune(
        self,
        raw: str,
        task_id: str,
        step_id: int,
        tool_name: str = "tool",
    ) -> PrunedObservation:
        """按需蒸馏并落盘。

        Args:
            raw: 工具返回的原始观察值。
            task_id: 所属任务 ID（决定落盘子目录）。
            step_id: 步序号（用于命名产物）。
            tool_name: 工具名（用于命名产物）。

        Returns:
            :class:`PrunedObservation`；未超阈值时 ``is_truncated=False`` 且摘要即原文。
        """
        original_chars = len(raw)
        original_tokens = self._count_tokens(raw)

        # 未超预算：原样返回，不产生磁盘副作用
        if original_tokens <= self.max_tokens:
            return PrunedObservation(
                summary=raw,
                is_truncated=False,
                original_tokens=original_tokens,
                original_chars=original_chars,
            )

        artifact_id = f"obs_step_{step_id}_{tool_name}"
        target_dir = self.artifacts_dir / task_id
        target_path = target_dir / f"{artifact_id}.log"

        try:
            # 磁盘 I/O 放入线程池，绝不阻塞事件循环
            await asyncio.to_thread(self._write_artifact, target_dir, target_path, raw)
            artifact_path: Optional[str] = str(target_path)
        except OSError as exc:
            # 落盘失败不应中断任务：退化为"仅摘要"，并明确告警
            logger.error(f"[Pruner] 原始输出落盘失败，仅保留摘要: {exc}")
            artifact_path = None
            artifact_id = None

        summary = self.build_summary(raw)
        handle_line = f"\n\n[完整输出已离线保存: artifact://{artifact_id}]" if artifact_id else ""
        logger.info(
            f"[Pruner] 观察值超限已卸载: tool={tool_name} "
            f"{original_tokens} tokens / {original_chars} chars -> 摘要 {len(summary)} chars"
        )
        return PrunedObservation(
            summary=f"{summary}{handle_line}",
            artifact_id=artifact_id,
            artifact_path=artifact_path,
            is_truncated=True,
            original_tokens=original_tokens,
            original_chars=original_chars,
        )

    @staticmethod
    def _write_artifact(target_dir: Path, target_path: Path, raw: str) -> None:
        """同步写入全量输出（由 :func:`asyncio.to_thread` 调度）。"""
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path.write_text(raw, encoding="utf-8", errors="replace")
