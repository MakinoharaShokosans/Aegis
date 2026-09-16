# AegisAgent Skills（专家领域技能）实施里程碑

> **对应设计规范**：`documents/agent_runtime/08_skills_management.md`  
> **责任模块**：`AegisAgent/src/agent_runtime/skills/` & `AegisAgent/src/tools/builtin/load_skill.py`  
> **核心原则**：两阶段渐进式披露、多源覆盖与安全隔离、SOP 结构化指导、零污染卸载。

---

## 一、架构定位与标准包规范

- [x] **Tool 与 Skill 职责边界划分**
  - [x] Tool 负责原子动作能力（"Can Do"，如 `bash`、`view_file`、`delegate_research`）
  - [x] Skill 负责领域专家方法论与排查 SOP（"How to Do Professionally"）
- [x] **标准 Skill 物理包目录规范**
  - [x] `SKILL.md`：YAML Frontmatter 元数据头 + SOP 正文
  - [x] `scripts/`：专用于提取、清洗和自动化分析的确定性辅助脚本目录
  - [x] `references/`：离线参考手册与 API 速查表目录
  - [x] `resources/`：模板与静态配置文件资产目录

---

## 二、强类型领域模型契约 (`agent_runtime/skills/models.py` & `registry.py`)

- [x] **`SkillSource` 来源字面量定义** (`builtin` / `global` / `workspace`)
- [x] **`SkillTrust` 信任级别契约** (`trusted` / `untrusted`)
- [x] **`SkillMetadata` 轻量元数据模型**
  - [x] `name`：技能唯一标识名
  - [x] `description`：一句话简要功能描述
  - [x] `triggers`：场景触发词列表
  - [x] `required_tools`：依赖的底层工具列表
  - [x] `skill_dir`：物理目录绝对路径
  - [x] `source`：技能物理来源标识
  - [x] `trust`：信任等级标注
  - [x] `high_privilege`：是否涉及高危工具布尔标记
  - [x] `warnings`：注入样态与安全告警列表
- [x] **`SkillPackage` 完整技能包模型**
  - [x] 持有 `metadata`
  - [x] `sop_content`：SOP 完整 Markdown 正文
  - [x] `scripts` / `references` / `resources` 资产文件路径索引映射表

---

## 三、多级目录扫描与覆盖优先级 (`registry.py`)

- [x] **三级目录发现机制**
  - [x] 优先级 1（最高）：工作区专属技能 `<workspace.root_path>/.aegis/skills/`
  - [x] 优先级 2：发行版内置技能包 `AegisAgent/src/skills/`（或自定义内置目录）
  - [x] 优先级 3（最低）：用户全局技能库 `~/.aegis/skills/`
- [x] **同名技能覆盖语义**
  - [x] 高优先级来源严格覆盖低优先级来源
  - [x] 覆盖时保留来源（`source`）与信任级别（`trust`）的精确追踪
- [x] **工作区作用域隔离**
  - [x] 工作区技能仅对当前目标工作区生效，严禁跨工作区污染泄漏

---

## 四、安全分级、信任边界与防御体系 (`registry.py` & `config.toml`)

- [x] **信任分级与默认拒绝（Default-Deny for Workspace Skills）**
  - [x] 内置技能（`builtin`）标记 `trusted`，默认启用（`allow_builtin = true`）
  - [x] 全局技能（`global`）标记 `trusted`，默认启用（`allow_global = true`）
  - [x] 工作区技能（`workspace`）标记 `untrusted`，**默认拒绝加载（`allow_workspace = false`）**
  - [x] 物理切断恶意开源仓库通过克隆即在 `.aegis/skills/` 静默注入系统提示词的攻击路径
- [x] **Frontmatter 静态扫描与风险标注**
  - [x] 集成 `guardrails/injection_guard.py` 静态扫描 `description` 与 `triggers`
  - [x] 命中间接注入特征时写入 `SkillMetadata.warnings` 进行审计可见化
