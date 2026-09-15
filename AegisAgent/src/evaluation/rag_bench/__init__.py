"""RAG 检索评测轨（零 LLM 消耗）。

规范：documents/技术选型/evaluation.md 第 2.1 节

模块职责：

- :mod:`evaluation.rag_bench.metrics`：HitRate@K / MRR@K / NDCG@K 与均值汇总；
- :mod:`evaluation.rag_bench.dataset`：``EvalCase`` 标注契约与 JSON/JSONL 读写；
- :mod:`evaluation.rag_bench.evaluate_retrieval`：离线驱动脚本 + 四组消融 + 报告渲染。

数据默认落位：

- 标注数据集：``src/evaluation/rag_bench/datasets/``
- 评测报告：``src/evaluation/rag_bench/reports/benchmark_report.md``
"""

from __future__ import annotations

__all__ = ["dataset", "evaluate_retrieval", "metrics"]
