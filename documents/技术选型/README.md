# Aegis 系统技术选型架构决策总览 (ADR Index)

> **定位**：Aegis (Engineering Research Agent) 模块化架构决策记录索引。  
> **设计哲学**：单一职责、高内聚低耦合。各子系统只专注本领域的核心权衡，统一向外提供确定性契约。

---

## 1. 系统核心设计原则

1. **确定性包裹非确定性**：LLM 负责非确定性推理与规划决策；底层状态机、通信层、数据契约、资源配额与排序算法具备 100% 确定性。
2. **独立微服务基础设施**：Agent Runtime 专注编排调度；RAG、Web 搜索、Bash 执行作为独立服务沉淀；拒绝将所有能力揉成黑盒单体。
3. **可观测与可恢复为一等公民**：多步骤长周期任务天然具备断点恢复（Checkpointing）、因果轨迹追溯（Trajectory Tracking）与全链路可视化能力。

---

## 2. 模块化技术选型文档导航

| 序号 | 架构领域 | 对应文档 | 核心技术与决策焦点 |
| :--- | :--- | :--- | :--- |
| **01** | **Agent 核心运行时** | [Agent Runtime 选型](file:///home/Skualeilu/Projects/Aegis/documents/技术选型/agent_runtime.md) | LangGraph 状态图、SQLite 状态快照、AsyncOpenAI 统一接入、Pydantic v2 契约、tiktoken 预算监控、死循环哈希检测、双轨可观测 |
| **02** | **独立 RAG 检索基础设施** | [RAG 检索服务选型](file:///home/Skualeilu/Projects/Aegis/documents/技术选型/rag_retrieval.md) | Qdrant 稠密+稀疏一体化、fastembed (ONNX 轻量 CPU 推理)、RRF 库内倒排互惠融合、bge-reranker 精排、tree-sitter 代码 AST 切片 |
| **03** | **受控代码执行沙箱** | [Bash Shell 服务选型](file:///home/Skualeilu/Projects/Aegis/documents/技术选型/bash_shell.md) | asyncio.subprocess、os.setsid 独立进程组两段式硬杀 (SIGTERM->SIGKILL)、Linux setrlimit 物理配额 (2GB/50MB)、海量输出截断卸载 |
| **04** | **外部网络信息摄取** | [Web 搜索服务选型](file:///home/Skualeilu/Projects/Aegis/documents/技术选型/web_search.md) | DuckDuckGo 开箱即用免费检索、httpx 异步抓取、trafilatura 智能去噪转 Markdown、WAF 阻断 Fail-Fast 降级与 Agent 自愈重规划 |
| **05** | **自动化双轨评测体系** | [评测工具链选型](file:///home/Skualeilu/Projects/Aegis/documents/技术选型/evaluation.md) | numpy 离线计算 IR 物理排序指标 (HitRate/MRR/NDCG)、pytest 端到端测试套件、Trajectory 因果轨迹量化故障自愈率 |

---

## 3. 技术栈汇总清单

完整的库、版本、模型与环境依赖速查表请参阅：
👉 [Aegis 全景技术栈清单 (Tech Stack BOM)](file:///home/Skualeilu/Projects/Aegis/documents/技术栈.md)
