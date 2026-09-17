# 目录结构与工程分层规范

> **责任领域**：`AegisAgent/` 全工程目录布局
> **契约基线**：`01`–`09` 规范 + `documents/技术选型/*` ADR
> **文档状态**：v2（落地修订版）。本文件是目录结构的**唯一权威来源**；与本文冲突的历史表述以本文为准。
> **v2 修订**：① `tool_layer/` 更名 `tools/` 并拆分为 `core/`（框架）+ `builtin/`（基础工具）；
> ② 新增 `edges/`，与 `nodes/` 一一对称；③ MCP 代码全部归并到 `mcps/`；
> ④ `guardrails/` 消除重名（`physical_budget.py` / `observation_pruner.py`）；
> ⑤ 补齐 `errors.py` / `tokenizer.py` / `checkpoint.py` / `prompt_loader.py` 等基础工具；
> ⑥ 全量实现已落地，本文件同步标注实现状态。

---

## 1. 设计原则

1. **契约与行为分离**
   `state.py` 只放纯类型契约（TypedDict / Pydantic 模型，零 I/O、零依赖）；运行期草稿纸行为放在 `execution_context.py`。

2. **内容与代码分离**
   专家技能的 `SKILL.md` 与辅助脚本是**内容**（数据），放 `src/skills/`；扫描与元数据解析是**代码**，放 `src/agent_runtime/skills/registry.py`。

3. **纯函数优先**
   `routing.py`、`edges/` 与 `guardrails/` 必须全部是确定性逻辑：不调用 LLM、不做网络 I/O，可离线单测。

4. **nodes 与 edges 对称**
   节点负责"做事"，边负责"决定下一步去哪"。每个节点一个模块，每条迁移一个模块——
   新增一条边只碰一个文件，`routing.py` 仅做聚合导出。

5. **基础工具单独存放**
   工具的**框架机制**（协议、Schema 转译、注册表、并发派发、HTTP 客户端）在 `tools/core/`；
   **具体基础工具**在 `tools/builtin/`。新增工具永远不碰框架代码，反之亦然。

6. **依赖严格单向**
   `config → state/errors → guardrails/edges → llm/memory/skills/observability → tools/mcps → nodes → workflow → api`。
   反向依赖一律禁止。

7. **不可信数据不进入特权上下文**
   外部内容（网页）只能由**受限工具表**的研究子智能体接触；主工具表通过
   `ToolRegistry(allow_untrusted=False)` **在构造期拒绝**不可信工具，
   子智能体输出必须通过强类型契约校验（见 `12_research_subagent.md`）。
   同类约束后续扩展到 MCP 工具与工作区技能包。

8. **Sidecar 契约不可穿透**
   `src/services/*` **禁止 import `agent_runtime`**（连 `config` 也不行，各自读 TOML 段落）；
   `src/mcps/*` 只允许依赖契约层，不得感知图与节点。

---

## 2. `src/agent_runtime/` 详细结构（编排内核）

