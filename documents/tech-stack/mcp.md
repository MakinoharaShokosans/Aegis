---
aliases:
  - MCP
  - Model Context Protocol
  - 模型上下文协议
  - 外部工具托管协议
tags:
  - tech-stack
  - python
  - mcp
  - protocol
  - tools
package: "mcp"
version: ">=2.2.0,<3.0.0"
project_role: "标准 Model Context Protocol 客户端，统一托管、发现、安全审计并调用外部独立进程（stdio）或远程服务（SSE）提供的工具"
entrypoints:
  - "AegisAgent/src/mcps/manager.py"
  - "AegisAgent/src/mcps/adapter.py"
  - "AegisAgent/src/mcps/vetting.py"
  - "AegisAgent/config/config.toml"
---

# MCP (Model Context Protocol) 辅助检索与理解指南

> [!info] 什么是 MCP
> **生活化比喻**：如果把大模型 Agent 比作一台电脑的“CPU”，那么各个团队开发的外部工具（如读取 GitHub 仓库、操作本地文件系统、查询外部文档库）就像是各种不同厂商生产的“USB 鼠标、键盘和移动硬盘”。在过去，接入每个新工具都必须手写一套驱动胶水代码；而 MCP 就是大模型生态里的**“通用 Type-C / USB 工业标准协议”**。只要外部工具开发者按照 MCP 协议标准输出接口，Aegis 插入“数据线”就能一键识别所有工具列表，并以统一步骤安全调用。

---

## 1. 小白心智模型（1分钟看懂）

- **解决的核心痛点**：如果不使用 MCP，每当系统需要接入第三方开源工具（如 GitHub API、Slack、PostgreSQL 检视器）时，开发者必须亲自编写适配器、处理进程通信、手工转换 JSON Schema。且外部工具代码直接运行在主进程中，一旦发生内存泄漏或被植入恶意 Prompt 注入指令，整个主系统将被直接击穿。
- **一句话本质**：MCP 是由 Anthropic 提出并开源的、**用于大模型与外部上下文工具之间通过 JSON-RPC 2.0 进行标准化通信的开放协议**。
- **三大核心物理机制**：
  1. **Transport（传输层通道）**：定义客户端与服务器之间的物理通信管道，常用包括 `stdio`（通过标准输入输出与本地子进程通信）和 `sse`（通过 HTTP Server-Sent Events 与远程服务通信）。
  2. **ClientSession（协议会话）**：客户端与 MCP 服务器握手建立的有状态连接，负责能力协商（Capabilities）、工具发现（`list_tools`）与工具调用（`call_tool`）。
  3. **Vetting & Sandboxing（安全审计与沙箱）**：对外部声明的工具描述做长度截断与注入嗅探，并通过内核配额（`rlimit`）限制 stdio 外部子进程的内存与 CPU 消耗。

---

## 2. 本项目中的角色与调用链路

