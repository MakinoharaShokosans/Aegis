# 02 集成测试路线规范 (Integration Testing Index)

> **定位**：Aegis 各子系统内部节点流转、状态机恢复、跨微服务 API 契约与前端 SSE 流式通信的集成测试规范。
> **核心原则**：真图真状态机（编译后 LangGraph 驱动）、真 SQLite 持久化落盘、Mock 外部无界网络、强类型契约严格自检。

---

## 📁 集成测试文档导航

| 序号 | 文档名称 | 针对子系统 | 核心测试范围 | 对应实际测试目录 |
| :---: | :--- | :--- | :--- | :--- |
| **01** | [`01_LangGraph节点状态机集成测试路线.md`](01_LangGraph节点状态机集成测试路线.md) | `AegisAgent` | `ToolRunner` 挂起与 `Command(resume=...)` 恢复、原子对铁律回归、SQLite Checkpoint 落盘、并发竞态 | `AegisAgent/tests/nodes/`, `tests/integration/` |
| **02** | [`02_FastAPI微服务与API契约测试路线.md`](02_FastAPI微服务与API契约测试路线.md) | `AegisAgent` ↔ `AegisRAG` ↔ `Sidecar` | 三道安全闸门（Host/Origin/Token）、任务生命周期与审批路由、RAG 网关代理、Bash 沙箱通信契约 | `AegisAgent/tests/api/`, `AegisRAG/tests/api/` |
| **03** | [`03_Frontend流式通信与数据流测试路线.md`](03_Frontend流式通信与数据流测试路线.md) | `AegisFrontend` ↔ `AegisAgent` | SSE 流式报文聚合解析、Token 鉴权头自动注入、网络中断指数退避重连、领域 API 契约适配 | `AegisFrontend/src/api/__tests__/` |

---

## 🛠️ 快速执行命令

```bash
# 1. 执行 LangGraph 状态机与工作流集成测试
cd /home/Skualeilu/Projects/Aegis/AegisAgent
uv run pytest tests/nodes/test_tool_runner.py tests/integration/test_graph_workflow.py tests/integration/test_crash_recovery.py -v

# 2. 执行 FastAPI 微服务接口与安全闸门集成测试
cd /home/Skualeilu/Projects/Aegis/AegisAgent
uv run pytest tests/api/test_security_gates.py tests/api/test_rag_routes.py tests/integration/test_api_lifecycle.py -v
cd /home/Skualeilu/Projects/Aegis/AegisRAG
uv run pytest tests/api/ -v

# 3. 执行前端流式通信与 API 契约集成测试
cd /home/Skualeilu/Projects/Aegis/AegisFrontend
npm run test src/api/__tests__/
```