```text
AegisAgent/src/agent_runtime/
├── __init__.py                            对外能力边界（仅导出稳定入口）
├── config.py                   ✅         强类型配置（TOML + .env 分层装配 + 回环护栏）
├── errors.py                   ✅         领域异常体系（code + context，与 HTTP 解耦）
├── tokenizer.py                ✅         统一分词计量（tiktoken + 字符粗算降级）
├── state.py                    ✅         契约唯一真源：AgentState / ExecutionContext / Milestone /
│                                          FailedAttempt / StepRecord / TaskStatus
├── execution_context.py        ✅         Spawn 构造 + Teardown 因果下沉与会话记忆回写（07）
├── context.py                  ✅         ContextManager：四层 Prompt 装配 + 上下文检视（06 §4）
├── prompt_loader.py            ✅         提示词加载（包内路径优先 + 项目根回退 + 缓存）
├── structured_output.py        ✅         结构化输出抽取（节点与研究子智能体共用）
├── envelope.py                 ✅         ★ XML 定界信封的**唯一实现侧**（主循环与子智能体共用）
├── checkpoint.py               ✅         AsyncSqliteSaver 生命周期（WAL / 建表 / 关闭）（04 §4）
├── routing.py                  ✅         路由契约**聚合导出**（实现分散在 edges/）
├── workflow.py                 ✅         进程级装配 + 任务级装配 + 图构建 + run/resume（04 §3–4）
│
├── edges/                      ✅         条件边：与 nodes/ 一一对称，每条迁移一个模块
│   ├── __init__.py
│   ├── base.py                            RouterFn 契约 + 终点/里程碑判定原语
│   ├── after_planner.py                   熔断→END / 里程碑全完成→evaluator / 否则→budget_guard
│   ├── after_budget_guard.py              熔断→END / 否则→executor
│   ├── after_executor.py                  熔断→END / 否则→planner
│   └── after_evaluator.py                 达成→END / 否则→planner
│
├── nodes/                      ✅         图节点：工厂函数闭包注入依赖
│   ├── __init__.py
│   ├── base.py                            NodeFn 契约 + 结构化解析/合并等纯辅助
│   ├── planner.py                         reasoning 层：宏观规划 + 里程碑计划 + 反思重规划
│   ├── budget_guard.py                    薄节点：包装 PhysicalBudgetGuard
│   ├── executor.py                        fast 层：生成 tool_calls（不执行）+ 金丝雀熔断
│   ├── tool_runner.py                     ★ 权限闸门（HITL 挂起点）+ 并发派发 + 观察值治理
│   └── evaluator.py                       reasoning 层：里程碑独立验收 + 事实沉淀
│
├── guardrails/                 ✅         纯确定性策略（零 LLM、零 I/O）
│   ├── __init__.py
│   ├── loop_detector.py                   MD5 指纹队列 + 连续错误计数 + 重规划通知文本
│   ├── physical_budget.py                 PhysicalBudgetGuard：步数 / Token / 挂钟时间三重熔断
│   ├── observation_pruner.py              Observation Pruner：JSON 轮廓 / Head+关键字+Tail / 离线落盘
│   ├── injection_guard.py                 ★ 注入样态扫描（标注与审计，非安全边界；技能与 MCP 共用）
│   ├── permission.py                      ★ 三级权限分级与越级判定（HITL 判定核心，纯函数）
│   ├── budget_ledger.py                   ★ 子智能体预算账本（父级唯一记账方）+ ChildBudget（子级计数器）
│   └── authority.py                       ★ 任务授权窗口（父级权限级别的权威推送点，叶子工具只读视图）
│
├── research/                   ✅         研究子智能体：不可信外部数据的隔离区（12）
│   ├── __init__.py
│   ├── contracts.py                       ResearchRequest / ResearchReport 强类型契约 + render_for_model
│   ├── runner.py                          有界异步循环：检索规划 → 并发抓取 → 强类型提炼
│   └── tool.py                            DelegateResearchTool + build_research_tool 装配
│
├── subagent/                   ✅         动态子智能体委派：能力衰减 + 预算切片 + 上下文隔离（13）
│   ├── __init__.py
│   ├── contracts.py                       Proposal（模型提议）/ Request（已收窄授权）分离 +
│   │                                      SubagentReport + 引用白名单（URL 白名单的泛化）
│   ├── runner.py                          有界异步循环：子级权限二次判定（**不 interrupt**）→ 派发 → 收尾
│   └── tool.py                            ★ SpawnSubagentTool：三道收窄在派发前一次完成
│
├── llm/                        ✅         双模型分层网关
│   ├── __init__.py
│   ├── endpoints.py                       端点解析 + 凭据注入（本地端点 EMPTY / 云端缺钥跳过）
│   ├── fallback.py                        tenacity 端点内退避 → 跨端点降级链
│   └── client.py                          统一门面 LLMGateway + LangChain↔OpenAI 消息转换
│
├── memory/                     ✅         记忆子系统（06）
│   ├── __init__.py
│   ├── models.py                          Workspace / WorkspaceMemory / CompressedMemory / TurnRecord
│   ├── sqlite_store.py                    SQLite(WAL) 五表存储 + 只读查询（get_session / list_turns）
│   ├── manager.py                         双层记忆门面 + 水位压缩调度 + 只读/更新接口
│   └── compactor.py                       对话对齐切片 + LLM 提炼 + 优雅降级
│
├── skills/                     ✅         技能注册表（代码侧；内容在 src/skills/）
│   ├── __init__.py
│   └── registry.py                        三档扫描 + frontmatter 解析 + 清单装配 + 按需加载
│
├── observability/              ✅         双轨可观测
│   ├── __init__.py
│   ├── logging.py                         Loguru 控制台 + 结构化 JSONL 双 sink
│   ├── trajectory.py                      Trajectory Store → storage/traces/{task_id}.jsonl
│   └── langfuse_tracer.py                 Langfuse 回调（可失败旁路，未配置即跳过）
│
├── api/                        ✅         交付层：HTTP + SSE（契约见 11_http_api.md）
│   ├── __init__.py
│   ├── app.py                             FastAPI 装配 + lifespan + CORS 白名单
│   ├── deps.py                            依赖注入（RuntimeDeps / TaskRegistry / MemoryManager）
│   ├── schemas.py                         对外 DTO（与 AgentState 解耦）
│   ├── errors.py                          领域异常 → HTTP 状态码映射 + 统一错误体
│   ├── task_registry.py                   任务句柄 + SSE 环形缓冲 + 订阅广播 + 并发闸门
│   ├── __main__.py                        uvicorn 入口（127.0.0.1:8000）
│   └── routes/
│       ├── __init__.py
│       ├── health.py                      进程健康 + sidecar 依赖连通性
│       ├── workspaces.py                  工作区 CRUD + 共享记忆上浮
│       ├── sessions.py                    会话 CRUD + 流水分页 + 上下文检视
│       ├── tasks.py                       提交/状态/SSE/续跑/取消/时间线/轨迹
│       ├── artifacts.py                   产物列表与原文下载（路径穿越防护）
│       └── introspection.py               skills / tools / mcp / models 自省（零密钥外泄）
│
└── prompts/                    ✅         提示词即内容（可热改）
    ├── system.md                          内置行为纪律（含外部信息纪律）
    ├── planner.md / executor.md / evaluator.md
    ├── research.md                        研究子智能体指令（检索规划 + 结论提炼）
    └── compactor.md                       会话记忆压缩提示词
```

