# 微观执行上下文与草稿纸治理规范 (ExecutionContext)

> **责任领域**：`AegisAgent/src/agent_runtime/state.py`（纯契约）与 `AegisAgent/src/agent_runtime/execution_context.py`（运行期行为）
> **核心原则**：任务自闭环、草稿纸隔离、观察值物理下沉、终结即归档、零污染外溢。
>
> **契约边界（重要）**：`ExecutionContext` **不是第二套持久化契约**。LangGraph 的 Checkpoint 单位始终是 `state.py` 定义的 `AgentState`；`ExecutionContext` 是单任务在内存中的运行时视图，任务终结时擦除，仅把结论回写 `AgentState`，全量链路落盘至 `storage/traces/{task_id}.jsonl`。两者的字段同名同义，`step_history` 属内存态审计视图、不进入 Checkpoint。详见 [`03_node_specification.md`](./03_node_specification.md) §3。

---

## 1. 架构定位：工作区、宏观 Session 与 微观 Execution 的界限

在 Aegis 系统中，严格确立三级上下文的职责边界：
* **顶级 `Workspace`（工作区工程视界）**：面向具体代码工程仓库，绑定物理根目录 `root_path` 与全局跨会话长期记忆；
* **宏观 `SessionContext`（会话交互主线）**：隶属于某工作区（1:N），纳管该任务线的已压缩情境记忆与低水位活跃人机对话流水；
* **微观 `ExecutionContext`（执行上下文 / 智能体草稿纸）**：面向 Agent 内部单次任务的 20~30 步多工具试错循环。它是任务运行时的**临时工作台（Scratchpad）**，其命令执行必须将所属工作区的 `root_path` 作为默认工作目录（`cwd`）。

