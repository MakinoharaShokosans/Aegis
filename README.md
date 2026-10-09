# Aegis: 专为真实代码工程打造的工业级自治智能体系统

> **项目定位**：Aegis 是一个面向大规模本地代码工程重构、代码审查与缺陷修复的高可靠软件工程智能体（Software Engineering Agent）系统。  
> **核心突破**：系统彻底告别玩具级（Toy Project）演示，针对智能体在真实工程落地中的**死循环失控**、**上下文日志撑爆**、**Shell 孤儿进程残留**、**无 GPU 环境语义检索失真**与**越权高危破坏**等致命痛点，构建了确定性状态图、进程组硬隔离沙箱、语法感知混合 RAG 与双向人机协同（HITL）防御护栏。

---

## 为什么需要 Aegis？真实工程落地的五大灾难与解法

市面主流开源代码智能体在处理大型代码仓库时，普遍面临五大灾难性崩溃。Aegis 针对性地确立了工业级工程防御标准：

| 生产现场真实灾难 | 业界普通开源方案表现 | Aegis 工业级工程防御机制 |
|---|---|---|
| **灾难 1：工具调用死循环** | 遇到报错反复执行相同命令，迅速烧光 Token 配额，耗尽 API 额度 | **结构化语义指纹去重**：维护工具调用指纹哈希队列，触发频次/重复阈值硬熔断，强制转入重规划 |
| **灾难 2：超长日志上下文溢出** | `pytest` 或 `make` 输出数万行日志，直接溢出 LLM 上下文导致会话报废 | **观察值双端裁剪与存盘**：首尾提取关键堆栈信息（压缩比 >92%），全量日志异步存盘为磁盘产物（Artifacts） |
| **灾难 3：未隔离进程引发资源耗尽** | 启动后台测试服务或遇死循环脚本，超时后残留大批僵尸/孤儿进程吃满服务器 | **Linux PGID 进程组硬隔离**：独立 Session 与 PGID，双段式级联信号（SIGTERM 优雅退出 -> SIGKILL 强杀整个进程树） |
| **灾难 4：无 GPU 场景代码检索失真** | 盲目采用固定字符滑动窗口切分代码，把函数从中腰斩，缺乏符号精确匹配 | **纯 CPU 语法感知混合 RAG**：Tree-sitter AST 边界切分 + Dense/BM25 双路向量 + Qdrant 服务端原生 RRF 算子下推 |
| **灾难 5：高危越权与黑盒盲盒运行** | 执行 `rm -rf` 或修改核心配置无需确认，过程黑盒不可见 | **HITL 审批门禁与白盒可观测**：四层 Token 滑动窗口真实水位计 + 单次 LLM 调用白盒还原 + 交互式权限越级审批卡片 |

---

## 质量门禁与硬核基准数据 (Proof Metrics)

Aegis 坚持以严谨的测试数据为最高准绳。全系统配备 **53 个测试套件，共 453 项自动化测试用例，全绿通过率 100.0%**，质量门禁零违规：

### 1. 全系统测试执行大盘

| 评估维度 / 测试套件 | 测试文件数 | 用例总数 | 通过数 (Passed) | 失败数 (Failed) | 执行耗时 | 测试通过率 | 内存峰值 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **01 单元测试 - Agent 核心运行时** | 18 | 263 | 263 | 0 | 24.88s | **100.0%** | < 280 MB |
| **01 单元测试 - RAG 语法检索微服务** | 13 | 61 | 61 | 0 | 73.18s | **100.0%** | < 1.45 GB |
| **01 单元测试 - Web 前端控制台** | 16 | 55 | 55 | 0 | 6.50s | **100.0%** | < 320 MB |
| **02 集成测试 - 状态机与微服务协同** | 4 | 22 | 22 | 0 | 15.60s | **100.0%** | < 310 MB |
| **03 安全对抗 - 越级拦截与 Prompt 注入** | 2 | 52 | 52 | 0 | 0.64s | **100.0%** | < 180 MB |
| **全系统总计 (Total)** | **53** | **453** | **453** | **0** | **120.80s** | **100.0%** | **系统安全可控** |

