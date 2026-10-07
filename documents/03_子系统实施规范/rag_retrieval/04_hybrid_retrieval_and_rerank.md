# 混合检索与精排规范

> **责任领域**：`AegisRAG/src/api/`（检索编排）、`AegisRAG/src/rerank/reranker.py`（目录归属裁决见 `07`）
> **状态**：[x] 已实现（`api/routes/retrieve.py`、`rerank/reranker.py`）
> **核心原则**：双路召回宁多勿漏、数据库内核级融合、精排只做最终收窄、空结果与低置信度必须可辨识、召回/融合/返回数量一律配置化。
>
> **范围提示**：本文档 §1~§5 是 ADR 已定稿、**必须实现**的核心链路（Cross-Encoder 精排尤其如此——它不是"可选优化"，双路召回不经精排直接把全部融合候选返回给模型，会造成 §5 提到的注意力迷失与 Token 膨胀）。§6~§7 是本轮调研新增的**未来增强**，标注了明确的优先级与前置条件，不与核心范围混淆。
>
> **本文档不重复配置数值**：召回候选数、融合候选数、返回数量、精排阈值等全部数值一律以 `AegisRAG/config/rag_config.toml` 的 `[retrieval]`/`[rerank]` 段为唯一真源（汇总表见 `README.md` §4）；下文只引用配置键名，不写字面数字，改配置不需要跟着改文档。

---

## 1. 双路召回与 RRF 融合

对齐 ADR（`技术选型/rag_retrieval.md` §1）已定稿的流水线，检索请求到达后：

1. Query 文本分别过 Dense（`bge-small`）与 Sparse（`bm25`）编码；
2. 用 Qdrant 的 `query_points` + `prefetch` 组合，同时对 `dense` 与 `sparse` 两个命名向量分别取 `[retrieval].dense_top_k`/`[retrieval].sparse_top_k` 条候选，融合方式指定为 `Fusion.RRF`——**融合发生在 Qdrant 引擎内部**，服务端代码不需要手写倒排合并/打分归一化逻辑（ADR §2.1 的核心卖点，实现时不要在 Python 侧重复造轮子）；
3. 融合后的候选集按 `[retrieval].fusion_top_k` 截取，作为精排输入。

## 2. Payload 预过滤（在召回阶段生效，而非事后过滤）

对齐 `tools/builtin/rag_search.py` 已实现的客户端契约——它会在请求里带上可选的 `filters.language`（见 `05` §1）。服务端必须把这类过滤条件转成 Qdrant 的 `Filter`（`must` 子句按 `language`/`repo_name`/`file_path` 前缀匹配），**作为 `prefetch` 查询的一部分**下推到 Qdrant 引擎层，而不是先取回 `dense_top_k`/`sparse_top_k` 条再在 Python 里过滤——后者会导致"过滤后候选集不足"（比如全部候选里符合语言条件的只剩寥寥几条，而不过滤直接查的话数据库层面能找到更多真正相关的同语言结果）。

## 3. Cross-Encoder 精排（核心范围，必须实现）

`[retrieval].fusion_top_k` 条候选集交给 `rerank/reranker.py` 的 `Reranker` 做 Query-Document 相关性打分，取 `[retrieval].default_top_k`（或请求显式传入的 `top_k`，见 `05` §1.1）作为最终返回结果（ADR §2.3 已定稿）。

按 `[rerank].mode` 二选一（v2 修订，原设计只有本地一条路径）：

* `"remote"`（**默认**）：调用 `POST {base_url}/rerank`（`[rerank.remote]`，默认网关 `https://api.openlux.ai/v1`，鉴权走 `RERANK_API_KEY`）。**协议提醒**：OpenAI 官方 API 没有标准 rerank 端点，实现采用的 `{"model","query","documents"}` → `{"results":[{"index","relevance_score"}]}` 是部分 OpenAI 兼容网关常见的事实标准约定，不是已验证过的规范，首次真实联调前需对照实际网关文档核实；
* `"local"`：`fastembed.rerank.cross_encoder.TextCrossEncoder(model_name=[rerank.local].model_name)`（默认 `BAAI/bge-reranker-base`；**注意实际类名**——不是早期设计里泛称的 `fastembed.Rerank`），离线/无 key 时的兜底路径。

* **批处理**：`fusion_top_k` 条候选一次性批量打分，不要逐条调用——两种 `mode` 下都是主要的延迟优化点（本地是 ONNX 批处理效率，远端是减少往返请求数）；
* **分数透传**：精排后的相关性分数保留在响应体的 `score` 字段（见 `05` §1），供 `low_confidence` 判定消费（仅在真正精排过的路径生效，`dense_only`/`sparse_only`/`hybrid_no_rerank` 调试模式下恒为 `False`——两类分数量纲不同，见 `07` 的工程优化记录）。

## 4. 空结果与低置信度治理（ADR 未覆盖的边界情况）

现有流水线设计只描述了"有结果"的路径，以下两种情况需要明确规则：

