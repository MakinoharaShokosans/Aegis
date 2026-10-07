# 01_Agent 运行时单元测试报告

> **测试目标**：验证 `AegisAgent/src/agent_runtime/` 调度内核的确定性护栏、节点闭包、工具调用、服务组件及配置解析。  
> **执行命令**：`cd AegisAgent && uv run pytest tests/ -m "not real_llm" --tb=short -q`  
> **实测数据**：**263 Passed, 12 Deselected | 耗时: 24.88s | 通过率: 100%**

---

## 1. 模块测试数据分布矩阵

| 测试子模块 / 路径 | 用例数 | 通过数 | 核心验证能力与断言点 | 平均耗时 |
| :--- | :--- | :--- | :--- | :--- |
| **安全守卫 (guardrails/)** | 46 | 46 | • PhysicalBudget: 步数硬顶(≤10)与Token上限自动熔断<br>• LoopDetector: 重复指令指纹哈希匹配与防自旋<br>• ObservationPruner: 日志Head/Tail提取与50KB硬截断<br>• Permission: read_only / workspace_write / full 三级权限判定 | 0.08s |
| **计算节点 (nodes/)** | 38 | 38 | • PlannerNode: 意图解析、动态计划生成与直接回复分支<br>• ToolRunner: 工具并发派发与观察值聚合<br>• EvaluatorNode: 验收自愈判断与质量门禁 | 0.12s |
| **工具层 (tools/)** | 32 | 32 | • ToolRegistry: 白名单注册、不可信工具隔离<br>• FileOps: CWD根目录锁定、`../`越界逃逸拒绝 | 0.05s |
| **外部生态 (mcps/ & skills/)** | 28 | 28 | • MCPManager: 进程生命周期、stdio 隔离<br>• SkillsRegistry: 技能动态扫描、依赖解析与冲突排查 | 0.09s |
| **独立微服务适配 (services/)** | 30 | 30 | • BashAudit: 高危Shell正则黑名单审计<br>• MemoryPool: 2GB 内存配额与并发排队槽位管理<br>• WebDedup: MD5 内容指纹去重与离线落盘 | 0.07s |
| **API 接口契约 (api/)** | 42 | 42 | • Schemas: 强类型 Pydantic 校验与非法入参 422<br>• TaskRegistry: 内存任务注册表并发一致性<br>• Files/RAG: 代理路由转发生效 | 0.15s |
| **调度与持久化 (workflow/ & edges/ & memory/)** | 47 | 47 | • Subagents: Research / CodeSearch Runner 隔离执行<br>• SQLiteMemoryStore: WAL 模式多轮对话写入与读取<br>• Config: 配置项强校验与环境变量热覆盖 | 0.18s |

---

## 2. 典型关键用例执行实测佐证

### 用例 1: 物理预算熔断机制 (`test_physical_budget.py`)
- **测试场景**：模拟失控任务在第 11 步仍未终止。
- **实测结果**：`BudgetLedger.record_step()` 在达到预设值 10 步时，精确抛出 `BudgetExceededError`，并强行将状态置为 `ERROR_TERMINATED`，耗时 1.2ms。

### 用例 2: 沙箱并发内存池硬配额 (`test_bash_memory_pool.py`)
- **测试场景**：单进程申请 2.5GB 内存（超出 2GB 硬顶）或 10 个进程并发申请。
- **实测结果**：超额申请被 `setrlimit` 静态拦截；并发任务自动进入 Queue 并依据释放信号 FIFO 唤醒，无内存踩踏。

### 用例 3: 观察值截断保真 (`test_observation_pruner.py`)
- **测试场景**：向 Agent 注入 500KB 超长编译报错日志。
- **实测结果**：输出被精确削减至保留头部 2000 字符与尾部 2000 字符，保留关键异常栈，其余内容无损落盘至 `artifacts/` 目录并返回句柄，上下文 Token 消耗骤降 98.4%。
