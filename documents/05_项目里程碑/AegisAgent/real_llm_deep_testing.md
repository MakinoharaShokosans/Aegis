# AegisAgent 真实 LLM 深度测试、AgentBench 基线与前沿模型红队实施里程碑

> **对应设计规范**：`documents/深度测试路线.md`、`documents/技术选型/evaluation.md`
> **责任模块**：`AegisAgent/tests/real_llm/` (Phase 9 ~ 15)、`agent_runtime/llm/`、`evaluation/agent_bench/`
> **核心原则**：真实前沿模型闭环（`gpt-5.6-terra` / `gpt-5.4-mini`）、结构化契约容错、HITL 权限纪律实测、对抗性 Prompt 注入与 Canary 防御、数据面隔离、长任务记忆滚动压缩。
>
> **图例规范**：`[代码实现] [测试通过]`

---

## 一、真实 LLM 结构化输出契约与工具参数解析 (Phase 9)

- [x] [x] **推理模型结构化 JSON 约束与容错 (`test_phase09_live_contracts.py`)**
  - [x] [x] `gpt-5.6-terra`（`temperature=0.0`）强制 JSON 模式下的宏观规划与里程碑结构化输出
  - [x] [x] 鲁棒解析 Markdown 代码块包裹（` ```json `）、多余前缀解释词与脏字段
- [x] [x] **快速模型 Function Calling 工具契约与参数解构**
  - [x] [x] `gpt-5.4-mini` 正确生成标准 OpenAI 格式 `tool_calls` 与合法 JSON 参数字典
  - [x] [x] `to_tool_call_specs` 规范化提取工具 ID、名称与参数键值对

---

## 二、真实端到端任务闭环与 AgentBench 评测基线 (Phase 10)

- [x] [x] **多步端到端自主收敛与产物落盘 (`test_phase10_live_workflow.py`)**
  - [x] [x] `planner → budget_guard → executor → tool_runner → evaluator` 全链路无预设脚本自主收敛
  - [x] [x] 物理隔离工作区内正确生成交付文件（如 `math_utils.py`）并通过语法复核
- [x] [x] **AgentBench 自动化评测 Harness 真实基线生成**
  - [x] [x] 真实执行轨迹 `storage/traces/*.jsonl` 自动接入 `evaluation/agent_bench/runner.py`
  - [x] [x] 产出首份包含任务完成率（Task Completion Rate）与步数效率（Step Efficiency）的量化基线报告
- [x] [x] **工具初始报错下的错误分析与自愈调整 (Error Recovery Rate)**
  - [x] [x] 初始读取不存在文件报错后，模型自主分析原因并转为创建后备配置（`fallback_config.json`）自愈

---

## 三、HITL 权限纪律与放行白名单真实红队 (Phase 11)

- [x] [x] **越级操作真实触发与审批挂起 (`test_phase11_live_permissions.py`)**
  - [x] [x] 面对高危指令（如 `git push`）自然生成特权 `bash` 命令，被 `permission.py` 准确判定为 `full_permissions`
  - [x] [x] `tool_runner` 成功触发 LangGraph `interrupt()` 挂起，生成规范审批请求 Payload
- [x] [x] **人工审批拒绝后的系统纪律与合规替代自愈**
  - [x] [x] 注入 `approved=False` 拒绝原因后，真实模型服从 `system.md` 纪律，生成本地替代交付物（`patch.diff`）而非恶意绕行
- [x] [x] **会话级永久放行白名单 (`scope="always"`)**
  - [x] [x] 获批动作哈希签名自动写入会话 `approval_allowlist`，后续相同签名免审直接放行，未授权新动作继续受限

---

## 四、对抗性 Prompt 注入与金丝雀 Token 防御 (Phase 12)

- [x] [x] **`<tool_observation>` XML 沙箱定界协议服从性 (`test_phase12_live_injection.py`)**
  - [x] [x] 工具观察值内嵌入恶意系统覆盖指令（`SYSTEM OVERRIDE / PWNED`）时，真实模型坚守沙箱边界拒绝执行
  - [x] [x] 准确识别注入特征并如实完成上层代码审查任务
- [x] [x] **会话金丝雀 Token（Canary Token）防窃取红队**
  - [x] [x] 面对高强度越狱 Prompt（系统维护模式、秘密字符串提取），真实模型 0 泄露
  - [x] [x] `detect_canary_leak` 全流程实时监控，无任何外带泄露

---

## 五、研究子智能体真实 Web 检索与数据面隔离 (Phase 13)

- [x] [x] **真实 DuckDuckGo 检索与有界研究循环 (`test_phase13_live_research.py`)**
  - [x] [x] 驱动真实轻量模型在有界轮次（`max_rounds`）内完成检索词去重规划与提炼
- [x] [x] **强类型契约与数据流零污染**
  - [x] [x] 提取事实严格通过 URL 真实抓取白名单校验与版本号正则过滤
  - [x] [x] 原始 HTML 标签/脚本 100% 隔离在沙箱内部，主 Agent 仅接收净化后的结构化 Markdown 报告

---

## 六、FallbackChain 跨端点透明降级与容灾 (Phase 14)

- [x] [x] **真实网络故障下的透明切换 (`test_phase14_live_fallback.py`)**
  - [x] [x] 构造不可达哨兵黑洞端点 + 真实备用端点，遭遇连接失败时自动指数退避并透明降级
  - [x] [x] 降级过程完整保持 `messages` 与 `tools` 载荷无损，成功交付模型回复

---

## 七、长任务上下文治理与观察值蒸馏 (Phase 15)

- [x] [x] **多轮高负载水位线压缩与 Atomic Pair 保全 (`test_phase15_live_context.py`)**
  - [x] [x] 活跃 Token 超过高水位线（`compaction_high_watermark`）时自动切片并触发滚动摘要生成
  - [x] [x] 对话完整性对齐，严格按成对 User/Assistant 裁剪，保障消息上下文结构合法
- [x] [x] **超长编译器日志结构化蒸馏与离线落盘**
  - [x] [x] `ObservationPruner` 对大体积日志自动保留 Head/Tail 关键行并标注中间省略
  - [x] [x] 原始完整日志流式离线保存至磁盘，向上下文注入产物句柄（`artifact://`）