### 2. 核心工程质量门禁 (Quality Gates) 实测指标

- **孤儿进程残留归零 (QG-03)**：在 100 次高并发超时中断测试中，Linux 进程树孤儿残留率为 **0%**；
- **崩溃断电秒级自愈 (QG-04)**：基于 SQLite Checkpoint 快照机制，系统意外中断后恢复续跑成功率 **100.0%**；
- **安全红队对抗防御 (QG-05)**：52 个复合指令逃逸、越级注入与提示词探测样本，全量拦截率 **100.0%**；
- **纯 CPU 检索基准**：Tree-sitter AST 语法切片自包含率 **100.0%**，代码符号精确查询 MRR@5 达到 **0.89**，启动期 7 大探针全链路自检耗时 **< 1.8s**。

---

## 系统全景架构与微服务矩阵

Aegis 采用物理隔离的微服务架构设计，划分为四个高内聚解耦组件：

```
+---------------------------------------------------------------------------------------------------+
|                                      AegisFrontend (控制台)                                       |
|                React 18 + Zustand / Monaco Editor / SSE 流式打字机 / HITL 审批卡片                |
+-------------------------------------------------|-------------------------------------------------+
                                                  | HTTP REST & Server-Sent Events (Port 8000)
                                                  v
+---------------------------------------------------------------------------------------------------+
|                                     AegisAgent (调度宿主核心)                                      |
|                                                                                                   |
|  +---------------------------------------------------------------------------------------------+  |
|  | [1. LangGraph 状态图引擎]  Planner 目标拆解 -> Executor 动作翻译 -> Evaluator 质量验收       |  |
|  +---------------------------------------------------------------------------------------------+  |
|  | [2. 安全护栏守门人]  物理预算熔断器 / 哈希指纹死循环拦截 / 观察值首尾裁剪 / Canary 防泄露    |  |
|  +---------------------------------------------------------------------------------------------+  |
|  | [3. 上下文与记忆体系]  四层金字塔记忆模型 / SQLite 事务级 Checkpoint / XML 定界信封协议     |  |
|  +---------------------------------------------------------------------------------------------+  |
+-----------------------------------|---------------------------------------|-----------------------+
                                    | HTTP (Port 8002 / 8003)               | HTTP (Port 8001)
                                    v                                       v
+---------------------------------------------------+   +-------------------------------------------+
|      AegisServices (受控沙箱与轻量 Sidecar)        |   |       AegisRAG (代码语义检索微服务)        |
|                                                   |   |                                           |
| - bash_shell: Linux PGID 进程组隔离 / setrlimit   |   | - indexer: Tree-sitter C/C++/Go AST 解析  |
| - web_search: 多源异步聚合 / 正文清洗 / LRU 去重  |   | - embeddings: FastEmbed 纯 CPU 稠密与稀疏 |
| - memory_pool: 全局内存双缓冲池治理               |   | - storage: Qdrant 原生 RRF 算子 / UUIDv5  |
+---------------------------------------------------+   +-------------------------------------------+
```

---

## 系统交互与功能展示 (System Showcase)

### 1. 人机协同控制台与会话初始化
系统提供工程级 Web 控制台，集成工作区配置、会话生命周期管控与多 Tab 工作区视图：

![人机协同控制台与会话初始化](projects_images/问候展示.png)

### 2. 确定性思维链流式展示 (CoT & Reasoning Timeline)
白盒化展现 Agent 思考推演、子任务拆解与里程碑推进过程，告别不可控的黑盒运行：

![可视化思考流程展示](projects_images/可视化思考流程展示.png)

### 3. 工程技能动态加载机制 (Dynamic Skills)
支持按需解析与动态装配工程领域专项技能（Skills），拓展 Agent 在特定代码工程、测试排查等垂直场景的专业能力：

![工程技能动态加载](projects_images/加载skills.png)

### 4. 纯 CPU 语法感知混合代码检索 (Code RAG)
结合 Tree-sitter AST 语法边界切片与 Dense/BM25 混合向量检索，秒级准确定位工程核心符号与上下文：

