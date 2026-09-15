"""Agent 轨迹评测轨。

规范：documents/技术选型/evaluation.md 第 2.2 节

模块职责：

- :mod:`evaluation.agent_bench.metrics`：完成率 / 故障自愈率 / 步骤效率 / 证据链合规率，
  输入是**已解析的 JSONL 记录列表**，不依赖任何运行期类；
- :mod:`evaluation.agent_bench.runner`：读取 ``storage/traces/*.jsonl`` → 汇总 → Markdown 报告。

解耦红线：本子包只读取轨迹文件，**禁止** import ``agent_runtime``。
"""

from __future__ import annotations

__all__ = ["metrics", "runner"]
