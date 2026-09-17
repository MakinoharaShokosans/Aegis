# Aegis 测试路线图全景总索引 (Test Roadmap Master Index)

> **定位**：Aegis 各独立子系统与微服务工程的测试规划、分阶段测试路线与自动化质量保障总入口。
> **子系统隔离原则**：`AegisAgent` 与 `AegisRAG` 作为两个独立的物理工程（具有独立的 `pyproject.toml`、虚拟环境与运行时边界），各自维护独立且高内聚的测试路线体系，互不混杂。

---

## 📁 测试路线文档拓扑

```text
documents/测试路线/
├── README.md                                    # [当前文档] 测试路线全景主索引与规范
│
├── AegisAgent/                                  # 👑 Agent 调度宿主主系统测试路线
│   ├── 测试路线.md                              # • 基础测试路线 (Phase 1~8: 单元/节点/API/对抗，Mock 驱动)
│   └── 深度测试路线.md                          # • 深度测试路线 (Phase 9~15: 真实前沿 LLM / AgentBench / 红队)
│
└── AegisRAG/                                    # 📚 独立代码检索子系统 (:8001) 测试路线
    └── 测试路线.md                              # • RAG 全栈测试路线 (Phase 1~7: AST 切分/向量化/Qdrant/精排/API/评测)
```

---

## 📊 各系统测试路线全景一览

| 子系统 | 对应测试路线文档 | 当前阶段覆盖 | 核心验证重点 | 执行环境 |
| :--- | :--- | :--- | :--- | :--- |
| **AegisAgent 基础** | [`AegisAgent/测试路线.md`](file:///home/Skualeilu/Projects/Aegis/documents/测试路线/AegisAgent/测试路线.md) | Phase 1 ~ 8 (已全部通过) | 单元/节点/HITL 审批/API 契约/对抗鲁棒性 (Mock 驱动) | `cd AegisAgent && uv run pytest tests/` |
| **AegisAgent 深度** | [`AegisAgent/深度测试路线.md`](file:///home/Skualeilu/Projects/Aegis/documents/测试路线/AegisAgent/深度测试路线.md) | Phase 9 ~ 15 (已全部通过) | 真实 LLM 输出契约、AgentBench 基线、Prompt 注入与 Canary 红队 | `cd AegisAgent && uv run pytest tests/real_llm/ -m real_llm` |
| **AegisRAG 检索** | [`AegisRAG/测试路线.md`](file:///home/Skualeilu/Projects/Aegis/documents/测试路线/AegisRAG/测试路线.md) | Phase 1 ~ 7 (待执行实施) | Tree-sitter AST 切分、FastEmbed/BM25 向量化、Qdrant 存储、Cross-Encoder 精排、FastAPI 接口与 RAGBench 评测 | `cd AegisRAG && uv run pytest tests/` |

---

## 🛠️ 测试执行命令快速指引

### 1. AegisAgent 测试
```bash
# 基础离线安全回归 (200/200 用例)
cd /home/Skualeilu/Projects/Aegis/AegisAgent
uv run pytest tests/ -q

# 真实 LLM 深度测试套件 (需配置 TERRA_KEY/LUNA_KEY)
uv run pytest tests/real_llm/ -m real_llm -v -s
```

### 2. AegisRAG 测试
```bash
# RAG 子系统测试执行
cd /home/Skualeilu/Projects/Aegis/AegisRAG
uv run pytest tests/ -v
```
