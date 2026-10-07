# AegisAgent 全局多层上下文装配功能与设计里程碑

> **对应设计规范**：`documents/agent_runtime/06_memory_and_context_management.md` §4  
> **责任模块**：`AegisAgent/src/agent_runtime/context.py`  
> **核心原则**：集中装配口径一致、纯函数式无副作用只读、XML 沙箱协议隔离、分层快照可检视。  
> 
> **图例规范**：`[代码实现] [测试通过]`

---

## 一、多层上下文标准装配公式

- [x] [x] **统一标准装配流水线**
  - [x] [x] 装配顺序：`[基础系统词] + [项目规则] + [工作区环境与全局记忆] + [会话压缩记忆] + [技能清单] + [活跃消息流]`
  - [x] [x] 纯函数式装配，零 I/O、不调用模型、不写任何状态，保证模型视界 100% 可重现

---

## 二、工作区规则探测与 XML 隔离沙箱

- [x] [x] **项目规则自动探测（`PROJECT_RULE_FILES`）**
  - [x] [x] 优先探测工作区根目录下的 `CLAUDE.MD` / `CLAUDE.md` / `AGENTS.md` / `.aegis/rules.md`
  - [x] [x] 探测成功后自动缓存，避免重复文件 I/O
- [x] [x] **规则防提权 XML 沙箱封装**
  - [x] [x] 规则文本严格封装在 `<project_rules source="workspace">` XML 标签中
  - [x] [x] 注入安全注释明确声明：项目规则仅供代码规范参考，绝对不得覆盖系统安全规则

---

## 三、工作区全局记忆与会话认知注入

- [x] [x] **跨会话共享记忆层注入**
  - [x] [x] 注入工作区名称与当前物理根路径（CWD）
  - [x] [x] 注入已确认项目架构定论（`confirmed_architecture`）
  - [x] [x] 注入跨会话共享编码规范（`project_conventions`）
  - [x] [x] 注入全局避坑黑名单（`global_failed_attempts`，严禁再犯）
- [x] [x] **动态会话记忆层注入**
  - [x] [x] 用户任务目标结构化封装（`<user_task>`）
  - [x] [x] 会话历史压缩摘要（`rolling_summary`）
  - [x] [x] 本任务已确认事实（`confirmed_facts`）
  - [x] [x] 本任务踩坑记录（`failed_attempts`）

---

## 四、安全指令与上下文检视能力

- [x] [x] **金丝雀指令（Canary Directive）注入**
  - [x] [x] 在上下文装配时将 `<!-- SECURITY_CANARY_DIRECTIVE -->` 锚定注入，明确保密纪律
- [x] [x] **分层结构化快照检视（`describe_layers`）**
  - [x] [x] 导出包含工作区、跨会话记忆、会话记忆、消息数、Token 预估的多层 JSON 结构
  - [x] [x] 直接支撑 `GET /api/v1/sessions/{id}/context` 可观测性端点