![代码语义与语法混合检索](projects_images/RAG检索.png)

### 5. 全链路白盒调用检视器 (LLM Inspector & Debugging)
支持对单次大模型调用的完整报文还原，实时检视 System Prompt、输入上下文、思维链、工具调用与 Token 水位：

![API请求查看和调试](projects_images/API请求查看和调试.png)

---

## 核心系统特性与工程护城河

### 1. 确定性图状态机与硬护栏 (AegisAgent)
- **LangGraph 三节点循环**：严格拆解规划（Planner）、受控执行（Executor）与阶段评估（Evaluator），任何执行偏差在 Evaluator 节点被立即纠偏；
- **哈希指纹死循环阻断**：对每次调用的 `(tool_name, arguments)` 计算 SHA-256 结构化指纹，连续重复 3 次或频次异常时立即熔断并注入重规划警告；
- **观察值双端裁剪治理**：当命令执行产出巨型日志时，保留 Head 100 行与 Tail 100 行关键报错堆栈，全量日志自动沉淀为磁盘 Artifacts，杜绝 Context Window 爆炸；
- **Canary 防提示词注入**：在系统提示词与输入定界符中埋入不可预测的随机 Canary 令牌，实时校验模型输出，检测到提示词泄漏瞬间阻断会话。

### 2. 进程组硬隔离受控 Shell 沙箱 (AegisServices)
- **独立 Session 与 PGID 硬隔离**：通过 `os.setsid()` 为每一个执行命令分配独立的 Linux 进程组，杜绝后台衍生进程逃逸；
- **两段式信号级联强杀**：命令超时或用户取消时，先向 `-pgid` 发送 `SIGTERM` 允许进程清理资源，若 2 秒内未退出则强制发送 `SIGKILL` 清空整个进程树；
- **高危命令正则与 AST 审计**：内置禁止命令黑名单（如格式化磁盘、直接提权、删除根目录等），在进程派生前实施毫秒级（< 0.8ms）硬拦截；
- **全局内存池治理**：对沙箱 stdout/stderr 流式读取限制单行与单缓冲区上限，防止单个超大输出打爆宿主内存。

### 3. 纯 CPU 语法感知混合代码 RAG (AegisRAG)
- **Tree-sitter 真 AST 切片**：针对 C、C++、Go 源代码，严格按照函数（`function_definition`）和结构体（`struct_specifier`）边界切分，配备尾随分号吸收算法，切片语法自包含率 100%；
- **Markdown 标题面包屑感知**：对开发规范和架构文档提取 H1~H3 层级面包屑（Breadcrumbs），编码时作为前缀标题头动态注入；
- **零 GPU 依赖双路混合检索**：基于 FastEmbed (ONNX Runtime) 在普通 CPU 单核上生成 1024 维 Dense 语义向量与 Qdrant BM25 词法稀疏向量；
- **服务端原生 RRF 融合算子下推**：充分利用 Qdrant 内部 `Prefetch` 与 `FusionQuery(fusion=Fusion.RRF)`，将语言预过滤与倒排秩融合在存储底层一步完成；
- **UUIDv5 确定性 Point ID 幂等**：基于内容 SHA-1 哈希生成确定性点位 ID，增量索引毫秒级跳过未变更切片，文件删除自动级联清理旧切片。

### 4. 全链路白盒可观测与人机协同 (AegisFrontend)
- **四层 Token 活跃滑动窗口水位计**：科学剥离全流程累计计费 Token 与单次请求活跃上下文，动态核算底模 System、工程长期记忆与滑窗轮次，直观预警模型截断；
- **HITL 双向人机协作审批门禁**：当智能体尝试执行高危命令时，前端以高可见度琥珀色卡片截断流程，提供“单次放行”、“永久加白”与“驳回并输入人类纠偏理由”三种路径；
- **逐次 LLM 调用白盒检视器**：Master-Detail 架构还原每一次大模型调用的原始 System Prompt、真实输入、思维链（CoT）与工具调用参数；
- **多 Tab 画布与 Git Diff 审查**：集成 Monaco Editor 与 DiffEditor，支持实时代码审查、语法高亮与外部文件变动感知（Live Sync Guard）。

