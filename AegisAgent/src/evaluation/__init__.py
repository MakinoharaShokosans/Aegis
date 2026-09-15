"""双轨评测体系：RAG 检索物理指标 + Agent 轨迹量化。

规范：documents/技术选型/evaluation.md

本包是**离线**评测 harness，严格遵守解耦红线：

1. 只依赖标准库、``numpy``（``rag_bench.dataset`` 按规范额外使用 ``pydantic``）；
2. **禁止** import ``agent_runtime`` 的任意编排模块，避免评测与被测内核耦合；
3. ``agent_bench`` 通过读取 ``storage/traces/*.jsonl`` 轨迹文件工作，
   因此可在运行时依赖缺失（或内核重构中）的环境下独立回归。

双轨拓扑：

- :mod:`evaluation.rag_bench`：HitRate@K / MRR@K / NDCG@K 与四组消融实验；
- :mod:`evaluation.agent_bench`：完成率 / 故障自愈率 / 步骤效率 / 证据链合规率。

pytest 入口位于 ``tests/evaluation/``（``10_directory_structure.md`` §4 裁决项⑨）。
"""

from __future__ import annotations

__all__ = ["agent_bench", "rag_bench"]
