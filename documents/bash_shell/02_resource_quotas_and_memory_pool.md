# Bash 执行沙箱 - 物理资源配额与内存池规范

> **责任领域**：`AegisAgent/src/services/bash_shell/memory_pool.py` 与 `sandbox.py`  
> **核心原则**：Linux 内核级资源硬配额（虚拟内存/文件大小/CPU时间）、全局内存池协调、并发闸门与自适应排队。

---

## 1. 物理资源硬配额设计 (`resource.setrlimit`)

为防止程序失控导致宿主机宕机或磁盘被打满，在子进程启动瞬间（`preexec_fn` 钩子内），利用 Linux 内核级系统调用注入硬性资源限制：

| 限制维度 | 配置键（`[bash_shell]`） | 超限时的内核行为 | 防护目标 |
| :--- | :--- | :--- | :--- |
| `RLIMIT_AS`（虚拟内存） | `rlimit_as_mb` | 内存分配失败并触发 `ENOMEM`，进程被终止 | 防止失控进程触发 Linux 全局 OOM Killer，误杀宿主服务或 IDE |
| `RLIMIT_FSIZE`（单文件大小） | `rlimit_fsize_mb` | 写入超限时内核发送 `SIGXFSZ` 终止进程 | 防止死循环重定向生成数十 GB 日志填满物理磁盘 |
| `RLIMIT_CPU`（纯 CPU 耗时） | `rlimit_cpu_sec` | 超过阈值发送 `SIGXCPU` | 阻断挖矿类或无限密集计算 |

**为什么用 `setrlimit` 而不是 cgroup / Docker**：本项目的定位是**单机本地运行**。
`setrlimit` 是进程级、零依赖、零特权（无需 root、无需容器运行时）的内核接口，
在 `preexec_fn` 里注入即可，不引入部署复杂度。代价是它只约束**单进程**，
无法约束进程树聚合——这正是 §2 的内存池要补的那一环。

### 1.1 `preexec_fn` 注入实现

```python
import resource
import os

def _apply_rlimits(max_virtual_memory_bytes: int, max_file_size_bytes: int, max_cpu_sec: int):
    """在子进程 fork 后、exec 前注入内核配额限制"""
    # 1. 提升为独立进程组
    os.setsid()
    
    # 2. 限制最大虚拟内存
    if max_virtual_memory_bytes > 0:
        resource.setrlimit(
            resource.RLIMIT_AS, 
            (max_virtual_memory_bytes, max_virtual_memory_bytes)
        )
        
    # 3. 限制最大输出文件尺寸
    if max_file_size_bytes > 0:
        resource.setrlimit(
            resource.RLIMIT_FSIZE, 
            (max_file_size_bytes, max_file_size_bytes)
        )
        
    # 4. 限制纯 CPU 秒数
    if max_cpu_sec > 0:
        resource.setrlimit(
            resource.RLIMIT_CPU, 
            (max_cpu_sec, max_cpu_sec)
        )
```

---

## 2. 全局内存池与并发协调器 (`GlobalMemoryBudget`)

内核 `RLIMIT_AS` 是**单进程**上限（`rlimit_as_mb`），它约束不了"多个并发命令同时逼近各自上限"的叠加效应。
因此在服务层叠加了一个应用级的**内存池 + 并发闸门**：把"单进程配额"升级为"整机可预测的内存占用"。

### 2.1 架构原理

* **总池容量（`memory_pool_mb`）**：`config.toml` 配置，语义为"允许 Bash 服务占用的整机内存上限"；
* **并发上限（`max_concurrent`）**：同时执行的任务数闸门；
* **单任务预估消耗（`estimated_mb`，请求可选字段）**：调用方可显式声明预估占用；
  **未声明时取 `rlimit_as_mb`**（即"按最坏情况占满自己的内核配额来占用池"）；
* **同步原语**（`memory_pool.py`）：
  - `asyncio.Condition` 守护"已用配额"计数——**配额不足时等待而非失败**，这是排队语义的载体；
  - `asyncio.Semaphore(max_concurrent)` 限制同时执行数——控制并发度，避免抢锁风暴；
  - 两者分离的原因：配额是"按 MB 计量的资源"，并发是"按任务数计量的资源"，混用一个信号量会导致小任务被大任务饿死。

### 2.2 排队语义与调用方契约

| 场景 | 行为 | 对外表现 |
| :--- | :--- | :--- |
| 配额与并发均充足 | 立即获得执行凭证 | 正常执行 |
| 配额或并发不足，且 `queue_wait_sec > 0` | 在预算内等待，获得后执行 | 正常执行（响应含实际等待时长） |
| 配额或并发不足，且 `queue_wait_sec <= 0` | **立即返回，不阻塞** | `status = QUEUED` + `estimated_wait_sec` 退避建议 |

**为什么"排队"是返回 QUEUED 而不是占着 HTTP 连接等**：Bash 服务是 sidecar，
调用方（Agent 的 executor）一轮可能并发派发多个工具。若服务端挂起连接，
会连带占满 Agent 的连接池与工具派发槽位。返回 `QUEUED` 让**调用方**决定
"稍后重试还是放弃"，把退避决策留在更有全局视野的一侧。

### 2.3 核心接口签名 (`memory_pool.py`)

```python
class GlobalMemoryBudget:
    def __init__(self, total_mb: int, max_concurrent: int, default_task_mb: int) -> None: ...

    # --- 只读观测（供 /api/v1/health 与 QUEUED 响应）---
    def snapshot(self, estimated_mb: int | None = None) -> dict[str, Any]: ...
    def estimate_wait_sec(self, estimated_mb: int | None = None) -> float: ...
    def normalize(self, estimated_mb: int) -> int: ...       # 超过池总量时截断到池上限

    # --- 配额获取（三种语义）---
    async def acquire(self, estimated_mb: int) -> None: ...          # 一直等到获得
    async def try_acquire(self, estimated_mb: int) -> bool: ...      # 拿不到立即返回 False
    async def acquire_or_queue(self, estimated_mb: int, wait_sec: float) -> tuple[bool, float]: ...

    async def release(self, mb: int, *, duration_sec: float | None = None) -> None: ...
```

> 编排入口 `sandbox.run_command` 使用 `acquire_or_queue(need_mb, queue_wait_sec)`：
> 其中 `need_mb = estimated_mb if estimated_mb is not None else cfg.rlimit_as_mb`。

## 3. 防护效果总结

通过“内核底座 `setrlimit` + 应用层协调 `GlobalMemoryBudget`”的双层物理约束：
1. **彻底杜绝整机雪崩**：任何失控程序只会自身遭遇 `ENOMEM` 或 `SIGXFSZ` 退出，绝不波及宿主环境；
2. **多租户/多会话平稳运行**：在有限的单机硬件上实现平滑排队，提供确定性物理资源分配。
