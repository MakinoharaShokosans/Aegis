# 目录结构与工程分层规范

> **责任领域**：`AegisAgent/` 全工程目录布局
> **契约基线**：`01`–`09` 规范 + `documents/技术选型/*` ADR
> **文档状态**：v1（统一裁决版）。本文件是目录结构的**唯一权威来源**；与本文冲突的历史表述以本文为准。
> **前置说明**：本文件只定义**结构与归属**，不定义实现细节；实现细节回引对应规范文档。

---

## 1. 设计原则

1. **契约与行为分离**
   `state.py` 只放纯类型契约（TypedDict / Pydantic 模型，零 I/O、零依赖）；运行期草稿纸行为放在 `execution_context.py`。对应 `07` 点名的两个文件。

2. **内容与代码分离**
   专家技能的 `SKILL.md` 与辅助脚本是**内容**（数据），放 `src/skills/`；技能的扫描、元数据解析与清单装配是**代码**，放 `src/agent_runtime/skills/registry.py`。两者绝不混放。

3. **纯函数优先**
   `routing.py` 与 `guardrails/` 必须全部是确定性逻辑：不调用 LLM、不做网络 I/O，可离线单测。这是"确定性包围非确定性"的落点。

4. **依赖严格单向**
   `config → state → guardrails/routing → llm/memory → tool_layer → nodes → workflow → api`。
   反向依赖一律禁止。

5. **Sidecar 契约不可穿透**
   `src/services/*` 与 `src/mcps/*` **禁止 import `agent_runtime`**。前者是独立 HTTP 服务，后者托管外部进程；一旦反向依赖就破坏了双子工程进程隔离的初衷（`01` §3）。

---

## 2. `src/agent_runtime/` 详细结构（编排内核）

```text
AegisAgent/src/agent_runtime/
├── __init__.py
├── config.py                  ✅ 已实现   Pydantic Settings 分层装配（TOML + .env）
├── state.py                   ＋          AgentState / Milestone / StepRecord / FailedAttempt 契约（02）
├── execution_context.py       ＋          草稿纸运行时对象 + Teardown 因果下沉（07）
├── context.py                 ＋          ContextManager 四层 Prompt 装配（06 §4）
├── routing.py                 ＋          4 个纯路由函数（04 §2）
├── workflow.py                ＋          图构建/编译 + run_agent / resume_agent（04 §3–4）
│
├── memory/                    ✅ 已实现   记忆子系统（06）
│   ├── __init__.py
│   ├── models.py                          Workspace / WorkspaceMemory / CompressedMemory / TurnRecord ...
│   ├── sqlite_store.py                    SQLite(WAL) 五表存储引擎
│   ├── manager.py                         双层记忆门面 + 水位压缩调度
│   └── compactor.py                       对话对齐切片 + LLM 提炼 + 优雅降级
│
├── llm/
│   ├── __init__.py
│   └── client.py              ＋          双模型网关：tenacity 退避 + 跨端点降级（05 §3）
│
├── guardrails/                            纯确定性，零 LLM
│   ├── __init__.py
│   ├── loop_detector.py       ＋          MD5 参数指纹 + consecutive_errors（05 §1）
│   ├── budget_guard.py        ＋          PhysicalBudgetGuard 类（05 §2）
│   └── pruner.py              ＋          Observation Pruner：Head/Tail 提炼 + 离线落盘（05 §4）
│
├── nodes/
│   ├── __init__.py
│   ├── planner.py             ＋          reasoning 层：宏观规划，产出决策指令
│   ├── budget_guard.py        ＋          薄节点：包装 guardrails.budget_guard
│   ├── executor.py            ＋          fast 层：生成 tool_calls + 并发派发（03 §4.3）
│   └── evaluator.py           ＋          reasoning 层：里程碑验收 + 事实沉淀（03 §4.4）
│
├── skills/
│   ├── __init__.py
│   └── registry.py            ＋          技能扫描 / frontmatter 解析 / 清单装配（08）
│
├── observability/                         双轨可观测（01 §4、技术栈.md）
│   ├── __init__.py
│   ├── logging.py             ＋          Loguru 结构化 JSONL 落盘
│   ├── trajectory.py          ＋          Trajectory Store → storage/traces/{task_id}.jsonl
│   └── langfuse_tracer.py     ＋          Langfuse 回调挂载与 Trace 关联
│
├── api/                                   ★ 用户入口（HTTP API，见 11_http_api.md）
│   ├── __init__.py
│   ├── app.py                 ＋          FastAPI 装配 + lifespan + CORS 白名单
│   ├── deps.py                ＋          依赖注入：config / MemoryManager / graph app / TaskRegistry
│   ├── schemas.py             ＋          请求/响应 DTO（与 AgentState 解耦，见 11 §3）
│   ├── errors.py              ＋          统一错误模型与异常处理器
│   ├── task_registry.py       ＋          运行中任务注册表 + SSE 事件广播
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── health.py          ＋
│   │   ├── workspaces.py      ＋
│   │   ├── sessions.py        ＋
│   │   ├── tasks.py           ＋
│   │   ├── artifacts.py       ＋
│   │   └── introspection.py   ＋          skills / tools / mcp 只读自省
│   └── __main__.py            ＋          uvicorn 入口（默认 127.0.0.1:8000）
│
└── prompts/                               提示词即配置，可热改
    ├── system.md              ＋          内置行为纪律（01 / README 点名）
    ├── planner.md             ＋
    ├── executor.md            ＋
    ├── evaluator.md           ＋
    └── compactor.md           ✅ 已实现
```