---

## 快速开始 (Quickstart)

### 环境依赖
- Linux 环境 (支持 `os.setpgid` 与 `resource.setrlimit` 系统调用)
- Python >= 3.11
- Node.js >= 20, pnpm
- Docker (用于可选的 Qdrant 独立集群；亦原生支持 Local 纯嵌入式持久化)

### 1. 克隆仓库与配置环境
```bash
git clone https://github.com/MakinoharaShokosans/Aegis.git
cd Aegis

# 复制并配置各模块环境变量
cp AegisAgent/.env.example AegisAgent/.env
cp AegisRAG/.env.example AegisRAG/.env
```
在 `AegisAgent/.env` 中配置你的大模型 API 基础地址（支持 DeepSeek, OpenAI, Claude, 通义千问等兼容网关）与 API Key。

### 2. 一键极速启动
项目提供统一的进程管理器 `./aegis`（亦可通过根目录脚本 `./start` 或 `./start.sh` 启动）：
```bash
# 赋予执行权限
chmod +x start start.sh aegis

# 一键启动全系统三大进程并聚合带颜色标签日志
./start
# 或使用进程管理器：
./aegis start
```

> **可选**：将 `aegis` 软链接至全局路径（如 `ln -sf $(pwd)/aegis ~/.local/bin/aegis`），即可在任意目录直接执行 `aegis start`。

启动后终端将实时聚合多源输出，自动标注颜色前缀：
- `【agent】：***`（AegisAgent 调度核心与受控沙箱）
- `【rag】：***`（AegisRAG 语法感知检索微服务）
- `【frontend】：***`（AegisFrontend Web 控制台）

按下 `Ctrl+C` 系统将自动通过级联信号（SIGTERM -> SIGKILL）优雅关闭所有托管进程组，保证端口与资源彻底释放。

#### 其他常用管理指令
```bash
./aegis status         # 实时探测各微服务及 Sidecar 的 HTTP 存活状态
./aegis stop           # 一键清理所有 Aegis 后台进程与占用端口
./aegis start agent    # 单独启动 AegisAgent (:8000)
./aegis start rag      # 单独启动 AegisRAG (:8001)
./aegis start frontend # 单独启动 AegisFrontend (:5173)
```

启动完成后，打开浏览器访问：**`http://localhost:5173`** 即可进入人机协作控制台。

### 3. 运行全量测试套件
```bash
# 运行 AegisAgent 核心与沙箱测试 (单线程安全隔离)
cd AegisAgent && pytest tests/ -v

# 运行 AegisRAG 语法解析与检索精度测试
cd ../AegisRAG && pytest tests/ -v

# 运行 AegisFrontend 前端状态机与组件测试
cd ../AegisFrontend && pnpm test
```

---

## 代码目录拓扑

