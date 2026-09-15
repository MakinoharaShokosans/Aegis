# 工作区、多会话与上下文治理规范 (Workspace, Multi-Session & Context Management)

> **责任领域**：`AegisAgent/src/agent_runtime/memory/` & `AegisAgent/src/agent_runtime/context.py`  
> **核心原则**：工作区一等公民（多工作区支持）、一个工作区多会话（1:N 级联从属）、物理工程路径强绑定、跨会话长期记忆共享、单会话高低水位动态压缩（80% 触发 / 40% 对话对齐）、确定性物理 Token 计量。

---

## 1. 架构定位：三级实体层级拓扑 (Three-tier Entity Hierarchy)

在实际工程研发场景中，开发者往往同时维护多个独立的代码库或工程项目，并在同一个项目下开启多条排查/开发任务线。因此，Aegis 确立严格的三级实体从属拓扑与两级记忆作用域：

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                   Aegis 实体层级与记忆生命周期拓扑 (Multi-Workspace)             │
│                                                                                  │
│  [第一级: 工作区] Workspace (一等公民：支持开多个独立项目工作区)                 │
│  - 物理绑定: 对应磁盘上的真实项目根目录 root_path (如 /home/user/project_a)      │
│  - 唯一标识: workspace_id (UUID 或 root_path 规范化哈希)                         │
│  - 元数据表: workspaces (workspace_id, name, root_path, description, timestamps) │
│  - 共享记忆: workspace_memories (项目架构定论、编码规范、全局踩坑黑名单)          │
│  - 机制职责: 跨会话持久共享；决定工具层默认工作目录 (cwd)；统一管理会话生命周期  │
│                                      │                                           │
│                                      ▼ (1 : N 级联从属)                           │
│  [第二级: 会话] Session (一个工作区下可开辟 N 个独立对话会话)                     │
│  - 任务锚定: 针对该工作区内某一具体任务或功能特性的持续交互主线                  │
│  - 唯一标识: session_id (UUID)，外键 workspace_id 强从属                         │
│  - 元数据表: sessions (session_id, workspace_id, title, timestamps)              │
│  - 情境记忆: session_memories (本会话已压缩阶段摘要、上轮操作实体句柄)            │
│  - 机制职责: 隔离不同任务的局部认知；驱动会话级 80%/40% 高低水位对话压缩          │
│                                      │                                           │
│                                      ▼ (1 : N 级联从属)                           │
│  [第三级: 对话轮次] Dialogue Turn (一个会话包含 N 轮原子人机交互记录)            │
│  - 原子交互: 一轮完整的交互包含 User 提问与 Assistant 答复                        │
│  - 流水载体: session_turns 表 (id, session_id, role, content, token_count)       │
│  - 切分机制: 水位线以上的活跃轮次送入 Prompt，水位线以下的溢出轮次进入压缩归档   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 工作区（Workspace）生命周期与管理规范

### 2.1 实体模型定义
工作区是 Aegis 的一等公民，具备完全独立的元数据与工程配置：
* **`workspace_id`**：全局唯一标识符（由客户端生成 UUID 或基于规范化绝对路径计算 SHA-256 哈希）；
* **`name`**：可读性友好的项目名称（如 `"Aegis Agent Core"`, `"Linux 6.1 Kernel"`）；
* **`root_path`**：工作区在本地文件系统的绝对路径（如 `"/home/user/workspace/aegis"`）。系统建立唯一索引，防止多实例并发冲突；
* **`description`**：工作区工程描述（如技术栈、目标、架构背景）；
* **`created_at` / `updated_at`**：生命周期时间戳。

### 2.2 工作区生命周期接口（Workspace Lifecycle APIs）
底层存储引擎与顶层管理器必须提供以下闭环操作：
1. **`create_or_get_workspace(name, root_path, description)`**：幂等创建或按物理路径检索已有工作区；
2. **`get_workspace(workspace_id)`**：根据 ID 获取工作区详情；
3. **`get_workspace_by_path(root_path)`**：根据绝对路径快速反查关联工作区；
4. **`list_workspaces()`**：按最近更新时间倒序枚举系统全部纳管的工作区；
5. **`update_workspace(workspace_id, ...)`**：修改工作区元数据（名称、描述等）；
6. **`delete_workspace(workspace_id)`**：物理销毁工作区，依托 SQLite `ON DELETE CASCADE` 级联清理其下属的所有会话（`sessions`）、记忆体（`session_memories`）、流水记录（`session_turns`）及工作区记忆（`workspace_memories`）。

### 2.3 物理工作目录绑定与隔离
* **环境定位**：当用户在某个工作区发起指令时，`ExecutionContext` 必须将该工作区的 `root_path` 作为工具调用（Bash Shell、Git 命令、文件读写、AST 语法树解析）的基准工作目录（`cwd`）；
* **路径越界防御**：工具执行器校验所有目标路径，防止逃逸出 `root_path` 破坏其他工作区文件。

---