---

## 3. `AegisAgent/` 全景结构

```text
AegisAgent/
├── config/config.toml          ✅         全部可调参数（含 [server] / [mcp] / [bash_shell] / [web_search]）
├── pyproject.toml  uv.lock  README.md  .env.example  .gitignore  .python-version
│
├── src/
│   ├── agent_runtime/          ✅         ← 见 §2
│   │
│   ├── tools/                  ✅         工具能力层（与 agent_runtime 平级）
│   │   ├── __init__.py
│   │   ├── core/                          【框架】不含任何具体工具
│   │   │   ├── __init__.py
│   │   │   ├── protocol.py                AegisTool 抽象基类 + ToolResult 统一契约
│   │   │   ├── schema.py                  AegisTool → OpenAI function Schema 转译
│   │   │   ├── registry.py                注册表（重名即失败）
│   │   │   ├── dispatcher.py              asyncio.gather 并发派发 + 单工具超时 + 失败降级
│   │   │   └── http_client.py             ServiceClient：共享连接池 + X-Trace-ID 透传
│   │   └── builtin/                       【基础工具】单独存放
│   │       ├── __init__.py                build_builtin_tools 装配入口
│   │       ├── bash.py                    调 bash_shell :8002
│   │       ├── rag_search.py              调 AegisRAG :8001
│   │       ├── web_search.py              调 web_search :8003
│   │       ├── file_ops.py                view_file / write_file（root_path 越界防护）
│   │       └── load_skill.py              渐进式披露第二阶段：按需挂载 SOP
│   │
│   ├── mcps/                   ✅         MCP 代码全部集中（不再跨包）
│   │   ├── __init__.py
│   │   ├── models.py                      命名空间规则 + MCPToolDefinition
│   │   ├── vetting.py                     ★ 工具描述消毒（注入样态硬拒 + 形状约束）
│   │   ├── adapter.py                     远端工具 → 本地 AegisTool 契约转译（trust=untrusted）
│   │   └── manager.py                     懒加载握手 / 故障隔离 / stdio 资源上限 / AsyncExitStack
│   │
│   ├── services/               ✅         同工程子系统（各自独立进程，禁止反向依赖）
│   │   ├── __init__.py
│   │   ├── settings.py                    独立 TOML 段落读取（不依赖 agent_runtime）
│   │   ├── bash_shell/                    settings / audit / memory_pool / sandbox / app / __main__  :8002
│   │   └── web_search/                    settings / providers / extractor / dedup / app / __main__  :8003
│   │
│   ├── skills/                 ✅         内置技能内容包（数据）。空目录以 __init__.py 占位
│   │   └── <skill_name>/{SKILL.md, scripts/, references/, resources/}
│   │
│   └── evaluation/             ✅         离线评测 harness（零 LLM 消耗）
│       ├── rag_bench/                     metrics(HR/MRR/NDCG) / dataset / evaluate_retrieval
│       │                                  + datasets/ + reports/
│       └── agent_bench/                   metrics(完成/自愈/效率/溯源) / runner + tasks/
│
├── tests/                      ✅         与 src 镜像的测试树（conftest + fixtures + 各子系统目录）
└── storage/
    ├── aegis_meta.db                      运行时生成（已 gitignore）
    ├── checkpoints/            ✅         LangGraph 状态快照
    ├── traces/                 ✅         {task_id}.jsonl 因果轨迹
    ├── artifacts/              ✅         {task_id}/ 离线卸载
    └── logs/                   ✅         Loguru JSONL
```

