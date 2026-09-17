"""代码检索子智能体的强类型契约与输出净化。

本模块是源码检索信任边界与保真度的技术核心：
1. **位置白名单校验**：子模型报告的所有代码位置（``file_path:start-end``）必须严格来自
   AegisRAG 本次真实召回的切片集合，伪造或凭记忆捏造的坐标直接被丢弃；
2. **状态机与拒答约束**：显式支持 ``found``、``partial`` 与 ``not_found`` 三态，
   3 轮未找到时如实返回 ``not_found`` 与已尝试检索词列表，杜绝代码幻觉；
3. **长度硬上限与结构化信封**：对输出结论与代码块进行长度截断，并通过代码模板统一渲染。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Mapping, Optional, Protocol, Sequence, Set, runtime_checkable
from pydantic import BaseModel, Field

from agent_runtime.guardrails.injection_guard import scan_injection, summarize_matches
from agent_runtime.structured_output import truncate_text

__all__ = [
    "CodeChunkEvidence",
    "CodeFinding",
    "CodeSearchReport",
    "CodeSearchRequest",
    "CodeSnippet",
    "StructuredCodeSearchTool",
    "build_code_report",
]

#: 允许的代码语言标签
_ALLOWED_LANGUAGES = {
    "c",
    "cpp",
    "c++",
    "go",
    "python",
    "rust",
    "java",
    "javascript",
    "typescript",
    "bash",
    "sh",
    "shell",
    "json",
    "yaml",
    "toml",
    "diff",
    "text",
    "plaintext",
}

#: 渲染信封的字符预算下限
_MIN_REPORT_BUDGET = 256


@runtime_checkable
class StructuredCodeSearchTool(Protocol):
    """代码检索子智能体对底层 RAG 检索工具的最小契约。"""

    name: str
    trust: str

    async def search_chunks(
        self,
        query: str,
        *,
        top_k: int = 5,
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """执行源码检索并返回结构化切片字典列表。"""


class CodeSearchRequest(BaseModel):
    """主 Agent 发起的高级代码检索请求。"""

    target: str = Field(description="检索目标（如：定位某函数实现、排查某逻辑、查找结构体定义）")
    questions: List[str] = Field(default_factory=list, description="需要回答的具体代码逻辑问题")
    file_hints: List[str] = Field(default_factory=list, description="可选，可能相关的文件路径或目录前缀")
    language: Optional[str] = Field(default=None, description="可选，限定语言（c/cpp/go/python等）")
    max_chunks: Optional[int] = Field(default=None, description="可选，覆盖单轮召回切片数上限")


class CodeChunkEvidence(BaseModel):
    """一条真实从 AegisRAG 召回的代码切片证据（仅保存在隔离区内存中）。"""

    file_path: str = Field(description="源文件相对路径")
    start_line: int = Field(description="起始行号")
    end_line: int = Field(description="结束行号")
    scope: str = Field(default="", description="封闭作用域（如函数名/类名）")
    content: str = Field(default="", description="代码切片正文")
    git_commit: str = Field(default="", description="切片所属 Git 提交哈希")

    @property
    def location(self) -> str:
        """格式化位置标识符：file_path:start_line-end_line。"""
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


class CodeFinding(BaseModel):
    """一条经过提炼的代码事实结论。"""

    question: str = Field(description="被回答的问题或定位点")
    answer: str = Field(description="结论正文（长度受 max_answer_chars 约束）")
    confidence: Literal["high", "medium", "low"] = Field(default="medium", description="置信度")
    locations: List[str] = Field(default_factory=list, description="支撑位置（必须属于真实召回切片）")


class CodeSnippet(BaseModel):
    """一段关键源码片段。"""

    file_path: str = Field(description="文件路径")
    start_line: int = Field(description="起始行号")
    end_line: int = Field(description="结束行号")
    language: str = Field(default="text", description="语言标签")
    code: str = Field(description="逐字保留的代码块（长度受 max_code_chars 约束）")
    display_only: bool = Field(default=True, description="恒为 True，展示用途")

    @property
    def location(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


class CodeSearchReport(BaseModel):
    """代码检索子智能体的最终产物（唯一允许回流主 Agent 的形状）。"""

    target: str = Field(description="检索目标")
    status: Literal["found", "partial", "not_found"] = Field(
        default="found", description="检索终态：found(完全找到) / partial(部分找到) / not_found(未找到)"
    )
    findings: List[CodeFinding] = Field(default_factory=list, description="提炼的事实结论")
    code_snippets: List[CodeSnippet] = Field(default_factory=list, description="提取的关键代码片段")
    attempted_queries: List[str] = Field(default_factory=list, description="实际尝试过的检索词列表")
    unresolved: List[str] = Field(default_factory=list, description="未能解答的问题或未定位到的符号")
    warnings: List[str] = Field(default_factory=list, description="警告与降级说明")
    rounds_used: int = Field(default=0, description="实际使用的检索重试轮数")
    total_tokens: int = Field(default=0, description="子智能体消耗的 Token")
    elapsed_sec: float = Field(default=0.0, description="子智能体挂钟耗时（秒）")
    truncated: bool = Field(default=False, description="是否发生过截断")

    @property
    def is_empty(self) -> bool:
        """是否没有任何可用结论。"""
        return self.status == "not_found" or not (self.findings or self.code_snippets)

    def render_for_model(self, max_chars: int) -> str:
        """把报告渲染为注入主 Agent 的 Markdown 文本。"""
        budget = max(max_chars, _MIN_REPORT_BUDGET)
        sections: List[str] = [
            f'<code_search_summary source="code_search" status="{self.status}" trust="trusted">',
            f"目标：{self.target}",
            f"状态：{'完全找到' if self.status == 'found' else '部分找到' if self.status == 'partial' else '未检索到实现'}"
            f"（共经历 {self.rounds_used} 轮检索/换词，尝试检索词：{', '.join(self.attempted_queries) or '无'}）",
        ]

        if self.findings:
            sections.append("\n### 代码实现结论")
            for finding in self.findings:
                locs = ", ".join(finding.locations) if finding.locations else "（未标注具体行号）"
                sections.append(
                    f"- [{finding.confidence}] 针对「{finding.question}」：\n"
                    f"  {finding.answer}\n"
                    f"  位置: {locs}"
                )

        if self.code_snippets:
            sections.append("\n### 关键代码片段")
            for snippet in self.code_snippets:
                fence = _fence_for(snippet.code)
                loc = f"{snippet.file_path}:{snippet.start_line}-{snippet.end_line}"
                sections.append(
                    f"#### {loc}\n"
                    f"{fence}{snippet.language}\n{snippet.code}\n{fence}"
                )

        if self.unresolved:
            sections.append("\n### 未找到/未解决事项")
            sections.extend(f"- {item}" for item in self.unresolved)

        if self.warnings:
            sections.append("\n### 注意事项")
            sections.extend(f"- {item}" for item in self.warnings)

        sections.append("</code_search_summary>")
        rendered = "\n".join(sections)
        text, truncated = truncate_text(rendered, budget)
        if truncated:
            text = text.replace("</code_search_summary>", "")
            text += "\n（内容超长已截断）\n</code_search_summary>"
        return text


def _fence_for(code: str) -> str:
    """选择比代码中最长连续反引号更长的围栏。"""
    longest = 0
    for run in re.findall(r"`+", code):
        longest = max(longest, len(run))
    return "`" * max(3, longest + 1)


def _clean_language(raw: Any) -> str:
    """归一化语言标签。"""
    language = str(raw or "text").strip().lower()
    return language if language in _ALLOWED_LANGUAGES else "text"


def build_code_report(
    raw: Mapping[str, Any],
    *,
    target: str,
    fetched_evidence: Sequence[CodeChunkEvidence],
    attempted_queries: Sequence[str],
    config: Any,
    rounds_used: int,
    total_tokens: int,
    elapsed_sec: float,
) -> CodeSearchReport:
    """把子模型的原始提炼 JSON 净化为严格校验的 :class:`CodeSearchReport`。

    执行位置白名单、文本截断、防爆载与注入标注。
    """
    # 真实召回的位置与文件集合
    allowed_locations: Set[str] = {item.location for item in fetched_evidence}
    allowed_files: Set[str] = {item.file_path for item in fetched_evidence}
    warnings: List[str] = []
    truncated = False

    raw_status = str(raw.get("status") or "").strip().lower()
    if raw_status in {"found", "partial", "not_found"}:
        status: Literal["found", "partial", "not_found"] = raw_status  # type: ignore[assignment]
    else:
        status = "found" if fetched_evidence else "not_found"

    # 1. 提炼 Findings
    findings: List[CodeFinding] = []
    for item in _as_list(raw.get("findings"))[: int(config.max_findings)]:
        if not isinstance(item, Mapping):
            continue
        answer_raw = str(item.get("answer") or "").strip()
        question = str(item.get("question") or "").strip()
        if not answer_raw:
            continue

        answer, cut = truncate_text(answer_raw, int(config.max_answer_chars))
        truncated = truncated or cut

        # 位置白名单过滤：只保留真实召回过的 location 或有效文件引用
        raw_locs = [str(loc).strip() for loc in _as_list(item.get("locations")) if str(loc).strip()]
        valid_locs = []
        for loc in raw_locs:
            if loc in allowed_locations or any(loc.startswith(f"{f}:") or loc == f for f in allowed_files):
                valid_locs.append(loc)

        confidence = str(item.get("confidence") or "medium").lower()
        findings.append(
            CodeFinding(
                question=question or target,
                answer=answer,
                confidence=confidence if confidence in {"high", "medium", "low"} else "medium",
                locations=valid_locs,
            )
        )

    # 2. 提取 Code Snippets
    code_snippets: List[CodeSnippet] = []
    dropped_snippets = 0
    for item in _as_list(raw.get("code_snippets"))[: int(config.max_code_snippets)]:
        if not isinstance(item, Mapping):
            continue
        file_path = str(item.get("file_path") or "").strip()
        code_raw = str(item.get("code") or "")
        if not file_path or not code_raw.strip():
            continue

        # 文件必须真实存在于召回列表中
        if file_path not in allowed_files:
            dropped_snippets += 1
            continue

        try:
            start_line = int(item.get("start_line") or 1)
            end_line = int(item.get("end_line") or start_line)
        except (TypeError, ValueError):
            start_line, end_line = 1, 1

        code, cut = truncate_text(code_raw, int(config.max_code_chars))
        truncated = truncated or cut
        code_snippets.append(
            CodeSnippet(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                language=_clean_language(item.get("language")),
                code=code,
                display_only=True,
            )
        )

    if dropped_snippets:
        warnings.append(f"已丢弃 {dropped_snippets} 段未能匹配真实召回文件的代码片段")

    # 3. 注入样态扫描（纵深防御）
    for finding in findings:
        summary = summarize_matches(scan_injection(finding.answer))
        if summary and summary not in warnings:
            warnings.append(summary)
    for snippet in code_snippets:
        summary = summarize_matches(scan_injection(snippet.code))
        if summary and summary not in warnings:
            warnings.append(summary)

    # 4. 未解决事项
    unresolved = [str(item).strip() for item in _as_list(raw.get("unresolved")) if str(item).strip()]

    if not fetched_evidence:
        status = "not_found"
        warnings.append("在 3 轮检索内未能从代码库中召回到相关代码切片")

    return CodeSearchReport(
        target=target,
        status=status,
        findings=findings,
        code_snippets=code_snippets,
        attempted_queries=list(attempted_queries),
        unresolved=unresolved,
        warnings=warnings,
        rounds_used=rounds_used,
        total_tokens=total_tokens,
        elapsed_sec=elapsed_sec,
        truncated=truncated,
    )


def _as_list(value: Any) -> List[Any]:
    """把任意值安全地视为列表。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
