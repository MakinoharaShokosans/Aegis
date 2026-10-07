# 04 深度评测与基准路线规范 (Evaluation & Benchmarks Index)

> **定位**：Aegis 体系中脱离 Mock 幻觉、面向真实前沿大模型能力契约、长上下文治理与 RAG 检索质量基准的深度量化评测体系。
> **核心原则**：不量化就是瞎优化；真实模型结构化断言；RAG 零 LLM-judge 消耗、纯数学统计、100% 确定性可复现。

---

## 深度评测文档导航

| 序号 | 文档名称 | 评测目标 | 核心指标 / 数据集 | 对应实际评测模块 |
| :---: | :--- | :--- | :--- | :--- |
| **01** | [`01_真实LLM前沿模型深度评测路线.md`](01_真实LLM前沿模型深度评测路线.md) | 真实模型输出合规、自主任务收敛、Prompt 注入红队防御、长任务上下文治理 | 任务完成率 (TCR)、步骤效率、Canary 泄露率 | `AegisAgent/tests/real_llm/` |
| **02** | [`02_RAG检索质量评测执行规范.md`](02_RAG检索质量评测执行规范.md) | 标准化代码检索评测 SOP、指标数学定义与数据集格式契约 | HitRate@K、MRR@K、NDCG@K ($K \in \{1,3,5,10\}$)、4:4:2 代码金标集 | `AegisAgent/src/evaluation/rag_bench/` |
| **03** | [`03_RAG全景消融基准评测报告.md`](03_RAG全景消融基准评测报告.md) | 官方基线报告：纯 Dense、纯 BM25、RRF 融合与 Cross-Encoder 4 组消融实测数据与深度归因 | MRR@3 提升 +53.8%、NDCG@5 提升 +49.6%、各阶段延迟分布 | `storage/traces/` 基线数据 |

---

## 快速执行命令

```bash
# 1. 运行真实 LLM 深度测试套件 (需要 TERRA_KEY 与 LUNA_KEY)
cd /home/Skualeilu/Projects/Aegis/AegisAgent
uv run pytest tests/real_llm/ -m real_llm -v -s

# 2. 启动 RAG 微服务并运行 RAGBench 4 组消融自动化评测
cd /home/Skualeilu/Projects/Aegis/AegisRAG && uv run uvicorn src.api.server:app --port 8001 &
cd /home/Skualeilu/Projects/Aegis/AegisAgent
uv run python -m src.evaluation.rag_bench.runner
```