---

## 4. 统一裁决记录

本表是历次规范冲突的**最终裁决**，冲突的历史表述一律以本表为准。

| # | 冲突点 | 最终裁决 | 理由 / 依据 |
|:--|:---|:---|:---|
| ① | `pruner.py` 归属：`guardrails/`（README 步骤六）vs `tools/`（`01` 架构图） | **归 `agent_runtime/guardrails/observation_pruner.py`**，并同步修订 `01` 架构图 | README 的文件级映射比示意图更具体；Pruner 属确定性治理逻辑，与 guardrails 同层 |
| ② | 技能内容位置：`src/skills/`（`08` + wheel 列表）vs `agent_runtime/skills/`（`08` 责任领域） | **内容在 `src/skills/`，代码在 `agent_runtime/skills/registry.py`** | 内容与代码分离原则 |
| ③ | `services/bash_shell`、`web_search` 是否拆为独立子工程 | **不拆分**，保留在 `AegisAgent/src/services/` 内，各自作为独立进程经 HTTP 暴露 | 只涉及 HTTP 服务与外部工具，共享工程与依赖锁；`AegisRAG` 因重依赖（onnxruntime/tree-sitter）才物理独立 |
| ④ | `budget_guard` 双身份：节点（`03`）vs 实现文件（README 步骤六） | **类在 `guardrails/physical_budget.py`，薄节点在 `nodes/budget_guard.py`** | 确定性逻辑与图节点解耦，便于离线单测 |
| ⑤ | `FailedAttempt` 在 `memory/models.py` 与 `02` 中重复定义 | **`state.py` 为唯一真源**，`memory/models.py` 改为 import | 避免两套契约漂移 |
| ⑥ | 产物命名 `{run_id}` vs `{task_id}` | **统一 `{task_id}`** | `task_id` 是 `AgentState` 的正式字段 |
| ⑦ | Bash 沙箱 cwd：临时目录（bash ADR）vs 工作区 `root_path`（`06` §2.3） | **以工作区 `root_path` 为 cwd**；`storage/artifacts/{task_id}/` 只用于日志与产物落盘 | Agent 的职责是修改目标工程 |
| ⑧ | `services/rag_retrieval/`（rag ADR）vs 独立子工程 `AegisRAG/` | **统一为 `AegisRAG/`** | 与仓库实际布局一致 |
| ⑨ | 评测入口 `pytest evaluation/`（evaluation ADR）vs `testpaths=["tests"]` | **harness 在 `src/evaluation/`，pytest 用例在 `tests/evaluation/`** | 与 `pyproject.toml` 的 pytest 配置一致 |
| ⑩ | 缺用户入口 | **提供 HTTP API**（`agent_runtime/api/`，`127.0.0.1:8000`），不提供 CLI | 由 Web 前端消费 Agent 能力 |
| ⑪ | 可观测性无代码落点 | **`agent_runtime/observability/`** | `01`/`技术栈.md` 要求双轨可观测 |
| ⑫ | `tool_layer/` 命名与内部混杂 | **更名 `tools/`，拆 `core/`（框架）与 `builtin/`（基础工具）** | 框架与业务分离；去掉冗余的 `_layer` |
| ⑬ | 条件边全部挤在 `routing.py` | **新增 `edges/`，与 `nodes/` 对称；`routing.py` 退化为聚合导出** | 新增边不必修改公共文件 |
| ⑭ | MCP 代码跨 `tools/` 与 `mcps/` 两处 | **全部归并到 `mcps/`**（`models` / `adapter` / `manager`） | 集中审计"谁拉起了什么进程" |
| ⑮ | 部分基础能力（异常/分词/检查点/提示词加载）无归属 | **`errors.py` / `tokenizer.py` / `checkpoint.py` / `prompt_loader.py` / `structured_output.py`** | 统一口径，避免各处重复实现 |
| ⑯ | "内部跑模型循环的能力"用**子图**还是 **tool** | **一律用 tool，禁用子图**（通则；首个实例是 `delegate_research`，泛化为 `spawn_subagent`） | 子图会共享 `messages` 与 Checkpoint ⇒ 被隔离的中间内容回流并**持久化进主任务快照**，恢复时重新喂回主上下文，隔离形同虚设；tool 天然把不可信内容的生命周期关在一次函数调用内。泛化论证见 `13` §1.3 |
| ⑰ | "主工具表不含 web_search" 只靠约定 | **`AegisTool.trust` + `ToolRegistry(allow_untrusted=False)` 构造期拒绝** | 把约定变成可执行不变量——想犯这个错都犯不了 |
| ⑱ | 工作区技能包静默进入**系统提示词** | **按来源分级：`builtin`/`global` 可信、`workspace` 默认拒绝**；元数据做注入标注与长度截断；内容纳入 XML 定界信封 | 克隆恶意仓库即可注入是唯一"零交互可中招"的路径，必须默认拒绝（`08` §4.1–4.3） |
| ⑳ | 人工审批的 `interrupt()` 放在哪个节点 | **新增 `tool_runner` 节点承载权限闸门，`executor` 只生成 `tool_calls`** | LangGraph 的 `interrupt()` 恢复时**重跑整个节点**；若闸门紧邻 fast 模型调用，审批后会让模型调用再发生一次——重复计费，且可能产生"用户批准的命令 ≠ 实际执行的命令"。拆开后重跑代价仅为纯函数判定 |
| ㉑ | 三级权限在 bash_shell 还是 Agent 侧判定 | **统一在 Agent 工具层判定**（`tool_runner`），bash_shell 只保留绝对红线 `CommandAudit` | 避免两套分类器漂移；工具层同时知道工具名与参数，是唯一能统一判定所有工具（含 MCP）的位置 |
| ⑲ | MCP 工具直接进主工具表 | **数据面与控制面分离**：描述消毒硬拒 + 结果标注；`trust="untrusted"` 且经 `untrusted_allowlist` **逐名授权**；stdio 子进程施加 setrlimit | 工具描述会进**工具 Schema**（位置高于观察值）；stdio server 是任意代码执行，只能靠 opt-in + 资源上限 + 审计（`09` §3.5） |
| ㉒ | 子智能体的 Token 消耗游离在父任务预算之外 | **`BudgetLedger`：父级唯一记账方，先预留后结算；子级只能报告不能记账；消耗以增量冲销进 `total_tokens`** | 工具层此前的隐含契约是"工具是叶子、便宜"，动态子智能体三条全破。若不显式补偿，父任务的物理熔断可被委托绕过；而**事后累加在并发下不成立**（父任务在子任务返回前不知道它花了多少）；冲销只能发生在审批闸门**之后**，否则 `interrupt()` 丢弃节点返回值会连带丢账（`13` §4） |
| ㉓ | 工具信任级是静态类属性 | **新增调用期覆盖 `ToolResult.trust`；`DispatchedResult.trust` 统一解析，不可信信封由编排层集中添加** | `spawn_subagent` 的输出信任级取决于**本次被授予了哪些工具**，静态属性表达不了这种依赖。信封由编排层加而非各工具自渲染，才能避免"某个工具忘了标注"的漏网（`13` §3.4） |
| ㉔ | 通用子智能体的输出契约交给主模型定义 | **禁止**：只保留"固定信封 + 保守信任级"；保真度由**引用白名单**兜底 | `12` 的安全性来自**语义**约束（URL 真实抓取过、版本号严格正则），那是逐用途手写的判断，模型只能给**形状**给不出**语义**。参数化 schema 会让强类型退化成"包装成 JSON 的自由文本"——**比自由文本更危险，因为它骗过阅读者的警惕**（`13` §3.1） |
| ㉕ | 子智能体内部能否请求人工审批 | **不能**。越级即失败，子级循环**不 import `interrupt`** | ①技术：`interrupt()` 恢复会重跑整个节点，而子智能体跑在 `tool_runner` 内部 ⇒ 挂起恢复会让子循环全量重跑，模型调用重复计费、有副作用的工具**执行两次**；②安全：审批洗白——父级被拦的动作可被子智能体重新包装成审批卡片。两害之下"派发前一次性衰减"是唯一既能保安全又能保语义的写法（`13` §2.3） |

