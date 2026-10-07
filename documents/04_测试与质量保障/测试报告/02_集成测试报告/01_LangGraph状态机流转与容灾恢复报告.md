# 01_LangGraph 状态机流转与容灾恢复报告

> **测试目标**：验证调度引擎的 LangGraph 循环状态图、原子消息对铁律、死循环熔断自愈及进程异常崩溃恢复。
> **测试文件**：`AegisAgent/tests/integration/test_graph_workflow.py` & `test_crash_recovery.py`
> **实测数据**：**13 Passed, 0 Failed | 耗时: 11.20s | 通过率: 100%**

---

## 1. 状态机推演实测用例矩阵

| 用例名称 | 状态流转链路 | 预期控制目标 | 实测结果 |
| :--- | :--- | :--- | :--- |
| `test_full_workflow_success_loop` | START -> Planner -> ToolRunner -> Evaluator -> END | 单轮或多轮标准任务端到端闭环交付 | PASS (顺利完成交付并生成结果) |
| `test_workflow_budget_guard_step_limit_termination` | Planner -> ToolRunner (连续循环) | 超出 10 步时触发硬件熔断退出 | PASS (精确定位超限并安全停止) |
| `test_workflow_loop_detection_and_replan` | ToolRunner -> (重复调用相同参数) | 看门狗检测到连续相同签名工具调用 | PASS (自愈拦截并强制回退重新规划) |
| `test_workflow_escalation_and_approval_closure` | ToolRunner -> HITL 挂起 -> Approve 恢复 -> END | 人工审批介入与快照恢复续跑 | PASS (无缝衔接上下文继续执行) |
| `test_workflow_escalation_rejection_and_adaptive_replan` | ToolRunner -> HITL 挂起 -> Reject 拒绝 -> Planner | 人工拒绝后 Agent 自适应调整策略重试 | PASS (接收拒绝理由并产生替代方案) |
| `test_workflow_always_allowlist_across_steps` | ToolRunner -> Always Approve -> 后续免审 | 会话级动态授权跨多步持续有效 | PASS (同类工具免二次打扰直接执行) |
| `test_sqlite_checkpoint_persistence_on_interrupt` | 任意状态 -> 突然中断 -> SQLite 查验 | 每个 Node 退出前状态原子落盘 | PASS (Checkpoints 表完整记录快照) |
| `test_sqlite_checkpoint_crash_recovery_and_resume` | 模拟模拟进程崩溃 -> 加载最后 Checkpoint 续跑 | 从中断位置而非从头开始继续推演 | PASS (状态精准复原，历史消息零丢失) |

---

## 2. 状态原子对（Atomic Tool Call / Message Pair）铁律检验

测试验证了当 `ToolRunner` 派发 3 个并发工具调用时，状态更新必须产生 **精确对应的 3 条 ToolMessage**，且 `tool_call_id` 一一配对。测试模拟注入异常时，未执行的工具调用被自动注入 `ToolResult.failure()`，杜绝了 LLM 上下文中出现“有调用无响应”导致下轮推理格式崩溃的问题。
