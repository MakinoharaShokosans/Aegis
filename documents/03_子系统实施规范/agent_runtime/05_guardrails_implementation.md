# 护栏机制与弹性熔断实现规范

> **责任领域**：`AegisAgent/src/agent_runtime/guardrails/` & `llm/`  
> **核心原则**：确定性包围非确定性，物理硬熔断，双轨死循环防御，多端点弹性降级。

---

## 1. 双轨死循环防御机制（Dual-Track Loop Breaker）

在长周期自主排错中，模型极易陷入两种不同形态的死胡同。必须通过双轨机制分别防御：

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        双轨死循环防御拓扑                              │
│                                                                        │
│  [调用入口] ──► 提取工具名与入参                                       │
│                    │                                                   │
│                    ├──► [规则 A: 相同参数哈希比对]                     │
│                    │    计算 MD5(tool + args) ➔ 连续 3 次完全相同?     │
│                    │    └── 是 ➔ 判定为无脑机械重复，直接拦截          │
│                    │                                                   │
│                    └──► [规则 B: 连续错误计数器 consecutive_errors]   │
│                         每次工具返回 exit_code != 0 ➔ 计数器 +1         │
│                         连续 3 次报错 (即便微调参数重试) ➔ 触发重规划  │
└────────────────────────────────────────────────────────────────────────┘
```

### 1.1 规则 A：参数指纹哈希（Fingerprint Hash）
* **原理**：将 `tool_name` 与排好序的 `args` 序列化为 JSON 字符串，计算 MD5 哈希：
  ```python
  import hashlib
  import json

  def compute_fingerprint(tool_name: str, args: dict) -> str:
      payload = json.dumps({"tool": tool_name, "args": args}, sort_keys=True, ensure_ascii=False)
      return hashlib.md5(payload.encode("utf-8")).hexdigest()
  ```
* **触发阈值**：`identical_fingerprint_limit = 3`（来自 `config.toml`）。若最近 3 次哈希完全一致，立即阻断并警告模型切换工具。

### 1.2 规则 B：连续错误状态计数器（Consecutive Error Counter）
* **痛点**：传统哈希容易被模型“微调参数”（例如编译报错后每次换一个编译参数 `-O1`、`-O2`、`-g`）绕过，造成在同一类问题上打转 10 步。
* **判定逻辑**：
  * 只要底层工具执行状态为 `FAILED` 或返回非零退出码，`state["consecutive_errors"] += 1`；
  * 一旦工具成功执行（`exit_code == 0`），立即清零；
  * **熔断跃迁**：当 `consecutive_errors >= 3` 时，条件边强制中断当前的微观 Executor 循环，直接回退流转至 `planner`，强制启动宏观反思与动态重规划。

---

## 2. 确定性物理预算守卫（Physical Budget Guard）

坚决不依赖外部不可靠的实时计费接口，完全基于本地可严格度量的物理指标实行确定性硬熔断：

```python
import time
from typing import Tuple, Optional

class PhysicalBudgetGuard:
    def __init__(self, max_steps: int, max_total_tokens: int, max_wall_time_sec: float):
        self.max_steps = max_steps
        self.max_total_tokens = max_total_tokens
        self.max_wall_time_sec = max_wall_time_sec
        self.start_time = time.time()

    def check(self, state: dict) -> Tuple[bool, Optional[str]]:
        # 1. 步数硬熔断
        if state.get("step_count", 0) >= self.max_steps:
            return True, f"执行总步数达上限 ({self.max_steps} 步)，触发安全熔断"

        # 2. 累计 Token 物理硬熔断
        if state.get("total_tokens", 0) >= self.max_total_tokens:
            return True, f"累计消耗 Token 达上限 ({self.max_total_tokens})，触发安全熔断"

        # 3. 物理挂钟时间硬熔断
        elapsed = time.time() - self.start_time
        if elapsed >= self.max_wall_time_sec:
            return True, f"单任务物理运行时间耗尽 ({elapsed:.1f}s >= {self.max_wall_time_sec}s)"

        return False, None