---

## 5. 依赖方向矩阵

行 = 调用方，列 = 被依赖方。`✔` 允许，`✘` 禁止。

| ↓ 调用 / → 被调用 | config | state | errors | guardrails | edges | llm | memory | tools | mcps | research | subagent | nodes | workflow | api | services |
|:---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **config** | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **state** | ✘ | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **errors** | ✘ | ✘ | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **guardrails** | ✔ | ✔ | ✔ | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **edges** | ✘ | ✔ | ✘ | ✘ | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **llm** | ✔ | ✔ | ✔ | ✘ | ✘ | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **memory** | ✔ | ✔ | ✔ | ✘ | ✘ | ✔ | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **tools** | ✔ | ✔ | ✔ | ✔ | ✘ | ✘ | ✘ | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **mcps** | ✔ | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ | ✔ | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **research** | ✔ | ✔ | ✔ | ✔ | ✘ | ✔ | ✘ | ✔ | ✘ | — | ✘ | ✘ | ✘ | ✘ | ✘ |
| **subagent** | ✔ | ✔ | ✔ | ✔ | ✘ | ✔ | ✘ | ✔ | ✘ | ✘ | — | ✘ | ✘ | ✘ | ✘ |
| **nodes** | ✔ | ✔ | ✔ | ✔ | ✘ | ✔ | ✔ | ✔ | ✔ | ✘ | ✘ | — | ✘ | ✘ | ✘ |
| **workflow** | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | — | ✘ | ✘ |
| **api** | ✔ | ✔ | ✔ | ✘ | ✔ | ✘ | ✔ | ✔ | ✔ | ✘ | ✘ | ✘ | ✔ | — | ✘ |
| **services** | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |

