# AegisAgent 确定性护栏与防注入体系功能与设计里程碑

> **对应设计规范**：`documents/agent_runtime/05_guardrails_implementation.md`  
> **核心原则**：确定性包围非确定性、双轨死循环防御、物理指标硬熔断、零开销缓存保全、全链路外泄拦截。  
> 
> **图例规范**：`[代码实现] [测试通过]`

---

## 一、双轨死循环防御机制 (`guardrails/loop_detector.py`)

- [x] [x] **工具调用指纹滑动窗口（Fingerprint History）**
  - [x] [x] 对工具名与参数字典计算 SHA-256 结构化内容指纹
  - [x] [x] 维持固定长度（如 5 步）滑动窗口队列
  - [x] [x] 检测相同指纹连续达到上限阈值（如 3 次）时主动拦截派发
- [x] [x] **连续错误累加与瞬态熔断**
  - [x] [x] 成功调用重置计数，失败调用连续递增
  - [x] [x] 达到连续错误上限时触发强制重规划信号注入
- [x] [x] **原子消息对完整性保全**
  - [x] [x] 指纹死循环拦截时自动补齐 `ToolMessage` 占位，防止 LLM 端点因缺少 tool_call_id 返回 400

---

## 二、物理预算硬熔断护栏 (`guardrails/physical_budget.py`)

- [x] [x] **全生命周期物理指标监控**
  - [x] [x] 累计执行步数（`step_count`）硬熔断
  - [x] [x] 累计消耗 Token（`total_tokens`）硬熔断
  - [x] [x] 任务运行挂钟时间（`wall_time`）硬超时熔断
- [x] [x] **分级预警与熔断拦截**
  - [x] [x] 达到预警水位（如 80%）时注入预算预警提示
  - [x] [x] 达到 100% 极限时直接置位 `should_terminate=True` 强制终止任务

---

## 三、观察值治理与离线卸载 (`guardrails/observation_pruner.py`)

- [x] [x] **语法感知紧凑摘要提炼**
  - [x] [x] JSON 超长输出：提取 `json_outline` 保留键名拓扑并截断大标量
  - [x] [x] 纯文本超长输出：Head / Tail 前后截取并保留关键报错行（ERROR_KEYWORDS）
- [x] [x] **全量原始观察值离线落盘（`artifact://`）**
  - [x] [x] 超出 Token 阈值的输出流式离线写入 `storage/artifacts/{task_id}/`
  - [x] [x] 上下文仅携带精炼摘要与磁盘产物句柄，彻底消除上下文爆炸

---

## 四、金丝雀 Token（Canary Token）与泄露熔断 (`guardrails/canary.py`)

- [x] [x] **会话级确定性 HMAC 派生（Session-scoped Canary）**
  - [x] [x] 基于 `session_id` 与密钥盐通过 HMAC-SHA256 派生会话专属 Canary Token
  - [x] [x] 同会话内多轮提问保持 Token 恒定，**100% 保全 Prompt KV Cache 命中**
  - [x] [x] 跨会话自动切换独立 Token，实现强密码学隔离
- [x] [x] **全链路泄露扫描与瞬态熔断**
  - [x] [x] `Executor` 节点：工具派发前递归扫描回复内容及所有 `tool_calls` 入参，阻断外带窃取
  - [x] [x] `Planner` / `Evaluator` 节点：生成后即时扫描，发现 Token 泄露立即硬熔断终止
- [x] [x] **交付物与记忆持久化主动脱敏**
  - [x] [x] 交付结论与记忆库写入前自动应用 `sanitize_canary`，防止 Token 残留

---

## 五、注入样态静态审计与标注 (`guardrails/injection_guard.py`)

- [x] [x] **潜在注入特征静态识别**
  - [x] [x] 扫描输入文本中的控制指令覆盖（"ignore instructions" / "system override" 等）
  - [x] [x] 命中文本输出审计标注警告，供安全视图检视与决策参考
