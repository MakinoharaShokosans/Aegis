# AegisAgent 状态契约与共享领域模型功能与设计里程碑

> **对应设计规范**：`documents/agent_runtime/02_state_definition.md`
> **责任模块**：`AegisAgent/src/agent_runtime/state.py`
> **核心原则**：唯一真源契约、物理指标替代外部计费、原子消息对保全、纯模型层零业务依赖。
>
> **图例规范**：`[代码实现] [测试通过]`

---

## 一、物理度量替代不可控外部计费

- [x] [x] **纯物理指标度量体系**
  - [x] [x] 坚决剔除易受汇率与模型定价波动的不可控 `cost_usd` 等字段
  - [x] [x] 全面采用 `total_tokens`、`step_count` 与挂钟时间等客观物理指标
  - [x] [x] 指标统一作为物理预算守护的判定基准

---

## 二、消息流原子对契约保证

- [x] [x] **LangGraph Reducer 原子消息对机制**
  - [x] [x] `messages: Annotated[List[AnyMessage], add_messages]` Reducer 契约
  - [x] [x] 保证 `AIMessage(tool_calls)` 与配对的 `ToolMessage` 永远成对追加
  - [x] [x] 彻底杜绝因消息不配对导致的 LLM 端点 HTTP 400 异常

---

## 三、共享领域模型（全工程唯一真源）

- [x] [x] **阶段里程碑模型（`Milestone`）**
  - [x] [x] `id`（自增序号）、`title`、`description`（验收标准）
  - [x] [x] `MilestoneStatus` 状态机（`pending` -> `in_progress` -> `completed` / `failed`）
- [x] [x] **已证伪错误尝试（`FailedAttempt` - 负向记忆）**
  - [x] [x] `action`（曾尝试的操作与参数）
  - [x] [x] `failure_reason`（失败核心根因）
  - [x] [x] `conclusion`（沉淀的禁区结论，严禁重犯）
- [x] [x] **单步执行审计记录（`StepRecord`）**
  - [x] [x] 记录阶段（`phase`）、推理（`thought`）、工具（`tool_name` / `tool_args`）
  - [x] [x] 记录精炼观察值摘要与离线产物句柄（`raw_artifact_path`）

---

## 四、全局状态契约（`AgentState`）与微观上下文（`ExecutionContext`）

- [x] [x] **`AgentState`（Checkpoint 持久化单位）**
  - [x] [x] 分区 0：工作区与会话归属（`workspace_id`, `workspace_path`, `session_id`）
  - [x] [x] 分区 1：任务目标与里程碑规划（`task_id`, `task_goal`, `milestones`, `current_milestone_idx`）
  - [x] [x] 分区 2：活跃流水与认知记忆（`messages`, `rolling_summary`, `confirmed_facts`, `failed_attempts`）
  - [x] [x] 分区 3：产物句柄映射表（`artifacts`）
  - [x] [x] 分区 4：物理预算与防御指标（`step_count`, `total_tokens`, `consecutive_errors`, `fingerprint_history`）
  - [x] [x] 分区 5：安全与控制标记（`canary_token`, `should_terminate`, `termination_reason`）
- [x] [x] **`ExecutionContext`（单任务内存态草稿纸）**
  - [x] [x] 仅在单任务生命周期中存在，任务终结即丢弃，不进持久化 Checkpoint
