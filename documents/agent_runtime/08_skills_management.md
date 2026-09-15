# 技能系统与渐进式披露规范 (Skills Management)

> **责任领域**：`AegisAgent/src/skills/` & `AegisAgent/src/agent_runtime/skills/`  
> **核心原则**：渐进式披露（Progressive Disclosure）、即时按需挂载（JIT Loading）、SOP 确定性指导、任务终结零污染卸载。

---

## 1. 架构定位：Skill 与 Tool 的本质区别

在 Aegis 系统中，严格划分 **Tool（基础工具）** 与 **Skill（专家技能）** 的职责边界：

* **Tool（基础原子工具）**：解决**“能做什么（Can Do）”**的问题，是系统的**动词**。
  - 例如：`bash`（执行命令）、`view_file`（读文件切片）、`rag_search`（检索代码）。
* **Skill（专家领域技能）**：解决**“如何专业地做（How to Do Professionally）”**的问题，是系统的**领域方法论（SOP）**。
  - 例如：`c_cpp_memory_leak_debugger`（内存泄漏排查技能）。它不是一个孤立的工具，而是一套组合使用 `bash`、`valgrind`、专属解析脚本与排查经验的完整工程流程包。

---

## 2. 标准 Skill 文件目录包解剖

每个 Skill 必须是一个独立的物理目录，遵循严格的包规范：

```text
skills/
└── <skill_name>/                     # 技能唯一标识（小写下划线）
    ├── SKILL.md                      # [必选] YAML 元数据头 + Markdown 标准作业程序 (SOP)
    ├── scripts/                      # [可选] 经过充分测试的确定性辅助脚本
    │   └── parse_report.py           # 专用于提取、清洗和格式化输出的脚本
    ├── references/                   # [可选] 领域离线参考手册（按需查阅，不常驻）
    │   └── cheatsheet.md             # 专业领域数据结构或 API 速查表
    └── resources/                    # [可选] 模版与静态配置资产
        └── template.conf             # 默认配置文件或压制文件模板
```

### 2.1 `SKILL.md` 规范模板

`SKILL.md` 顶部必须包含结构化的 YAML Frontmatter，正文严格遵循 SOP 编写：

```markdown
---
name: c_cpp_memory_leak_debugger
description: 专用于 C/C++ 内存泄漏、野指针与 Use-After-Free 问题的诊断。当编译或运行时出现段错误、AddressSanitizer 或 Valgrind 报警时调用。
triggers:
  - "segmentation fault"
  - "valgrind"
  - "AddressSanitizer"
  - "heap-use-after-free"
required_tools:
  - bash
---

# C/C++ 内存泄漏与野指针排查 SOP

## 1. 前置准备与编译重编译
若未携带调试符号，优先以 `-g -fsanitize=address` 重新编译目标：
```bash
make clean && CFLAGS="-g -fsanitize=address" make
```

## 2. 诊断执行与日志清洗
执行可执行文件，若生成详细 ASan 日志，调用本 Skill 自带脚本提取关键调用栈：
```bash
python {skill_dir}/scripts/parse_asan.py /tmp/asan.log
```

## 3. 常见陷阱与禁区 (Anti-Patterns)
- 严禁对未经 malloc/new 分配的栈上局部变量执行 free；
- 优先检查结构体生命周期是否早于其内部持有的指针。
```

---

## 3. 两阶段渐进式披露生命周期（Progressive Disclosure）

为了杜绝将数十个技能的数万字 SOP 一股脑塞进 Prompt 导致 Context 报废，系统严格执行**两阶段渐进式暴露机制**：

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        Skills 渐进式运行时流水线                       │
│                                                                        │
│  [阶段一：轻量元数据常驻] (System Prompt)                              │
│  - 仅注入 Skills 清单 (Name + 1句话 Description，约 20~30 Token/个)    │
│  - 无论有 10 个还是 100 个 Skills，总开销稳定在 1000 Token 以内        │
│                                                                        │
│  [阶段二：识别并按需即时挂载] (JIT Activation)                         │
│  - 用户提问命中技能场景 ➔ Agent 主动调用 load_skill(skill_name)        │
│  - 完整 SOP 动态载入当前任务微观 ExecutionContext (草稿纸)             │
│                                                                        │
│  [阶段三：辅助脚本安全执行] (Execution Sandbox)                        │
│  - Agent 按照 SOP 引导，调用 skill_dir/scripts/ 下的辅助脚本           │
│                                                                        │
│  [阶段四：任务终结即擦除] (Teardown & Eviction)                        │
│  - 任务结束交付结论后，庞大的 SOP 随 ExecutionContext 彻底销毁          │
│  - 下一次新会话完全干净，零污染外溢                                    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 多级目录扫描与覆盖优先级