---

## 3. `AegisAgent/` 全景结构

```text
AegisAgent/
├── config/
│   └── config.toml                        ✅ 已有（待补 [server] 与 [mcp] 段）
├── pyproject.toml  uv.lock  README.md
├── .env.example  .gitignore  .python-version
│
├── src/
│   ├── agent_runtime/                     ← 见 §2
│   │
│   ├── skills/                            内置技能「内容包」（数据，非 Python 逻辑）
│   │   └── <skill_name>/
│   │       ├── SKILL.md                   必选，YAML frontmatter
│   │       ├── scripts/                   辅助脚本（如 parse_asan.py）
│   │       ├── references/
│   │       └── resources/
│   │
│   ├── tool_layer/
│   │   ├── __init__.py
│   │   ├── base.py            ＋          AegisTool 协议 / 基类
│   │   ├── registry.py        ＋          tools_registry
│   │   ├── dispatcher.py      ＋          asyncio.gather 并发派发（01 架构图点名）
│   │   ├── http_client.py     ＋          共享 httpx 连接池 + X-Trace-ID 透传
│   │   ├── mcp_adapter.py     ＋          MCP 命名空间转译（09）
│   │   └── tools/
│   │       ├── __init__.py
│   │       ├── bash_tool.py           ＋
│   │       ├── rag_tool.py            ＋
│   │       ├── web_search_tool.py     ＋
│   │       ├── file_tool.py           ＋
│   │       └── skill_tool.py          ＋   load_skill（08）
│   │
│   ├── mcps/
│   │   ├── __init__.py
│   │   ├── models.py          ＋          MCPServerConfig / MCPToolDefinition（09）
│   │   └── manager.py         ＋          stdio/SSE 托管、防僵尸、懒加载连接池（09）
│   │
│   ├── services/                          同工程内子系统，可独立进程启动（裁决项③）
│   │   ├── __init__.py
│   │   ├── bash_shell/
│   │   │   ├── __init__.py
│   │   │   ├── app.py         ＋          POST /api/v1/shell/execute
│   │   │   ├── sandbox.py     ＋          os.setsid + setrlimit + SIGTERM→SIGKILL
│   │   │   ├── audit.py       ＋          命令黑名单审计
│   │   │   ├── memory_pool.py ＋          GlobalMemoryBudget 排队与预估
│   │   │   └── __main__.py    ＋          uvicorn 入口 :8002
│   │   └── web_search/
│   │       ├── __init__.py
│   │       ├── app.py         ＋          /api/v1/search/*
│   │       ├── providers.py   ＋          duckduckgo / tavily 适配器
│   │       ├── extractor.py   ＋          trafilatura 正文提炼
│   │       ├── dedup.py       ＋          MD5 内容指纹去重
│   │       └── __main__.py    ＋          uvicorn 入口 :8003
│   │
│   └── evaluation/
│       ├── __init__.py
│       ├── rag_bench/
│       │   ├── __init__.py
│       │   ├── metrics.py             ＋  HitRate@K / MRR@K / NDCG@K（numpy）
│       │   ├── dataset.py             ＋
│       │   ├── evaluate_retrieval.py  ＋  离线驱动脚本
│       │   ├── datasets/              ＋  标注数据集
│       │   └── reports/               ＋  benchmark_report.md 输出
│       └── agent_bench/
│           ├── __init__.py
│           ├── metrics.py             ＋  Completion / Recovery / Efficiency / Provenance
│           ├── runner.py              ＋
│           └── tasks/                 ＋  20~50 个标准工程研究场景
│
├── tests/
│   ├── conftest.py            ＋          共享 fixture（临时 DB、mock LLM、mock 工具）
│   ├── fixtures/              ＋
│   ├── test_config.py         ＋
│   ├── memory/                ＋          test_models / test_sqlite_store / test_compactor / test_manager
│   ├── guardrails/            ＋
│   ├── nodes/                 ＋
│   ├── routing/               ＋
│   ├── workflow/              ＋
│   ├── context/               ＋
│   ├── llm/                   ＋
│   ├── skills/                ＋
│   ├── mcps/                  ＋
│   ├── services/              ＋
│   ├── api/                   ＋
│   └── evaluation/            ＋          pytest 入口在此（裁决项⑨）
│
└── storage/
    ├── aegis_meta.db                      运行时生成（已 gitignore）
    ├── checkpoints/                      ✅ .gitkeep — LangGraph 状态快照
    ├── traces/                           ✅ .gitkeep — {task_id}.jsonl 因果轨迹
    ├── artifacts/                        ✅ .gitkeep — {task_id}/ 离线卸载
    └── logs/                  ＋ .gitkeep — Loguru JSONL 落盘
```