```text
Aegis/
├── AegisAgent/               # [调度宿主与核心引擎]
│   ├── src/
│   │   ├── runtime/          # 状态模型、分层配置、SQLite Checkpoint、四层上下文装配
│   │   ├── workflow/         # LangGraph 状态图编排、Planner/Executor/Evaluator 节点
│   │   ├── guardrails/       # 物理硬预算、死循环检测、观察值裁剪、三级权限管控、Canary
│   │   ├── tools/            # 工具统一协议、内置文件/Shell/Git工具、Skills 动态技能、MCP
│   │   ├── memory/           # 四层记忆体系、任务事件总线、多厂商双模型网关
│   │   ├── subagents/        # ResearchSubagent、CodeSearchSubagent、动态子智能体
│   │   ├── api/              # FastAPI 安全闸门、SSE 事件流推送、Supervisor 守护
│   │   └── supervisor/       # 进程级存活守护与心跳探针
│   └── tests/                # 263 项自动化单元与集成测试
│
├── AegisServices/            # [受控沙箱与外网检索 Sidecar]
│   ├── bash_shell/           # PGID 组隔离沙箱、命令黑白名单审计、全局双缓冲内存池
│   └── web_search/           # 多源异步聚合检索、Trafilatura 正文提取、LRU 内容哈希去重
│
├── AegisRAG/                 # [代码语义检索微服务]
│   ├── src/
│   │   ├── indexer/          # Tree-sitter C/C++/Go AST 解析、语言路由、Markdown 面包屑
│   │   ├── embeddings/       # FastEmbed 纯 CPU 稠密与 BM25 稀疏双路向量化管道
│   │   ├── storage/          # Qdrant 客户端适配、原生 RRF 融合下推、UUIDv5 幂等点位
│   │   ├── rerank/           # Cross-Encoder 交叉重排模型、min_score 低置信度硬护栏
│   │   └── api/              # 7 大领域启动前置体检探针 (Preflight)、FastAPI 同步路由
│   └── tests/                # 61 项 AST 语法与检索精度测试
│
├── AegisFrontend/            # [控制台与人机协同 Web UI]
│   ├── src/
│   │   ├── stores/           # Zustand 状态驱动 (useTaskStore, useWorkspaceStore等)
│   │   ├── api/              # Fetch EventSource SSE 长连接解析、模块化 REST API
│   │   ├── components/       # ChatPane, HitlApprovalCard, TraceTimeline, LlmInspector
│   │   └── components/canvas # Monaco Editor / DiffEditor / MarkdownReader 多 Tab 画布
│   └── tests/                # 55 项状态机流转与交互组件测试
│
├── documents/                # [系统级技术规格与深度复盘知识库]
│   ├── 04_测试与质量保障/    # 全套测试报告、红队对抗测试数据、质量门禁审计产物
│   └── 07_面试与求职复盘/    # 83 篇源码级模块架构解剖与大厂架构答辩专刊
│
├── start                     # 全系统服务一键启动管理脚本
└── LICENSE                   # MIT License
```

---

## 深度技术文档导航

为了满足架构评审、技术选型复盘与面试深挖需求，项目沉淀了完备的技术文档体系：

- **[质量保障与测试报告库](documents/04_测试与质量保障/README.md)**：
  - [全系统测试执行总纲与质量门禁报告](documents/04_测试与质量保障/测试报告/00_全系统测试执行总纲与质量门禁报告.md)
  - [红队权限越级与沙箱对抗测试报告](documents/04_测试与质量保障/测试报告/03_端到端与安全对抗报告/01_权限越级与沙箱合谋对抗测试报告.md)
  - [Prompt 注入防御与 Canary 熔断报告](documents/04_测试与质量保障/测试报告/03_端到端与安全对抗报告/02_Prompt注入防御与Canary硬熔断报告.md)
  - [RAG 全景消融基准与检索评测报告](documents/04_测试与质量保障/测试报告/04_深度评测报告/02_RAG全景消融基准与检索质量评测报告.md)
- **[源码级系统概况与解剖总纲 (83 篇专刊)](documents/07_面试与求职复盘/项目概况/README.md)**：
  - [00 系统全景与宏观架构设计](documents/07_面试与求职复盘/项目概况/00_系统全景与宏观架构/01_系统目标与全景拓扑.md)
  - [01 AegisAgent 调度宿主内核深度剖析 (38 篇)](documents/07_面试与求职复盘/项目概况/01_AegisAgent_调度宿主与核心引擎/00_子系统架构总览与分层契约.md)
  - [02 AegisServices 受控沙箱与检索 Sidecar (11 篇)](documents/07_面试与求职复盘/项目概况/02_AegisServices_受控沙箱与外网检索/00_子系统架构总览与Sidecar隔离.md)
  - [03 AegisRAG 代码语义检索微服务 (15 篇)](documents/07_面试与求职复盘/项目概况/03_AegisRAG_代码语义检索微服务/00_子系统架构总览与双流水线.md)
  - [04 AegisFrontend 控制台与人机协同 (16 篇)](documents/07_面试与求职复盘/项目概况/04_AegisFrontend_控制台与人机协同/00_子系统架构总览与人机协同.md)

---

## 许可证

本项目采用 [MIT License](LICENSE) 开源许可证。
