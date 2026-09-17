# AegisAgent 研究子智能体（Research Subagent）系统功能与设计里程碑

> **对应设计规范**：`documents/agent_runtime/12_research_subagent.md`  
> **核心原则**：特权隔离、强类型契约、有界循环预算、代码模板渲染、数据流零污染。  
> 
> **图例规范**：`[代码实现] [测试通过]`

---

## 一、权限分离与安全沙箱架构

- [x] [x] **网络检索与宿主特权物理隔离**
  - [x] [x] 主 Agent 剥离直接执行 `web_search` 的特权，避免恶意网页进入高权限上下文
  - [x] [x] 研究子智能体运行于 0 本地权限沙箱（无 `bash`、无 `file_write`）
- [x] [x] **受限工具表注册机制**
  - [x] [x] `ToolRegistry(allow_untrusted=False)` 构造期拒绝将不可信工具注册进主特权表
  - [x] [x] `web_search` 仅作为受限工具提供给子智能体，主 Agent 唯一可见入口为 `delegate_research`

---

## 二、强类型输入输出契约 (`agent_runtime/research/contracts.py`)

- [x] [x] **`ResearchRequest` 结构化请求**
  - [x] [x] `topic`：研究主题与技术目标
  - [x] [x] `specific_questions`：精准的技术提问清单
- [x] [x] **`ResearchReport` 结构化报告与四道硬性约束**
  - [x] [x] **约束 1（URL 真实白名单）**：校验引用的 URL 必须存在于本次抓取的白名单中，剔除模型幻觉/伪造链接
  - [x] [x] **约束 2（技术版本号正则校验）**：对报告中涉及的依赖版本号强制执行 SemVer / PEP440 正则校验
  - [x] [x] **约束 3（输出长度硬上限）**：限制报告正文与代码片段最大长度，防止恶意网页膨胀攻击
  - [x] [x] **约束 4（固定安全标识）**：`display_only` 等安全属性由代码契约常量给定，模型无法篡改覆盖

---

## 三、有界异步研究循环与韧性降级 (`agent_runtime/research/runner.py`)

- [x] [x] **三维度硬配额预算控制**
  - [x] [x] 最大迭代轮次限制（默认最多 3 轮检索规划）
  - [x] [x] 累计 Token 物理配额硬限制
  - [x] [x] 挂钟时间硬超时熔断
- [x] [x] **三阶段异步流水线**
  - [x] [x] 阶段 1：检索词生成与去重规划（Fast/廉价轻量模型驱动）
  - [x] [x] 阶段 2：并发网页检索与正文清洗提取
  - [x] [x] 阶段 3：强类型结构化事实提炼与技术代码保留
- [x] [x] **全链路异常优雅降级**
  - [x] [x] 网页解析失败或 WAF 拦截时记录局部失败并继续推进
  - [x] [x] 超时或模型解析失败时输出部分已有结论，不抛出异常打断主 Agent 图流程

---

## 四、安全渲染与主 Agent 委托工具 (`agent_runtime/research/tool.py`)

- [x] [x] **代码模板驱动的安全信封渲染**
  - [x] [x] 子模型自由散文永不直接进入主 Agent 上下文
  - [x] [x] 报告由固定 Python 模板渲染为 `<external_content source="research" trust="untrusted">` XML 信封
- [x] [x] **`delegate_research` 委托工具集成**
  - [x] [x] 作为 `trust="trusted"` 工具注入主 Agent 工具注册表
  - [x] [x] 向上屏蔽复杂的网络并发与重试细节，提供原子化研究交付