---

## 4. 统一裁决记录

本表是历次规范冲突的**最终裁决**，冲突的历史表述一律以本表为准。

| # | 冲突点 | 最终裁决 | 理由 / 依据 |
|:--|:---|:---|:---|
| ① | `pruner.py` 归属：`guardrails/`（README 步骤六）vs `tool_layer/`（`01` 架构图） | **归 `agent_runtime/guardrails/pruner.py`**，并同步修订 `01` 架构图 | README 的文件级映射比示意图更具体；Pruner 属确定性治理逻辑，与 guardrails 同层 |
| ② | 技能内容位置：`src/skills/`（`08` + wheel 列表）vs `agent_runtime/skills/`（`08` 责任领域） | **内容在 `src/skills/`，代码在 `agent_runtime/skills/registry.py`** | 内容与代码分离原则；与 `pyproject.toml` 的 `packages` 列表一致 |
| ③ | `services/bash_shell`、`web_search` 是否拆为独立子工程 | **不拆分**，保留在 `AegisAgent/src/services/` 内，作为可独立 `uvicorn` 启动的 FastAPI 子应用 | 只涉及 HTTP 服务与外部工具，与 Agent 共享 config 与契约；`AegisRAG` 因重依赖（onnxruntime/tree-sitter）才独立 |
| ④ | `budget_guard` 双身份：节点（`03`）vs 实现文件（README 步骤六） | **类在 `guardrails/budget_guard.py`（`PhysicalBudgetGuard`），薄节点在 `nodes/budget_guard.py`** | 确定性逻辑与图节点解耦，便于离线单测 |
| ⑤ | `FailedAttempt` 在 `memory/models.py` 与 `02` 中重复定义 | **`state.py` 为唯一真源**，`memory/models.py` 改为 import | 避免两套契约漂移；属小幅重构已实现模块 |
| ⑥ | 产物命名 `{run_id}` vs `{task_id}` | **统一 `{task_id}`**（`storage/artifacts/{task_id}/`、`storage/traces/{task_id}.jsonl`） | `task_id` 是 `AgentState` 的正式字段 |
| ⑦ | Bash 沙箱 cwd：`storage/artifacts/{run_id}/workspace/`（bash ADR）vs 工作区 `root_path`（`06` §2.3） | **以工作区 `root_path` 为 cwd**；`storage/artifacts/{task_id}/` 只用于日志与产物落盘 | Agent 的职责是修改目标工程；锁死到临时目录则任务无法完成。路径越界防护以 `root_path` 为边界 |
| ⑧ | `services/rag_retrieval/`（rag ADR）vs 独立子工程 `AegisRAG/` | **统一为 `AegisRAG/`** | 与仓库实际布局一致 |
| ⑨ | 评测入口 `pytest evaluation/`（evaluation ADR）vs `testpaths=["tests"]` | **harness 在 `src/evaluation/`，pytest 用例在 `tests/evaluation/`** | 与 `pyproject.toml` 的 pytest 配置一致 |
| ⑩ | 缺用户入口 | **提供 HTTP API**（`agent_runtime/api/`，`127.0.0.1:8000`），不提供 CLI | 后续将由 Web 前端消费 Agent 能力 |
| ⑪ | 可观测性无代码落点 | **新增 `agent_runtime/observability/`** | `01`/`技术栈.md` 要求 Loguru JSONL + Langfuse + Trajectory 双轨 |

