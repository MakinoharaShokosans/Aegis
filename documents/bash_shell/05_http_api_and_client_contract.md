# Bash 执行沙箱 - 服务契约与客户端适配规范

> **责任领域**：`AegisAgent/src/services/bash_shell/app.py` 与 `AegisAgent/src/tools/builtin/bash.py`  
> **核心原则**：HTTP REST 契约化通信、强类型 DTO 约束、解耦红线（禁止反向依赖 Agent 内部模块）。

---

## 1. 服务接口定义 (FastAPI 端点)

Bash Shell 作为独立微服务（默认运行于 `127.0.0.1:8002`），向 Agent 工具层暴露以下接口：

### 1.1 执行命令端点：`POST /api/v1/shell/execute`
执行受控命令的核心接口，支持资源排队、物理配额注入与输出提炼。

#### 请求体 Schema (`ShellExecuteRequest`)
```json
{
  "command": "gcc -Wall -O2 src/main.c -o build/main",
  "workspace_id": "ws_9a8b7c",
  "workspace_root": "/home/user/projects/target_repo",
  "task_id": "9b1e7c54-46c5-4428-a408-dbcbcf123456",
  "step_id": 3,
  "timeout_sec": 60,
  "requested_mb": 2048
}
```

#### 响应体 Schema (`ShellExecuteResponse`)
```json
{
  "status": "COMPLETED",               // COMPLETED | TIMED_OUT | BLOCKED | QUEUED
  "exit_code": 0,
  "distilled_stdout": "Compilation succeeded. Output: build/main",
  "distilled_stderr": "",
  "is_truncated": false,
  "artifact_path": "storage/artifacts/9b1e.../step_3_bash.log",
  "execution_time_ms": 1420,
  "error_message": null
}
```

### 1.2 健康检查与自省：`GET /health`
```json
{
  "status": "healthy",
  "service": "bash_shell",
  "version": "0.1.0",
  "memory_pool": {
    "total_mb": 8192,
    "available_mb": 6144,
    "active_workers": 1,
    "queued_tasks": 0
  }
}
```

---

## 2. 错误码与降级契约

| HTTP 状态码 | 业务错误标记 | 产生原因 | Agent 处理策略 |
| :--- | :--- | :--- | :--- |
| **`200 OK`** | `COMPLETED` | 命令正常执行结束（无论 exit_code 是否为 0） | 读取提炼文本，exit_code != 0 时触发反思 |
| **`200 OK`** | `TIMED_OUT` | 超过 `timeout_sec`，两段式强杀 | 将超时作为确定性事实反馈，引导拆分命令 |
| **`403 FORBIDDEN`** | `BLOCKED` | 命中 CommandAudit 高危黑名单 | 将安全红线提示反馈给 Agent，引导合规操作 |
| **`422 UNPROCESSABLE`** | `PATH_ESCAPE` | 操作路径逃逸出 `workspace_root` | 提示路径越界，要求在工作区内操作 |
| **`503 UNAVAILABLE`** | `RESOURCE_EXHAUSTED` | 全局内存池长时间排队超时 | 建议降低并发或稍后重试 |

---

## 3. Agent ToolLayer 客户端适配器 (`tools/builtin/bash.py`)

在 Agent 调度主进程中，通过统一的 `AegisTool` 规范对接 Shell 服务：

```python
from tools.core.protocol import AegisTool, ToolResult
from tools.core.http_client import ServiceClient

class BashTool(AegisTool):
    name = "bash"
    description = "在当前工作区物理目录下执行受控 Bash 终端命令，包含编译构建、代码调试与测试运行。"

    def __init__(self, client: ServiceClient, workspace_id: str, workspace_root: str, task_id: str):
        self.client = client
        self.workspace_id = workspace_id
        self.workspace_root = workspace_root
        self.task_id = task_id

    async def execute(self, command: str, timeout_sec: int = 60) -> ToolResult:
        payload = {
            "command": command,
            "workspace_id": self.workspace_id,
            "workspace_root": self.workspace_root,
            "task_id": self.task_id,
            "timeout_sec": timeout_sec,
        }
        resp = await self.client.post("/api/v1/shell/execute", json=payload)
        data = resp.json()
        
        # 组装返回给 Agent 上下文的确定性结果
        output = data.get("distilled_stdout") or data.get("distilled_stderr") or ""
        artifact = data.get("artifact_path")
        if artifact:
            output += f"\n[全量执行日志: {artifact}]"
            
        return ToolResult(
            success=(data.get("exit_code") == 0),
            content=output,
            metadata={"exit_code": data.get("exit_code"), "duration_ms": data.get("execution_time_ms")}
        )
```
