# AegisAgent 核心运行时单元测试路线图 (Unit Test Roadmap)

> **定位**：`AegisAgent` 核心调度宿主纯函数、算法契约、配置加载与状态校验的单元测试路线。
> **原则**：无网络 I/O、无外部进程派生、纯内存运行、输入输出 100% 确定性。

---

## 1. 现状盘点：纯函数与单元契约覆盖矩阵

| 目标源码模块 | 对应测试文件 | 状态 | 核心验证重点 |
| :--- | :--- | :---: | :--- |
| `guardrails/permission.py` | `tests/guardrails/test_permission.py` | `[x] [x]` | 权限三级归一化、工具名单分类、Bash 正则分类器、动作签名确定性 |
| `edges/after_tool_runner.py` | `tests/edges/test_edges.py` | `[x] [x]` | 路由判定纯函数：硬熔断转向 `END`，正常转向 `planner` |
| `edges/after_executor.py` | `tests/edges/test_edges.py` | `[x] [x]` | 路由分支：含工具调用转向 `tool_runner`，无工具调用转向 `evaluator` |
| `agent_runtime/config.py` | `tests/test_config.py`<br/>`tests/test_config_robustness.py` | `[x] [x]` | TOML 配置反序列化、Pydantic 启动期强校验、非法正则容错 |
| `agent_runtime/tokenizer.py` | `tests/test_tokenizer.py` | `[x] [x]` | Tiktoken 离线词表加载、消息结构分词计数、超长截断预警 |
| `agent_runtime/memory.py` | `tests/test_memory.py` | `[x] [x]` | 内存账本与配额计算、多轮任务状态栈纯函数突变 |
| `mcps/vetting.py` | `tests/mcps/test_vetting.py` | `[x] [x]` | MCP 工具描述静态白名单校验、高危关键词规则拦截 |
| `api/schemas.py` | `tests/api/test_schemas.py` | `[x] [x]` | Pydantic Request/Response 模型字段校验、枚举序列化 |

---

## 2. 细分测试用例规范

### 2.1 权限判定与规则分类器 (`tests/guardrails/test_permission.py`)
- **`normalize_level` 归一化**：
  - 合法字符串 (`"read_only"`, `"workspace_write"`, `"full_permissions"`) 正确透传；
  - 空值、非法枚举值安全回落至默认级别（`workspace_write`）。
- **`required_level_for` 判定优先级**：
  - 显式白名单工具优于通用命令匹配；
  - Bash 脚本分类器：`full_permission_patterns` 准确区分 `network_egress`（`curl`, `wget`, `ssh`）与 `global_env`（`sudo`, `chmod 777`）；
  - `workspace_write_patterns` 正确识别工作区内部文件写入；未命中时安全收敛为 `read_only`。
- **`action_signature` 散列稳定性**：
  - 参数字典键值乱序时，通过 `sort_keys=True` 保证相同调用签名唯一不变；
  - 不同参数必定产生互斥签名。

### 2.2 状态机边路由纯函数 (`tests/edges/test_edges.py`)
- **`route_after_tool_runner`**：
  - 当 `state["should_terminate"] is True` 时，直接路由至 `END`；
  - 工具正常执行完毕后，路由回 `planner` 重新对齐里程碑。
- **`route_after_executor`**：
  - 检测最后一条消息是否包含 `tool_calls`：存在工具调用派发至 `tool_runner`，否则派发至 `evaluator`。

### 2.3 配置解析与健壮性自检 (`tests/test_config_robustness.py`)
- **配置段落缺失保护**：`[permissions]`、`[models]` 段落缺失时抛出具象的 `ValidationError`，包含缺失字段路径；
- **非法正则隔离**：若某条规则写入非法语法（如 `[a-z`），`_compile()` 记录 Warning 并安全忽略该条，绝不影响同配置文件内其余规则。

### 2.4 Tokenizer 词表与分词计算 (`tests/test_tokenizer.py`)
- 离线加载 `cl100k_base` 与 `o200k_base` 编码器；
- 对包含 System、User、AIMessage 的多轮结构精准统计 Token 占用，误差范围 $\le 2$ tokens。

---

## 3. 验收标准与执行

- 模块分支覆盖率 $\ge 95\%$（`permission.py` 实测 99%）；
- 单测耗时 $\le 2.0$ 秒；
- 执行命令：
  ```bash
  cd /home/Skualeilu/Projects/Aegis/AegisAgent
  uv run pytest tests/guardrails/test_permission.py tests/edges/test_edges.py tests/test_config.py tests/test_tokenizer.py -v
  ```
