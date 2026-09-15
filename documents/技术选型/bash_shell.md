# 架构决策记录：受控 Bash Shell 执行沙箱与输出治理服务

> **状态**：已定稿 (Accepted)
> **责任领域**：`AegisAgent/src/services/bash_shell/`（**同工程子系统**，独立进程，默认监听 `127.0.0.1:8002`）
> **核心目标**：为 Agent 提供安全、确定、具备硬超时、物理资源配额与输出防溢出治理的代码编译与实验执行沙箱。
>
> **v2 修订记录**：① 执行工作目录（cwd）由"锁定临时目录"改为**工作区 `root_path`**（见 §2.3），修正了与原方案的自相矛盾——Agent 的职责是修改目标工程，锁死到临时目录会导致任务无法完成；② 产物与轨迹命名统一由 `{run_id}` 改为 `{task_id}`，对齐 `AgentState` 契约；③ 明确本服务为**同工程子系统**而非独立子工程（裁决记录见 `10_directory_structure.md` 裁决项③⑦）。

---

## 1. 架构总览与执行流转拓扑

```text
 Agent Runtime (通过 httpx 调用 /api/v1/shell/execute)
                          │  入参携带 workspace_id + workspace_root + task_id
                          ▼
        [ CommandAudit ] ──► 高危破坏性命令前置正则拦截
                          │ (通过校验)
                          ▼
        [ Subprocess Sandbox ]
         ├── os.setsid 建立独立进程组 (PGID)
         ├── resource.setrlimit: 内存 2GB / 文件 50MB / CPU 时间
         ├── cwd = Workspace.root_path  (目标工程根目录)
         └── 路径越界校验: 任何写入必须落在 root_path 之内
                          │
        ┌────────────────┴────────────────┐
        ▼ (若执行超时)                     ▼ (正常完成)
两段式进程组硬杀                 异步流式读取 stdout / stderr
SIGTERM (等待 2s) -> SIGKILL              │
                                          ▼
                         [ 全量日志落盘 (Offloading) ]
                         storage/artifacts/{task_id}/step_{step_id}_bash.log
                                          │
                                          ▼
                         [ Distilled Observation 提炼 ]
                         - 成功：Head 20行 + Tail 30行 + 证据句柄
                         - 失败：关键字过滤 (error, fatal, segfault) + Exit Code
                                          │
                                          ▼
                         返回给 Agent 进行推理与自我修正
```

> **关键解耦**：**执行目录（cwd）与落盘目录是两个不同的位置**。cwd 是用户的目标工程（会被真实修改），落盘目录是 Aegis 自己的 `storage/artifacts/`（只存日志与产物）。混淆二者是本服务历史上最大的设计错误。

---

## 2. 核心技术决策与权衡依据

### 2.1 进程生命周期与孤儿进程治理

* **痛点**：模型可能编写死循环 C 程序（如 `while(1)`），或执行产生多级派生子进程的复杂 Makefile。普通 `kill(pid)` 只能杀掉父进程，残留的孤儿进程会长期耗尽系统资源。
* **治理方案**：
  1. 采用 Python **`asyncio.create_subprocess_shell`** 保证执行非阻塞；
  2. 启动时配置 `preexec_fn=os.setsid`，为该执行分配独立的进程组 ID（PGID）；
  3. **两段式超时熔断**：配置 `timeout_sec`（默认 60s）。一旦超时，先向进程组发送 `SIGTERM`（`os.killpg(pgid, signal.SIGTERM)`），等待 2 秒未退出则升级为 `SIGKILL`，**彻底清退所有衍生孤儿进程**。

### 2.2 Linux 物理资源硬配额：选用 `resource (setrlimit)` + 全局队列管理

* **痛点**：防止死循环程序耗尽系统内存引发全局崩机，或无休止写入日志撑满磁盘。
* **治理方案**：
  利用 Linux 系统调用设置单任务物理边界：
  - **`RLIMIT_AS` (虚拟内存)**：上限 2GB。超限时内核自动返回 `ENOMEM`，程序崩溃并报错，杜绝触发 Linux 宿主机的全局 OOM Killer 杀掉主服务；
  - **`RLIMIT_FSIZE` (单文件大小)**：上限 50MB，防止死循环输出巨型日志文件写满磁盘；
  - **`RLIMIT_CPU` (CPU 秒数)**：限制最大纯 CPU 运算时长。
