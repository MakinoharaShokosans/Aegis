# AegisFrontend 组件与状态单元测试路线图 (Unit Test Roadmap)

> **定位**：`AegisFrontend` Web 前端工程中关于 Zustand 响应式 Store 状态变迁、UI 纯组件渲染交互与纯函数工具库的单元测试路线。
> **原则**：基于 `vitest` + `jsdom` + `@testing-library/react`，无真实后端依赖，DOM 自动化隔离清理。

---

## 1. 现状盘点：组件与状态机单测覆盖矩阵

| 目标源码模块 | 对应测试文件 | 状态 | 核心验证重点 |
| :--- | :--- | :---: | :--- |
| `src/stores/useTaskStore.ts` | `src/stores/__tests__/useTaskStore.test.ts` | `[x] [x]` | 同会话多轮提交历史消息累积、审批挂起与决策恢复状态机 |
| `src/stores/useWorkspaceStore.ts` | `src/stores/__tests__/useWorkspaceStore.test.ts` | `[x] [x]` | 活动工作区切换、项目文件树缓存、选中与编辑状态 |
| `src/stores/useRagStore.ts` | `src/stores/__tests__/useRagStore.test.ts` | `[x] [x]` | 检索参数响应式绑定、语言与仓库过滤、相关度阈值筛选 |
| `src/components/chat/HitlApprovalCard.tsx` | `src/components/chat/__tests__/HitlApprovalCard.test.tsx` | `[x] [x]` | 风险动作卡片渲染、"批准本次" (`once`) / "免审" (`always`) / "拒绝" 交互派发 |
| `src/components/chat/TraceTimeline.tsx` | `src/components/chat/__tests__/TraceTimeline.test.tsx` | `[x] [x]` | 节点流转可视化、子智能体专属 Badge 徽标、耗时计算格式化 |
| `src/components/chat/LlmInvocationInspector.tsx` | `src/components/chat/__tests__/LlmInvocationInspector.test.tsx` | `[x] [x]` | Token 消耗数字展示、原始 Prompt / Response 弹窗查看、Tool Call JSON 高亮 |
| `src/components/chat/InputConsole.tsx` | `src/components/chat/__tests__/InputConsole.test.tsx` | `[x] [x]` | Cmd+Enter 快捷提交、斜杠命令解析、执行中输入锁死 |
| `src/components/domain/WaterLevelMeter.tsx` | `src/components/domain/__tests__/WaterLevelMeter.test.tsx` | `[x] [x]` | 水位百分比计算、三级色彩切换（安全绿 / 预警黄 / 危险红） |
| `src/components/domain/MilestoneItem.tsx` | `src/components/domain/__tests__/MilestoneItem.test.tsx` | `[x] [x]` | 里程碑 4 态演进（等待/运行/完成/失败）、子任务折叠交互 |
| `src/components/canvas/TabBar.tsx` | `src/components/canvas/__tests__/TabBar.test.tsx` | `[x] [x]` | 多标签页切换激活、未保存修改脏标记（Dirty Indicator）与关闭保护 |
| `src/components/sidebar/ProjectsTree.tsx` | `src/components/sidebar/__tests__/ProjectsTree.test.tsx` | `[x] [x]` | 目录树折叠展开、隐藏文件规则、点击选中高亮联动 |
| `src/utils/exportWorkflow.ts` | `src/utils/__tests__/exportWorkflow.test.ts` | `[x] [x]` | 任务执行全量 Trace 导出为结构化 JSON 与 Markdown 审计报告 |

---

## 2. 细分测试用例规范

### 2.1 任务调度与多轮会话状态机 (`useTaskStore.test.ts`)
- **同会话连续提交上下文累加**：在同一 `session_id` 下，连续触发两次 `submitTask()`，断言第二轮启动后任务消息列表中仍然完整保留第一轮的 User 提问与 Assistant 回复；
- **审批拦截态切换**：接收审批信号后，`isWaitingApproval` 立即置为 `true`，派发决策成功后自动复位回 `false`；
- **错误回滚保护**：提交失败时重置 `isLoading` 状态并写入全局错误提示。

### 2.2 越级审批交互卡片 (`HitlApprovalCard.test.tsx`)
- **动作要素渲染**：清晰渲染待执行指令（如 `git push`）、动作类型（如 `network_egress`）及风险提示文案；
- **决策按钮回调**：
  - 点击“批准本次”触发 `onApprove(approval_id, "once")`；
  - 点击“当前会话免审”触发 `onApprove(approval_id, "always")`；
  - 点击“拒绝执行”触发 `onReject(approval_id)`；
- **防重复点击锁**：点击后按钮立即进入 `disabled` 状态，杜绝网络抖动下的人工并发连击。

### 2.3 Token 预算水位计安全警示 (`WaterLevelMeter.test.tsx`)
- **阈值变色逻辑**：
  - Token 占用率 $< 70\%$：呈现绿色安全态；
  - $70\% \le \text{rate} \le 90\%$：呈现黄色预警态；
  - $> 90\%$：呈现赤红色危险态，提示上下文即将触发原子对裁剪或物理熔断。

---

## 3. 验收标准与执行

- TypeScript 编译无类型报错（`tsc --noEmit`）；
- 核心组件交互与 Store 状态逻辑 100% 通过；
- 执行命令：
  ```bash
  cd /home/Skualeilu/Projects/Aegis/AegisFrontend
  npm run test
  ```
