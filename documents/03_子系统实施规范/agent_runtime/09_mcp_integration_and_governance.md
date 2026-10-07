# MCP (Model Context Protocol) 集成与运行时治理规范

> **责任领域**：`AegisAgent/src/mcps/` & `AegisAgent/src/mcps/adapter.py`
> **核心原则**：标准协议转译、命名空间物理隔离、子进程安全治理、懒加载按需连接、观察值截断受控。

---

## 1. 架构定位与核心使命

在 Aegis 系统中，**MCP（Model Context Protocol）是连接庞大开源外部工具生态的标准化桥梁**。

* **传统插件痛点**：过去每接入一个新系统（如 GitHub、PostgreSQL、Docker、Sentry），必须手写一套 Python 适配代码，维护成本极高，且外部依赖容易污染主项目环境。
* **MCP 的解耦价值**：基于 JSON-RPC 2.0 协议标准，Agent Runtime 作为 **MCP Client (Host)**，通过标准协议与由社区成熟维护的 **MCP Server** 进程通信，实现生态开箱即用。

### 1.1 MCP 三大原语在 Aegis 中的映射

| MCP 原语 | 协议形态 | Aegis 映射与消费方式 |
| :--- | :--- | :--- |
| **Tools (工具)** | 带 JSON Schema 的可执行函数 | 经转译后作为标准 `AegisTool` 注册到 `tools`，供模型自主调用 |
| **Resources (资源)** | 具有唯一 URI 的只读数据源 (`file://`, `postgres://`) | 供 Agent 按需读取，作为上下文直接注入 `ExecutionContext` |
| **Prompts (提示词)** | 预定义的结构化交互模板 | 映射为斜杠快捷指令或专家工作流（如 `/review_pr`） |

---

## 2. 整体工程拓扑与五大治理机制

外部 MCP Server 是非受控的独立进程，运行时必须具备完善的防护与生命周期托管机制：

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        Aegis MCP 运行时治理架构                        │
│                                                                        │
│  [config.toml] ──► 声明式服务器清单 (stdio 命令 / 环境变量 / sse)       │
│                          │                                             │
│  ┌───────────────────────▼──────────────────────────────────────────┐  │
│  │ 1. 进程生命周期管理器 (MCPManager)                                │  │
│  │    - stdio 进程池、PID 托管、心跳检测 (Ping)、防僵尸进程 (Zombie) │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │ 2. 协议转译与命名空间 (Schema Adapter & Namespacing)              │  │
│  │    - inputSchema -> OpenAI Function Calling Schema 毫秒转译       │  │
│  │    - 强制防重名命名空间: mcp__{server_name}__{tool_name}         │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │ 3. 懒加载连接池 (Lazy Connector)                                │  │
│  │    - 启动零开销；首调时才真正拉起子进程握手并缓存 ClientSession   │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │ 4. 观察值截断与安全守卫 (Pruner & Security Guard)                 │  │
│  │    - 拦截超限返回 (Token > 1500) -> 物理下沉至 storage/artifacts/  │  │
│  │    - 执行超时熔断 (单次调用上限 60s)                              │  │
│  └───────────────────────┬──────────────────────────────────────────┘  │
│                          │                                             │
│  [tools] ◀──────────┴── 伪装为原生 AegisTool，注入 Executor 调度  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 关键治理机制详述

### 3.1 传输模式与进程托管（Transport & Process Lifecycle）
* **`stdio` 传输模式（主打本地）**：
  - Agent 作为父进程派生子进程，通过标准 I/O 进行全双工通信（如 `npx @modelcontextprotocol/server-github`）；
  - **防僵尸与优雅退出**：注册 Python `atexit` 钩子与异步上下文管理器，当 Agent 进程终止（收到 `SIGINT` / `SIGTERM`）时，递归杀掉进程组下的所有子进程。
* **`sse` 传输模式（主打远程）**：
  - 通过 HTTP Server-Sent Events 连接常驻服务，配置超时重试与断线重连。

