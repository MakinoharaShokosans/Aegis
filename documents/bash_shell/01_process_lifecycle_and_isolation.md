# Bash 执行沙箱 - 进程生命周期与隔离规范

> **责任领域**：`AegisAgent/src/services/bash_shell/sandbox.py`  
> **核心原则**：进程组隔离 (PGID)、两段式硬超时升级熔断、孤儿与僵尸进程全面治理。

---

## 1. 痛点分析与治理目标

在长周期工程排查与代码重构中，Agent 执行的 Shell 命令具有高度不可控性：
1. **死循环与假死**：模型可能编写出 `while(1)` 的 C 程序、无限递归脚本或阻塞在无应答的交互式提示符（如 `sudo` 密码输入、`apt-get` 确认）；
2. **多级衍生孤儿进程（Orphan Processes）**：`make`、`npm`、`docker build` 或复杂 Shell 管道会派生孙进程。若仅使用常规 `proc.kill()`，操作系统仅杀掉顶层 Shell 包装进程，派生出的后台子进程会脱离管控成为孤儿进程，持续侵占 CPU 和内存；
3. **事件循环饥饿**：主服务是基于 Python `asyncio` 的异步服务，子进程阻塞不可抢占主事件循环。

治理目标：**任何执行必须置于独立进程组内，支持两段式强制熔断，执行完毕后系统内零悬挂衍生进程。**

---

## 2. 进程组隔离机制 (Process Group ID)

### 2.1 `os.setsid` 会话与进程组创建
启动子进程时，通过 `preexec_fn=os.setsid`，在操作系统层面为新进程创建全新的 Session 和独立的进程组（Process Group）：

```python
import os
import asyncio

process = await asyncio.create_subprocess_shell(
    cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=str(workspace_root),
    preexec_fn=os.setsid,  # 核心：将子进程提升为独立进程组首长 (PGID == PID)
)
```

### 2.2 信号广播原则
向进程发送信号时，绝不使用 `os.kill(pid, sig)`，而是向负数 PID 或通过 `os.killpg` 发送信号，确保信号无遗漏广播到整个进程树：

$$\text{kill}(\text{pgid}) \implies \forall p \in \text{ProcessGroup}(\text{pgid}), \quad \text{signal}(p)$$

---

## 3. 两段式超时升级熔断协议 (Two-Stage Escalation)

当命令物理挂钟执行时间超过 `timeout_sec`（默认 60s）时，触发确定性熔断阶梯：

```text
       命令启动 (t = 0)
              │
              ├── (t < timeout_sec) ──► 正常退出
              │
    [ t = timeout_sec 触发超时 ]
              │
              ├──► 第一阶段：软终止 (Graceful Termination)
              │    向进程组发送 SIGTERM: os.killpg(pgid, signal.SIGTERM)
              │    允许程序执行善后清理（保存断点、关闭临时文件句柄）
              │
    [ 等待软退出窗口: GRACE_PERIOD = 2.0 秒 ]
              │
              ├── (2s 内退出) ──► 记录 TIMED_OUT 并正常回收资源
              │
              └──► 第二阶段：硬诛杀 (Hard Kill Escalation)
                   向进程组发送 SIGKILL: os.killpg(pgid, signal.SIGKILL)
                   内核直接剥夺资源，强行注销整个进程组，杜绝任何抵抗
```

### 3.1 核心代码契约

```python
try:
    stdout_bytes, stderr_bytes = await asyncio.wait_for(
        process.communicate(), 
        timeout=timeout_sec
    )
except asyncio.TimeoutError:
    pgid = os.getpgid(process.pid)
    logger.warning(f"命令执行超时 (>{timeout_sec}s)，向进程组 {pgid} 发送 SIGTERM")
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    try:
        # 等待 2 秒善后窗口
        await asyncio.wait_for(process.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        logger.error(f"进程组 {pgid} 在 SIGTERM 后 2s 仍未退出，升级为 SIGKILL 强杀")
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
```

---

## 4. 孤儿与僵尸进程防御准则

1. **统一回收（Wait-Reaping）**：无论是超时强杀还是异常中断，必须调用 `await process.wait()` 读取退出状态，防止在 Linux 进程表内残留 `<defunct>` 僵尸进程条目；
2. **非阻塞 I/O 读取**：使用 `asyncio.subprocess.PIPE`，底层绑定异步文件描述符，避免死锁缓冲区；
3. **生命周期绑定**：每次命令执行均为临时沙箱实例，任务结束后对应 PGID 完全销毁。
