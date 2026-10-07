# Bash 执行沙箱 - 服务契约与客户端适配规范

> **责任领域**：`AegisAgent/src/services/bash_shell/app.py` 与 `AegisAgent/src/tools/builtin/bash.py`  
> **核心原则**：HTTP REST 契约化通信、强类型 DTO 约束、解耦红线（禁止反向依赖 Agent 内部模块）。

---

## 1. 服务接口定义 (FastAPI 端点)

Bash Shell 作为独立微服务（默认运行于 `127.0.0.1:8002`），向 Agent 工具层暴露以下接口：

### 1.1 执行命令端点：`POST /api/v1/shell/execute`

执行受控命令的核心接口，支持配额排队、内核配额注入与输出提炼。

#### 请求体（`ShellExecuteRequest`）

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--: | :--- |
| `workspace_id` | str | ✅ | 工作区标识（审计与溯源用；服务端以 `workspace_root` 为执行边界） |
| `workspace_root` | str | ✅ | 目标工程绝对路径（子进程 `cwd`，同时是路径越界边界） |
| `task_id` | str | ✅ | 任务标识，决定产物目录 `{artifacts_dir}/{task_id}/` |
| `step_id` | int | ✅ | 步骤序号，决定日志名 `step_{step_id}_bash.log` |
| `command` | str | ✅ | 待执行命令 |
| `timeout_sec` | float | — | 本次硬超时；缺省取 `[bash_shell].timeout_sec` |
| `queue_wait_sec` | float | — | 允许等待内存池配额的秒数；`0` 表示池满立即返回 `QUEUED` |
| `estimated_mb` | int | — | 预估内存占用（MB）；缺省按 `rlimit_as_mb` 计（即最坏情况） |
| `write_paths` | list[str] | — | 调用方显式声明的写入/删除目标，额外做越界校验 |

```json
{
  "workspace_id": "ws_9a8b7c",
  "workspace_root": "/home/user/projects/target_repo",
  "task_id": "9b1e7c54-46c5-4428-a408-dbcbcf123456",
  "step_id": 3,
  "command": "gcc -Wall -O2 src/main.c -o build/main",
  "timeout_sec": 60,
  "queue_wait_sec": 0,
  "write_paths": ["build/main"]
}
```

> 📋 规划中（尚未实现）：`permission_level` 字段与越级 HITL 审核，
> 见 [`03_command_audit_and_path_sandbox.md`](./03_command_audit_and_path_sandbox.md) §2。

#### 响应体（`ShellExecutionResult`）

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `status` | enum | `SUCCESS` / `FAILED` / `TIMEOUT` / `KILLED` / `QUEUED` |
| `exit_code` | int \| null | 退出码；被信号终止时为负值（如 `-9`）；`QUEUED` 时为 `null` |
| `distilled_stdout` / `distilled_stderr` | str | 蒸馏后的输出（结构化输出原样保留） |
| `is_truncated` | bool | 是否被裁剪；全量日志见 `artifact_path` |
| `artifact_path` | str | 全量日志落盘绝对路径 |
| `execution_time_ms` | int | 实际执行耗时（毫秒） |
| `timed_out` | bool | 是否因超时被硬杀 |
| `queue_wait_sec` | float | 本次等待配额的实际秒数 |
| `estimated_wait_sec` | float | 内存池给出的退避建议（`QUEUED` 时使用） |

**状态语义辨析**：

* `SUCCESS` / `FAILED` —— 进程正常结束，由 `exit_code` 区分（`0` / 非 `0`）；
* `TIMEOUT` —— 超时后进程**在宽限期内自行配合退出**；
* `KILLED` —— 宽限期耗尽被 `SIGKILL` **强制中断**；
* `QUEUED` —— 未执行，配额不足且等待预算耗尽。

> 之所以区分 `TIMEOUT` 与 `KILLED`：前者可能是"慢但正常"，后者一定是被强制中断，
> 两者对模型"该不该重试/拆小命令"的决策含义不同。

```json
{
  "status": "SUCCESS",
  "exit_code": 0,
  "distilled_stdout": "Compilation succeeded. Output: build/main",
  "distilled_stderr": "",
  "is_truncated": false,
  "artifact_path": "/abs/path/storage/artifacts/9b1e.../step_3_bash.log",
  "execution_time_ms": 1420,
  "timed_out": false,
  "queue_wait_sec": 0.0,
  "estimated_wait_sec": 0.0
}
```

### 1.2 健康检查：`GET /api/v1/health`

```json
{
  "status": "ok",
  "service": "bash_shell",
  "version": "0.1.0",
  "memory_pool": {
    "total_mb": 8192,
    "used_mb": 2048,
    "available_mb": 6144,
    "waiting_tasks": 0,
    "max_concurrent": 4,
    "active_tasks": 1,
    "completed_tasks": 37
  }
}
```

> `memory_pool` 字段由 `GlobalMemoryBudget.snapshot()` 直接导出（`Dict[str, Any]`），
> 上表为当前字段；Agent 的依赖探测（`api/routes/health.py`）就是打这个端点。

