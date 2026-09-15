"""工具能力层（与 ``agent_runtime`` 平级）。

**为什么单独成包而不塞进 ``agent_runtime``**：工具是"能力"，编排是"决策"。
把工具放在平级包，用包边界强制二者的依赖方向为单向
（``agent_runtime.nodes`` → ``tools``），避免工具反向感知图、状态机与节点。

内部严格三分：

* :mod:`~tools.core`    —— 工具**框架**（协议、Schema 转译、注册表、并发派发、HTTP 客户端），
  不含任何具体工具；
* :mod:`~tools.builtin` —— **基础工具**实现（bash / rag_search / web_search / file_ops / load_skill）；
* ``mcps``（平级包）     —— MCP 外部工具桥接，单独成包以便集中托管子进程。
"""

__all__: list[str] = []
