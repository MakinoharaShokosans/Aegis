# Aegis Bash Shell 执行沙箱 - 实施技术规范索引

> **责任领域**：`AegisAgent/src/services/bash_shell/`（同工程独立微服务，默认监听 `127.0.0.1:8002`）  
> **核心原则**：进程组级物理隔离 (PGID)、两段式硬超时熔断 (SIGTERM->SIGKILL)、Linux 内核物理配额 (2GB/50MB)、工作区根路径强绑定 (CWD)、海量输出流式落盘与结构化提炼。

---

## 1. 文档拓扑结构与技术规范

| 文档序号 | 技术领域 | 核心规范与实现重点 |
| :--- | :--- | :--- |
| [01_process_lifecycle_and_isolation.md](./01_process_lifecycle_and_isolation.md) | **进程生命周期与隔离** | `asyncio.create_subprocess_shell`、`os.setsid` 独立进程组 (PGID)、两段式硬超时熔断 (SIGTERM->SIGKILL)、孤儿进程与僵尸进程全面防御 |
| [02_resource_quotas_and_memory_pool.md](./02_resource_quotas_and_memory_pool.md) | **物理资源配额与内存池** | Linux `resource.setrlimit` 内核级约束（2GB 虚拟内存 / 50MB 单文件 / CPU 秒数）、`GlobalMemoryBudget` 进程级内存池、信号量并发闸门与等待队列 |
| [03_command_audit_and_path_sandbox.md](./03_command_audit_and_path_sandbox.md) | **高危审计与工作区沙箱** | `CommandAudit` 危险命令正则前置拦截、工作区 `root_path` 严格绑定 (CWD)、路径越界逃逸校验 (`Path.resolve()`)、执行目录与落盘目录彻底解耦 |
| [04_output_governance_and_artifacts.md](./04_output_governance_and_artifacts.md) | **输出流式治理与离线卸载** | `StreamReader` 异步流式分块读取、全量输出落盘 `storage/artifacts/{task_id}/`、成功状态 Head 20/Tail 30 行提取、失败状态核心报错关键字检索与错误自愈引导 |
| [05_http_api_and_client_contract.md](./05_http_api_and_client_contract.md) | **服务契约与客户端适配** | FastAPI 路由契约 (`POST /api/v1/shell/execute`)、`ShellExecuteRequest/Response` 强类型 DTO、状态自省与 Agent ToolLayer (`tools/builtin/bash.py`) 适配 |

---

## 2. 核心架构拓扑

```text
 Agent Runtime (通过 tools/builtin/bash.py 经 HTTP 调用)
                          │  入参携带 workspace_id + workspace_root + task_id + command
                          ▼
             [ 1. CommandAudit 前置拦截 ]
               ├── 命中正则黑名单 (rm -rf /, mkfs, 写入系统关键目录) ──► 立即返回 403 阻断警告
               └── 审计通过 ──► 进入资源调度
                          │
                          ▼
        [ 2. GlobalMemoryBudget 并发与内存协调池 ]
          ├── 剩余配额充足 ──► 扣减内存预算，获得执行凭证
          └── 配额不足 ──► 任务入队等待，通知预计等待时长
                          │
                          ▼
            [ 3. Subprocess Sandbox 物理隔离沙箱 ]
             ├── os.setsid 建立独立进程组 (PGID)
             ├── resource.setrlimit 注入内核物理配额:
             │    ├── RLIMIT_AS: 2GB 虚拟内存 (防触发宿主 OOM Killer)
             │    ├── RLIMIT_FSIZE: 50MB (防死循环日志写满磁盘)
             │    └── RLIMIT_CPU: 纯 CPU 时间上限
             ├── cwd 强绑定: Workspace.root_path (目标工程绝对路径)
             └── 路径穿越校验: 写入目标必须落在 root_path 子树内
                          │
         ┌────────────────┴────────────────┐
         ▼ (若超出 timeout_sec)             ▼ (正常或报错退出)
   两段式硬超时熔断                StreamReader 异步流式分块读取
   os.killpg(pgid, SIGTERM)                 │
   等待 2s 未退 -> SIGKILL                  ▼
   清理全部孤儿衍生进程            [ 4. 全量日志离线卸载 (Offloading) ]
                                   写入 storage/artifacts/{task_id}/step_{step_id}_bash.log
                                            │
                                            ▼
                                   [ 5. 观察值结构化感知提炼 (Distillation) ]
                                   ├── 退出码 == 0: Head 20 + Tail 30 行 + 证据句柄
                                   └── 退出码 != 0: 报错关键字 (error/fatal/segfault) + 退出码
                                            │
                                            ▼
                          构造 ShellExecuteResponse 返回给 Agent 进行推理与修正
```

---

## 3. 代码映射一览

* **配置定义**：[`src/services/bash_shell/settings.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/services/bash_shell/settings.py)（读取 `config.toml` 中 `[bash_shell]` 段）
* **命令审计**：[`src/services/bash_shell/audit.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/services/bash_shell/audit.py)
* **并发与内存池**：[`src/services/bash_shell/memory_pool.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/services/bash_shell/memory_pool.py)
* **沙箱与执行引擎**：[`src/services/bash_shell/sandbox.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/services/bash_shell/sandbox.py)
* **FastAPI 接入层**：[`src/services/bash_shell/app.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/services/bash_shell/app.py)
* **服务启动入口**：[`src/services/bash_shell/__main__.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/services/bash_shell/__main__.py)
* **客户端调用端点**：[`src/tools/builtin/bash.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/tools/builtin/bash.py)
