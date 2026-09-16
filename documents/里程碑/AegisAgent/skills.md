# AegisAgent Skills（专家领域技能）系统功能与设计里程碑

> **对应设计规范**：`documents/agent_runtime/08_skills_management.md`  
> **核心原则**：渐进式披露、多源覆盖与安全隔离、SOP 结构化指导、零污染卸载。

---

## 一、技能包标准与资产组织

- [x] **领域 SOP 与原子工具职责解耦**
  - [x] 原子工具负责底层操作能力（如 `bash`、`view_file`、`delegate_research`）
  - [x] 专家技能封装标准作业程序（SOP）与排查方法论
- [x] **标准物理技能包规范**
  - [x] `SKILL.md`：标准化 YAML Frontmatter 元数据头与 Markdown SOP 正文
  - [x] `scripts/`：确定性数据清洗与自动化分析辅助脚本支持
  - [x] `references/`：离线参考手册与 API 速查表资产支持
  - [x] `resources/`：配置模板与静态资源支持

---

## 二、多源发现与作用域覆盖

- [x] **三级多源目录自动扫描**
  - [x] 工作区专属技能（优先级 1，最高）：`<workspace.root_path>/.aegis/skills/`
  - [x] 发行版内置技能（优先级 2）：`AegisAgent/src/skills/`
  - [x] 用户全局技能库（优先级 3）：`~/.aegis/skills/`
- [x] **同名技能覆盖与来源追溯**
  - [x] 高优先级来源同名技能精确覆盖低优先级来源
  - [x] 完整保留技能来源（`builtin` / `global` / `workspace`）追踪
- [x] **工作区作用域物理隔离**
  - [x] 工作区技能仅对当前所属工作区可见，跨工作区严格互斥隔离

---

## 三、安全分级、信任边界与防注入治理

- [x] **来源信任分级与默认拒绝策略（Default-Deny）**
  - [x] 内置技能（`builtin`）与全局技能（`global`）默认标记 `trusted` 并启用
  - [x] 工作区技能（`workspace`）默认标记 `untrusted` 且**默认拒绝加载**，物理切断克隆恶意仓库的静默注入路径
- [x] **Frontmatter 元数据静态安全扫描**
  - [x] 静态检测描述与触发词中的潜在注入特征，命中文本记录至风险告警列表
- [x] **元数据长度硬限制**
  - [x] 描述长度与触发词数量硬截断，防止超长文本挤占系统提示词空间
- [x] **高危工具权限识别与预警**
  - [x] 自动检测技能是否依赖 `bash`、`write_file` 等高危工具，显式标注 `high_privilege` 预警
- [x] **权限边界防提权协议**
  - [x] 系统提示词明确声明技能 SOP 仅为流程指导，严禁用于突破安全围栏或提权

---

## 四、两阶段渐进式披露生命周期（Progressive Disclosure）

- [x] **阶段一：轻量技能清单常驻（Low Token Overhead）**
  - [x] 系统提示词仅注入技能名称与一句话描述，单技能开销稳定在 20~30 Token
  - [x] 清单文本严格封装在 `<available_skills source="..." trust="...">` XML 安全信封中
- [x] **阶段二：即时按需挂载（JIT Activation via `load_skill`）**
  - [x] Agent 识别到对应场景时，主动调用 `load_skill(skill_name)`
  - [x] 完整 SOP 动态拉取并封装在 `<skill_sop>` XML 信封中进入当前任务上下文
  - [x] 自动注入辅助脚本目录绝对路径，便于模型引导执行
- [x] **阶段三：任务终结零污染卸载（Zero-Pollution Eviction）**
  - [x] 完整 SOP 仅在当前单任务生命周期中生效，任务结束后彻底释放，不污染跨会话长期记忆

---

## 五、运行时工具与自省服务能力

- [x] **内置技能加载工具（`load_skill`）**
  - [x] 提供统一的技能拉取接口与参数校验
  - [x] 技能不存在时提供结构化优雅降级说明，保障工作流不崩溃
  - [x] 技能命中时输出完整 SOP 内容与关联脚本索引
- [x] **系统自省与状态查询 API**
  - [x] 提供 `GET /api/v1/skills` 端点，支持实时查询已加载技能列表、来源渠道、信任状态与安全告警
