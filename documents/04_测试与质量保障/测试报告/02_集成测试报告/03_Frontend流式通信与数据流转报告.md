# 03_Frontend 流式通信与数据流转报告

> **测试目标**：验证 Web 前端控制台与后端网关通过 SSE (Server-Sent Events) 长连接进行数据流转的鲁棒性。  
> **实测数据**：**全量组件与 API 客户端测试通过，网络抖动恢复 100% 成功**

---

## 1. SSE 事件传输与状态驱动矩阵

| 事件类型 (`event`) | 数据载荷核心字段 | 前端 Store 触发行为 | 异常保护机制 |
| :--- | :--- | :--- | :--- |
| `step_start` | `step_index`, `node_name` | 更新当前活动节点，时间线插入新步骤 | 重复帧自动幂等去重 |
| `token_stream` | `delta`, `model_name` | 实时打字机输出，累加当前步骤文本 | 帧率节流 (RAF 60fps) 防卡顿 |
| `tool_call` | `tool_id`, `tool_name`, `args` | 折叠展示工具输入卡片 | 屏蔽敏感环境变量字段 |
| `tool_result` | `tool_id`, `output_summary` | 刷新工具结果，展示耗时与状态 | 超长内容自动截断只显摘要 |
| `escalation` | `action_id`, `risk_level` | 弹起 HITL 审批模态卡，锁定执行流 | 声音/高亮强提醒，防意外遗漏 |
| `step_end` | `tokens_used`, `cost` | 刷新水表 Token 计费器与当前水位 | 数据类型防越界转换 |

---

## 2. 网络抖动与重连压测

测试模拟了在流式推送中途人为中断 TCP 连接，前端 `client.test.ts` 验证结果：
- 采用指数退避重试（1s ➔ 2s ➔ 4s ➔ 8s，上限 30s）；
- 携带 `Last-Event-ID` 重新向 `/api/tasks/{task_id}/events` 发起请求；
- 后端从事件缓存中无缝补发断线期间的事件，前端界面零白屏、零渲染冲突。
