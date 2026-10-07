# 03 端到端测试路线规范 (End-to-End Testing Index)

> **定位**：Aegis 全系统跨 4 大独立物理进程（Frontend :5173、Agent :8000、RAG :8001、Sandbox :8002）的业务闭环、人机协同与系统级容灾自愈测试路线。
> **核心原则**：真实网络拓扑、全链路无 Mock 穿透、异常故障硬注入、生产级状态持久化。

---

## 📁 端到端测试文档导航

| 序号 | 文档名称 | 核心演练场景 | 涉及进程链路 |
| :---: | :--- | :--- | :--- |
| **01** | [`01_全系统业务闭环E2E测试路线.md`](01_全系统业务闭环E2E测试路线.md) | 标准需求开发闭环、越级高危动作与人机协同审批闭环、多轮会长会话上下文治理 | `Frontend` ➔ `Agent` ➔ `RAG` ➔ `Sandbox` ➔ `Frontend` |
| **02** | [`02_系统崩溃断电续跑容灾测试路线.md`](02_系统崩溃断电续跑容灾测试路线.md) | 主进程异常硬崩溃 (`kill -9`)、SQLite WAL 状态机快照恢复、`/resume` 断点接续执行 | `Agent` (崩溃重启) ➔ `SQLite` ➔ `Frontend` 重新连接 |

---

## 🛠️ 快速执行命令

```bash
# 启动本地微服务集群
cd /home/Skualeilu/Projects/Aegis/AegisRAG && uv run uvicorn src.api.server:app --port 8001 &
cd /home/Skualeilu/Projects/Aegis/AegisAgent && uv run python -m src.api.server &
cd /home/Skualeilu/Projects/Aegis/AegisFrontend && npm run dev &

# 运行自动化集成回归脚本
cd /home/Skualeilu/Projects/Aegis/AegisAgent
uv run pytest tests/integration/test_crash_recovery.py tests/integration/test_graph_workflow.py -v
```
