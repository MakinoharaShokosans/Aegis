"""代码检索子智能体对外工具适配器（``delegate_code_search``）。

本工具将主 Agent 的复杂源码调研与实现追踪意图，转交给代码检索子智能体执行：
- 内部运行最多 3 轮“检索-判别-换词-提炼”循环；
- 支持高置信度早停与 3 轮未找到如实拒答；
- 所有代码切片与试错过程留在隔离区，仅向主上下文回流经位置白名单校验的结构化报告。
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional
from loguru import logger

from agent_runtime.errors import AgentError
from agent_runtime.llm.client import LLMGateway
from agent_runtime.observability.event_bus import TaskEventBus
from agent_runtime.prompt_loader import PromptLibrary
from agent_runtime.code_search.contracts import CodeSearchRequest
from agent_runtime.code_search.runner import CodeSearchRunner
from tools.core.protocol import AegisTool, ToolResult

__all__ = ["DelegateCodeSearchTool", "build_code_search_tool"]


class DelegateCodeSearchTool(AegisTool):
    """委托代码检索子智能体在代码库中进行多轮深度探索与证据提炼。

    Args:
        runner: 代码检索执行器。
        max_report_chars: 渲染进主上下文的字符上限。
        default_max_chunks: 默认单轮召回切片数。
        timeout_sec: 硬超时（秒）。
    """

    name = "delegate_code_search"
    description = (
        "委托专用代码检索子智能体在代码库中进行多轮深度检索、符号追踪与实现提炼。"
        "适合：排查复杂业务逻辑实现、多符号关联追踪、定位跨文件调用链路或模糊探索。"
        "子智能体会自主判别切片有效性并自适应重试换词（最多 3 轮），提炼出带精确行号与验证代码的结构化报告；"
        "若代码库中确实未实现该功能，将如实返回未找到。"
        "（注：若已知具体符号名且只想直查单处定义，可使用基础工具 `rag_search`）"
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "检索与调研目标（一句话说清要定位什么功能或实现）"},
            "questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "需要回答的具体代码逻辑问题列表",
            },
            "file_hints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选，可能相关的文件路径或目录前缀",
            },
            "language": {"type": "string", "description": "可选，限定编程语言（c/cpp/go/python等）"},
            "max_chunks": {"type": "integer", "description": "可选，单轮检索最多召回切片数"},
        },
        "required": ["target"],
    }

    #: 接口可信：回流内容已经过真实切片位置白名单过滤与强类型净化
    trust = "trusted"

    def __init__(
        self,
        runner: CodeSearchRunner,
        *,
        max_report_chars: int = 4000,
        default_max_chunks: int = 5,
        timeout_sec: float = 60.0,
    ) -> None:
        self._runner = runner
        self._max_report_chars = int(max_report_chars)
        self._default_max_chunks = int(default_max_chunks)
        self.timeout_sec = timeout_sec

    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        """执行一次受控源码深度调研。"""
        target = str(args.get("target") or "").strip()
        if not target:
            return ToolResult.failure("缺少 target 参数")

        questions = [str(item).strip() for item in (args.get("questions") or []) if str(item).strip()]
        file_hints = [str(item).strip() for item in (args.get("file_hints") or []) if str(item).strip()]
        language = str(args.get("language") or "").strip() or None

        try:
            max_chunks = int(args.get("max_chunks") or self._default_max_chunks)
        except (TypeError, ValueError):
            max_chunks = self._default_max_chunks

        request = CodeSearchRequest(
            target=target,
            questions=questions,
            file_hints=file_hints,
            language=language,
            max_chunks=max_chunks,
        )

        try:
            report = await self._runner.run(request)
        except AgentError as exc:
            logger.error(f"[DelegateCodeSearch] 检索失败: {exc}")
            return ToolResult.failure(str(exc), tool=self.name)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[DelegateCodeSearch] 检索出现未预期异常")
            return ToolResult.failure(f"{type(exc).__name__}: {exc}", tool=self.name)

        return ToolResult(
            ok=True,
            content=report.render_for_model(self._max_report_chars),
            is_truncated=report.truncated,
            meta=report.model_dump(),
        )


def build_code_search_tool(
    *,
    gateway: LLMGateway,
    rag_tool: Any,
    prompts: PromptLibrary,
    config: Any,
    event_bus: Optional[TaskEventBus] = None,
) -> DelegateCodeSearchTool:
    """装配 ``delegate_code_search`` 工具。"""
    runner = CodeSearchRunner(
        gateway=gateway,
        rag_client_or_tool=rag_tool,
        prompts=prompts,
        config=config,
        event_bus=event_bus,
    )
    logger.debug(
        f"[CodeSearch] 代码检索子智能体已装配，模型层级={config.model_tier}，最大轮数={config.max_rounds}"
    )
    return DelegateCodeSearchTool(
        runner,
        max_report_chars=int(config.max_report_chars),
        default_max_chunks=int(config.max_chunks_per_round),
        timeout_sec=float(config.max_wall_time_sec) + 15.0,
    )
