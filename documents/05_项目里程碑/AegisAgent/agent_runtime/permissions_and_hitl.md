# AegisAgent 三级权限分级与人机协同审批（HITL）功能与设计里程碑

> **对应设计规范**：`documents/技术选型/bash_shell.md` §2.3、`documents/agent_runtime/04_routing_and_control_flow.md` §4.5、`documents/agent_runtime/11_http_api.md` §4.4  
> **责任模块**：`AegisAgent/src/agent_runtime/guardrails/permission.py`, `nodes/tool_runner.py`, `edges/after_tool_runner.py`, `api/routes/tasks.py`, `api/task_registry.py`  
> **核心原则**：只读/写入/全权三级偏序划分、确定性纯函数判定、越级挂起审批（HITL）、会话级永久放行白名单、原子对铁律保障。  
> 
> **图例规范**：`[代码实现] [测试通过]`

---

## 一、三级权限分级与确定性判定引擎 (`guardrails/permission.py`)

- [x] [x] **三级权限偏序模型与级别归一化**
  - [x] [x] `read_only` (0) < `workspace_write` (1) < `full_permissions` (2) 偏序矩阵
  - [x] [x] `normalize_level` 鲁棒归一化与非法/空值安全回落
- [x] [x] **多层级工具所需权限判定 (`required_level_for`)**
  - [x] [x] 显式工具名单优先：只读名单、工作区写入名单、特权名单
  - [x] [x] Bash 命令正则三分类：网络外联（`network_egress`）、全局环境变更（`global_env`）、本地构建写入（`workspace_write`）、只读巡检（`read_only`）
  - [x] [x] 未知工具（如第三方 MCP）按 `unknown_tool_level` 默认最高权限保守拦截
- [x] [x] **权限判定与动作签名**
  - [x] [x] `check_permission` 偏序放行与超限拒绝原因生成
  - [x] [x] `action_signature` 稳定 MD5 参数排序哈希签名（供会话白名单免审比对）

---

## 二、节点权限闸门与状态机挂起恢复 (`nodes/tool_runner.py` & `edges/after_tool_runner.py`)

- [x] [x] **独立 `tool_runner` 权限闸门与派发节点**
  - [x] [x] 逐项判定工具调用越级，无越级时直接并发派发
  - [x] [x] 越级且未在白名单时调用 LangGraph `interrupt(payload)` 挂起图执行
  - [x] [x] 接收 `Command(resume=...)` 恢复执行，支持单次放行（`once`）与会话白名单（`always`）
  - [x] [x] 审批拒绝时合成带详细理由的 `ToolMessage` 观察值，驱动模型自愈重规划
- [x] [x] **原子对铁律与指纹死循环防御**
  - [x] [x] 无论批准/拒绝/死循环拦截/执行失败，严格保证 `tool_call_id` 与 `ToolMessage` 1:1 一一配对
  - [x] [x] 指纹死循环命中时拦截本次派发并合成提示信息
- [x] [x] **`route_after_tool_runner` 路由边**
  - [x] [x] 硬熔断（`should_terminate=True`）➔ 直接进入 `END`
  - [x] [x] 正常执行或被拒绝后 ➔ 回流 `planner` 推进或重规划

---

## 三、API 审批端点与任务注册表状态管理 (`api/`)

- [x] [x] **HTTP 审批 RESTful 交互端点 (`routes/tasks.py`)**
  - [x] [x] `POST /api/v1/tasks/{id}/approve`：批准待审核越级操作并恢复后台执行
  - [x] [x] `POST /api/v1/tasks/{id}/reject`：拒绝越级操作并注入拒绝原因驱动重规划
  - [x] [x] 错误语义与状态校验：未知任务 `404`、非待审批状态/审批 ID 不匹配 `409`
- [x] [x] **任务注册表状态机与会话白名单存活 (`task_registry.py`)**
  - [x] [x] `TaskStatus` 新增 `waiting_for_approval` 挂起状态
  - [x] [x] `approval_allowlist` 绑定会话生命周期，跨 `resume` 存活
  - [x] [x] 并发安全锁与单会话任务互斥保护