**关键约束**：

- `nodes/*` 之间**禁止互相 import**；跨节点复用逻辑下沉为 `nodes/base.py` 的纯函数。
- `edges/*` 只依赖 `state` 与 `langgraph`，**不得**依赖 `llm`/`memory`/`tools`。
- `guardrails/` 不得依赖 `llm`，保证可离线确定性单测。
- `services/*` **连 `config` 都不依赖**——各自通过 `services/settings.py` 读 TOML 段落。
- `research/*` 与 `subagent/*` 只依赖 `tools.core` 的**契约**（`AegisTool` / `ToolRegistry` /
  `ToolDispatcher`），**不 import 任何具体工具**——受限工具表由 `workflow` 注入（依赖倒置）。
- **`nodes/*` 不得依赖 `subagent/`**：`tool_runner` 只通过 `envelope` / `budget_ledger` /
  `authority` 这三个共享原语与委派能力交互。若 `nodes` 需要 import `subagent`，
  说明委派逻辑漏进了编排层。
- **LLM 循环型能力不得放进 `tools/builtin/`**：`tools/builtin/` 只放叶子工具；
  凡内部要跑模型循环的（如研究子智能体、动态子智能体），归入各自的编排包
  （`research/` / `subagent/`），否则会形成 `tools ↔ research` 的包级循环。