## 3. 会话（Session）在工作区内的生命周期

### 3.1 1:N 级联从属机制
* 一个工作区可以包含多个会话，但一个会话**必须且只能归属于一个工作区**；
* 会话提供独立的交互隔离：开发新特性开 `Session A`，重构老模块开 `Session B`，二者互不干扰各自的活跃对话流与局部认知记忆。

### 3.2 会话管理接口
1. **`create_session(workspace_id, title)`**：在指定工作区下创建新会话；
2. **`list_sessions_by_workspace(workspace_id)`**：按时间倒序拉取指定工作区下的所有会话列表；
3. **`get_session(session_id)`**：查询特定会话的元信息及其所属工作区；
4. **`delete_session(session_id)`**：删除指定会话，级联清理其对应的对话流水与会话记忆。

---

## 4. 统一上下文装配标准公式 (Context Ingestion)

每次向大模型发起请求时，装配器（`ContextManager`）按以下严格顺序动态组装 Prompt：

$$\text{Final Context} = \underbrace{\text{[系统提示词]}}_{\text{自带} + \text{项目规则}} + \underbrace{\text{[工作区环境与全局记忆]}}_{\text{项目根路径} + \text{架构定论} + \text{避坑黑名单}} + \underbrace{\text{[会话已压缩记忆]}}_{\text{单会话情境沉淀}} + \underbrace{\text{[活跃对话流水]}}_{\text{低水位线以上的完整对话}} + \text{[当前输入]}$$

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        最终拼装视界 (Assembled Context)                │
│                                                                        │
│  1. 系统提示词 (System Prompts)                                        │
│     ├── 1.1 内置行为纪律 (prompts/system.md, ReAct 思考与工具规范)     │
│     └── 1.2 用户项目规则 (如 CLAUDE.MD / 编码风格约束)                │
│                                                                        │
│  2. 工作区全局共享视界 (Workspace Shared Context)                      │
│     ├── 2.1 工作区基本元数据 (名称、物理根路径 root_path)              │
│     ├── 2.2 项目架构与核心入口定论 (confirmed_architecture)            │
│     ├── 2.3 项目编码与工程规范 (project_conventions)                   │
│     └── 2.4 全局避坑黑名单 (global_failed_attempts)                     │
│                                                                        │
│  3. 会话已压缩记忆 (Session Compressed Memory)                         │
│     ├── 3.1 本次排查与任务阶段背景摘要 (summary)                        │
│     ├── 3.2 本会话探索出的局部事实与踩坑 (confirmed_facts / attempts)  │
│     └── 3.3 上轮核心操作对象句柄 (last_action_target)                   │
│                                                                        │
│  4. 活跃对话流水 (Active Dialogue Stream)                              │
│     └── 处于安全水位线以内的未压缩完整人机对话对 (User 问 + Agent 答)  │
│                                                                        │
│  5. 当前用户输入 (Current User Input)                                  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 单会话内部：高低水位对话对齐压缩算法（Watermark Compaction）

### 5.1 核心参数与物理度量标准
坚决摒弃粗糙的“固定轮数切片”，基于物理 Token 高低水位进行动态治理：
* **`session_token_limit`**：单会话 Token 硬预算（从 `config.toml` 配置，例如 `32000`）；
* **`compaction_high_watermark = 0.80`**：**高水位触发线（80%）**。当当前活跃对话累积 Token 数达到 $32000 \times 80\% = 25600$ 时，触发压缩；
* **`compaction_ratio = 0.40`**：**目标压缩基准线（40%）**。目标将最古老的约 $32000 \times 40\% = 12800$ Token 移出活跃窗口并进行压缩提炼；
* **分词计量**：使用 `tiktoken` 库在本地快速对每轮文本进行绝对精确的分词计算，零网络延迟与零外部依赖。

### 5.2 对话完整性对齐切片算法（Turn-Aligned Slicing）
**绝对不可在句子、单词或单条消息中间粗暴截断**！必须以“完整的用户提问 + 智能体交付响应（User + Assistant 对）”为原子边界对齐：

```text
当前活跃对话总 Token: 26,500 (超过 80% 触发线!)
目标截取压缩量: ~10,600 Token (最古老的 40%)

最古老 ──► [第 1 轮: User 问 + Agent 答]  (2,000 Token)  ──┐
           [第 2 轮: User 问 + Agent 答]  (6,500 Token)    ├── 累计 11,500 Token
           [第 3 轮: User 问 + Agent 答]  (3,000 Token)  ──┘   (最贴近 40% 的完整对话边界!)
────────── ✂️ 严格在第 3 轮 Assistant 响应之后对齐切断 (Clean Cut) ────────────────────
保留活跃 ──► [第 4 轮: User 问 + Agent 答]  (4,000 Token)
           [第 5 轮: User 问 + Agent 答]  (11,000 Token)
           ...

压缩执行与水位恢复：
1. 提取 [第 1~3 轮] 作为 overflow_turns；
2. 调度 Fast 模型提炼总结，就地合并入该会话的 session_memories；
3. 更新会话的水位标记: compacted_until_turn_id = 第 3 轮最后一条记录的主键 ID；
4. 活跃窗口仅保留 [第 4 轮 之后]，活跃 Token 骤降至 15,000 (恢复到 47% 安全低水位)；
5. 释放出的 53% 空间为后续多轮交互提供了充裕的会话呼吸空间。
```