* **并发资源协调**：
  - **全局内存池（Global Memory Budget）**：服务启动时配置总可用内存池（例如宿主机 16GB，分配 8GB 给 Bash 服务）；
  - **任务队列与等待机制**：新任务到达时检查剩余可用配额，不足时进入等待队列，向调用方返回 `status: QUEUED` 与预估等待时间；
  - **资源回收与释放**：任务完成后立即释放占用的配额，唤醒队列中的下一个任务；
  - 确保本地单机环境下多个 Agent 任务有序执行，避免资源争抢导致系统崩溃。

### 2.3 工作区沙箱与前置命令审计（Workspace Sandbox）

* **治理方案**：
  1. **工作目录绑定工作区（Workspace-bound CWD）**：执行前将子进程 `cwd` 设置为**该任务所属工作区的 `root_path`**（目标工程绝对路径），使 `make`、`git`、编译器能够真实作用于用户工程。工作目录由 Agent 随请求下发并通过 `workspace_id` 反查校验，服务端**不得**接受任意客户端路径；
  2. **路径越界防护（Path Escape Guard）**：所有显式的写入/删除目标路径在派发前规范化（`Path.resolve()`），若最终路径不在 `root_path` 子树内，立即拒绝并返回 `422 PATH_ESCAPE_DETECTED`，防止逃逸到其他工作区或系统目录；
  3. **产物落盘隔离**：日志与产物一律写入 Aegis 自身的 `storage/artifacts/{task_id}/`，**与 cwd 解耦**，避免污染用户工程的工作区（用户工程内只应出现 Agent 有意修改的源码与补丁）；
  4. **高危指令正则黑名单（CommandAudit）**：在命令派发前进行前置语法拦截（拦截 `rm -rf /`、`mkfs`、敏感系统文件改动等），直接返回强类型安全警告，引导模型更换合规命令。

### 2.4 海量输出治理与离线卸载（Observation Offloading & Distillation）

* **痛点**：编译 Linux 内核模块或运行压力测试可能产生上万行日志，直接喂入模型会导致 Context Window 爆炸与模型”中间迷失”。
* **治理方案**：
  1. **无损全量异步流式落盘**：`stdout` 与 `stderr` 通过 `StreamReader` 分块读取，完整写入 `storage/artifacts/{task_id}/step_{step_id}_bash.log`；
  2. **结构化感知的分级提炼（Structure-Aware Distillation）**：
     - **结构化输出（JSON/YAML/XML）**：优先尝试解析并验证完整性，避免截断破坏语法结构；若解析失败再降级为文本处理；
     - **成功状态（Exit Code == 0）**：提取头部 20 行 + 尾部 30 行，中间提示省略行数并附带文件句柄；
     - **失败状态（Exit Code != 0）**：优先提取含有 `error:`, `fatal:`, `warning:`, `undefined reference`, `Segmentation fault` 等关键行，附带退出码与修复建议，引导模型实现精准的**错误自愈（Self-Correction）**。

### 2.5 服务接口契约

暴露 `POST /api/v1/shell/execute`，返回包含 `exit_code`, `distilled_stdout`, `distilled_stderr`, `is_truncated`, `artifact_path`, `execution_time_ms` 的强类型响应对象。

请求体需携带定位执行上下文的三要素：

```json
{
  "workspace_id": "ws_...",
  "workspace_root": "/home/user/projects/target",   // 服务端以 workspace_id 反查校验，二者必须一致
  "task_id": "9b1e...",
  "step_id": 7,
  "command": "make -j4",
  "timeout_sec": 60
}
```

**装配约束**：本服务为同工程子系统，可依赖 `config`，但**禁止 import `agent_runtime`**（见 `10_directory_structure.md` §5 依赖方向矩阵）。
