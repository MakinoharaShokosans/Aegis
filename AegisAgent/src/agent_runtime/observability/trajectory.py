"""因果轨迹持久化（Trajectory Store）。

每步生成一条 JSONL 记录写入 ``storage/traces/{task_id}.jsonl``。

**记录契约**（评测 harness 直接消费，字段变更需同步 ``agent_bench``）::

    {
      "task_id": str, "seq": int, "ts": float,
      "type": "node" | "tool" | "guard" | "final",
      "node": str, "phase": str,
      "thought": str, "tool_name": str, "tool_args": dict,
      "observation_summary": str, "artifact_path": str,
      "ok": bool, "step_count": int, "total_tokens": int, "consecutive_errors": int
    }

**写入策略**：每条记录独立 append 并立即 flush（而非长期持有句柄），
好处是进程被强杀时已完成的步骤不会丢失——审计与评测数据必须比性能优先。
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from loguru import logger

__all__ = ["TrajectoryRecorder"]


class TrajectoryRecorder:
    """单任务的轨迹记录器。

    Args:
        traces_dir: 轨迹根目录。
        task_id: 任务 ID（决定文件名）。
    """

    __slots__ = ("traces_dir", "task_id", "_path", "_seq")

    def __init__(self, traces_dir: str | Path, task_id: str) -> None:
        self.traces_dir = Path(traces_dir)
        self.task_id = task_id
        self._path = self.traces_dir / f"{task_id}.jsonl"
        self._seq = 0

    @property
    def path(self) -> Path:
        """轨迹文件路径。"""
        return self._path

    def next_seq(self) -> int:
        """分配下一个单调递增序号。"""
        self._seq += 1
        return self._seq

    async def record(
        self,
        *,
        record_type: str,
        node: str = "",
        phase: str = "",
        thought: str = "",
        tool_name: str = "",
        tool_args: Optional[Mapping[str, Any]] = None,
        observation_summary: str = "",
        artifact_path: str = "",
        ok: bool = True,
        step_count: int = 0,
        total_tokens: int = 0,
        consecutive_errors: int = 0,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """追加一条轨迹记录。

        Args:
            record_type: ``"node"`` / ``"tool"`` / ``"guard"`` / ``"final"``。
            node: 节点名。
            phase: 执行阶段。
            thought: 推理摘要。
            tool_name: 工具名。
            tool_args: 工具入参（调用方需先脱敏）。
            observation_summary: 精炼观察值。
            artifact_path: 产物句柄。
            ok: 该步是否成功。
            step_count: 当前步数。
            total_tokens: 当前累计 Token。
            consecutive_errors: 当前连续错误数。
            extra: 附加字段。

        Note:
            写盘失败只告警不抛出——轨迹是旁路，绝不能中断主任务。
        """
        payload: Dict[str, Any] = {
            "task_id": self.task_id,
            "seq": self.next_seq(),
            "ts": time.time(),
            "type": record_type,
            "node": node,
            "phase": phase,
            "thought": thought,
            "tool_name": tool_name,
            "tool_args": dict(tool_args or {}),
            "observation_summary": observation_summary,
            "artifact_path": artifact_path,
            "ok": ok,
            "step_count": step_count,
            "total_tokens": total_tokens,
            "consecutive_errors": consecutive_errors,
        }
        if extra:
            payload.update(dict(extra))

        try:
            await asyncio.to_thread(self._append_line, payload)
        except OSError as exc:
            logger.error(f"[Trajectory] 轨迹写入失败（不影响主流程）: {exc}")

    def _append_line(self, payload: Mapping[str, Any]) -> None:
        """同步 append 一行 JSON（由线程池调度）。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
