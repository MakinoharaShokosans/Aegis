---
aliases:
  - Pydantic
  - 数据校验与设置库
  - 强类型数据契约
tags:
  - tech-stack
  - python
  - validation
  - data-contract
  - schema
package: "pydantic"
version: ">=2.13.5,<3.0.0"
project_role: "系统数据契约总闸门，负责 Agent 全局状态模型、工具入参 Schema、API 请求响应体以及 TOML 配置的强类型解析与物理校验"
entrypoints:
  - "AegisAgent/src/agent_runtime/state.py"
  - "AegisAgent/src/agent_runtime/config.py"
  - "AegisAgent/src/agent_runtime/api/schemas.py"
---

# Pydantic 辅助检索与理解指南

> [!info] 什么是 Pydantic
> **生活化比喻**：Python 本身是一门“动态弱类型”语言，函数传参默认就像一个敞开大门的仓库，谁都可以往里面塞数字、字符串甚至是 None。Pydantic 就像是守在数据大门口的**“极其严苛的高速智能安检仪”**：无论外面传来多么混乱的 JSON 字典，经过它扫描时，不仅会严格检查每个字段的类型、范围和必填性，还会自动将合规数据清洗打包为强类型的 Python 原生对象；一旦发现违规字段，立刻就地报警并指出精确到字符的错误原因。

---

## 1. 小白心智模型（1分钟看懂）

- **解决的核心痛点**：如果不使用 Pydantic，处理外部请求或 LLM 生成的 JSON 时，需要手写几十行冗长繁琐的 `if "task_id" not in data or not isinstance(data["task_id"], str): raise ...`，稍有不慎漏掉一个字段校验，就会在深层业务逻辑中引发难以调试的 `KeyError` 或 `TypeError`。
- **一句话本质**：Pydantic v2 是一个**基于 Rust 内核（pydantic-core）的高性能数据校验与数据转换引擎**。
- **两大核心物理机制**：
  1. **BaseModel（数据契约蓝图）**：通过标准的 Python 类型注解声明数据结构，兼具校验、文档生成与序列化能力。
  2. **BaseSettings（环境与配置装载器，来自 pydantic-settings）**：将 `.env` 环境变量或 `config.toml` 文件内容自动解析映射为强类型配置对象。

---

## 2. 本项目中的角色与调用链路

