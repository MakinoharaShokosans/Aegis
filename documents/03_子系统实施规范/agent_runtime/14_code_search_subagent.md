# 源码检索子智能体规范（Code Search Subagent）

> **责任领域**：`AegisAgent/src/agent_runtime/code_search/`
> **契约基线**：`01` §3 信任边界、`05` 护栏、`10` 目录与依赖矩阵、`12_research_subagent.md`、`13_subagent_delegation.md`
> **文档状态**：v1（已落地）
> **一句话定位**：**将多轮 RAG 检索、切片有效性判别、自适应改词重试与源码提炼封装进独立的子智能体生命周期**，实现"有效即早停、无效则换词、无果则拒答"的确定性代码检索闭环。

---

## 1. 产生背景与痛点

在主 Agent 解决复杂代码任务（如定位函数实现、追踪跨模块调用链、排查业务逻辑）时，如果直接由主 Agent 单次调用 `rag_search`：
1. **主上下文与 Checkpoint 污染**：试错检索的多个原始切片（每次数千 Token）直接注入主上下文与 Checkpoint，严重稀释上下文注意力；
2. **挤占主图步数**：主 Agent 在主循环中反复 ReAct 试错换词，容易过早耗尽主图 `max_steps` 或触发循环检测；
3. **缺少主动判别与自适应换词**：首次检索词往往不够精准，缺少对切片有效性的判别与 Query Reformulation 机制；
4. **代码幻觉风险**：在检索无果时，模型容易依据弱相关切片强行推测代码实现。

---

## 2. 核心机制设计

### 2.1 有界 3 轮执行循环与状态机

```
请求 (target, questions, file_hints)
  │
  ├─ 1. 初始化独立 ChildBudget (Token / 挂钟上限)
  │
  ├─ 2. Round 1: Fast 模型规划精准代码检索词 → 并发调用 RAG retrieve
  │               收集 Evidence (file_path, lines, scope, content)
  │               外发 SSE 事件: code_search.round
  │
  ├─ 3. Round 2..3 (按需):
  │       ├─ Fast 模型判别当前证据是否已充分覆盖 target
  │       ├─ 若充分 → 【早停 Early Exit】直接进入提炼
  │       └─ 若不充分 → 提取代码线索，重写检索词再搜一轮
  │
  ├─ 4. 结论提炼 (Distill): 仅基于已收集 Evidence 提炼关键代码位置与实现结论
  │
  ├─ 5. 引用白名单净化 (build_code_report):
  │       ├─ 严格校验 location (file_path:start-end) 是否落在真实召回切片内 (伪造引用直接剔除)
  │       ├─ 长度硬截断 (max_answer_chars, max_code_chars, max_report_chars)
  │       └─ 若 status="not_found"，显式附带已尝试检索词与未能解答列表
  │
  └─ 6. 渲染回流主 Agent: <code_search_summary status="..." trust="trusted"> 结构化信封
```

### 2.2 确定性拒答契约（"3 次没有就承认没有"）

- 若 3 轮检索用尽仍未找到目标代码，状态置为 `status="not_found"`；
- `findings` 保持为空，在 `unresolved` 中记录未找到的问题；
- 返回合法的 `ToolResult(ok=True)` 并在内容中如实说明已尝试检索词与未找到的事实，避免主循环误判为工具故障，同时彻底杜绝主模型根据弱相关文本产生幻觉。

### 2.3 强引用位置白名单（Location Whitelist）

- 子智能体提炼出的每一个位置（`file_path:start_line-end_line`），必须严格存在于本次运行中真实由 AegisRAG 召回的 `CodeChunkEvidence` 集合中；
- 凭记忆或猜测编造的行号或文件将被底层确定性代码剔除。

---

## 3. 交互契约与配置

### 3.1 工具入参

```json
{
  "name": "delegate_code_search",
  "description": "委托专用代码检索子智能体在代码库中进行多轮深度检索、符号追踪与实现提炼...",
  "parameters": {
    "target": "string",
    "questions": ["string"],
    "file_hints": ["string"],
    "language": "string",
    "max_chunks": "integer"
  }
}
```

### 3.2 配置项 (`config.toml`)

```toml
[code_search]
enabled = true                      # 关闭后主 Agent 仅具备单次 rag_search 基础检索能力
model_tier = "fast"                 # 使用便宜快速的层级
max_rounds = 3                      # 内部检索与判别重试轮数上限
max_chunks_per_round = 5            # 单轮检索最多召回切片数
max_source_chars = 6000             # 单切片正文进入子上下文的截断上限
max_wall_time_sec = 45              # 子智能体挂钟上限（秒）
max_total_tokens = 20000            # 子智能体 Token 上限
max_findings = 6                    # 结论条目上限
max_answer_chars = 500              # 单条结论长度上限
max_code_snippets = 5               # 代码片段条目上限
max_code_chars = 2000               # 单个代码片段长度上限
max_report_chars = 4000             # 渲染后注入主上下文的上限
```
