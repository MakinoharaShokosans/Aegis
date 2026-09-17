"""代码检索子智能体的有界执行循环（CodeSearchRunner）。

实现最多 3 轮“检索-判别-改词-提炼”的状态机闭环：
1. **首轮规划**：根据 target 与 questions 生成精准初始代码检索词；
2. **多轮判别与改词**：根据切片上下文判定是否已充分解答；若充分则【早停 Early Exit】，不充分则重写 Query；
3. **确定性拒答**：3 轮用尽仍无果时返回 ``not_found`` 报告；
4. **事件流接入**：通过 TaskEventBus 向外广播 ``code_search.*`` 实时进度。
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Mapping, Optional, Sequence

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from agent_runtime.guardrails.budget_ledger import ChildBudget
from agent_runtime.llm.client import LLMGateway
from agent_runtime.observability.event_bus import TaskEventBus
from agent_runtime.prompt_loader import PromptLibrary
from agent_runtime.code_search.contracts import (
    CodeChunkEvidence,
    CodeSearchReport,
    CodeSearchRequest,
    build_code_report,
)
from agent_runtime.structured_output import extract_json_object, truncate_text

__all__ = ["CodeSearchRunner"]

_EVIDENCE_SEPARATOR = "\n\n---\n\n"


class CodeSearchRunner:
    """源码深度检索有界状态机。"""

    __slots__ = (
        "_gateway",
        "_rag_client_or_tool",
        "_prompts",
        "_config",
        "_bus",
    )

    def __init__(
        self,
        gateway: LLMGateway,
        rag_client_or_tool: Any,
        prompts: PromptLibrary,
        config: Any,
        event_bus: Optional[TaskEventBus] = None,
    ) -> None:
        self._gateway = gateway
        self._rag_client_or_tool = rag_client_or_tool
        self._prompts = prompts
        self._config = config
        self._bus = event_bus

    async def run(self, request: CodeSearchRequest) -> CodeSearchReport:
        """执行一次受控源码深度检索。"""
        budget = ChildBudget(
            max_tokens=int(self._config.max_total_tokens),
            max_wall_time_sec=float(self._config.max_wall_time_sec),
        )
        warnings: List[str] = []
        evidence: Dict[str, CodeChunkEvidence] = {}
        attempted_queries: List[str] = []
        rounds_used = 0

        await self._emit(
            {
                "event": "code_search.started",
                "target": request.target,
                "questions": len(request.questions),
                "max_rounds": int(self._config.max_rounds),
            }
        )

        max_rounds = max(1, int(self._config.max_rounds))
        per_query_k = int(request.max_chunks or self._config.max_chunks_per_round)

        for round_idx in range(1, max_rounds + 1):
            if budget.exhausted:
                warnings.append(budget.reason())
                break

            rounds_used += 1

            # 1. 规划或判别本轮检索词
            if round_idx == 1:
                queries = await self._plan_initial_queries(request, budget)
            else:
                decision = await self._evaluate_and_reformulate(
                    request, list(evidence.values()), attempted_queries, budget
                )
                if decision.get("status") == "sufficient" or not decision.get("queries"):
                    logger.info(
                        f"[CodeSearch] 第 {round_idx-1} 轮证据已充分，触发早停 (Early Exit): {decision.get('reason')}"
                    )
                    break
                queries = decision.get("queries", [])

            if not queries:
                break

            # 2. 执行 RAG 检索
            new_queries = [q for q in queries if q not in attempted_queries]
            if not new_queries:
                logger.info("[CodeSearch] 没有产生新的检索词，结束循环")
                break

            attempted_queries.extend(new_queries)

            fetched_chunks = await self._retrieve_all(new_queries, top_k=per_query_k, language=request.language)
            for chunk in fetched_chunks:
                evidence.setdefault(chunk.location, chunk)

            # 3. 外发事件
            await self._emit(
                {
                    "event": "code_search.round",
                    "round": rounds_used,
                    "queries": list(new_queries),
                    "new_chunks": len(fetched_chunks),
                    "total_evidence": len(evidence),
                }
            )

        # 4. 提炼结论
        raw_distill = await self._distill(request, list(evidence.values()), attempted_queries, budget)

        # 5. 强类型净化与白名单校验
        report = build_code_report(
            raw_distill,
            target=request.target,
            fetched_evidence=list(evidence.values()),
            attempted_queries=attempted_queries,
            config=self._config,
            rounds_used=rounds_used,
            total_tokens=budget.tokens,
            elapsed_sec=budget.elapsed,
        )

        if warnings:
            report.warnings = [*warnings, *report.warnings]

        logger.info(
            f"[CodeSearch] 完成: 状态={report.status} 轮数={rounds_used} 切片={len(evidence)} "
            f"tokens={budget.tokens} 耗时={budget.elapsed:.1f}s 结论={len(report.findings)}"
        )

        await self._emit(
            {
                "event": "code_search.finished",
                "target": request.target,
                "status": report.status,
                "rounds": rounds_used,
                "evidence_count": len(evidence),
                "findings": len(report.findings),
                "snippets": len(report.code_snippets),
                "tokens": budget.tokens,
                "elapsed_sec": round(budget.elapsed, 2),
            }
        )

        return report

    # ==========================================================================
    # 阶段实现
    # ==========================================================================

    async def _plan_initial_queries(self, request: CodeSearchRequest, budget: ChildBudget) -> List[str]:
        """生成首轮精确检索词（最多 2 条）。"""
        user_prompt = [
            "## 模式 A：首轮检索词规划",
            f"检索目标：{request.target}",
        ]
        if request.questions:
            user_prompt.append("具体待解答问题：")
            user_prompt.extend(f"- {q}" for q in request.questions)
        if request.file_hints:
            user_prompt.append(f"相关文件线索：{', '.join(request.file_hints)}")
        if request.language:
            user_prompt.append(f"限定语言：{request.language}")

        user_prompt.append("\n请给出 1~2 个最可能精准定位到符号定义或实现的检索词。")

        try:
            response = await self._gateway.invoke(
                self._config.model_tier,
                [
                    SystemMessage(content=self._prompts.load("code_search")),
                    HumanMessage(content="\n".join(user_prompt)),
                ],
                force_json=True,
            )
            budget.add_tokens(response.total_tokens)
            parsed = extract_json_object(response.content) or {}
            queries = [str(q).strip() for q in (parsed.get("queries") or []) if str(q).strip()]
            return queries[:2] if queries else [request.target]
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[CodeSearch] 首轮规划失败，降级为直搜 target: {exc}")
            return [request.target]

    async def _evaluate_and_reformulate(
        self,
        request: CodeSearchRequest,
        evidence: Sequence[CodeChunkEvidence],
        attempted_queries: Sequence[str],
        budget: ChildBudget,
    ) -> Dict[str, Any]:
        """判别已有证据是否充分；若不充分，根据切片提取的新线索重写检索词。"""
        lines = [
            "## 模式 A：切片相关性判别与换词重试",
            f"检索目标：{request.target}",
        ]
        if request.questions:
            lines.append("具体问题：")
            lines.extend(f"- {q}" for q in request.questions)

        lines.append(f"\n已尝试过的检索词：{', '.join(attempted_queries)}")
        lines.append(f"\n当前已召回证据（共 {len(evidence)} 个切片）：")

        for item in evidence[:8]:
            snippet, _ = truncate_text(item.content, 400)
            lines.append(f"### {item.location} ({item.scope or '全局'})\n{snippet}")

        lines.append(
            "\n要求：\n"
            "1. 若已有切片已完整解答了问题或找到了定义，返回 `{\"status\": \"sufficient\", \"queries\": [], \"reason\": \"...\"}` 触发早停；\n"
            "2. 若现有切片未完全覆盖，从代码中观察新的函数名/结构体/头文件，返回 `{\"status\": \"need_more\", \"queries\": [\"新词\"], \"reason\": \"...\"}`；\n"
            "3. 只能返回 JSON。"
        )

        try:
            response = await self._gateway.invoke(
                self._config.model_tier,
                [
                    SystemMessage(content=self._prompts.load("code_search")),
                    HumanMessage(content="\n".join(lines)),
                ],
                force_json=True,
            )
            budget.add_tokens(response.total_tokens)
            parsed = extract_json_object(response.content) or {}
            return parsed
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[CodeSearch] 判别与改词阶段失败: {exc}")
            return {"status": "sufficient", "queries": []}

    async def _retrieve_all(
        self,
        queries: Sequence[str],
        *,
        top_k: int,
        language: Optional[str] = None,
    ) -> List[CodeChunkEvidence]:
        """并发执行多词 RAG 检索。"""
        async def run_one(query: str) -> List[CodeChunkEvidence]:
            try:
                raw_chunks = await self._execute_rag_query(query, top_k=top_k, language=language)
                results: List[CodeChunkEvidence] = []
                for chunk in raw_chunks:
                    results.append(
                        CodeChunkEvidence(
                            file_path=str(chunk.get("file_path") or ""),
                            start_line=int(chunk.get("start_line") or 1),
                            end_line=int(chunk.get("end_line") or 1),
                            scope=str(chunk.get("enclosing_scope") or chunk.get("scope") or ""),
                            content=str(chunk.get("content") or ""),
                            git_commit=str(chunk.get("git_commit") or ""),
                        )
                    )
                return results
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[CodeSearch] 检索失败 [{query}]: {exc}")
                return []

        batches = await asyncio.gather(*(run_one(q) for q in queries))
        collected: List[CodeChunkEvidence] = []
        for batch in batches:
            collected.extend(batch)
        return collected

    async def _execute_rag_query(
        self,
        query: str,
        *,
        top_k: int,
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """底层 RAG 客户端/工具适配调用。"""
        tool = self._rag_client_or_tool
        payload: Dict[str, Any] = {"query": query, "top_k": top_k}
        if language:
            payload["filters"] = {"language": language}

        # 1. 直接适配 search_chunks 方法
        if hasattr(tool, "search_chunks"):
            return await tool.search_chunks(query, top_k=top_k, language=language)

        # 2. 适配 ServiceClient (HTTP Client)
        if hasattr(tool, "request_json"):
            data = await tool.request_json("POST", "/api/v1/retrieve", payload=payload)
            return data.get("results") or data.get("chunks") or []

        # 3. 适配 RagSearchTool
        if hasattr(tool, "_client") and hasattr(tool._client, "request_json"):
            data = await tool._client.request_json("POST", "/api/v1/retrieve", payload=payload)
            return data.get("results") or data.get("chunks") or []

        return []

    async def _distill(
        self,
        request: CodeSearchRequest,
        evidence: Sequence[CodeChunkEvidence],
        attempted_queries: Sequence[str],
        budget: ChildBudget,
    ) -> Mapping[str, Any]:
        """模式 B：从收集到的证据提炼最终结构化报告。"""
        if not evidence:
            return {
                "status": "not_found",
                "findings": [],
                "code_snippets": [],
                "unresolved": [request.target, *request.questions],
                "warnings": [f"经 3 轮检索（已尝试检索词：{', '.join(attempted_queries)}），未召回到相关源码切片"],
            }

        lines = [
            "## 模式 B：结论提炼与引用归因",
            f"检索目标：{request.target}",
        ]
        if request.questions:
            lines.append("待解答问题：")
            lines.extend(f"- {q}" for q in request.questions)

        lines.append(f"\n## 真实召回的代码切片（唯一合法证据源，共 {len(evidence)} 条）")
        blocks = []
        for item in evidence:
            blocks.append(
                f"### {item.location} ({item.scope or '全局'})\n{item.content}"
            )
        lines.append(_EVIDENCE_SEPARATOR.join(blocks))

        lines.append(
            "\n## 要求\n"
            "1. 严格基于上述代码切片提炼结论；\n"
            "2. `locations` 必须从上述切片的 `file_path:start_line-end_line` 中直接选取；\n"
            "3. 如果完全找不到目标实现，将 `status` 设为 `\"not_found\"`；如果只找到部分，设为 `\"partial\"`；\n"
            "4. 提取核心实现的完整关键代码块到 `code_snippets`；\n"
            "5. 只输出 JSON。"
        )

        try:
            response = await self._gateway.invoke(
                self._config.model_tier,
                [
                    SystemMessage(content=self._prompts.load("code_search")),
                    HumanMessage(content="\n".join(lines)),
                ],
                force_json=True,
            )
            budget.add_tokens(response.total_tokens)
            parsed = extract_json_object(response.content)
            if parsed is None:
                logger.warning("[CodeSearch] 提炼输出不是合法 JSON，返回 fallback 结构")
                return {"status": "partial", "findings": []}
            return parsed
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[CodeSearch] 提炼阶段失败: {exc}")
            return {"status": "not_found", "unresolved": [request.target]}

    async def _emit(self, event: Mapping[str, Any]) -> None:
        """向任务事件总线发送事件。"""
        if self._bus is None:
            return
        await self._bus.emit(event)