- **在本项目的位置**：全局数据契约与校验层（Data Contract & Validation Layer）。
- **核心入口文件**：
  - 核心领域模型（Milestone, FailedAttempt）：[`AegisAgent/src/agent_runtime/state.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/state.py)
  - 系统分层配置模型（AegisConfig）：[`AegisAgent/src/agent_runtime/config.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/config.py)
  - HTTP API 请求响应契约：[`AegisAgent/src/agent_runtime/api/schemas.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/api/schemas.py)
  - RAG 检索参数与响应契约：[`AegisRAG/src/api/schemas.py`](file:///home/Skualeilu/Projects/Aegis/AegisRAG/src/api/schemas.py)
- **典型执行流转链路**：
  ```text
  外部 HTTP JSON / LLM 工具调用字符串
                 │
                 ▼
     Pydantic 模型实例化与自动类型转换
                 │
        ┌────────┴────────────────────────┐
        ▼                                 ▼
   [校验通过]                         [字段缺失/类型不合规]
  转为强类型对象注入 AgentState       抛出 RequestValidationError
  或下发给具体 Python 工具执行        直接拦截并返回友好错误定位
  ```

---

## 3. 核心 Symbol 速查字典（类 / 函数 / 属性 / 装饰器）

### `BaseModel`（核心类）

- **通俗职责**：数据契约基类。所有自定义的数据模型、请求体、响应体必须继承它。
- **常用特性**：支持类属性类型注解、默认值、自动生成 `__init__`、数据转字典与 JSON 字符串。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/state.py:L66`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/state.py#L66)
- **最小实战代码**：
  ```python
  from pydantic import BaseModel, Field

  class Milestone(BaseModel):
      id: int = Field(description="里程碑序号（自增，从 1 开始）")
      title: str = Field(description="里程碑标题")
      description: str = Field(default="", description="达成标准与验收说明")
      status: str = Field(default="pending", description="当前状态")
  ```
- **关键注意点**：Pydantic v2 中获取字典使用 `.model_dump()`，获取 JSON 使用 `.model_dump_json()`，不要再写 v1 的 `.dict()` 或 `.json()`。

---

### `Field`（字段配置函数）

- **通俗职责**：精细化约束单个字段的元数据、默认值、数值范围、正则模式以及文档描述说明。
- **参数说明**：
  - `default`: 默认值（非必填时设置）。
  - `default_factory`: 动态默认值构造函数（如 `list`、`dict`）。
  - `description`: 字段的语义描述（会被导出至 LLM Tool Call 的 JSON Schema 中供大模型理解）。
  - `ge` / `le`: 大于等于 / 小于等于的数值约束。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/state.py:L69`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/state.py#L69)、[`AegisAgent/src/agent_runtime/config.py:L40`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/config.py#L40)
- **最小实战代码**：
  ```python
  from pydantic import BaseModel, Field

  class RuntimeGuardrailsConfig(BaseModel):
      max_steps: int = Field(default=25, ge=1, le=100, description="单任务最大步数上限")
      consecutive_errors_limit: int = Field(default=3, ge=1, description="连续报错熔断阈值")
  ```

---

### `BaseSettings`（配置基类，来自 `pydantic_settings`）

- **通俗职责**：系统级设置容器，能够自动从环境变量、`.env` 文件或外部解析好的字典中读取配置，并进行强类型转换。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/config.py:L31`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/config.py#L31)、[`AegisAgent/src/services/bash_shell/settings.py:L25`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/services/bash_shell/settings.py#L25)
- **最小实战代码**：
  ```python
  from pydantic_settings import BaseSettings, SettingsConfigDict

  class BashShellSettings(BaseSettings):
      model_config = SettingsConfigDict(env_prefix="AEGIS_SHELL_", env_file=".env", extra="ignore")
      host: str = "127.0.0.1"
      port: int = 8002
      timeout_sec: int = 60
  ```

---

### `field_validator` / `model_validator`（校验装饰器）

- **通俗职责**：自定义业务校验钩子。`field_validator` 校验单个字段值，`model_validator` 跨字段联合校验整个对象。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/config.py:L85`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/config.py#L85)
- **最小实战代码**：
  ```python
  from pydantic import BaseModel, field_validator

  class HostConfig(BaseModel):
      host: str

      @field_validator("host")
      @classmethod
      def forbid_wildcard_host(cls, v: str) -> str:
          if v == "0.0.0.0":
              raise ValueError("安全红线：工具链具备 Shell 执行能力，严禁监听 0.0.0.0！")
          return v
  ```

---

## 4. 本项目典型用法与实操范式

### 范式 1：LLM 工具入参声明与自动生成 JSON Schema
```python
# 路径：AegisAgent/src/tools/core/schema.py
from pydantic import BaseModel, Field

class FileReadArgs(BaseModel):
    file_path: str = Field(description="工作区内拟读取的目标文件相对路径")
    offset: int = Field(default=1, ge=1, description="起始行号（从 1 开始）")
    limit: int = Field(default=200, le=500, description="单次最大读取行数")

# 导出供 OpenAI / LangChain 注册给 LLM 的标准工具结构体
tool_definition = {
    "name": "read_file",
    "description": "按行读取工作区中的代码或文本文件",
    "parameters": FileReadArgs.model_json_schema()
}
```

### 范式 2：HTTP 请求体验证与序列化响应
```python
# 路径：AegisAgent/src/agent_runtime/api/routes/tasks.py
from fastapi import APIRouter
from pydantic import BaseModel

class TaskSubmitRequest(BaseModel):
    task_goal: str
    workspace_id: str
    permission_level: str = "workspace_write"

@router.post("/tasks", response_model=TaskOut)
async def submit_task(body: TaskSubmitRequest):
    # body 已经过 Pydantic 严格校验，所有属性均为强类型保障
    task_id = await registry.create_task(body.workspace_id, body.task_goal)
    return TaskOut(task_id=task_id, status="queued")
```

---

## 5. 新手易错陷阱与排坑指南

> [!warning] 陷阱 1：可变对象（list/dict）使用普通默认值
> **现象**：`class MyModel(BaseModel): tags: list = []` 虽在 Pydantic v2 中被允许，但如果在不同实例间直接修改可能会造成状态混淆或意外赋值。
> **正解**：对于集合类型，推荐使用 `Field(default_factory=list)` 声明全新的实例副本。

> [!warning] 陷阱 2：Pydantic v1 与 v2 API 混用
> **现象**：调用 `.dict()`、`.json()`、`@validator` 或 `class Config` 时抛出废弃警告或运行错误。
> **正解**：本项目锁定 Pydantic v2（`>=2.13.5`），全面使用全新 API：
> - 导出字典：`model.model_dump()`（替代 `.dict()`）
> - 导出 JSON：`model.model_dump_json()`（替代 `.json()`）
> - 类配置：`model_config = SettingsConfigDict(...)`（替代内部 `class Config`）
> - 字段校验器：`@field_validator`（替代 `@validator`）

> [!warning] 陷阱 3：TypedDict 与 BaseModel 混淆使用
> **现象**：在 LangGraph 状态定义处继承了 `BaseModel` 导致 Checkpoint 序列化或增量更新（Reducer）报错。
> **正解**：LangGraph 的全局 `AgentState` 在本项目中是 `TypedDict`（见 [`state.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/state.py#L99)），而具体的业务实体（`Milestone`、`FailedAttempt`）才是 `BaseModel`。不可将两者颠倒。