- **XML 定界信封只允许一处实现**（`envelope.py`）：协议分叉在安全上不可接受——
  一份实现加了不可信警示、另一份忘了加，读者就会把不可信内容当成可信内容。

> 注：`services` 行全为 `✘` 指的是"不依赖 `agent_runtime`"；`services/settings.py` 是服务侧自有模块，不受本矩阵约束。

---

## 6. 打包与资源约定

`pyproject.toml` 的 `[tool.hatch.build.targets.wheel] packages` 必须覆盖：

```toml
packages = [
    "src/agent_runtime",
    "src/tools",
    "src/mcps",
    "src/services",
    "src/skills",
    "src/evaluation",
]
```

**非 `.py` 资源打包（已实测验证，无需额外配置）**：`src/agent_runtime/prompts/*.md` 与 `src/skills/**` 下的 `SKILL.md` / 脚本必须随 wheel 分发。

**hatchling 对 `packages` 列出的目录默认打包其下全部文件（含 `.md` / `.sh`），无需 `include` 或 `force-include`。** 已在构建 `aegis_agent-0.1.0-py3-none-any.whl` 时实测确认：

| 资源 | wheel 内路径 | 结果 |
|:---|:---|:---|
| 提示词 | `agent_runtime/prompts/{system,planner,executor,evaluator,compactor}.md` | ✓ 已打包 |
| 技能 SOP | `skills/<name>/SKILL.md` | ✓ 已打包 |
| 技能脚本 | `skills/<name>/scripts/*.sh` | ✓ 已打包 |

**唯一例外**：被 `.gitignore` 排除的文件不会被 hatchling 打包（默认遵循 VCS ignore）。

**提示词与技能路径解析**：运行时**禁止**写死相对路径；统一走 `prompt_loader.py` 的"包内优先 + 项目根回退"双策略。

---

## 7. 命名与占位约定

- **任务标识**：一律 `task_id`（UUID）。产物路径 `storage/artifacts/{task_id}/`，轨迹 `storage/traces/{task_id}.jsonl`。
- **实现状态标记**：`✅` = 已实现。本规范 v2 起，§2/§3 的目录均已落地。
- **空目录占位**：需要入库的空目录一律放 `.gitkeep`；Python 包目录必须有 `__init__.py`。
- **时区与时间**：一律使用 Unix 秒（浮点），不用本地化字符串。

---

## 8. 技能扫描优先级（裁决项②细化）

技能注册表按**由高到低**扫描，同名技能高优先级**严格覆盖**低优先级：

| 优先级 | 扫描根 | 用途 |
|:--|:---|:---|
| 1（最高） | `<workspace.root_path>/.aegis/skills/` | 目标工程自带的项目级技能 |
| 2 | `AegisAgent/src/skills/`（内置） | 随发行版交付的官方技能包 |
| 3（最低） | `~/.aegis/skills/` | 用户全局技能库 |

**实现细节**：注册表按"低优先级先写入、高优先级后覆盖"的顺序遍历，天然实现覆盖语义；
`build_prompt_summary()` 只注入名称 + 一句话描述（渐进式披露第一阶段），
完整 SOP 由 `load_skill` 工具按需载入。

---

## 9. 溯源对照

