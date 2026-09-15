# Aegis 内置系统提示词（待编写）

> 规范：`documents/agent_runtime/01_architecture_overview.md` §4.3
> 状态：骨架占位（尚未编写）

本文件承载 Agent 的内置行为纪律（ReAct 思考与工具规范）。
运行时装配顺序见 `06_memory_and_context_management.md` §4：

1. 系统提示词（本文件 + 工作区项目规则如 `CLAUDE.MD`）
2. 工作区全局共享记忆
3. 会话已压缩情境记忆
4. 活跃对话流水
5. 当前用户输入
