# AegisAgent 微观执行上下文与记忆生命周期功能与设计里程碑

> **对应设计规范**：`documents/agent_runtime/07_execution_context_management.md` & `06_memory_and_context_management.md`  
> **责任模块**：`AegisAgent/src/agent_runtime/execution_context.py` & `memory/`  
> **核心原则**：四阶段生命周期管理、会话流水低高水位压缩、全量链路轨迹留痕、交付主动脱敏。

---

## 一、微观执行上下文四阶段生命周期

- [x] **Spawn 阶段（任务初始状态构造）**
  - [x] `build_initial_state`：继承会话层认知记忆（摘要、事实、踩坑记录），实现新任务不踩旧坑
  - [x] 物理指标（步数、Token、错误数）归零重置
  - [x] 自动绑定会话级 Canary Token（保全 KV 缓存）
- [x] **Evolution 阶段（微观执行与草稿留痕）**
  - [x] 维持单任务内存态 `step_history`，记录单步推理与工具交互
- [x] **Distillation 阶段（因果提炼与沉淀）**
  - [x] 从终态中提炼新增的踩坑记录（`collect_failed_attempts`）与里程碑清单（`collect_milestones`）
- [x] **Teardown 阶段（链路落盘与收敛回写）**
  - [x] `finalize`：全量步骤与链路记录落盘持久化
  - [x] 将本轮结论回写会话流水库，内部执行细节绝不污染下一轮对话

---

## 二、会话记忆存储与水位线动态压缩 (`memory/`)

- [x] **SQLite 跨会话持久化存储引擎 (`memory/sqlite_store.py`)**
  - [x] 数据库模式：`workspaces`、`sessions`、`turns`、`workspace_memory`
  - [x] 工作区物理级联删除支持
  - [x] 多工作区与多会话严格隔离检索
- [x] **双水位线动态压缩器 (`memory/compactor.py`)**
  - [x] 维护低水位线（`watermark_turns`）与高水位线（`max_turns`）
  - [x] 超出高水位线时触发模型压缩，将历史轮次蒸馏为结构化摘要与事实列表
  - [x] 压缩时保障原子消息对不割裂
  - [x] LLM 异常时提供确定性启发式截断优雅降级

---

## 三、轨迹留痕与交付物脱敏治理

- [x] **全量执行轨迹记录器 (`observability/trajectory.py`)**
  - [x] 记录节点（Node）、工具（Tool）、护栏（Guard）与终态（Final）执行快照
  - [x] 异步持久化至 `storage/traces/{task_id}.jsonl`
- [x] **交付物抽取与主动脱敏（`extract_delivery`）**
  - [x] 从终态消息流中抽取最后一条面向用户的交付文本
  - [x] 自动应用 `sanitize_canary` 剔除金丝雀探针，确保敏感 Token 不外溢至用户端或记忆库
