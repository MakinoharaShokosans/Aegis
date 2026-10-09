# Aegis

Aegis 是一个面向本地代码工程重构、代码审查与缺陷修复的自治智能体（Software Engineering Agent）系统。
针对长流程 Agent 执行中的死循环失控、上下文日志溢出、进程残留、AST 代码检索与人机协同审批等问题，提供确定性状态图流转、PGID 沙箱隔离、语法感知代码 RAG 与白盒可观测控制台。

---

## 架构拓扑

```mermaid
graph TD
    subgraph Client["前端交互层"]
        Frontend["AegisFrontend<br/>React 18 / Zustand / Monaco Editor / HITL 审批"]
    end

    subgraph Host["调度核心层"]
        Agent["AegisAgent (调度宿主 :8000)<br/>LangGraph 状态图 / Checkpoint 持久化 / 上下文装配 / 安全护栏"]
    end

    subgraph Services["执行与检索服务层"]
        Sandbox["AegisServices (:8002 / :8003)<br/>Bash Shell (PGID 进程组硬隔离) / Web Search"]
        RAG["AegisRAG (:8001)<br/>Tree-sitter AST 切片 / FastEmbed 纯 CPU 向量 / Qdrant RRF 融合"]
    end

    Frontend -->|HTTP REST & SSE 流| Agent
    Agent -->|HTTP| Sandbox
    Agent -->|HTTP| RAG
```

---

## 界面展示

### 1. 控制台与会话初始化
![控制台与会话初始化](projects_images/问候展示.png)

### 2. 思维链与规划流式展示
![可视化思考流程展示](projects_images/可视化思考流程展示.png)

### 3. 技能动态加载
![工程技能动态加载](projects_images/加载skills.png)

### 4. 语法感知代码检索
![代码语义与语法混合检索](projects_images/RAG检索.png)

### 5. LLM 调用白盒检视与调试
![API请求查看和调试](projects_images/API请求查看和调试.png)

---

## 核心特性

- **确定性状态图流转**：基于 LangGraph 构建 Planner（规划）、Executor（执行）、Evaluator（评估）闭环状态机，支持 SQLite 检查点事务持久化与断点续跑。
- **安全沙箱与进程隔离**：Shell 命令执行通过 `os.setsid()` 绑定独立 Linux 进程组（PGID），超时或取消时执行两段式信号级联强杀（SIGTERM -> SIGKILL），避免孤儿进程残留。
- **运行护栏与防死循环**：基于工具调用入参计算 SHA-256 结构化指纹，连续重复或频次异常时自动熔断；长日志自动执行首尾保留裁剪，杜绝上下文溢出。
- **纯 CPU 语法感知代码 RAG**：采用 Tree-sitter 对 C/C++/Go 代码进行 AST 语义边界切分，结合 FastEmbed 稠密向量与 Qdrant BM25 稀疏向量进行原生 RRF 倒排融合检索。
- **人机协同与白盒可观测**：高危操作触发 HITL 交互式卡片审批；提供单次 LLM 调用的完整输入、CoT 推理过程、Prompt 与 Token 水位还原。

---

## 快速开始

### 1. 环境准备
- Linux 环境
- Python >= 3.11
- Node.js >= 20, pnpm
- 环境变量配置：
  ```bash
  cp AegisAgent/.env.example AegisAgent/.env
  cp AegisRAG/.env.example AegisRAG/.env
  ```
  在 `AegisAgent/.env` 中配置大模型 API Key 及基础地址。

### 2. 一键启动
项目根目录提供统一进程管理器 `./aegis`（亦可通过 `./start`）：
```bash
# 赋予执行权限
chmod +x start start.sh aegis

# 启动全系统（Agent :8000、RAG :8001、Frontend :5173）
./start
# 或
./aegis start
```

终端将聚合输出带标签日志（`【agent】：`、`【rag】：`、`【frontend】：`）。按 `Ctrl+C` 自动清理所有进程。

#### 常用管理命令
```bash
./aegis status         # 检查各服务存活状态
./aegis stop           # 停止所有后台进程并释放端口
./aegis start agent    # 单独启动 AegisAgent
./aegis start rag      # 单独启动 AegisRAG
./aegis start frontend # 单独启动 AegisFrontend
```

启动后在浏览器打开 **`http://localhost:5173`** 即可进入 Web 控制台。

### 3. 运行测试
全系统包含 53 个测试套件，共 453 项自动化测试用例：
```bash
cd AegisAgent && pytest tests/ -v
cd ../AegisRAG && pytest tests/ -v
cd ../AegisFrontend && pnpm test
```

---

## 代码目录拓扑

```text
Aegis/
├── AegisAgent/               # 调度宿主与核心引擎 (LangGraph、状态机、护栏、记忆、API)
├── AegisServices/            # 受控沙箱 (PGID 隔离 Shell) 与检索 Sidecar
├── AegisRAG/                 # 代码语义检索微服务 (Tree-sitter AST、FastEmbed、Qdrant)
├── AegisFrontend/            # Web 控制台 (React 18、Monaco Editor、HITL 审批)
├── documents/                # 技术规格、测试报告与架构设计文档
├── projects_images/          # 系统交互截图
├── aegis                     # 多进程服务统一管理器
├── start                     # 快捷启动脚本
└── LICENSE                   # MIT License
```

---

## 技术文档导航

- [测试执行总纲与质量报告](documents/04_测试与质量保障/测试报告/00_全系统测试执行总纲与质量门禁报告.md)
- [安全对抗与沙箱隔离报告](documents/04_测试与质量保障/测试报告/03_端到端与安全对抗报告/01_权限越级与沙箱合谋对抗测试报告.md)
- [RAG 检索质量评测报告](documents/04_测试与质量保障/测试报告/04_深度评测报告/02_RAG全景消融基准与检索质量评测报告.md)
- [架构概况与系统解剖专刊 (83 篇)](documents/07_面试与求职复盘/项目概况/README.md)

---

## 许可证

本项目采用 [MIT License](LICENSE) 开源许可证。