1. **召回阶段零命中**（Collection 为空、或 Payload 过滤条件过窄导致 `prefetch` 无候选）：直接返回空 `results` 列表，**不进入精排阶段**（避免对空输入调用 Reranker 产生无意义开销或报错）；
2. **有结果但精排分数普遍偏低**（低于 `[rerank].min_score`）：**仍然返回这些结果**（不要悄悄丢弃——由 Agent/模型自己判断相关性更合适，服务端没有足够的任务上下文替模型做"这个够不够相关"的决策），但可以在响应体里附带一个 `low_confidence: true` 标记（见 `05` §1），让 Agent 侧未来有能力据此调整后续策略（比如据此判断"这个代码库里可能真的没有相关实现，应该换个检索词或改用其它工具"）。这个字段目前是**本规范新提出的设计**，`rag_search.py` 客户端尚未消费，实现时应在响应 Schema 里预留但不强制客户端处理。

> **`[rerank].min_score` 不是一个可以拍脑袋定的数字**：`fastembed.Rerank` 的实际打分分布只有实现后才能观测到，`rag_config.toml` 里当前是占位值（见该文件注释），实现时必须用 `06_evaluation_and_benchmarking.md` 的基线数据校准，不能凭感觉写一个"看起来合理"的阈值就当作生产配置。

> **`low_confidence` 的思路出处与一处关键改造**：这借鉴的是 CRAG（Corrective RAG，`知识库/技术栈学习/RAG/TEMP/05-动态自适应与反思架构/05.2-CRAG校正性RAG与联网回退.md`）"检索质量差就换路径"的核心思想，但**改造了落地位置**：CRAG 原始设计是"本地检索烂 → 检索服务自己转去调联网搜索引擎兜底"；这个动作放在 AegisRAG 内部做是**架构违规**——`12_research_subagent.md` 定义的信任边界明确规定网络抓取只能由隔离的研究子智能体持有，`rag_search` 是主 Agent 工具表里的**可信**结构性工具，不能让一个可信工具在内部悄悄拐去碰不可信的公网内容。所以 AegisRAG 只负责**诚实上报** `low_confidence`，"要不要转去调 `delegate_research`" 的决策权留在 Agent 侧的 planner，路径分离，信任边界不被打破。这条边界原则同样是 §6 把查询改写类技术整体排除在 AegisRAG 职责外的依据——详见 `01` §6。

## 5. 延迟预算的参考量级

纯粹作为实现时的性能预期基线（非强制 SLA，实测后应回填真实数据）：单机 CPU、`BAAI/bge-small-en-v1.5` + `[rerank].model_name`，`fusion_top_k` 条候选精排，单次 `/retrieve` 请求预期落在**百毫秒级**（Dense+Sparse 编码几十毫秒 + Qdrant 查询个位数毫秒 + 精排候选集几十至一百多毫秒）。若实测显著偏离此量级（例如精排耗时随候选集数量线性上升到秒级），应优先检查是否误用了逐条调用而非批量打分（见 §3）。

---

## 6. 未来增强：检索结果后处理（RSE 缝合 + MMR 多样性选择，非本轮核心范围）

> 本节两项都**只做结果的排列/合并**，不引入任何模型调用（对照 `01` §6："查询语义改写类"的增强不属于 AegisRAG 职责——这两项属于纯粹的检索后处理，不受那条边界约束，可以留在 AegisRAG 内部做）。

**相邻段落缝合（RSE）**——来源 `知识库/技术栈学习/RAG/TEMP/03-上下文富化与压缩/03.4-动态相关段落提取(Relevant Segment Extraction - RSE).md`：精排结果里如果出现同一文件里 `chunk_index`（`02` §6 已预留）相邻或间隔在 `[retrieval].rse_max_gap`（预留配置项，见 `rag_config.toml` 注释）以内的多个切片（例如一个 `struct` 定义切片 + 紧随其后操作它的函数切片都被命中），在返回前按 `file_path` + `chunk_index` 排序缝合成一段连续代码，而不是让模型拿到两段断章取义的碎片自己去脑补它们的位置关系。这是纯 Python 侧的区间合并逻辑，不需要额外模型调用，实现成本低，是这批未来增强里优先级相对最高的一项。

**多样性去扎堆（Dartboard / MMR）**——来源 `知识库/技术栈学习/RAG/TEMP/04-混合检索与重排序/04.5-飞镖盘多样性检索(Dartboard Retrieval).md`：C/C++ 项目里同一个功能常有多个重载或多份相似实现（如不同平台的条件编译分支），精排单纯按相关性打分，最终结果可能被同一组高度相似的重载占满。可以在精排后、截取最终 `default_top_k` 之前，对精排候选集做一轮 MMR 式的边际相关性重排（权衡系数即 `[retrieval].mmr_lambda`，预留配置项：越接近 1 越偏纯相关性，越接近 0 越偏多样性），避免最终结果说的是同一件事的多种写法。**与 RSE 的取舍张力**：RSE 想把"相邻的"合并到一起，MMR 想把"相似的"打散开——两者要合作而非打架，落地顺序建议是**先精排 → 按分数截取候选 → 对候选做 RSE 缝合（合并同文件相邻项）→ 对缝合后的段落集合做多样性去重（不同文件/不同位置的雷同实现才去重，不要把刚缝合好的同一段又拆散）**。

## 7. 优先级与依赖关系小结

§6 的两项均标注为**非本轮核心**，但内部也有优先级差异：RSE 是纯确定性后处理、零模型调用成本，值得在核心链路稳定后第一批评估；MMR 多样性次之——两者落地前都应先用 `06` 的 ablation 矩阵各加一行验证，证明有实际收益后才把预留的 `rse_max_gap`/`mmr_lambda` 配置项从"占位注释"转为"生效配置"。