- [x] [x] **Server-Sent Events (SSE) 审批事件流**
  - [x] [x] 实时推送 `task.waiting_for_approval` 事件及完整审批卡片 payload
  - [x] [x] 实时推送 `task.approved` 与 `task.rejected` 决策审计事件

---

## 四、全链路自动化集成测试闭环 (`tests/integration/`)

- [x] [x] **API 全生命周期集成测试 (`test_api_lifecycle.py`)**
  - [x] [x] 越级 ➔ `waiting_for_approval` ➔ `/approve` ➔ 恢复执行成功
  - [x] [x] 越级 ➔ `waiting_for_approval` ➔ `/reject` ➔ 收到拒绝原因并完成
  - [x] [x] SSE 实时推送审批事件流断言
- [x] [x] **状态机端到端工作流闭环 (`test_graph_workflow.py`)**
  - [x] [x] 完整规划-执行-挂起-批准-验收全链路闭环
  - [x] [x] 审批拒绝后规划器自适应调整方案（本地补丁替代远端推送）闭环
  - [x] [x] `always` 永久放行白名单跨多步调用免审生效验证

---

## 五、安全对抗评测与已知架构约束 (Security Adversarial & Architectural Constraints)

- [x] [x] **正则黑名单分类器的能力边界与已知局限 (`test_permission_adversarial.py` & `test_vetting_adversarial.py`)**
  - **有效防御面**：命令连接符（`&&`, `;`, `||`, `|`）、标准子命令替换（`$(cmd)`, `` `cmd` ``）、大小写混淆（`CURL`, `Git Push`）、空白字符与换行混淆、标准中英文 Prompt 注入关键词硬拒绝。
  - **已知局限**：
    1. **Bash 变量拼接间接执行**：无法静态推断变量字符串拼接（如 `a=cu; b=rl; "$a$b"`），判定回退到只读。
    2. **Base64 编码管道**：无法解码管道传递的 Base64 内容（`echo ... | base64 -d | bash`），判定回退到只读。
    3. **MCP 描述 Unicode 同形字混淆（Homoglyphs）**：使用西里尔字母（如 `е` U+0435）替换拉丁字母 `e` 的伪造指令（如 `systеm ovеrridе`）可绕过纯 ASCII 注入正则并被放行注册。
  - **架构定位声明**：上述基于表面字符串的黑名单正则定位为**轻量级人机协同与可疑内容标注层**，并非绝对安全边界；系统的底层硬安全由非特权容器沙箱、只读文件系统挂载与权限偏序隔离共同保障。
- [x] [x] **批量越级合谋防御与原子对治理 (`test_tool_runner.py`)**
  - 单批混杂越级与合规工具时，中断载荷聚合主动作与关联动作；
  - 拒绝时精准剥离越级项并合成拒绝观察值，合规项正常并发派发，100% 保持 `tool_call_id` 1:1 配对。
- [x] [x] **SQLite 检查点落盘与跨进程崩溃恢复 (`test_crash_recovery.py`)**
  - 使用生产级 `SqliteCheckpointStore` (`AsyncSqliteSaver`) 真实将中断快照持久化到 SQLite 数据库文件；
  - 模拟进程重启后在全新 Runtime 实例上无缝读取快照并通过 `/resume` 恢复执行；
  - 固化 `_session_approvals` 仅驻留内存、进程重启后安全重置的无状态设计预期。
- [x] [x] **并发竞态与原子锁保护 (`test_task_registry.py`)**
  - `submit_decision` 采用异步锁保护状态检查与流转，杜绝 `/approve` 与 `/reject` 并发竞争导致的双协程重跑。
- [x] [x] **配置健壮性与 OpenAPI 契约回归 (`test_config_robustness.py`)**
  - 非法正则配置安全隔离跳过，不影响合法正则；
  - `/tasks/{id}/approve`、`/reject`、`/resume` 端点与 `waiting_for_approval` 状态模型 100% 符合 OpenAPI 契约。

