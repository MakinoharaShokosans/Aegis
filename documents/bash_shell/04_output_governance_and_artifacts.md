# Bash 执行沙箱 - 输出流式治理与离线卸载规范

> **责任领域**：`AegisAgent/src/services/bash_shell/sandbox.py` 与 `AegisAgent/src/agent_runtime/guardrails/observation_pruner.py`  
> **核心原则**：异步流式分块读取、全量长输出离线物理落盘、结构化感知提炼、错误自愈信息高密度保留。

---

## 1. 痛点：输出海量化与上下文爆炸

在运行真实编译或大型项目测试时，一次 `cmake .. && make -j` 或全量回归测试可能产生数千甚至数万行输出：
* 若直接将原始日志全量喂入 LLM 上下文，会导致单步请求消耗数万 Token，迅速击穿物理预算；
* 触发大模型的“中间迷失”（Lost in the Middle）现象，丢失真正关键的编译报错行；
* 极端情况下直接击穿端点的输入 Token 上限导致 API 报错（如 HTTP 400 Context Length Exceeded）。

因此，必须在执行层与运行时之间建立**无损物理落盘 + 观察值提炼卸载（Observation Offloading & Distillation）**双轨通道。

---

## 2. 异步流式分块读取 (StreamReader)

子进程产生的 `stdout` 与 `stderr` 通过 `asyncio.StreamReader` 异步分块读取，防止进程输出填满操作系统管道缓冲区（通常为 64KB）导致子进程挂死：

```python
async def _read_stream(stream: asyncio.StreamReader) -> bytes:
    chunks = []
    while True:
        chunk = await stream.read(65536) # 64KB 分块读取
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)
```

---

## 3. 全量日志离线物理落盘 (Artifact Offloading)

无论是成功还是失败的执行，原始未经截断的输出**永远完整落盘保存**，为离线评测、人工审计与调试提供坚实证据：

* **存储路径**：`storage/artifacts/{task_id}/step_{step_id}_bash.log`
* **格式规范**：包含执行元数据头（命令、CWD、环境变量注入、执行耗时、退出码）及完整原始标准输出/标准错误：

```text
================================================================================
Aegis Bash Execution Record
Task ID:     9b1e7c54-46c5-4428-a408-dbcbcf123456
Step ID:     5
Command:     gcc -Wall -O2 src/main.c -o build/main
CWD:         /home/user/projects/aegis_target
Exit Code:   1
Duration:    1240 ms
Timestamp:   2026-09-15 16:30:22 UTC
================================================================================
--- STDOUT ---
...
--- STDERR ---
src/main.c: In function 'init_buffer':
src/main.c:42:15: error: 'BUFFER_SIZE' undeclared (first use in this function)
...
```

---

## 4. 观察值结构化感知提炼 (Structure-Aware Distillation)

向 LLM 上下文注入的观察值（`observation`）必须经过高信噪比提炼：

### 4.1 成功执行状态（Exit Code == 0）

采用 **Head + Tail 黄金窗口**，行数由配置项决定（默认 `distill_head_lines = 20`、
`distill_tail_lines = 30`，可在 `[bash_shell]` 覆盖）：

* 保留开头的 `distill_head_lines` 行：通常包含构建配置、版本声明与环境初始化；
* 保留末尾的 `distill_tail_lines` 行：通常包含最终编译成功输出、产物路径或测试汇总结果（如 `Passed 48/48 tests`）；
* 中间被略过的部分明确提示省略行数，并告知全量日志磁盘句柄：

```text
[构建配置启动...]
(前 N 行内容，N = distill_head_lines)
... [已省略中间 1,280 行编译输出，完整日志已归档至 storage/artifacts/.../step_5_bash.log] ...
(末尾 M 行汇总，M = distill_tail_lines)
[100%] Built target main_executable
```

### 4.2 失败执行状态（Exit Code != 0）

优先保证**故障自愈（Self-Correction）**所需的信息密度，提取最具解释力的报错片段：

1. 提取命中高危关键字的行（`error:`、`fatal:`、`Segmentation fault`、`core dumped`、
   `undefined reference`、`cannot find -l` 等）；
2. **关键字行数上限为 `distill_max_keyword_lines`**（默认 200）。超限时会在摘要中
   显式标注"关键字行已截断"——因为失败场景下关键字行可能刷屏，若不设上限，
   蒸馏结果本身就会撑爆上下文，违背本节的初衷；
3. 保留末尾 `distill_tail_lines` 行作为上下文结束符（编译类工具的最终结论通常在尾部）；
4. 输出包含退出码（`Exit Code`），确保 Agent 能迅速对症下药。

### 4.3 结构化输出完整性嗅探

若输出是 JSON / YAML 等结构化格式，**优先保证语法完整**而不是按行裁剪
（截断会破坏语法，模型无法解析）：

* 嗅探缓冲上限为 `structured_sniff_max_bytes`（默认 256 KiB）；
* 完整且可解析 → 原样返回；
* 超出嗅探上限或解析失败 → 降级为 §4.1 / §4.2 的文本蒸馏路径。

### 4.4 流式读取分块

管道读取分块大小为 `stream_chunk_bytes`（默认 64 KiB）。
它与蒸馏参数无关，只影响"边读边落盘"的吞吐与内存占用——
分块越小内存峰值越低，越大系统调用越少。
