"""同工程子系统集合。

**解耦红线**：本包下的子系统是独立进程的 sidecar，
**禁止 import `agent_runtime` / `tools` / `mcps`**（连配置也不共用，
各自通过 :mod:`services.settings` 读取 `config.toml` 的对应段落）。

理由见 `documents/agent_runtime/01_architecture_overview.md` §3：
把 LangGraph / LangChain / OpenAI SDK 拖进服务进程会破坏崩溃隔离与秒级冷启动。
"""

__all__: list[str] = []
