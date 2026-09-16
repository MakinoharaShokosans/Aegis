# Bash 执行沙箱 - 进程生命周期与隔离规范

> **责任领域**：`AegisAgent/src/services/bash_shell/sandbox.py`  
> **核心原则**：进程组隔离 (PGID)、两段式硬超时升级熔断、孤儿与僵尸进程全面治理。

---

## 1. 痛点分析与治理目标

在长周期工程排查与代码重构中，Agent 执行的 Shell 命令具有高度不可控性：
1. **死循环与假死**：模型可能编写出 `while(1)` 的 C 程序、无限递归脚本或阻塞在无应答的交互式提示符（如 `sudo` 密码输入、`apt-get` 确认）。
   其中**交互式挂起由结构性手段消除**（见 §5），而不是靠正则识别或超时兜底——
   超时是最后一道闸，不应该被用来处理本可避免的等待；
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
              ├── (t < timeout_sec) ──► 正常退出 → status = SUCCESS / FAILED
              │
    [ t = timeout_sec 触发超时 ]
              │
              ├──► 第一阶段：软终止 (Graceful Termination)
              │    向进程组发送 SIGTERM: os.killpg(pgid, signal.SIGTERM)
              │    允许程序执行善后清理（保存断点、关闭临时文件句柄）
              │
    [ 等待软退出窗口: sigterm_grace_sec（配置项，默认 2s）]
              │
              ├── (宽限期内退出) ──► status = TIMEOUT，正常回收资源
              │
              └──► 第二阶段：硬诛杀 (Hard Kill Escalation)
                   向进程组发送 SIGKILL: os.killpg(pgid, signal.SIGKILL)
                   内核直接剥夺资源，强行注销整个进程组 → status = KILLED
```

**状态取值**（唯一真源为 `sandbox.ShellStatus`）：`SUCCESS` / `FAILED` / `TIMEOUT` / `KILLED` / `QUEUED`。
注：`TIMEOUT` 表示"超时后自行配合退出"，`KILLED` 表示"宽限期耗尽被 SIGKILL 强杀"——
两者对模型的含义不同（前者可能是慢但正常，后者一定是被强制中断）。

### 3.1 核心代码契约

**关键点：绝不用 `process.communicate()`**。它会把全部输出缓冲在内存中，
既违背 §04 的"流式落盘、全量日志不驻留内存"原则，又会在超时取消时
**丢弃已产生的输出**——而那恰恰是排障最需要的部分。

正确做法是：两个独立协程用 `read(chunk)` 流式读取并分块写入日志文件，
超时后先杀进程组、再**排空管道**（`_settle_pumps`），最后才回收进程：

```python
# 1) 流式泵：stdout / stderr 各一个协程，边读边落盘（不驻留内存）
async def _pump(reader: asyncio.StreamReader, handle) -> None:
    while True:
        chunk = await reader.read(settings.stream_chunk_bytes)
        if not chunk:
            break
        await asyncio.to_thread(handle.write, chunk)   # 磁盘 I/O 不阻塞事件循环

pumps = [
    asyncio.create_task(_pump(proc.stdout, out_handle)),
    asyncio.create_task(_pump(proc.stderr, err_handle)),
]

# 2) 超时 → 两段式硬杀（宽限期取自 [bash_shell].sigterm_grace_sec）
try:
    await asyncio.wait_for(proc.wait(), timeout=timeout_sec)
except asyncio.TimeoutError:
    await _terminate_process_group(proc, settings.sigterm_grace_sec)

# 3) 排空残留数据后再收尾，避免管道未读满导致的状态丢失
await _settle_pumps(pumps, grace_sec=settings.sigterm_grace_sec)
```

> 详见 `sandbox.py` 的 `_pump_stream` / `_terminate_process_group` / `_settle_pumps`。
> 本节的代码是**契约示意**，实现以源码为准。

---

## 4. 孤儿与僵尸进程防御准则

1. **统一回收（Wait-Reaping）**：无论是超时强杀还是异常中断，必须调用 `await process.wait()` 读取退出状态，防止在 Linux 进程表内残留 `<defunct>` 僵尸进程条目；
2. **非阻塞 I/O 读取**：使用 `asyncio.subprocess.PIPE`，底层绑定异步文件描述符，避免死锁缓冲区；
3. **排空管道**：进程被杀后仍可能有未读数据在管道缓冲区中，必须等两个泵协程收敛（`_settle_pumps`）再关闭文件句柄；
4. **生命周期绑定**：每次命令执行均为临时沙箱实例，任务结束后对应 PGID 完全销毁。

---

## 5. 非交互隔离（结构性消除"交互式挂起"）

**问题**：`sudo` 密码、`apt-get` 确认、`ssh` 首次连接指纹确认等提示会**无限等待输入**。

**解法（已实现）**：子进程创建时绑定 `stdin=asyncio.subprocess.DEVNULL`：

```python
proc = await asyncio.create_subprocess_shell(
    command,
    cwd=str(workspace_root),
    stdin=asyncio.subprocess.DEVNULL,   # ← 交互式提示立即得到 EOF，快速失败而非挂起
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    preexec_fn=_apply_limits_and_setsid,
)
```

**为什么不用正则识别"裸 sudo / 无 -y 包安装"**：

* 正则无法穷举交互式场景（`ssh` 指纹、`gpg` 口令、`read` 内建、程序自定义 prompt）；
* 误报代价高——`sudo -n`、`DEBIAN_FRONTEND=noninteractive apt-get install` 都是合法用法；
* `DEVNULL` 是**语义级**保证：没有 stdin，就不可能出现"等待输入"，无需枚举。

被拒绝的交互式命令会立刻以非零退出码返回，错误信息（如 `sudo: a password is required`）
由 §04 的失败态蒸馏提取，模型据此改用 `-n` 或非交互参数。
