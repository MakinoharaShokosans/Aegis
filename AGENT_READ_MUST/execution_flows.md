# Execution Flows

> 状态标签: `[Current]`(实码校验) | `[Unverified]`(历史推断待印证) | `[Unknown]`(尚无证据) | `[Stale]`(待修正)

## 1. 任务主干生命周期
```text
[ 用户端请求 ] ──► POST /api/tasks ──► 任务入队与持久化 (SQLite)
                                             │
                                             ▼
                                  prepare_task (编译状态机)
                                             │
      ┌──────────────────────────────────────┴──────────────────────────────────────┐
      │                                                                             │
      ▼                                                                             │
[ budget_guard ] (检查 Token/步数/挂钟物理硬限制)                                     │
      │                                                                             │
      ▼                                                                             │
[ planner ] (双层规划分解: 生成/修订里程碑 Milestone)                                │
      │                                                                             │
      ▼                                                                             │
[ executor ] (单步决策: 思考、选取工具并生成参数)                                      │
      │                                                                             │
      ├── (需调用工具) ──► [ tool_runner ] (沙箱/网络/RAG/MCP 执行并回填观察)        │
      │                           │                                                 │
      └───────────────────────────┴──► [ evaluator ] (反思评估: 检验里程碑达成度)   │
                                             │                                      │
                         ┌───────────────────┼───────────────────┐                  │
                         ▼                   ▼                   ▼                  ▼
                    [ 达成成功 ]        [ 触发重规划 ]      [ 需人工审批 ]    [ 预算超限熔断 ]
                     (succeeded)          (to planner)      (waiting_approval)  (terminated)
```

## 2. 实时事件流与反馈交互
- `[Current]` **SSE 传输链路**: `TaskEventBus` 捕获节点状态跃迁、工具调用日志与思考文本，推送到 `/api/tasks/{task_id}/events` 流式端点。
- `[Current]` **HITL 网关**: 当涉及高危操作或评估器主动发起审批时，任务置为 `waiting_for_approval`，前端挂起等待用户 `POST /approve` 或 `POST /reject`。