---

## 5. 依赖方向矩阵

行 = 调用方，列 = 被依赖方。`✔` 允许，`✘` 禁止。

| ↓ 调用 / → 被调用 | config | state | guardrails | routing | llm | memory | tool_layer | mcps | nodes | workflow | api | services |
|:---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **config** | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **state** | ✘ | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **guardrails** | ✔ | ✔ | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **routing** | ✘ | ✔ | ✘ | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **llm** | ✔ | ✔ | ✘ | ✘ | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **memory** | ✔ | ✔ | ✘ | ✘ | ✔ | — | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| **tool_layer** | ✔ | ✔ | ✔ | ✘ | ✘ | ✘ | — | ✔ | ✘ | ✘ | ✘ | ✘ |
| **mcps** | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ | — | ✘ | ✘ | ✘ | ✘ |
| **nodes** | ✔ | ✔ | ✔ | ✘ | ✔ | ✔ | ✔ | ✘ | — | ✘ | ✘ | ✘ |
| **workflow** | ✔ | ✔ | ✔ | ✔ | ✘ | ✔ | ✘ | ✔ | ✔ | — | ✘ | ✘ |
| **api** | ✔ | ✔ | ✘ | ✘ | ✘ | ✔ | ✘ | ✔ | ✘ | ✔ | — | ✘ |
| **services** | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | — |

**关键约束**：
- `nodes/*` 之间**禁止互相 import**（`03` §1）。跨节点复用逻辑必须下沉为纯函数模块。
- `services/*` 只能依赖 `config`（读取自身端口/配额），**不得**依赖 `state` 或 `agent_runtime`。
- `routing` 与 `guardrails` 不得依赖 `llm`，保证可离线确定性单测。

---

## 6. 打包与资源约定

`pyproject.toml` 的 `[tool.hatch.build.targets.wheel] packages` 必须覆盖以下包：

```toml
packages = [
    "src/agent_runtime",
    "src/tool_layer",
    "src/mcps",
    "src/services",
    "src/skills",
    "src/evaluation",
]
```