```

### 2.1 子智能体消耗必须计入同一本账

`PhysicalBudgetGuard` 读的是 `state["total_tokens"]`，而**子智能体（研究 / 动态委派）
的 Token 消耗由它自己的循环产生，主图节点看不见**。若不显式补偿，父任务的物理熔断
可被"委托"绕过：单轮并发派发用的是无上限的并发聚合，子任务可以烧掉远超父任务上限的额度，
而父任务计量增量为 0。

因此引入 `guardrails/budget_ledger.py` 的 `BudgetLedger`（父级唯一记账方）：

| 纪律 | 原因 |
|:---|:---|
| **先预留、后执行、再结算**（而非事后累加） | 事后累加在并发下不成立——父任务在子任务返回前不知道它花了多少，N 个并发子任务各自按上限开销，第一次对账就已超支 |
| 准入函数**不含 `await`** | 单线程事件循环中"无 `await`"即原子；否则并发派发会读到同一余额并各自全额预留 |
| 账本由父级持有，子级**只能报告不能记账** | 子级自述的用量可被注入内容伪造；记账数据必须是框架直接给出的运行时计量 |
| 结算覆盖**全部**退出路径（含超时被取消） | `asyncio.wait_for` 会取消子任务所在协程，结算若写在子级内部会被跳过 |
| 消耗以**增量**冲销进 `total_tokens`，且在**审批闸门之后** | 账本随任务重建、`total_tokens` 由 Checkpoint 持久化；`interrupt()` 会丢弃本节点返回值，闸门之前记账会永久丢账 |

**不变量**：任意时刻，`父任务已用 + 子智能体已结算 + 在途预留 ≤ max_total_tokens`。

> 详见 `13_subagent_delegation.md` §4。修复前的状态是：`delegate_research` 的消耗
> 随工具结果返回后**无人读取**，对父任务熔断完全不可见。

---

## 3. 双模型分层多端点故障转移（Dual-Tier Fallback Chain）

针对云端供应商可能遭遇的 HTTP 429 限流、5xx 内部错误或网络闪断，`AegisAgent` 配置了两级模型链，并依托 `tenacity` 实施自动降级转移：

```text
[Reasoning 链: Planner 规划与报告]
Primary: DeepSeek-R1 (api.deepseek.com) ──(失败退避重试)──► Backup: SiliconFlow-R1 ──(均不可用)──► 抛出告警

[Fast 链: Executor 动作与记忆压缩]
Primary: DeepSeek-V3 (api.deepseek.com) ──► Backup 1: OpenAI-4o-mini ──► Backup 2: Local Ollama (Qwen2.5)
```

### 3.1 指数退避与跨端点重试逻辑
1. **端点内重试**：当单个端点遭遇网络抖动或 429 时，执行 3 次指数退避（`backoff_factor = 2.0`）；
2. **端点间切换**：若重试 3 次后该端点仍不可用，标记该端点进入冷却期，自动将请求透明切流至 `endpoints[1]`；
3. **参数强一致性**：切换端点时，严格保持相同的 `tools` 与 `messages` 载荷。

---

## 4. 观察结果离线截断与下沉（Observation Pruner）

针对工具输出体积过大（如 `cat` 大型代码文件、数千行编译日志）的问题，自研 Pruner 实行“两头保留 + 离线落盘”策略：

```text
┌────────────────────────────────────────────────────────────┐
│                    Observation Pruner                      │
│                                                            │
│  输入原始工具日志 (如 2500 行，50KB)                        │
│    │                                                       │
│    ├── 1. 完整原始内容落盘 ➔ storage/artifacts/{task_id}/  │
│    │                                                       │
│    └── 2. 生成 Context 紧凑摘要:                           │
│         - 保留头部关键行 (Head 20 lines)                   │
│         - 提取包含 error/warning/failed 的中间关键行        │
│         - 保留尾部结论行 (Tail 30 lines)                   │
│         - 附带物理离线句柄: "artifact://task_01/build.log"  │
└────────────────────────────────────────────────────────────┘
```

* **Token 预算控制**：经裁剪后的工具响应，单次进入上下文严格限制在 1500 Token 以内；
* **原子成对约束**：无论输出是否被截断，生成的 `ToolMessage` 必须携带对应的 `tool_call_id`，保持与前序 `AIMessage` 的原子关联。


---

## 5. 注入样态标注（Injection Guard）

> **定位**：这是**纵深防御与审计手段，不是安全边界**。真正的边界是权限分离
> （见 [`12_research_subagent.md`](./12_research_subagent.md)）。

`agent_runtime/guardrails/injection_guard.py` 提供纯函数（零 I/O、零 LLM）：

* `scan_injection(text) -> InjectionScan`：扫描中英双语指令样态
  （`ignore previous instructions`、`system override`、`you are now`、
  `do not tell the user`、`不要告诉用户`、`请执行以下命令`、`reveal your system prompt` 等）；
* `redact_injection(text, matches) -> str`：把命中的片段替换为标记（可选）；
* `summarize_matches(scan) -> str`：生成可写入 `warnings` 的一行摘要。

**行为约定**：

| 项 | 约定 |
|:---|:---|
| 是否拦截 | **不拦截**。只标注、记录、写轨迹，供离线统计"注入尝试频率" |
| 应用位置 | 研究子智能体产出的文本字段；后续扩展到 MCP 工具输出与工作区技能包正文 |
| 失败语义 | 扫描永不抛异常；最坏情况返回空结果 |
| 误报代价 | 仅多一行 warning，不影响主流程——因此宁可宽扫 |