### 3.2 契约透明转译与命名空间防冲突（Namespacing）
* **命名冲突痛点**：若同时挂载了 `filesystem` 和 `github` 两个 Server，两者均提供了名为 `read_file` 的工具，将导致模型调用歧义。
* **强制命名空间转译**：
  - 注册到大模型时，工具名称强制加前缀：`mcp__{server_name}__{tool_name}`；
  - 转换示例：`github` 的 `create_issue` -> `mcp__github__create_issue`；
  - 大模型下发调用时，`MCPToolAdapter` 截获并剥离前缀，精准派发给目标 Server 的对应函数。

### 3.3 启动零等待：懒加载连接池（Lazy Initialization）
* **设计原则**：系统启动时不一次性拉起全部配置的 MCP Server，避免占用过多系统内存及延长冷启动时间。
* **首调握手**：
  - 启动阶段仅加载静态配置与工具元数据缓存；
  - 仅当模型在推理中生成了对该 Server 下工具的调用时，才即时拉起子进程并建立会话。

### 3.4 观察值截断与原子成对防护（Observation Pruning）
* MCP Server 的输出不受本系统控制，容易产生单次上万行的结果；
* 必须在 MCP 工具调用层强制挂接 `ObservationPruner`：
  - 超过 1500 Token 自动将全量 JSON 输出离线落地至 `storage/artifacts/{task_id}/mcp_{tool_name}.json`；
  - 严格保持 `tool_call_id` 对应的 `ToolMessage` 原子对结构。

---

### 3.5 不可信数据治理：数据面与控制面分离

MCP 的风险必须拆成两类，对策完全不同——把它们混为一谈是这类集成最常见的设计错误：

| 面 | 载体 | 风险 | 对策 |
| :--- | :--- | :--- | :--- |
| **数据面** | `tools/list` 的 `description` / `inputSchema`；`tools/call` 的返回内容 | **工具描述投毒**（描述会进工具 Schema，位置高于普通观察值）；返回内容注入 | **注册前消毒 + 返回后标注** |
| **控制面** | stdio 模式下的 MCP Server **进程本体** | **任意代码执行**——它是用户主动运行的第三方程序 | **默认关闭 + 显式 opt-in + 资源上限 + 审计**；架构无法代偿 |

> **必须说清的边界**：stdio MCP Server 不是"数据源"，而是**一段你选择运行的代码**。
> 任何提示词层或契约层防御都无法让它变安全。能做的只有：默认关闭、限制其资源消耗、
> 留下可审计证据。

#### 3.5.1 数据面：描述消毒与结果标注

`mcps/vetting.py` 在 `_connect()` 拿到 `tools/list` 之后、注册之前执行：

1. **注入样态硬拒**：`description` 命中 `injection_guard` 任一模式即**拒绝注册该工具**。
   与技能不同——**工具描述本就不该包含指令样态**，因此这里可以硬拒而不是仅标注；
2. **形状约束**：`description` 截断至 `max_description_chars`；`inputSchema` 必须是合法 object；
3. **拒绝留痕**：被拒工具写入 `MCPManager` 的拒绝清单，经 `/api/v1/mcp/servers` 暴露供人工复核；
4. **结果标注**：`tools/call` 的返回内容照旧由 executor 包进 `<tool_observation>`，
   并由 `injection_guard` 追加标注。

#### 3.5.2 控制面：显式授权与资源上限

1. **默认关闭**：所有 server `enabled = false`，必须人工逐个开启；
2. **资源上限**：stdio server 以 `sh -c 'ulimit -v …; ulimit -f …; ulimit -t …; exec <cmd>'` 包装启动，
   施加 `RLIMIT_AS` / `RLIMIT_FSIZE` / `RLIMIT_CPU`；并置于独立会话（`setsid`）避免信号串扰；
3. **显式授权**：`MCPToolAdapter.trust = "untrusted"`，因此**默认无法进入主工具表**。
   授权通过 `ToolRegistry(untrusted_allowlist={...})` **逐名**授予——
   把"用户为该 server 显式开启 + 描述通过消毒"这一人工动作，
   在代码里表达成一份**具名能力清单**，而不是一个粗放的布尔开关；
4. **审计**：拉起了哪个 server、命令与参数、声明了哪些工具、哪些被拒，全部落轨迹。

**为什么不用 summarizer 包裹 MCP 工具**：研究子智能体的"隔离 + 蒸馏"是为
**只读信息源**设计的；MCP 工具多为**动作执行器**（建 issue、写库），
参数必须精确、返回值必须原样，包一层模型只会引入失真与成本。
动作型风险的正确对策是**权限闸门**，不是蒸馏。

