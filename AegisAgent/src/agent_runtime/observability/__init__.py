"""双轨可观测层。

对齐 ``documents/agent_runtime/01_architecture_overview.md`` §4：

* **本地系统轨**：Loguru 结构化 JSONL，供离线评测与故障自愈率统计；
* **平台可视化轨**：Langfuse，供调用树拓扑与耗时瀑布流；
* **因果轨迹轨**：``storage/traces/{task_id}.jsonl``，记录每步的
  Thought / Action / Distilled Observation，是评测 harness 的数据源。

三者都是**旁路**：任何一条轨出问题都不得影响主执行流程。
"""

from agent_runtime.observability.logging import setup_logging
from agent_runtime.observability.trajectory import TrajectoryRecorder

__all__ = ["TrajectoryRecorder", "setup_logging"]
