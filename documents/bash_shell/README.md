# Aegis Bash Shell 执行沙箱 - 实施技术规范索引

> **责任领域**：`AegisAgent/src/services/bash_shell/`（同工程独立微服务，默认监听 `127.0.0.1:8002`）  
> **核心原则**：进程组级物理隔离 (PGID)、两段式硬超时熔断 (SIGTERM->SIGKILL)、Linux 内核物理配额、工作区根路径强绑定 (CWD)、海量输出流式落盘与结构化提炼。
>
> ### 实现状态图例（**阅读前必看**）
>
> | 标记 | 含义 |
> | :--- | :--- |
> | ✅ | **已实现**，且与本节描述一致（可在对应源码文件核对） |
> | 📋 | **规划中，尚未实现**。仅记录设计意图，**不得**据此认为系统具备该能力 |
>
> 本批规范的原则：**配置值一律不在文档中硬编码**，均以 `config.toml` 的
> `[bash_shell]` 段为唯一真源；文档只说明语义与默认值。

---

## 1. 文档拓扑结构与技术规范

| 文档序号 | 技术领域 | 状态 | 核心规范与实现重点 |
| :--- | :--- | :--: | :--- |
| [01_process_lifecycle_and_isolation.md](./01_process_lifecycle_and_isolation.md) | **进程生命周期与隔离** | ✅ | `asyncio.create_subprocess_shell`、`os.setsid` 独立进程组 (PGID)、`stdin=DEVNULL` 非交互隔离、两段式硬超时熔断 (SIGTERM->SIGKILL)、孤儿进程防御 |
| [02_resource_quotas_and_memory_pool.md](./02_resource_quotas_and_memory_pool.md) | **物理资源配额与内存池** | ✅ | Linux `resource.setrlimit` 内核级约束（`rlimit_as_mb` / `rlimit_fsize_mb` / `rlimit_cpu_sec`）、`GlobalMemoryBudget` 内存池、并发闸门与等待队列 |
| [03_command_audit_and_path_sandbox.md](./03_command_audit_and_path_sandbox.md) | **高危审计与工作区沙箱** | ✅ / 📋 | ✅ `CommandAudit` 七条规则前置拦截（403）、工作区 `root_path` 绑定 (CWD)、路径越界校验、执行目录与落盘目录解耦<br>📋 **三级权限分级管控**与**越级人工审核（HITL）**——设计已记录，**尚未实现** |
| [04_output_governance_and_artifacts.md](./04_output_governance_and_artifacts.md) | **输出流式治理与离线卸载** | ✅ | `StreamReader` 异步流式分块读取、全量输出落盘 `storage/artifacts/{task_id}/`、成功态 Head/Tail 提取、失败态报错关键字检索与自愈引导 |
| [05_http_api_and_client_contract.md](./05_http_api_and_client_contract.md) | **服务契约与客户端适配** | ✅ | FastAPI 路由契约 (`POST /api/v1/shell/execute`)、`ShellExecuteRequest/Result` 强类型 DTO、`GET /api/v1/health` 自省、Agent (`tools/builtin/bash.py`) 适配 |

---

## 2. 核心架构拓扑

```text
 Agent Runtime (通过 tools/builtin/bash.py 经 HTTP 调用)
                          │  入参携带 workspace_id + workspace_root + task_id + command
                          ▼
             [ 1. CommandAudit 前置审计 ]  ✅ 已实现
               ├── 命中七条高危规则 (rm -rf /, mkfs, dd 裸写, 关机重启, fork 炸弹,
               │    敏感系统路径写入, 递归改根权限) ──► 抛 AuditRejected，HTTP 403
               └── 审计通过 ──► 进入资源调度
             📋 规划中：三级权限分级 + 越级 HITL 人工审核（尚未实现，见 03 §2）
                          │
                          ▼
        [ 2. GlobalMemoryBudget 并发与内存协调池 ]
          ├── 剩余配额充足 ──► 扣减内存预算，获得执行凭证
          └── 配额不足 ──► 任务入队等待，通知预计等待时长
                          │
                          ▼
            [ 3. Subprocess Sandbox 物理隔离沙箱 ]
             ├── os.setsid 建立独立进程组 (PGID)
             ├── stdin 绑定 DEVNULL：交互式提示立即 EOF 失败，不会挂住
             ├── resource.setrlimit 注入内核物理配额（数值取自 [bash_shell]）:
             │    ├── RLIMIT_AS   ← rlimit_as_mb   (防触发宿主 OOM Killer)
             │    ├── RLIMIT_FSIZE ← rlimit_fsize_mb (防死循环日志写满磁盘)
             │    └── RLIMIT_CPU  ← rlimit_cpu_sec
             ├── cwd 强绑定: Workspace.root_path (目标工程绝对路径)
             └── 路径穿越校验: 写入目标必须落在 root_path 子树内
                          │
         ┌────────────────┴────────────────┐
         ▼ (若超出 timeout_sec)             ▼ (正常或报错退出)
   两段式硬超时熔断                StreamReader 异步流式分块读取
   os.killpg(pgid, SIGTERM)                 │
   等待 sigterm_grace_sec 未退 -> SIGKILL    ▼
   清理全部孤儿衍生进程            [ 4. 全量日志离线卸载 (Offloading) ]
                                   写入 storage/artifacts/{task_id}/step_{step_id}_bash.log
                                            │
                                            ▼
                                   [ 5. 观察值结构化感知提炼 (Distillation) ]
                                   ├── 退出码 == 0: Head + Tail 行（行数取自配置）+ 证据句柄
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

---

## 4. 配置项唯一真源

所有可调参数位于 `AegisAgent/config/config.toml` 的 `[bash_shell]` 段，**文档不重复其数值**：

| 配置键 | 语义 | 被谁消费 |
| :--- | :--- | :--- |
| `timeout_sec` | 单命令默认硬超时 | `sandbox.run_command` |
| `sigterm_grace_sec` | SIGTERM → SIGKILL 宽限期 | `sandbox._terminate_process_group` |
| `rlimit_as_mb` / `rlimit_fsize_mb` / `rlimit_cpu_sec` | 内核物理配额 | `sandbox` 的 `preexec_fn` |
| `memory_pool_mb` / `max_concurrent` | 全局内存池与并发闸门 | `memory_pool.GlobalMemoryBudget` |
| `artifacts_dir` | 全量日志落盘根目录 | `sandbox` / `settings.artifacts_root` |
| `stream_chunk_bytes` | 管道流式读取分块大小 | `sandbox` 流式读取循环 |
| `distill_head_lines` / `distill_tail_lines` | 成功态 Head/Tail 行数 | `sandbox` 蒸馏 |
| `distill_max_keyword_lines` | 失败态关键字行上限 | `sandbox` 蒸馏 |
| `structured_sniff_max_bytes` | 结构化输出完整性嗅探缓冲上限 | `sandbox` 蒸馏 |

> 后四项为**可选调优项**：`settings.py` 提供内置默认值，可在 TOML 中覆盖。
