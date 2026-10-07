# LangGraph 节点状态机集成测试路线图 (StateGraph Integration Test)

> **定位**：`AegisAgent` 基于 LangGraph 状态图的组件协同、节点流转、中断挂起恢复与持久化落盘集成测试路线。
> **铁律**：严禁裸调用节点函数规避挂起语义，必须在真实编译的 StateGraph 上通过 `graph.ainvoke()` 驱动；原子对 `(AIMessage.tool_calls, ToolMessage)` 必须 100% 闭环。

---

## 1. 现状盘点：状态图集成覆盖矩阵

| 目标集成链路 | 对应测试文件 | 状态 | 核心验证重点 |
| :--- | :--- | :---: | :--- |
| `nodes/tool_runner.py` | `tests/nodes/test_tool_runner.py` | `[x] [x]` | 真实 `interrupt()` 触发、`Command(resume=...)` 恢复、`once`/`always`/`reject` 分支 |
| **原子对铁律回归** | `tests/nodes/test_tool_runner.py` | `[x] [x]` | 无论批准、拒绝、工具抛错还是死循环拦截，`tool_call_id` 与 `ToolMessage` 绝对一对一配对 |
| `workflow.py` 编排闭环 | `tests/integration/test_graph_workflow.py` | `[x] [x]` | Planner -> Executor -> ToolRunner -> Evaluator 全状态机自主收敛闭环 |
| 跨步与持久化续跑 | `tests/integration/test_crash_recovery.py` | `[x] [x]` | `SqliteCheckpointStore` 真实落盘、WAL 模式、进程崩溃重启断点续跑 |
| 并发与状态竞态 | `tests/api/test_task_registry.py` | `[x] [x]` | 真实 `asyncio.gather` 并发提交与审批、互斥锁状态防脏写 |
| 专用代码检索子智能体 | `tests/workflow/test_code_search_runner.py` | `[x] [x]` | 位置白名单过滤、3 轮自适应改词、早停与确定性拒答 |
| 外部研究子智能体 | `tests/workflow/test_research_runner.py` | `[x] [x]` | 有界异步循环（步数上限）、URL 白名单、产物信封隔离 |

---

## 2. 细分测试用例规范

### 2.1 ToolRunner 节点中断与恢复分支 (`tests/nodes/test_tool_runner.py`)
- **场景 A（只读放行）**：只读工具调用直接派发，图流转无中断挂起；
- **场景 B（越级挂起 -> 批准本次 `once`）**：
  - 触发 `interrupt()` 挂起，返回包含 `approval_id` 的 payload；
  - 传入 `Command(resume={"approved": True, "scope": "once"})`，派发底层工具并回填正常 `ToolMessage`；
- **场景 C（越级挂起 -> 拒绝执行 `reject`）**：
  - 传入 `Command(resume={"approved": False, "reason": "禁止该操作"})`；
  - 生成带 `[APPROVAL REJECTED]` 前缀的观察值回填模型，底层工具未派发；
- **场景 D（越级挂起 -> 会话免审 `always`）**：
  - 传入 `Command(resume={"approved": True, "scope": "always"})`；
  - 将动作签名录入 `approval_allowlist`，后续同一任务再次触发同签名动作不再挂起；
- **场景 E（原子对严格对称铁律）**：
  - 单次调用含 3 个工具（1个成功，1个拒绝，1个异常），断言返回消息列表严格包含 3 条对应的 `ToolMessage`，无单向脱漏。

### 2.2 工作流闭环与自适应重规划 (`tests/integration/test_graph_workflow.py`)
- **审批拒绝后模型自适应重规划**：
  - 模拟模型试图执行提权命令被拒绝；
  - 验证下一轮 `planner` 接收到拒绝观察值后，自适应生成基于只读工具的替代方案，最终收敛至正常完成。

### 2.3 SQLite Checkpoint 持久化落盘与容灾恢复 (`tests/integration/test_crash_recovery.py`)
- 使用生产级 `SqliteCheckpointStore` 挂载临时数据库；
- 任务执行至审批挂起态时销毁当前 runtime 实例，模拟宿主进程退出；
- 新建 runtime 实例调用 `aget_state()`，验证成功还原历史全部消息与挂起快照，并能通过 `resume` 续跑至结束。

---

## 3. 验收标准与执行

- 必须通过编译后的真实 StateGraph 驱动；
- SQLite 测试后自动释放临时数据库文件；
- 执行命令：
  ```bash
  cd /home/Skualeilu/Projects/Aegis/AegisAgent
  uv run pytest tests/nodes/test_tool_runner.py tests/integration/test_graph_workflow.py tests/integration/test_crash_recovery.py -v
  ```