- [x] **元数据长度防御截断**
  - [x] `description` 截断至 `max_description_chars`（默认 200 字符）
  - [x] `triggers` 截断至 `max_triggers`（默认 12 条）
- [x] **高危权限信号识别与预警**
  - [x] 检测 `required_tools` 与 `high_privilege_tools`（`bash` / `write_file` 等）交集
  - [x] 命中时置位 `high_privilege=True`，并在元数据与自省端点中显式标注警示

---

## 五、两阶段渐进式披露生命周期 (Progressive Disclosure)

- [x] **阶段一：系统提示词轻量清单常驻 (`build_prompt_summary`)**
  - [x] 仅导出 Name + 截断后的 Description
  - [x] 控制单条开销在 20~30 Token，百个技能开销稳定在低预算内
  - [x] 输出封装在 `<available_skills source="..." trust="...">` XML 安全信封中
  - [x] 系统提示词明确声明：技能 SOP 仅为流程指导，严禁用于提权或绕过安全护栏
- [x] **阶段二：按需即时挂载 (JIT Mounting via `load_skill`)**
  - [x] Agent 识别到特定场景时自主调用 `load_skill(skill_name)`
  - [x] 完整 SOP 正文按需动态拉取并封装在 `<skill_sop>` XML 信封中
  - [x] 自动展开可用辅助脚本的物理目录绝对路径（`skill_dir/scripts`）
- [x] **阶段三：任务终结零污染卸载 (Teardown & Eviction)**
  - [x] 庞大 SOP 仅存在于单任务的执行流中，不外溢至跨会话记忆库

---

## 六、内置工具接入与注册表集成 (`tools/builtin/load_skill.py`)

- [x] **`LoadSkillTool` 契约实现**
  - [x] 遵循 `AegisTool` 规范与 `ToolTrust.TRUSTED`
  - [x] 构造参数接收 `SkillsRegistry` 实例
  - [x] 输入参数通过 Pydantic 校验 `skill_name`
- [x] **优雅降级与提示**
  - [x] 请求未命中技能时返回结构化错误说明，不中断任务
  - [x] 请求成功时格式化输出 SOP 内容、辅助脚本与参考资料索引
- [x] **ToolRegistry 统一注册**
  - [x] `build_builtin_tools` 自动组装并注册 `load_skill` 工具

---

## 七、运行时配置、工作流与端点集成

- [x] **配置解析 (`config.toml` & `config.py`)**
  - [x] `[skills]` 配置节（`allow_builtin`, `allow_global`, `allow_workspace`, `max_description_chars`, `max_triggers`, `high_privilege_tools`）
- [x] **工作流依赖注入 (`workflow.py`)**
  - [x] `SkillsRegistry.from_workspace` 工厂方法随工作区环境初始化
  - [x] 注入 `ContextManager` 用于系统提示词装配
  - [x] 注入 `build_builtin_tools` 供主 Agent 调度
- [x] **HTTP 自省端点 (`api/routes/introspection.py`)**
  - [x] `GET /api/v1/skills`：返回已发现技能列表、来源、信任级、高权限预警及告警列表

---

## 八、质量保障与自动化测试验收

- [x] **单元测试覆盖**
  - [x] Skills 元数据解析与 YAML Frontmatter 校验测试
  - [x] 多级目录扫描与覆盖优先级测试（工作区 > 内置 > 全局）
  - [x] `allow_workspace = false` 默认拒绝安全策略测试
  - [x] `load_skill` 工具执行与 SOP 结构化输出测试
  - [x] XML 定界信封与系统提示词装配测试
- [x] **集成测试与回归**
  - [x] LangGraph 工作流中 Agent 调用 `load_skill` 的端到端闭环测试
  - [x] FastAPI `/api/v1/skills` 端点集成测试
  - [x] 全套测试套件 **76/76 测试全绿 (100% 通过率)**