**非 `.py` 资源打包**：`src/agent_runtime/prompts/*.md` 与 `src/skills/**/SKILL.md` 等必须在 wheel 中保留，否则 `uv sync`/安装后提示词与技能包会丢失。需要显式声明包含规则（hatchling 的 `include` 或 `force-include`），并在安装后加一条冒烟测试：`importlib.resources` 能读到 `prompts/system.md`。

**提示词与技能路径解析**：运行时**禁止**写死相对路径；统一通过 `importlib.resources` 或"包内相对路径 + 项目根回退"双策略解析（现有 `compactor.py::_resolve_default_prompt_path` 已是该模式，新代码须沿用）。

---

## 7. 命名与占位约定

- **任务标识**：一律 `task_id`（UUID）。产物路径 `storage/artifacts/{task_id}/`，轨迹 `storage/traces/{task_id}.jsonl`。
- **未实现文件**：本规范中用 `＋` 标记的文件均**尚未创建**；`✅` 为已实现。
- **空目录占位**：需要入库的空目录一律放 `.gitkeep`（`storage/` 与 `src/services/*` 已有先例），并在本文件登记。
- **`__init__.py` 策略**：所有 Python 包目录必须有 `__init__.py`（含 `src/skills/`，即使它是内容目录——保持 hatchling `packages` 解析稳定）。

---

## 8. 技能扫描优先级（裁决项②细化）

技能注册表 `registry.py` 按**由高到低**的顺序扫描，同名技能高优先级**严格覆盖**低优先级：

| 优先级 | 扫描根 | 用途 |
|:--|:---|:---|
| 1（最高） | `<workspace.root_path>/.aegis/skills/` | 工作区（目标工程）自带的项目级技能 |
| 2 | `AegisAgent/src/skills/`（内置） | 随发行版交付的官方技能包 |
| 3（最低） | `~/.aegis/skills/` | 用户全局技能库 |

**渐进式披露**（`08` §3）：系统提示词仅注入技能清单（名称 + 一句话描述，总量控制在 1000 Token 内）；命中场景后由 Agent 调用 `load_skill` 载入完整 SOP；任务结束随 `ExecutionContext` 销毁。

---

## 9. 溯源对照

| 结构 | 依据 |
|:---|:---|
| `config.py` / `state.py` / `context.py` / `workflow.py` / `routing.py` / `nodes/` / `guardrails/` / `llm/` | `README.md` §2 步骤一~七、§4 |
| `memory/*` / `execution_context.py` | `06`、`07` 责任领域 |
| `guardrails/loop_detector.py` / `budget_guard.py` / `pruner.py` | `README.md` 步骤六（逐文件点名） |
| `llm/client.py` | `README.md` 步骤五 |
| `skills/registry.py` + `tool_layer/tools/skill_tool.py` | `README.md` 步骤三、`08` |
| `mcps/manager.py` / `mcps/models.py` / `tool_layer/mcp_adapter.py` | `README.md` 步骤四、`09` §5 |
| `src/skills/<name>/{SKILL.md,scripts,references,resources}` | `08` §2 |
| `prompts/system.md` / `prompts/*.md` | `01` §4.3、`README.md` §4 |
| `services/bash_shell/` / `services/web_search/` | `技术选型/bash_shell.md`、`web_search.md` 责任领域 |
| `evaluation/rag_bench/datasets/` / `agent_bench/tasks/` | `技术选型/evaluation.md` |
| `storage/{checkpoints,traces,artifacts}` | `01` §5、`06` §7 |
| `api/` | 裁决项⑩（HTTP API 入口） |

---

## 10. 待办（尚未落地，仅供追踪）

- `pyproject.toml` 需新增运行依赖：`fastapi`、`uvicorn[standard]`（裁决项③与⑩）、`langgraph-checkpoint-sqlite`（断点续跑）、`mcp`（`09`）。
- `config.toml` 需新增 `[server]`（host/port/CORS）与 `[mcp]` 段。
- 上述依赖与 `uv.lock` 必须在同一次变更中同步刷新。
