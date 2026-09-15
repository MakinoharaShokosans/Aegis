# 架构决策记录：Agent Runtime 核心运行时

> **状态**：已定稿 (Accepted)  
> **责任领域**：`agent_runtime/` 与 `tool_layer/`  
> **核心目标**：构建具备显式状态机、崩溃续跑、预算守卫、因果可追溯与强类型契约的微型操作系统级 Agent 宿主。

---

## 1. 架构总览与执行拓扑

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        Aegis Agent Runtime                             │
│                                                                        │
│  [ LangGraph ]                ──► 状态图调度 / 条件边分支 / 循环迭代         │
│  [ AsyncOpenAI ]              ──► 全生态 OpenAI 兼容协议 (DeepSeek/GPT/本地)│
│  [ Pydantic v2 ]              ──► 强类型状态契约 / Tool Schema 自动生成     │
│  [ Context Pyramids ]         ──► 三层金字塔上下文治理 / trim_messages 截断  │
│  [ SQLite (AsyncSqliteSaver) ]──► 任务元数据表 + 状态快照 / 断点续跑 / Time-Travel │
│  [ Enhanced Guardrails ]      ──► 参数指纹 + 连续错误计数器 / 物理硬熔断    │
│  [ Tool Concurrency ]         ──► asyncio.gather 并行分发工具调用            │
│  [ Prompts Repository ]       ──► 独立 Markdown 规范文件 (prompts/*.md)   │
│  [ Trajectory Store ]         ──► storage/traces/{run_id}.jsonl 因果轨迹归档 │
│  [ Loguru + Langfuse ]        ──► 本地结构化日志 + 分布式调用瀑布流与成本追踪 │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心技术决策与权衡依据

### 2.1 编排引擎：选用 LangGraph

* **决策理由**：
  1. **显式状态机（Explicit State）**：打破传统 Agent（如 AgentExecutor）内部无法精细干预的黑盒 `while` 循环，采用基于 Pydantic 的全局强类型状态 Schema（`AgentState`），状态跃迁 100% 透明；
  2. **天然支持有向循环图（Cyclic Graphs & Conditional Edges）**：工程研究天然需要试错循环（例如：编译报错 -> 诊断错误 -> 修改代码 -> 重新编译）；
  3. **细粒度节点生命周期控制**：可方便地在 Node 之间插入防死循环检测器（Loop Detector）、Token 预算熔断器与上下文修剪逻辑。
* **工程约束**：只使用 LangGraph 核心图算子，工具适配与观察截断下沉至自研的 `tool_layer`，杜绝依赖第三方高层臃肿组件。

### 2.2 状态持久化与断点续跑：SQLite (aiosqlite) + AsyncSqliteSaver

* **决策理由**：
  1. **双重核心职责**：
     - **状态快照（Checkpoints）**：`AsyncSqliteSaver` 依赖 SQLite 表存储状态跃迁的 StateSnapshot，支持长任务因限流或崩溃时**毫秒级重入恢复（Crash Recovery）**与**时空穿梭排错（Time-Travel）**；
     - **任务元数据注册表（Run Registry）**：管理任务状态（PENDING/RUNNING/SUCCESS/FAILED）、起止时间、耗时与 Token 统计，无需引入额外的 MySQL/Postgres。
  2. **异步非阻塞与并发读写优化**：
     - 使用 `aiosqlite` 异步驱动，深度契合 `asyncio` 事件循环；
     - 启用 **WAL (Write-Ahead Logging) 模式**（`PRAGMA journal_mode=WAL;`），实现读写并发不互斥，消除单文件排他锁瓶颈。
  3. **单机便携性**：数据库收敛保存在 `storage/checkpoints/aegis_state.db` 与 `storage/aegis_meta.db`，无外部守护进程，开箱即跑。

### 2.3 LLM 协议与多套配置熔断机制：官方原生 AsyncOpenAI

* **决策理由**：
  1. **工程减法**：不引入沉重的三方适配框架（如 LiteLLM）。当前业界主流模型（DeepSeek-R1/V3、OpenAI、vLLM、Ollama、SiliconFlow）均原生对齐 `/v1/chat/completions` 标准；
  2. **配置驱动模型路由**：通过简单配置 `base_url` 与 `api_key`，按需在 Planner（推理模型）与 Executor（高精度工具调用模型）间灵活切换；
  3. **多套配置熔断与自动降级（Multi-Config Fallback）**：
     - 支持配置多套独立的 LLM 端点（每套包含独立的 `base_url`、`api_key`、`model_name`）；
     - 主配置失败时（超时、429、5xx、鉴权失败）自动切换至备用配置；
     - 配合 `tenacity` 库对 HTTP 429（限流）与 5xx 错误实现指数退避重试（Exponential Backoff）。

### 2.4 数据契约与上下文治理：Pydantic v2 + tiktoken + 智能 Pruner

* **决策理由**：
  1. **Pydantic v2 强类型契约**：约束全局状态、所有工具输入输出参数与因果轨迹结构。基于 Rust 核心毫秒级校验，自动生成标准的 Function Calling JSON Schema；
  2. **本地预算感知（tiktoken）**：快速在本地计算 Prompt Token 数量，零网络开销；
  3. **观察截断与卸载（Observation Offloading）**：
     - 当工具输出超限时，自研 Pruner 拦截原始日志落地到 `storage/artifacts/`，仅提取精炼摘要注入 Context；
     - **结构化格式感知（Structure-Aware Pruning）**：优先检测 JSON/YAML 等结构化输出，保持语法完整性；对纯文本日志采用 Head + Tail + Error 关键行提取策略。

### 2.5 提示词工程管理：独立 Markdown 规范文件 (`prompts/*.md`)

* **决策理由**：
  1. **代码与 Prompt 完全解耦**：存放在 `agent_runtime/prompts/` 目录下，彻底告别在 Python 代码中硬编码长文本 f-string 的混乱做法；
  2. **遵循现代大模型最佳实践**：现代 LLM 对结构清晰的 Markdown 格式具有最高的指令遵循度（Instruction Following）；
  3. **平滑演进**：平时保持纯 Markdown，若未来个别 Prompt 需引入复杂的循环渲染或条件分支，仅需加一行 `jinja2.Template(md).render(...)` 即可无缝扩展。

### 2.6 双轨可观测与因果追溯：Loguru + Langfuse + Trajectory Store

* **决策理由**：
  1. **本地系统轨（Loguru）**：异步写入 `storage/traces/{run_id}.jsonl`，记录全系统的结构化因果轨迹（包含 `step_id`, `phase`, `thought`, `action`, `distilled_observation` 与 `is_correction` 标记），直接作为自动化评测集输入；
  2. **平台可视化轨（Langfuse）**：通过 Docker 容器本地运行，一键挂载 LangGraph 的 `CallbackHandler`。在 Web UI 展现清晰的调用树拓扑图、瀑布流（Waterfall）、耗时与 Token 成本，提升演示与排障效率；
  3. **证据链溯源（Evidence Provenance）**：基准测试等大体积物料下沉落盘，最终 Markdown 报告必须显式标注证据引用句柄（如 `artifact://...`），彻底消灭报告幻觉。

---

## 3. 核心机制演进与精益优化规范 (Refinements)

针对长周期工程研究任务在实际运行中的**显存溢出、调试僵局、并发低效与费用失控**，系统实施以下四项架构级优化：

### 3.1 优化一：三层金字塔上下文压缩与治理（解决 Context 线性膨胀）

* **痛点**：单纯无脑追加消息，在执行 15~20 步后累积达到上万 Token，造成推理变慢、费用飙升及注意力迷失（Lost in the Middle）。
* **架构设计：三层金字塔上下文模型**：
  ```text
  ┌────────────────────────────────────────────────────────┐
  │  Layer 1: 永久锚定层 (Pinned System Context)           │  <-- 永远不删
  │  - 原始任务目标 (task_goal)                             │
  │  - 里程碑计划与当前阶段 (milestones)                    │
  ├────────────────────────────────────────────────────────┤
  │  Layer 2: 滚动摘要层 (Rolling Summary)                 │  <-- 阶段跃迁/超阈值压缩
  │  - 过去已完成里程碑的核心结论与事实摘要                │
  ├────────────────────────────────────────────────────────┤
  │  Layer 3: 活跃滑动窗口 (Active Working Memory)          │  <-- 动态滑窗 (近 3 轮)
  │  - 最近 3 轮原汁原味的 Tool Call 与 Observation        │
  └────────────────────────────────────────────────────────┘
  ```
* **两大工程死穴规避**：
  1. **工具调用原子对（Atomic Message Pair）整块裁剪**：
     - 严禁用数组暴力切片截断！若将大模型的 `AIMessage(tool_calls=[...])` 切掉而遗留孤立的 `ToolMessage`，将直接导致模型 API 报 **400 校验错误**（*tool_call_id 不匹配*）；
     - 裁剪时必须以“一次思考 + 对应工具响应”为不可分割的原子单元；
     - 落地依托 LangGraph 原生 `langchain_core.messages.trim_messages` 并结合 `RemoveMessage` 机制剔除陈旧历史。
  2. **读写分离机制（Working Context vs Audit Trajectory）**：
     - 给大模型看的上下文做严格的金字塔剪枝；
     - 本地 SQLite 与 `storage/traces/` 依然持久化全量未裁剪的历史因果链，确保离线评测与排障日志 100% 完整。

### 3.2 优化二：增强型死循环防御与连续错误计数器（解决微调打转漏洞）

* **痛点**：传统参数哈希比对（`md5(args)`）容易被大模型微调参数重试绕过（如每次变更加一个编译参数 `-Wall`、`-O1` 但持续报错），导致在原地死磕打转。
* **架构设计：双轨死循环熔断器**：
  1. **规则 A（原版指纹哈希）**：连续 3 次调用完全一致的工具与参数 -> 判定为无脑重复，直接拦截；
  2. **规则 B（连续错误状态计数器 `consecutive_errors`）**：
     - State 中维护 `consecutive_errors: int` 计数器；
     - 只要工具执行返回 `exit_code != 0` 或 `status == "FAILED"`，计数器 `+1`；一旦执行成功则立即清零；
     - **熔断阈值**：**无论参数如何微调，只要工具连续报错达到 3 次**，判定模型陷入调试僵局，条件边强行拉出当前微观循环，回退至 `planner` 触发重规划（Dynamic Replanning）。

### 3.3 优化三：多工具调用的并行异步执行（解决 I/O 阻塞耗时）

* **痛点**：模型单轮下发多个工具调用（如同时检索 3 个网页或并发检索 2 个源码符号）时，顺序串行执行导致耗时成倍累加。
* **架构设计：`asyncio.gather` 并发分发**：
  - `tool_node` 接收到 `message.tool_calls` 列表时，采用异步协程池并发请求底层微服务：
    ```python
    # 并发派发工具执行，等待全部完成
    tool_results = await asyncio.gather(*[
        dispatch_single_tool(call, state) for call in tool_calls
    ])
    ```
  - 总耗时从 $\sum t_i$ 缩减为 $\max(t_i)$，显著提升长任务执行效率。

### 3.4 优化四：`AgentState` 强类型规格定义 (含预算累加与 Reducer)

结合上述优化，最终落实的 `AgentState` 完整 Pydantic / TypedDict 规范如下：

```python
from typing import Annotated, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class Milestone(BaseModel):
    id: int
    title: str
    description: str
    status: Literal["pending", "in_progress", "completed", "failed"]

class AgentState(TypedDict):
    # 1. 目标与阶段规划
    task_id: str
    task_goal: str
    milestones: list[dict]                               # 里程碑计划列表
    current_milestone_idx: int                           # 当前进行中的里程碑索引
    
    # 2. 对话上下文与金字塔摘要 (遵循 Atomic Pair 裁剪)
    messages: Annotated[list[AnyMessage], add_messages]  # 活跃对话消息列表
    rolling_summary: str                                 # 历史已压缩阶段的全局事实摘要
    
    # 3. 产物与执行度量
    artifacts: dict[str, str]                            # 物料句柄 (artifact_id -> 磁盘绝对路径)
    step_count: int                                      # 当前执行总步数
    consecutive_errors: int                              # 连续错误计数器 (用于触发重规划)
    fingerprint_history: list[str]                       # 参数哈希历史 (保留最近 5 次)
    # 4. 物理预算与 Token 统计 (费用对齐上游，内部纯物理计数)
    total_tokens: int                                    # 累计消耗 Token (确定性硬指标)
```