```text
┌────────────────────────────────────────────────────────────────────────┐
│  Workspace (项目根目录: /home/user/project_a, 共享规范与架构定论)      │
│    │                                                                   │
│    ▼ (1 : N 级联)                                                      │
│  SessionContext (宏观人机对话主线 - session_id)                         │
│  User: "排查网络库连接泄露并修复"                                       │
│    │                                                                   │
│    ▼ [1. Spawn 诞生]                                                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ ExecutionContext (微观单任务执行草稿纸 - task_id)                 │  │
│  │  - 环境: cwd = Workspace.root_path                               │  │
│  │  - Step 1: 调用 bash 运行 valgrind -> 发现 leak at connection.cpp │  │
│  │  - Step 2: 调 tools 读代码 -> 截断下沉到 storage/artifacts/   │  │
│  │  - Step 3: 修改代码并 make test -> 编译报错 (consecutive_errors=1)│  │
│  │  - Step 4: 修复头文件引用 -> 编译通过 (consecutive_errors=0)      │  │
│  │  - Step 5: 验证通过，生成 patch.diff                             │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│    │                                                                   │
│    ▼ [2. Distill 提炼] & [3. Teardown 销毁]                            │
│  返回精炼结论 + last_action_target (修改了哪些文件与符号)              │
│  内部 5 步草稿全量归档 storage/traces/{task_id}.jsonl                  │
│    │                                                                   │
│  Agent: "已修复连接泄露，核心原因是...补丁已生成至 patch.diff"          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 执行上下文的四阶段生命周期（Lifecycle）

### 2.1 阶段一：诞生（Spawn & Ingestion）
* **触发点**：用户在某工作区的特定会话主线提出新指令，`SessionManager` 派发执行任务；
* **环境与上下文继承**：
  - 继承工作区环境：绑定 `workspace_id` 与 `workspace_path`，确立工具层执行基准目录；
  - 继承终极目标：`task_goal`；
  - 继承工作区全局事实与规范：`confirmed_facts`（已知环境、架构信息、编码规范）；
  - 继承避坑禁区：`failed_attempts`（已证伪的方案与全局黑名单）；
* **初始化瞬态环境**：
  - 分配唯一的 `task_id`（UUID）；
  - 重置物理计数器：`step_count = 0`，`consecutive_errors = 0`，`fingerprint_history = []`；
  - 建立该任务独立的产物目录：`storage/artifacts/{task_id}/`。

### 2.2 阶段二：演进与草稿流转（Evolution & Scratchpad Rolling）
* 在 LangGraph 的有向循环图中流转（Planner $\leftrightarrow$ Executor）；
* **每一步（Step）记录因果因果三元组**：
  `Step = (thought: 推理内容, action: 工具调用, observation: 截断后的观察值)`；
* **草稿纸动态修剪（Scratchpad Trimming）**：
  - 当单次任务执行超过 15 步时，中间尝试过的早期非关键排错过程进行动态语义折叠；
  - 必须维持**原子消息对（Atomic Pair）约束**：`AIMessage(tool_calls)` 与 `ToolMessage` 必须成对维护与成对淘汰，杜绝孤立消息导致 API 400 校验错误。

### 2.3 阶段三：提炼与产物归纳（Distillation & Provenance）
* **任务结束触发**（任务成功完成，或触发熔断）；
* **提炼三大核心要素**：
  1. **最终工作成果与交付总结**；
  2. **关键实体与产物句柄（`last_action_target`）**：
     ```json
     {
       "modified_files": ["src/network/connection_pool.cpp"],
       "symbols": ["ConnectionPool::release"],
       "artifacts": ["storage/artifacts/run_01/leak_fix.patch"]
     }
     ```
  3. **新踩坑反思（若有失败）**：生成新的 `FailedAttempt` 回传给 `SessionContext`。

### 2.4 阶段四：销毁与因果下沉（Teardown & Eviction）
* **内存彻底擦除**：执行上下文中的大量瞬态消息（几十轮详细交互、工具原始 JSON）从内存中销毁；
* **因果日志下沉落盘**：将未裁剪的完整执行链路写入 `storage/traces/{task_id}.jsonl`，用于离线评测（Agent Bench）与 Debug；
* **零污染原则**：执行上下文的内部细节**绝对不直接进入下一次人机对话**。

---

## 3. 观察值物理截断与下沉机制（Observation Offloading）

工具执行可能产生巨大体积输出（如 `cat` 大型代码、数百行编译报错、测试用例 Dump）。如果全量灌入执行上下文，单步即可撑爆 Token 预算。

### 3.1 拦截与落盘策略
当工具单次输出体积超过阈值（如 **1500 Token** 或 **4000 字符**）时，Pruner 立即介入：
1. **全量无损落盘**：将原始日志保存至物理文件：
   `storage/artifacts/{task_id}/obs_step_{step_id}_{tool_name}.log`
2. **生成紧凑认知视界（Compact View）**：
   - 保留头部关键行（Head 20 行，获取命令启动与入参确认）；
   - 提取包含 `error`、`warning`、`failed`、`exception` 的关键报错行（最多 30 行）；
   - 保留尾部结论行（Tail 30 行，获取退出码与最终状态）；
   - 附带物理文件引用句柄：
     ```text
     [输出过长，已截断并落盘。完整日志参见: artifact://run_01/obs_step_3_bash.log]
     ```

---

## 4. 瞬态护栏状态机流转

执行上下文实时维护三个确定性状态变量，驱动条件边（Conditional Edges）的熔断：

### 4.1 连续错误计数器（`consecutive_errors`）
```text
工具执行完毕
    │
    ├── exit_code == 0 且无网络异常 ──► consecutive_errors = 0 (立即清零)
    │
    └── exit_code != 0 或捕获异常 ──► consecutive_errors += 1
                                           │
                                           ├── < 3 ──► 继续当前微观修复
                                           └── >= 3 ──► 触发熔断，强行回退至 Planner 重新规划
```

### 4.2 参数指纹队列（`fingerprint_history`）
* 保留最近 5 次工具调用的 `MD5(tool_name + sorted_args)`；
* 若连续 3 次哈希完全一致，判定模型陷入死锁循环，条件边直接阻断并注入告警。

### 4.3 物理预算累加（`step_count` & `total_tokens`）
* 每完成一次节点跃迁，`step_count += 1`；
* 累加 LLM 消耗的真实物理 Token；
* 达到 `max_steps` 或 `max_total_tokens` 时置位 `should_terminate = True`。

---

## 5. 强类型数据契约（ExecutionContext Schema）

在 `AegisAgent/src/agent_runtime/state.py` 中的完整定义：

```python
from typing import Annotated, List, Dict, Optional, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class StepRecord(BaseModel):
    """单步执行因果轨迹记录"""
    step_id: int
    phase: Literal["planning", "executing", "reflecting"]
    thought: str
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    observation_summary: Optional[str] = None
    raw_artifact_path: Optional[str] = None  # 若输出过长，记录物理落盘路径

class ExecutionContext(TypedDict):
    """
    单任务微观执行上下文 (AgentState)
    """
    # 1. 任务身份与目标 (从 Session 继承)
    task_id: str
    task_goal: str
    confirmed_facts: List[str]
    failed_attempts: List[dict]

    # 2. 运行时草稿纸 (Scratchpad)
    messages: Annotated[List[AnyMessage], add_messages]
    step_history: List[StepRecord]

    # 3. 产物与文件句柄
    artifacts: Dict[str, str]  # 逻辑名 -> 物理磁盘路径
    last_action_target: Dict[str, List[str]] # 交付前沉淀的核心修改对象

    # 4. 瞬态防御计数器 (任务结束即销毁)
    step_count: int
    total_tokens: int
    consecutive_errors: int
    fingerprint_history: List[str]

    # 5. 控制流标记
    should_terminate: bool
    termination_reason: str
```
