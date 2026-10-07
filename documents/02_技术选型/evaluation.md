# 架构决策记录：自动化双轨评测工具链 (Evaluation Harness)

> **状态**：已定稿 (Accepted)
> **责任领域**：`AegisAgent/src/evaluation/`（harness），pytest 用例位于 `AegisAgent/tests/evaluation/`
> **核心目标**：为 RAG 检索算法与 Agent 整体自主执行提供量化基准、消融实验与防止负优化的端到端回归保障。

---

## 1. 架构总览与双轨评测拓扑

```text
                           Aegis 评测体系 (src/evaluation/)
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 ▼                                             ▼
     [ RAG 检索评测: rag_bench ]                   [ Agent 轨迹评测: agent_bench ]
     - 驱动：evaluate_retrieval.py (基于 numpy)    - 驱动：pytest test_agent_runner.py
     - 数据：src/evaluation/rag_bench/datasets/    - 数据：src/evaluation/agent_bench/tasks/
     - 指标：HitRate@K / MRR@K / NDCG@K / 耗时      - 指标：完成率 / 故障自愈率 / 步骤效率 / 证据合规率
     - 成本：零 LLM 消耗，纯数学与统计              - 来源：解析 storage/traces/{task_id}.jsonl 轨迹
                 │                                             │
                 └──────────────────────┬──────────────────────┘
                                        ▼
                         [ 自动化量化报告输出 (tabulate) ]
                         生成控制台 ASCII 表格与 benchmark_report.md
```

---

## 2. 核心技术决策与权衡依据

### 2.1 RAG 检索评测：纯数学指标与确定性计算（零 LLM 消耗）

* **为什么选用 `numpy` 自研评测计算器，而不盲从 Ragas？**
  - Ragas 默认模式重度依赖调用 LLM 作为裁判（LLM-as-a-judge），评测速度慢、API 费用高昂且打分具有随机性；
  - 经典信息检索（IR）指标（Hit Rate, MRR, NDCG）本质是纯数学公式。基于测试集标准答案（Ground Truth），用 **`numpy`** 离线毫秒级即可完成数百个用例的计算，零成本、确定性 100%；
* **支持消融实验（Ablation Study）**：
  一键运行对比四组配置的指标差异：
  - `Dense Only` (纯语义向量)
  - `Sparse Only` (纯 BM25 词法向量)
  - `Hybrid + RRF` (双路召回倒排融合)
  - `Hybrid + Cross-Encoder Rerank` (融合 + 重排精选)
  量化证明每项优化带来的准确率与排序增益。

### 2.2 Agent 轨迹评测：聚焦因果链与核心自愈率（Self-Correction Rate）

* **评测数据源**：直接读取运行时生成的结构化日志 `storage/traces/{task_id}.jsonl`。
* **面试级核心量化指标**：
  1. **Task Completion Rate（任务完成率）**：物理断言检查是否最终产出合格的技术报告与 Benchmark 数据产物；
  2. **Error Recovery Rate（故障自愈率，核心杀手锏）**：当 Shell 编译或网络请求报错时，Agent 在接下来的步骤中**自主修正错误并继续推进任务的成功比例**；
  3. **Step Efficiency（步骤效率）**：实际执行步骤数与基准最优步骤数比值，严防注意力漂移与无意义试错；
  4. **Evidence Provenance Ratio（证据链合规率）**：检查最终 Markdown 报告中标注的每项性能结论，是否均能反向溯源到合法的 `artifact://` 句柄或 `rag://` 文档来源，彻底消灭报告幻觉。

### 2.3 测试工程化：基于 `pytest` 的自动化驱动套件

* **决策理由**：
  1. 将 20~50 个标准工程研究场景沉淀为 `pytest` 自动化测试用例（如 `test_kernel_analysis_benchmark()`）；
  2. 一条命令 `pytest tests/evaluation/` 完成全系统能力回归，杜绝改动 Prompt 后引起前向能力退化；
  3. 规范支持集成至 GitHub Actions CI/CD 流水线。

### 2.4 报告可视化生成：选用 `tabulate`

自动将消融实验与评测基准数据格式化为高可读性的 Markdown 与控制台对比表格（输出至 `src/evaluation/rag_bench/reports/benchmark_report.md`）。
