# 03_Frontend 状态机与组件测试报告

> **测试目标**：验证 `AegisFrontend/` 前端工程的 Zustand 响应式状态机、React 19 组件渲染、Monaco Diff 比对与 SSE 事件解析。
> **执行命令**：`cd AegisFrontend && npm run test`
> **实测数据**：**16 Test Files Passed (16), 55 Tests Passed (55) | 耗时: 6.50s | 通过率: 100%**

---

## 1. 前端测试套件全景分布表

| 测试文件 | 用例数 | 状态 | 覆盖功能模块 |
| :--- | :--- | :--- | :--- |
| `src/stores/__tests__/useTaskStore.test.ts` | 6 | PASS | 任务创建、切换当前任务、审批状态原子突变、消息追加 |
| `src/stores/__tests__/useWorkspaceStore.test.ts` | 4 | PASS | 工作区根目录绑定、文件树展开折叠、活动文件切换 |
| `src/stores/__tests__/useRagStore.test.ts` | 4 | PASS | RAG 检索状态追踪、Collection 向量库就绪状态、耗时统计 |
| `src/components/chat/__tests__/HitlApprovalCard.test.tsx` | 5 | PASS | HITL 审批卡片渲染、高危动作红色警告标、Approve/Reject 触发 |
| `src/components/chat/__tests__/InputConsole.test.tsx` | 4 | PASS | 多行文本输入、Ctrl+Enter 快捷键提交、运行中禁用态 |
| `src/components/chat/__tests__/TraceTimeline.test.tsx` | 4 | PASS | 思维链时间线可视化、工具调用耗时徽章、错误折叠面板 |
| `src/components/chat/__tests__/LlmInvocationInspector.test.tsx` | 3 | PASS | Token 消耗抽屉、模型调用元数据比对、Prompt 检视弹窗 |
| `src/components/canvas/__tests__/TabBar.test.tsx` | 3 | PASS | 编辑器多标签页切换、已修改状态圆点标识、关闭标签页 |
| `src/components/sidebar/__tests__/ProjectsTree.test.tsx` | 4 | PASS | 代码目录树展开、文件图标渲染、点击激活文件回调 |
| `src/components/domain/__tests__/WaterLevelMeter.test.tsx` | 3 | PASS | Token 水位计动态计量、超过 80% 变黄告警、超过 95% 变红 |
| `src/components/domain/__tests__/MilestoneItem.test.tsx` | 2 | PASS | 里程碑状态切换、完成勾选图标与折叠 |
| `src/components/common/__tests__/DirectoryPickerModal.test.tsx` | 3 | PASS | 本地工程路径选择对话框、路径合法性校验 |
| `src/components/common/__tests__/AegisVisuals.test.tsx` | 2 | PASS | 系统 Logo、运行状态呼吸灯、连接态 SVG 图标 |
| `src/api/__tests__/client.test.ts` | 3 | PASS | Fetch EventSource 封装、SSE 双换行分帧、断网重连 |
| `src/api/__tests__/modules.test.ts` | 3 | PASS | REST 接口封装、4xx/5xx 状态码拦截与统一错误包装 |
| `src/utils/__tests__/exportWorkflow.test.ts` | 2 | PASS | 会话导出为 Markdown 与结构化 JSON 日志 |

---

## 2. 交互与状态保障关键亮点

1. **HITL 人机协同审批卡片隔离**：
   - 当任务产生 `escalation` 时，`HitlApprovalCard` 阻断输入区，展示具体执行命令、参数差异及预计耗时；测试验证点击 Approve 后向 `/api/tasks/{task_id}/approve` 正确提交 Payload。
2. **SSE 流式双换行防崩解析**：
   - 验证在复杂 Markdown（含代码块内的换行符）流式推送时，SSE 分帧解析器能够准确按协议界定，零丢包、零 JSON 解析崩溃。