---

## 4. 声明式配置规范 (`config.toml`)

在 [`AegisAgent/config/config.toml`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/config/config.toml) 中，提供标准声明结构：

```toml
# ------------------------------------------------------------------------------
# 8. MCP (Model Context Protocol) 外部扩展服务器配置
# ------------------------------------------------------------------------------
[mcp]
enabled = true
connection_timeout_sec = 30
call_timeout_sec = 60

# 数据面治理（描述消毒）
max_description_chars = 1000    # 工具描述长度上限
reject_on_injection = true      # 描述命中注入样态时拒绝注册该工具

# 控制面治理（stdio 子进程资源上限，Linux）
rlimit_as_mb = 1024             # RLIMIT_AS 虚拟内存上限
rlimit_fsize_mb = 50            # RLIMIT_FSIZE 单文件大小上限
rlimit_cpu_sec = 300            # RLIMIT_CPU 纯 CPU 时间上限

# 本地 stdio 模式服务器
[mcp.servers.filesystem]
enabled = true
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/home/Skualeilu/Projects"]
env = {}

# 带敏感 Token 的 stdio 服务器 (敏感 Key 引用自 .env)
[mcp.servers.github]
enabled = false
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
env = { GITHUB_PERSONAL_ACCESS_TOKEN = "env:GITHUB_TOKEN" }

# 远程 HTTP/SSE 模式服务器
[mcp.servers.remote_doc]
enabled = false
transport = "sse"
url = "http://127.0.0.1:8005/sse"
env = {}
```

---

## 5. 强类型代码契约设计

在 `AegisAgent/src/mcps/` 中的代码实现标准：

### 5.1 数据模型规范 (`mcps/models.py`)

```python
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field

class MCPServerConfig(BaseModel):
    """单个 MCP 服务器配置"""
    name: str
    enabled: bool = True
    transport: Literal["stdio", "sse"] = "stdio"
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = None
    timeout_sec: float = 60.0

class MCPToolDefinition(BaseModel):
    """转译后的标准工具元数据"""
    server_name: str
    original_name: str
    namespaced_name: str         # mcp__{server_name}__{original_name}
    description: str
    input_schema: dict           # 标准 JSON Schema
```

### 5.2 命名空间转译与适配器 (`mcps/adapter.py`)

```python
from typing import Any, Dict
from pydantic import BaseModel

def to_namespaced_tool(server_name: str, raw_tool: dict) -> dict:
    """
    将原始 MCP 工具转换为带命名空间的 OpenAI Function Calling 规范
    """
    orig_name = raw_tool["name"]
    namespaced_name = f"mcp__{server_name}__{orig_name}"

    return {
        "type": "function",
        "function": {
            "name": namespaced_name,
            "description": f"[{server_name} 插件] {raw_tool.get('description', '')}",
            "parameters": raw_tool.get("inputSchema", {
                "type": "object",
                "properties": {},
            })
        }
    }

def parse_namespaced_tool(namespaced_name: str) -> tuple[str, str]:
    """
    从 mcp__server__tool 解析回 server_name 与 original_tool_name
    """
    parts = namespaced_name.split("__", 2)
    if len(parts) != 3 or parts[0] != "mcp":
        raise ValueError(f"非法的 MCP 工具名称: {namespaced_name}")
    return parts[1], parts[2]
```

### 5.3 生命周期托管接口 (`mcps/manager.py`)

```python
class MCPManager:
    """MCP 客户端与子进程生命周期管理器"""

    async def initialize(self, configs: Dict[str, MCPServerConfig]) -> None:
        """初始化配置，注册 atexit 清理钩子"""
        ...

    async def get_all_tools(self) -> List[dict]:
        """获取所有已启用 MCP 服务的转译工具清单 (注入 Executor)"""
        ...

    async def call_tool(self, namespaced_name: str, arguments: dict, task_id: str) -> Any:
        """
        根据命名空间分发到具体 Server 执行，
        并通过 ObservationPruner 实施长日志截断下沉
        """
        ...

    async def shutdown_all(self) -> None:
        """安全关闭所有 stdio 子进程与 sse 会话，防止僵尸进程"""
        ...
```