| 结构 | 依据 |
|:---|:---|
| `config.py` / `state.py` / `context.py` / `workflow.py` / `routing.py` / `nodes/` / `guardrails/` / `llm/` | `README.md` §2 步骤一~七 |
| `memory/*` / `execution_context.py` | `06`、`07` 责任领域 |
| `guardrails/{loop_detector,physical_budget,observation_pruner}.py` | `README.md` 步骤六、`05` §1/§2/§4 |
| `llm/{endpoints,fallback,client}.py` | `README.md` 步骤五、`05` §3 |
| `skills/registry.py` + `tools/builtin/load_skill.py` | `README.md` 步骤三、`08` |
| `mcps/{models,adapter,manager}.py` | `README.md` 步骤四、`09` §5 |
| `src/skills/<name>/{SKILL.md,scripts,references,resources}` | `08` §2 |
| `prompts/system.md` 等 | `01` §4.3 |
| `services/{bash_shell,web_search}/` | `技术选型/bash_shell.md`、`web_search.md` |
| `evaluation/{rag_bench,agent_bench}/` | `技术选型/evaluation.md` |
| `storage/{checkpoints,traces,artifacts,logs}` | `01` §5、`06` §7 |
| `edges/` | 裁决项⑬ |
| `research/` + `guardrails/injection_guard.py` | `12_research_subagent.md` |
| `subagent/` + `guardrails/{budget_ledger,authority}.py` + `envelope.py` | `13_subagent_delegation.md` |
| `api/` | 裁决项⑩、`11_http_api.md` |

---

## 10. 落地状态台账

| 项 | 状态 |
|:---|:---|
| `pyproject.toml` 依赖（fastapi / uvicorn / mcp / langgraph-checkpoint-sqlite）与 `uv.lock` | ✅ 已完成（`uv lock --check` 通过，114 包） |
| `config.toml` 的 `[server]` / `[mcp]` / `[bash_shell]` / `[web_search]` 段 | ✅ 已完成 |
| `config.py` 强类型模型与回环 fail-closed 护栏 | ✅ 已完成 |
| 契约层（`state` / `errors` / `tokenizer`） | ✅ 已完成 |
| 策略层（`guardrails/` 三件套） | ✅ 已完成 |
| 能力层（`llm` / `memory` / `skills` / `observability`） | ✅ 已完成（`memory` 为最早期实现） |
| 工具层（`tools/core` 框架 + `tools/builtin` 五个基础工具） | ✅ 已完成 |
| MCP 层（`mcps/` 三件套） | ✅ 已完成 |
| 编排层（`edges/` + `nodes/` + `routing` + `context` + `execution_context` + `workflow`） | ✅ 已完成 |
| 交付层（`api/` + 6 组路由） | ✅ 已完成（OpenAPI：25 路径 / 30 操作） |
| 子系统（`services/bash_shell` + `web_search`） | ✅ 已完成 |
| 评测 harness（`rag_bench` + `agent_bench`） | ✅ 已完成 |
| 外部检索隔离（`research/` + `Trust` 机制 + 注入标注） | ✅ 已完成（见 `12_research_subagent.md`） |
| 动态子智能体委派（`subagent/` + 预算账本 + 三道收窄 + 引用白名单 + 调用期信任级） | ✅ 已完成（见 `13_subagent_delegation.md`） |
| 子智能体预算对账缺口修复（消耗回流 `total_tokens`） | ✅ 已完成（裁决㉒；修复了工具层对预算**只读**导致的委托绕过） |
| 工作区技能包的不可信边界（信任分级 / 默认拒绝 / 披露信封） | ✅ 已完成（见 `08` §4.1–4.3，裁决⑱） |
| MCP 工具的不可信边界（描述消毒 / 逐名授权 / 子进程资源上限） | ✅ 已完成（见 `09` §3.5，裁决⑲） |
| 本地代码库（RAG 检索结果） | 视为可信（用户自己的工作区）；若将来索引外部仓库需重新评估 |
| **三级权限分级 + 越级 HITL 人工审核** | ✅ 已完成：`guardrails/permission.py` 纯函数判定 + `nodes/tool_runner.py` 权限闸门（`interrupt`/`Command(resume)`）+ `/approve`、`/reject` 端点 + 会话级永久放行白名单 |
| 自动化测试覆盖 | ⬜ 持续补齐中 |
