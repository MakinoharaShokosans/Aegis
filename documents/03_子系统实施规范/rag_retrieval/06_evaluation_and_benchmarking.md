# 检索质量评测与基准规范

> **责任领域**：`AegisRAG/` 的 `/api/v1/retrieve` 输出 ↔ `AegisAgent/src/evaluation/rag_bench/`（**已存在**的零 LLM 评测 harness）
> **状态**： 规划中，尚未实现（评测 harness 代码本身已就绪，但从未接入过 AegisRAG 的真实输出）
> **核心原则**：不量化就是瞎优化——`02`/`03`/`04` 里任何一项"未来增强"要不要做，都应该先用本文档描述的基准跑出数字再决定，而不是凭直觉。

---

## 0. 为什么单独成篇

`documents/技术选型/evaluation.md` 已经定型了"零 LLM 消耗、纯数学统计"的评测哲学，`AegisAgent/src/evaluation/rag_bench/`（`metrics.py` 498 行、`dataset.py`、`evaluate_retrieval.py` 539 行）也已经把 `hit_rate_at_k` / `reciprocal_rank_at_k`（MRR）/ `ndcg_at_k` 这套 harness 完整实现好了——**但它至今从未跑过一次针对 AegisRAG 真实检索结果的评测**，因为 AegisRAG 还没有代码，也因为此前的 `01`~`05` 规范里没有任何一处说明"AegisRAG 的输出该怎么喂给这个现成的 harness"。这是一处纯粹的"文档没有把两个已经存在的东西接起来"的空白，本篇负责把这条线补上。

## 1. 现成 Harness 的契约（不要重新发明）

`src/evaluation/rag_bench/dataset.py::EvalCase`：

| 字段 | 说明 |
| :--- | :--- |
| `case_id` | 用例唯一标识 |
| `query` | 查询原文 |
| `gold_chunk_ids` | 金标切片 ID 列表（"回答这个查询所必需的正确切片"） |
| `metadata` | 附加标注（难度/场景标签），不参与指标计算 |

`src/evaluation/rag_bench/evaluate_retrieval.py::RetrievalResult`（每条用例对应一次真实检索的返回）：核心是一个 `ranked_ids: list[str]`（按相关性排序的切片 ID 序列）。

**关键前提**：`ranked_ids` 里的每个元素，必须**恰好**对应 `05` §1.1 响应体里新加的 `results[].chunk_id`。这就是为什么 `05` 文档把 `chunk_id` 列为"不可省略"字段——没有它，下面整条评测链路无法接线。

`metrics.py` 提供的三个指标，语义与本子系统的对应关系：

| 指标 | 考核对象 | 在 AegisRAG 流水线里对应哪一段 |
| :--- | :--- | :--- |
| `hit_rate_at_k` | Top-K 里有没有命中至少一个金标切片 | 双路召回 + RRF 融合（`04` §1）的召回能力下限 |
| `reciprocal_rank_at_k`（MRR） | 第一个命中的金标切片排第几 | 精排（`04` §3）把真正相关的项顶到前面的能力 |
| `ndcg_at_k` | 综合排序质量（多个金标切片的相对排序） | 召回 + 精排整体的联合表现 |

**不引入 Faithfulness / Context Precision 等 LLM-judge 指标**——`知识库/技术栈学习/RAG/TEMP/07-系统度量与评估体系/07.1-RAG评测指标定义指南.md` 里提到的这两项需要额外调用 LLM 做裁判，与 `evaluation.md` 定型的"零 LLM 消耗"原则冲突，且它们考核的是"生成阶段"（模型有没有编造），而 AegisRAG 只对"检索阶段"负责——生成阶段的忠实度已经有 `agent_bench`（`documents/深度测试路线.md` Phase 10）在覆盖，职责不重叠。

## 2. 金标数据集构建方法（本子系统专属，harness 本身不管这个）

`dataset.py` 只定义了 `EvalCase` 的格式，怎么标注 `gold_chunk_ids` 是每个接入方自己的事。对代码检索场景，建议：