---

## 6. 跨会话机制：工作区全局共享记忆治理

### 6.1 资产沉淀与隔离
* **工作区内共享**：`workspace_memories` 归属于特定 `workspace_id`。同一个工作区下创建的所有 Session，在装配 Prompt 时均注入同一份架构事实、编码规范与踩坑黑名单；
* **跨工作区严格隔离**：`Workspace A`（如 C++ 后端项目）的事实绝不泄漏给 `Workspace B`（如 Python 数据分析项目）。

### 6.2 记忆上浮机制（Promotion Protocol）
* 在某个单会话中，若探索出对整个项目具有长效指导意义的技术事实（如“编译时需额外传递 `-lpthread`”）：
  - 既可通过 Agent 自主反思识别；
  - 也可通过调用 `promote_fact_to_workspace(workspace_id, fact, category)` 或 `record_global_failure(workspace_id, failure)` 向上沉淀；
* 写入后，该工作区下的后续会话及并行会话均能立刻感知。

---

## 7. SQLite 底层表结构完整规范 (`storage/aegis_meta.db`)

```sql
PRAGMA foreign_keys = ON;

-- 1. 工作区实体主表 (一等公民: 支持多工作区独立运作)
CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,             -- 工作区唯一标识 (UUID 或 SHA-256 哈希)
    name TEXT NOT NULL,                        -- 工作区可读名称 (如 "Aegis Core")
    root_path TEXT NOT NULL,                   -- 本地物理工程根目录绝对路径
    description TEXT DEFAULT '',               -- 工作区背景或项目描述
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_root ON workspaces(root_path);

-- 2. 工作区全局长期记忆表 (与工作区 1:1 强从属，跨会话共享)
CREATE TABLE IF NOT EXISTS workspace_memories (
    workspace_id TEXT PRIMARY KEY,             -- 关联工作区标识
    project_conventions TEXT DEFAULT '[]',     -- JSON 数组: 项目编码与工程规范
    confirmed_architecture TEXT DEFAULT '[]', -- JSON 数组: 核心架构定论
    global_failed_attempts TEXT DEFAULT '[]', -- JSON 数组: 全局避坑黑名单
    updated_at REAL NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE
);

-- 3. 会话元数据主表 (隶属于工作区，1:N 级联从属)
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,               -- 会话 UUID
    workspace_id TEXT NOT NULL,                -- 所属工作区唯一标识 (外键)
    title TEXT DEFAULT '',                     -- 会话主题/排查目标
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sessions_ws ON sessions(workspace_id);

-- 4. 对话轮次流水表 (隶属于会话，1:N 级联从属，带精确物理 Token 缓存)
CREATE TABLE IF NOT EXISTS session_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,                  -- 所属会话 (外键)
    role TEXT NOT NULL,                        -- 'user' | 'assistant'
    content TEXT NOT NULL,                     -- 对话正文
    token_count INTEGER NOT NULL DEFAULT 0,    -- 该轮次物理 Token 数 (tiktoken 计算缓存)
    timestamp REAL NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_session_turns_active ON session_turns(session_id, id ASC);

-- 5. 单会话已压缩情境记忆表 (包含水位指针，1:1 隶属于会话)
CREATE TABLE IF NOT EXISTS session_memories (
    session_id TEXT PRIMARY KEY,               -- 关联会话 (外键)
    compacted_until_turn_id INTEGER DEFAULT 0, -- 标记已压缩到的 turn_id (此 ID 之前为已压缩)
    summary TEXT DEFAULT '',                   -- 本会话阶段摘要
    confirmed_facts TEXT DEFAULT '[]',         -- JSON 数组: 本会话探索出的局部事实
    failed_attempts TEXT DEFAULT '[]',         -- JSON 数组: 本会话踩坑记录
    last_action_target TEXT DEFAULT '{}',      -- JSON 对象: 上轮操作核心实体 (文件/符号)
    updated_at REAL NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
```

---

## 8. 优雅降级与非阻塞防御

1. **Token 计算降级**：若分词器因特殊未收录字符解析异常，回退至字符粗算保底（`len(text) // 2`），记录 debug 日志，绝不阻断流程；
2. **压缩过程非关键路径**：压缩调用在交接点执行。遭遇 Fast LLM 超时或格式异常，记录 `logger.warning`，水位线不向前推进，原样保留对话，确保主交互高可用；
3. **工作区级联完整性**：删除工作区时强制开启 SQLite 外键级联检查，自动清理全部从属资产，绝不残留无主孤儿数据。