## 2. 错误码与降级契约

**成功与"命令失败"都走 200**：命令返回非零退出码不是服务端错误，而是业务结果，
必须让模型看到完整信息。HTTP 非 2xx 只用于"请求被拒绝或无法执行"。

| HTTP | 错误码 | 产生原因 | Agent 侧处理策略 |
| :--- | :--- | :--- | :--- |
| `200` | status=`SUCCESS`/`FAILED` | 命令执行结束（`exit_code` 区分成败） | 读蒸馏文本；非零退出码触发反思 |
| `200` | status=`TIMEOUT`/`KILLED` | 超时后被软退/强杀 | 作为确定性事实反馈，引导拆小命令或加超时 |
| `200` | status=`QUEUED` | 配额不足且等待预算耗尽 | 按 `estimated_wait_sec` 退避后重试 |
| `403` | `AUDIT_REJECTED` | 命中 `CommandAudit` 规则（详见 `03` §1.1） | 将安全红线提示反馈给模型，引导合规替代方案 |
| `422` | `PATH_ESCAPE_DETECTED` | 写入目标逃逸出 `workspace_root` | 提示路径越界，要求在工作区内操作 |
| `422` | `WORKSPACE_INVALID` | `workspace_root` 不存在或不是目录 | 提示工作区配置错误（通常是装配 bug） |
| `400` | `VALIDATION_ERROR` | 请求体不满足 DTO 约束（FastAPI 校验） | 装配层 bug，检查请求字段 |

**统一错误体**：

```json
{
  "error": {
    "code": "AUDIT_REJECTED",
    "message": "禁止递归强制删除根目录（rm -rf /）",
    "rule": "RM_RF_ROOT"
  }
}
```

> 📋 规划中（尚未实现）：`403 APPROVAL_REQUIRED` + `approval_details`（越级 HITL 审核），见 `03` §2。

## 3. Agent ToolLayer 客户端适配器 (`tools/builtin/bash.py`)

Agent 侧通过统一的 `AegisTool` 契约对接 Shell 服务。**必须实现 `invoke(args)`**
（而非自定义方法名）——这是 `ToolDispatcher` 调用工具的固定入口。

```python
from tools.core.protocol import AegisTool, ToolResult
from tools.core.http_client import ServiceClient
from agent_runtime.errors import DependencyUnavailableError


class BashTool(AegisTool):
    name = "bash"
    trust = "trusted"          # 本地受控执行，返回值可视为可信数据

    description = (
        "在目标工程目录中执行 Shell 命令（编译、测试、git、查看文件等）。"
        "命令以工作区根目录为工作目录执行；超长输出会自动落盘，只返回摘要与句柄。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的完整 Shell 命令"},
            "timeout_sec": {"type": "number", "description": "可选，本次超时秒数"},
        },
        "required": ["command"],
    }

    def __init__(self, client: ServiceClient, *, workspace_id: str,
                 workspace_root: str, task_id: str, default_timeout_sec: float = 60.0) -> None:
        self._client = client
        self._workspace_id = workspace_id
        self._workspace_root = workspace_root
        self._task_id = task_id
        self.timeout_sec = default_timeout_sec
        self._counter = itertools.count(1)   # 本任务内的 bash 调用序号，用于产物命名

    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        command = str(args.get("command", "")).strip()
        if not command:
            return ToolResult.failure("缺少 command 参数")

        payload = {
            "workspace_id": self._workspace_id,
            "workspace_root": self._workspace_root,
            "task_id": self._task_id,
            "step_id": next(self._counter),
            "command": command,
            "timeout_sec": float(args.get("timeout_sec") or self.timeout_sec),
        }

        try:
            data = await self._client.request_json(
                "POST", "/api/v1/shell/execute", payload=payload
            )
        except DependencyUnavailableError as exc:
            return ToolResult.failure(str(exc), tool=self.name)   # 不可达 → 计入连续错误

        if str(data.get("status")) == "QUEUED":
            return ToolResult(ok=True, content="命令已进入等待队列，请稍后重试。", meta={"queued": True})

        exit_code = data.get("exit_code")
        content = "\n".join(
            s for s in (data.get("distilled_stdout") or "", data.get("distilled_stderr") or "")
            if s.strip()
        ) or "（无输出）"

        return ToolResult(
            ok=exit_code == 0,
            content=content,
            exit_code=exit_code,
            artifact_path=data.get("artifact_path") or None,
            is_truncated=bool(data.get("is_truncated")),
            meta={"execution_time_ms": data.get("execution_time_ms")},
        )
```

**三个容易写错的点**（这也是本节此前版本的问题）：

1. `ToolResult` 的字段是 **`ok` / `content` / `meta`**，不是 `success` / `metadata`；
2. `ServiceClient` 暴露的是 **`request_json(method, path, payload=...)`**，没有 `.post()`；
3. 工具入口固定为 **`async def invoke(self, args: Mapping)`**，不是 `execute(command, timeout)`。

> 实现细节以 `src/tools/builtin/bash.py` 为准；本节示例为保证可读性做了精简。
