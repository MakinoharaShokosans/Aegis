"""研究子智能体：外部不可信数据的隔离区。

> 规范：``documents/agent_runtime/12_research_subagent.md``
> 目录与依赖约定：``documents/agent_runtime/10_directory_structure.md`` §2/§5

**它解决的问题**：主 Agent 同时握着"不可信外部文本"和"高特权工具"（bash、写文件）
时，一次成功的间接提示注入就能把网页内容变成特权动作。
本包把外部抓取与提炼移进一个**受限工具表**的子智能体，
主 Agent 结构性地拿不到原始网页，只接收通过强类型校验的报告。

**三个模块的职责**：

* :mod:`~agent_runtime.research.contracts` —— 强类型契约与四道结构性约束（净化入口）
* :mod:`~agent_runtime.research.runner`    —— 有界异步循环（检索规划 → 抓取 → 提炼）
* :mod:`~agent_runtime.research.tool`      —— 主 Agent 唯一可见的 ``delegate_research`` 接口

**为什么不是 LangGraph 子图**：子图共享父图的 ``messages`` 与 Checkpoint，
会让原始网页内容回流主上下文（裁决记录见 `10` §4 裁决项⑯）。
"""

from agent_runtime.research.contracts import (
    CodeExample,
    Finding,
    ResearchReport,
    ResearchRequest,
    ResearchSource,
    VersionFact,
    build_report,
)
from agent_runtime.research.runner import ResearchRunner
from agent_runtime.research.tool import DelegateResearchTool, build_research_tool

__all__ = [
    "CodeExample",
    "DelegateResearchTool",
    "Finding",
    "ResearchReport",
    "ResearchRequest",
    "ResearchRunner",
    "ResearchSource",
    "VersionFact",
    "build_report",
    "build_research_tool",
]