1. **来源 1——真实修复/开发历史反推**：从目标仓库的 `git log` 里挑一些"为了解决某个具体问题而修改了哪些函数"的提交，把问题描述（或该提交的 commit message 改写成自然语言查询）作为 `query`，被修改的函数对应的切片 ID 作为 `gold_chunk_ids`——这类样本最贴近 Agent 实际会发起的查询模式；
2. **来源 2——符号名直查**：用"这个函数/结构体是做什么的"作为 `query`，该符号所在的切片作为唯一金标——用来校验最基础的精确检索能力，这也是本子系统最核心、最不能退化的查询模式（`rag_search` 工具明确引导模型"建议包含关键符号名"，见 `05` §3）；
3. **来源 3——跨文件概念性查询**：用"XX 机制是怎么实现的"这种没有明确指向单一符号的查询，金标是一组分散在多个文件里的相关切片——用来考核 RRF 融合与 Sparse 召回补充 Dense 语义检索盲区的能力。

**数据集与索引状态绑定**：`gold_chunk_ids` 依赖 `chunk_id` 在"内容不变"时保持稳定（`03` §3 的确定性 Point ID 设计），意味着标注完成后只要源码对应位置不改，重新跑 `ingest` 不会让标注失效——这是本规范特意把 Point ID 设计成确定性的直接原因之一，`03` 写这条规则时就已经在为这里的可复用性铺路。

## 3. 消融矩阵（对齐 ADR 的既有设想，落到具体可执行的基准跑法）

`技术选型/evaluation.md` §2.1 定义的四组消融配置，在 AegisRAG 语境下具体化为：

| 配置 | 如何实测 | 目的 |
| :--- | :--- | :--- |
| `Dense Only` | `/retrieve` 请求带 `{"mode": "dense_only"}`（需在服务端支持一个调试开关，跳过 §1 的 RRF 融合与 §2 的稀疏路） | 单独衡量语义检索质量下限 |
| `Sparse Only` | 同上，`{"mode": "sparse_only"}` | 单独衡量关键词/符号名匹配能力下限——预期在"来源 2"类用例上表现突出 |
| `Hybrid + RRF`（不精排） | `{"mode": "hybrid_no_rerank"}`，直接返回 RRF 融合后的 Top-K | 证明双路融合相对单路的增益 |
| `Hybrid + Rerank`（默认生产配置） | 不带调试参数的正常请求 | 证明精排相对"只融合不精排"的增益——**这组数字直接回答"精排到底值不值得做"，预期应该是四组里表现最好的一组，否则说明精排环节本身有问题** |

**后续未来增强项的验证方式相同**：`04` §6 提到的 RSE 缝合 / MMR 多样性，落地时同样应该在这张矩阵上各加一行做 A/B 对比，而不是加了就默认认为有效。查询侧的语义改写类技术不在此列——那类不属于 AegisRAG 职责范围（`01` §6），要不要做、怎么评测是 Agent 侧的事。

## 4. 落地路径

1. 服务端 `/api/v1/retrieve` 支持 §3 的调试 `mode` 参数（生产 Agent 侧调用永远不传，仅评测脚本使用）；
2. 评测脚本**放在 `AegisAgent` 侧**（`src/evaluation/rag_bench/rag_service_client.py`，与 `dataset.py`/`evaluate_retrieval.py` 同级），**不放在 `AegisRAG/`**——`01` §6 已经定了这条边界：两者是完全独立的虚拟环境，AegisRAG 里 import 不到 `rag_bench` 的数据集/指标代码，唯一干净的做法是评测脚本作为 `AegisAgent` 生态的一部分，像 `rag_search.py` 一样单纯通过 `httpx` 调用 AegisRAG 的 `/api/v1/retrieve`，不反向依赖。脚本逻辑：读取 `EvalCase` 数据集 → 对每条 `query` 真实调用 `/api/v1/retrieve` 四种 `mode` → 把 `results[].chunk_id` 组装成 `RetrievalResult.ranked_ids` → 交给 `evaluate_retrieval.py::evaluate()` 出报告；
3. 首次跑通后产出的报告即为**基线**，之后每次改动切分策略、更换 embedding 模型、或评估 `04` 的未来增强项，都以这份基线为参照对比，回归退化要能被立刻发现。
