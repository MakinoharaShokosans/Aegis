# Bash 执行沙箱 - 物理资源配额与内存池规范

> **责任领域**：`AegisAgent/src/services/bash_shell/memory_pool.py` 与 `sandbox.py`  
> **核心原则**：Linux 内核级资源硬配额（虚拟内存/文件大小/CPU时间）、全局内存池协调、并发闸门与自适应排队。

---

## 1. 物理资源硬配额设计 (`resource.setrlimit`)

为防止程序失控导致宿主机宕机或磁盘被打满，在子进程启动瞬间（`preexec_fn` 钩子内），利用 Linux 内核级系统调用注入硬性资源限制：

```text
┌────────────────────────┬─────────────┬────────────────────────────────────────────────────────┐
│ 限制维度                │ 默认硬配额   │ 超限内核行为与防护目标                                  │
├────────────────────────┼─────────────┼────────────────────────────────────────────────────────┤
│ RLIMIT_AS (虚拟内存)   │ 2048 MB     │ 内核返回 ENOMEM 异常，进程被终止；防止触发 Linux 全局  │
│                        │ (2 GB)      │ OOM Killer 误杀宿主服务或开发环境 IDE。                │
├────────────────────────┼─────────────┼────────────────────────────────────────────────────────┤
│ RLIMIT_FSIZE (文件大小) │ 50 MB       │ 写入超过 50MB 时内核发送 SIGXFSZ 信号终止进程；防止死  │
│                        │             │ 循环重定向生成数十 GB 巨型日志填满物理磁盘。           │
├────────────────────────┼─────────────┼────────────────────────────────────────────────────────┤
│ RLIMIT_CPU (纯CPU耗时) │ 300 秒      │ 纯用户态/内核态 CPU 运行超过阈值发送 SIGXCPU；阻断恶意 │
│                        │             │ 加密货币挖矿或无限密集数学计算。                       │
└────────────────────────┴─────────────┴────────────────────────────────────────────────────────┘
```

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

在单机本地运行多个 Agent 会话或并发工具调用时，单个命令 2GB 的配额若不受全局约束，4 个并发即可能占用 8GB 内存。因此在服务层引入了应用级的**内存池与并发闸门机制**。

### 2.1 架构原理
* **总池容量（`memory_pool_mb`）**：在 `config.toml` 中配置（默认 8192 MB）；
* **并发上限（`max_concurrent`）**：在 `config.toml` 中配置（默认 4 个）；
* **单任务预估消耗（`requested_mb`）**：每次命令提交时预估（默认 2048 MB）；
* **信号量与队列等待**：
  - 当可用内存池足以支付 `requested_mb` 且并发未达上限时，立即可获得执行槽位；
  - 配额不足时，任务进入 `asyncio.Event` 等待队列，向外部返回 `status: QUEUED` 与预计排队位置；
  - 任务完成后通过 `finally` 块释放配额，唤醒队列中的下一个等待者。

### 2.2 核心代码契约 (`memory_pool.py`)

```python
class GlobalMemoryBudget:
    def __init__(self, total_mb: int, max_concurrent: int):
        self.total_mb = total_mb
        self.available_mb = total_mb
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()

    async def acquire(self, requested_mb: int, timeout: float = 30.0) -> bool:
        """尝试申请内存预算与并发槽位"""
        await asyncio.wait_for(self.semaphore.acquire(), timeout=timeout)
        async with self._lock:
            if self.available_mb >= requested_mb:
                self.available_mb -= requested_mb
                return True
        # 内存不足时退还信号量
        self.semaphore.release()
        return False

    async def release(self, requested_mb: int) -> None:
        """任务完成，安全归还内存预算与并发槽位"""
        async with self._lock:
            self.available_mb = min(self.total_mb, self.available_mb + requested_mb)
        self.semaphore.release()
```

---

## 3. 防护效果总结

通过“内核底座 `setrlimit` + 应用层协调 `GlobalMemoryBudget`”的双层物理约束：
1. **彻底杜绝整机雪崩**：任何失控程序只会自身遭遇 `ENOMEM` 或 `SIGXFSZ` 退出，绝不波及宿主环境；
2. **多租户/多会话平稳运行**：在有限的单机硬件上实现平滑排队，提供确定性物理资源分配。