运行时启动时扫描**三个**位置，同名技能由高优先级**严格覆盖**低优先级：

| 优先级 | 扫描根 | 定位 |
| :-- | :--- | :--- |
| 1（最高） | `<workspace.root_path>/.aegis/skills/` | 工作区（目标工程）自带的项目级技能，**仅对该工作区可见** |
| 2 | `AegisAgent/src/skills/` | 随发行版交付的**内置**官方技能包 |
| 3（最低） | `~/.aegis/skills/` | 用户全局技能库，本机跨项目通用 |

**内容与代码分离（重要）**：

- 上表三个根目录存放的是**技能内容包**（`SKILL.md` + `scripts/` + `references/` + `resources/`），属于**数据**，不含 Python 编排逻辑；
- 扫描、YAML frontmatter 解析与"可用技能清单"装配的**代码**位于 `AegisAgent/src/agent_runtime/skills/registry.py`；
- 二者不可混放（裁决依据：`10_directory_structure.md` 裁决项②）。

**隔离性**：工作区级技能只在对应工作区内生效，严禁跨工作区泄漏（与工作区记忆的隔离原则一致，`06` §6.1）。

---

## 5. 强类型代码契约设计

在 `AegisAgent/src/agent_runtime/skills/` 中的实现规范：

### 5.1 数据模型与清单装配

```python
from pathlib import Path
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class SkillMetadata(BaseModel):
    """技能轻量元数据 (常驻系统提示词)"""
    name: str
    description: str
    triggers: List[str] = Field(default_factory=list)
    required_tools: List[str] = Field(default_factory=list)
    skill_dir: Path

class SkillPackage(BaseModel):
    """完整技能包 (按需动态加载)"""
    metadata: SkillMetadata
    sop_content: str               # SKILL.md 正文 Markdown
    scripts: Dict[str, Path]       # 脚本名 -> 绝对路径
    references: Dict[str, Path]    # 参考文档名 -> 绝对路径
    resources: Dict[str, Path]     # 模版资源名 -> 绝对路径
```

### 5.2 技能加载器工具（Built-in Tool: `load_skill`）

作为 Agent 默认可调用的系统级工具注册到 `tool_layer`：

```python
class LoadSkillInput(BaseModel):
    skill_name: str = Field(description="要调取加载的专家技能唯一标识名称")

async def load_skill(input_data: LoadSkillInput, registry: "SkillsRegistry") -> str:
    """
    按需将特定技能的详细 SOP 和脚本路径动态拉入当前微观执行上下文
    """
    skill = registry.get_skill(input_data.skill_name)
    if not skill:
        return f"错误：未找到名为 '{input_data.skill_name}' 的专家技能。"
        
    return f"""
## 已成功挂载专家技能: [{skill.metadata.name}]
SOP 指引规范如下：
{skill.sop_content}

可用辅助脚本目录: {skill.metadata.skill_dir / 'scripts'}
请严格按照上述 SOP 展开诊断与修复！
"""
```

### 5.3 系统提示词轻量清单装配

在 `SessionContext` 组装系统提示词时，调用 `registry.get_prompt_summary()`：

```markdown
## 可用专家技能清单 (Available Skills)
当你识别到当前任务命中以下特定场景时，必须先通过 `load_skill(skill_name)` 获取专业 SOP，再按指导排查：
- `c_cpp_memory_leak_debugger`: 专用于 C/C++ 内存泄漏、野指针与 Use-After-Free 问题的诊断。
- `cmake_config_fixer`: 专用于 CMake 目标依赖缺失与编译器标志配置错误排查。
- `git_bisect_troubleshooter`: 专用于大型代码库历史回归 Bug 引入点的自动化二分排查。
```