- **在本项目的位置**：外部扩展工具托管与治理层（External Tool Governance Layer）。
- **核心入口文件**：
  - MCP 服务器生命周期管理：[`AegisAgent/src/mcps/manager.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/mcps/manager.py)
  - 工具定义适配器：[`AegisAgent/src/mcps/adapter.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/mcps/adapter.py)
  - 工具描述安全审计（数据面治理）：[`AegisAgent/src/mcps/vetting.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/mcps/vetting.py)
  - 外部服务配置项：[`AegisAgent/config/config.toml`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/config/config.toml#L111-L143)
- **典型执行流转链路**：
  ```text
  系统启动 (读取 config.toml [mcp] 配置，保持懒加载)
                 │
                 ▼
  Agent 首次按需加载工具 (initialize)
                 │
                 ├──────────────────────────┐
                 ▼                          ▼
  stdio 模式 (拉起 npx 子进程)        sse 模式 (HTTP 握手)
  通过 setrlimit 注入内核配额               连接远程端点
                 │                          │
                 └──────────────┬───────────┘
                                ▼
                      ClientSession.list_tools()
                                │
                                ▼
                      vet_tool_definition (防 Prompt 注入消毒)
                                │
                                ▼
                      注册为 mcp__{server}__{tool} 统一命名空间
                                │
                                ▼
                      Executor 触发工具调用 ──► session.call_tool()
  ```

---

## 3. 核心 Symbol 速查字典（类 / 函数 / 属性 / 装饰器）

### `StdioServerParameters`（本地进程参数类）

- **通俗职责**：配置如何拉起一个本地 stdio 形式的 MCP 命令行子进程。
- **参数说明**：
  - `command: str`：可执行程序名（如 `"npx"` 或 `"python"`）。
  - `args: List[str]`：命令参数列表（如 `["-y", "@modelcontextprotocol/server-filesystem", "/path"]`）。
  - `env: Dict[str, str]`：注入子进程的环境变量（凭证引用）。
- **本项目调用点**：[`AegisAgent/src/mcps/manager.py:L96`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/mcps/manager.py#L96)
- **最小实战代码**：
  ```python
  from mcp import StdioServerParameters

  server_params = StdioServerParameters(
      command="npx",
      args=["-y", "@modelcontextprotocol/server-github"],
      env={"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxxx"}
  )
  ```

---

### `stdio_client` / `sse_client`（客户端传输上下文）

- **通俗职责**：异步上下文管理器，建立并维持与目标服务进程的通信双向流管道。
- **签名/参数速查**：
  - `stdio_client(server_params)`：建立本地标准输入输出管道。
  - `sse_client(url)`：建立 HTTP/SSE 远程长连接管道。
  - **返回值**：`(read_stream, write_stream)` 句柄。
- **本项目调用点**：[`AegisAgent/src/mcps/manager.py:L310-L311`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/mcps/manager.py#L310-L311)

---

### `ClientSession`（协议会话控制类）

- **通俗职责**：协议层面的交互中心。
- **常用方法速查**：
  - `await session.initialize()`：执行协议握手与版本协商。
  - `await session.list_tools()`：拉取该服务器暴露的所有工具元数据与 JSON Schema。
  - `await session.call_tool(name, arguments)`：执行具体的工具调用并返回结果列表。
- **本项目调用点**：[`AegisAgent/src/mcps/manager.py:L309`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/mcps/manager.py#L309)

---

## 4. 本项目典型用法与实操范式

### 范式 1：基于 AsyncExitStack 的生命周期托管与防僵尸进程
```python
# 路径：AegisAgent/src/mcps/manager.py
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.stdio import stdio_client

async def _connect_stdio(self, server_name: str, params: StdioServerParameters) -> ClientSession:
    # 1. 使用 AsyncExitStack 统一纳管所有打开的子进程与管道连接
    read_stream, write_stream = await self._exit_stack.enter_async_context(
        stdio_client(params)
    )
    # 2. 建立 ClientSession
    session = await self._exit_stack.enter_async_context(
        ClientSession(read_stream, write_stream)
    )
    # 3. 握手初始化
    await session.initialize()
    return session
```

### 范式 2：数据面治理与 Prompt 注入拦截
```python
# 路径：AegisAgent/src/mcps/vetting.py
def vet_tool_definition(raw_desc: str, max_chars: int = 1000) -> str:
    # 1. 严格检查工具描述中是否隐藏了越权提示词攻击
    injection_patterns = ["ignore previous instructions", "system prompt override"]
    for pattern in injection_patterns:
        if pattern in raw_desc.lower():
            raise SecurityVettingError(f"工具描述命中恶意注入样态: {pattern}")
    
    # 2. 长度截断，防止恶意工具用海量无效描述挤爆大模型 Context
    if len(raw_desc) > max_chars:
        return raw_desc[:max_chars] + "...[TRUNCATED]"
    return raw_desc
```

---

## 5. 新手易错陷阱与排坑指南

> [!warning] 陷阱 1：在临时 Task 内初始化 MCP 导致生命周期失控
> **现象**：`anyio.EndOfStream` 或在关闭时报错 `Task <...> was destroyed but it is still pending`。
> **原因**：MCP 官方 Python SDK 依赖 `anyio` 传输管道，其任务取消作用域与创建连接时的那个 asyncio Task 严格绑定。
> **正解**：遵循本项目 [`manager.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/mcps/manager.py#L16) 的设计，MCP 连接必须在应用总 Lifespan 主任务内集中初始化和关闭，严禁在临时的工具调用协程中动态开辟。

> [!warning] 陷阱 2：直接将远程工具名原样暴露导致命名冲突
> **现象**：两个外部 MCP 服务器都定义了名为 `read_file` 的工具，后者直接覆盖前者导致功能错乱。
> **正解**：本项目严格采用**双下划线隔离命名空间**：`mcp__{server_name}__{tool_name}`，确保所有工具名字全局唯一且调用路径清晰可溯。
