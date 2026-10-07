# 01 单元测试路线规范 (Unit Testing Index)

> **定位**：Aegis 各子系统纯函数、状态机原子突变与无 I/O 契约的单元测试规划与执行规范。
> **核心原则**：纯函数优先、零外部网络 I/O、确定性断言、毫秒级执行。

---

## 📁 单元测试文档导航

| 序号 | 文档名称 | 针对子系统 | 核心测试范围 | 对应实际测试目录 |
| :---: | :--- | :--- | :--- | :--- |
| **01** | [`01_Agent运行时单元测试路线.md`](01_Agent运行时单元测试路线.md) | `AegisAgent` | 权限分级判定 (`permission.py`)、纯函数路由 (`edges/`)、配置加载与校验、Token 计算 | `AegisAgent/tests/guardrails/`, `tests/edges/`, `tests/` |
| **02** | [`02_RAG切分与向量单元测试路线.md`](02_RAG切分与向量单元测试路线.md) | `AegisRAG` | Tree-sitter C/C++/Go AST 切分器、Markdown 结构切分、Dense/BM25 向量生成、UUIDv5 幂等 ID | `AegisRAG/tests/indexer/`, `tests/embeddings/`, `tests/storage/` |
| **03** | [`03_Frontend组件与状态单元测试路线.md`](03_Frontend组件与状态单元测试路线.md) | `AegisFrontend` | Zustand 状态机 Store 突变、React 纯组件交互渲染、工作流审计导出工具函数 | `AegisFrontend/src/stores/__tests__/`, `src/components/**/__tests__/` |

---

## 🛠️ 快速执行命令

```bash
# 1. 执行 Agent 核心单元测试
cd /home/Skualeilu/Projects/Aegis/AegisAgent
uv run pytest tests/guardrails/test_permission.py tests/edges/test_edges.py tests/test_config.py -v

# 2. 执行 RAG 算法与切分单元测试
cd /home/Skualeilu/Projects/Aegis/AegisRAG
uv run pytest tests/indexer/ tests/embeddings/ tests/storage/test_ids_and_idempotency.py -v

# 3. 执行 Frontend 组件与状态单元测试
cd /home/Skualeilu/Projects/Aegis/AegisFrontend
npm run test
```
