# AegisAgent 受控 Bash Shell 沙箱服务功能与设计里程碑

> **对应设计规范**：`documents/bash_shell/01~05`
> **责任模块**：`AegisAgent/src/services/bash_shell/` & `AegisAgent/src/tools/builtin/bash.py`
> **运行端口**：`:8002`（独立微服务进程）
> **核心原则**：PGID 进程组隔离、setrlimit 物理边界、高危指令正则审计、工作区根目录硬约束。
>
> **图例规范**：`[代码实现] [测试通过]`

---

## 一、进程生命周期与物理资源隔离 (`sandbox.py`)

- [x] [x] **PGID 独立进程组与孤儿进程治理**
  - [x] [x] 为每个执行命令分配全新 PGID（`os.setsid`），防止子进程逃逸
  - [x] [x] 两段式超时强制熔断机制：超时先发送 `SIGTERM` 优雅终止，超时未退出升级为 `SIGKILL` 强杀整个进程组
- [x] [x] **OS 级物理资源硬限制（`setrlimit`）**
  - [x] [x] 施加虚拟内存硬配额（`RLIMIT_AS`，默认 2GB），物理阻止 Fork 炸弹或内存耗尽崩溃
  - [x] [x] 施加最大 CPU 执行时间硬配额（`RLIMIT_CPU`）
- [x] [x] **内存池并发排队控制 (`memory_pool.py`)**
  - [x] [x] 动态内存估算与信号量排队机制，防止高并发导致宿主机 OOM

---

## 二、命令安全审计与路径沙箱 (`audit.py`)

- [x] [x] **三级权限分级管控与越级判定**（判定与闸门位于 **Agent 工具层**，见 `10` 裁决项㉑）
  - [x] [x] `read_only`（只读巡检）、`workspace_write`（默认工作区写）、`full_permissions`（全权限）三级定义
    —— 实现于 `agent_runtime/guardrails/permission.py`
  - [x] [x] 指令动作识别与越级行为判定（只读下写、工作区写入下网络推送/全局环境变更）
    —— 配置驱动的正则分类表（`[permissions]`），程序化构造亦有保守默认值
  - [x] [x] 越级挂起与人工审批（`interrupt()` → `/approve`｜`/reject`）+ 会话级永久放行白名单
    —— 闸门在 `nodes/tool_runner.py`；bash_shell 侧**只保留绝对红线**，不做权限分级（避免两套分类器漂移）
- [x] [x] **高危指令正则黑名单拦截（绝对硬红线）**
  - [x] [x] 拦截破坏性系统命令（如 `rm -rf /`、系统级重写、敏感系统路径写篡改）
  - [x] [x] 拦截 Fork 炸弹
  - [x] [x] 交互式挂起防护 —— **由结构性手段实现**：子进程 `stdin=DEVNULL`，
    交互式提示立即 EOF 快速失败；**不采用正则黑名单**（无法穷举且会误伤
    `sudo -n`、`DEBIAN_FRONTEND=noninteractive` 等合法用法），详见 `bash_shell/01` §5
- [x] [x] **工作区 CWD 严格边界与防路径逃逸**
  - [x] [x] 强制绑定当前工作区根目录为执行 cwd
  - [x] [x] 静态解析写入重定向（`>`、`>>`、`tee`）与路径参数，严禁逃逸越界至工作区外部目录

---

## 三、输出流式治理与微服务通信 (`sandbox.py` / `app.py` / `tools/builtin/bash.py`)

- [x] [x] **输出治理与离线落盘**
  - [x] [x] 分块流式捕获 stdout / stderr，防止缓冲区死锁
  - [x] [x] 超长执行日志与编译输出自动落盘并提取 Head/Tail 错误行
- [x] [x] **FastAPI 独立微服务与 Tool 适配器**
  - [x] [x] 暴露 `POST /api/v1/shell/execute` 独立 HTTP 契约
  - [x] [x] Agent 端通过 `BashTool` 与 `ServiceClient` 走连接池调用，支持重试与超时降级
