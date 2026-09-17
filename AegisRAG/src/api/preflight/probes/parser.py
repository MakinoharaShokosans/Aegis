"""语法树切分器与 Markdown 解析就绪度探针。

验证 Tree-Sitter C/C++/Go 语法解析、Markdown 面包屑提取 (CCH) 及 Fallback 切分器可用性。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, List

from api.preflight.models import CheckStatus, DiagnosticItem
from api.preflight.probes.base import BaseProbe
from indexer.ast_splitter import split_ast
from indexer.fallback_splitter import split_fallback
from indexer.markdown_splitter import split_markdown

if TYPE_CHECKING:
    from api.settings import RagConfig

__all__ = ["ParserProbe"]


class ParserProbe(BaseProbe):
    """AST 语法解析与切分器就绪度探针。"""

    @property
    def category_name(self) -> str:
        return "语法解析器与切分器就绪度"

    def run_checks(self, settings: RagConfig) -> List[DiagnosticItem]:
        items: List[DiagnosticItem] = []

        # 1. Tree-Sitter C 语言切分测试
        c_code = "int add(int a, int b) {\n    return a + b;\n}\n"
        try:
            start = time.perf_counter()
            chunks_c = split_ast(content=c_code, file_path="main.c", repo_name="probe_repo")
            lat = (time.perf_counter() - start) * 1000.0
            if len(chunks_c) == 1 and chunks_c[0].chunk_type == "function":
                items.append(
                    DiagnosticItem(
                        name="Tree-Sitter C 语法切分",
                        status=CheckStatus.PASS,
                        message=f"C 语言 AST 解析正常 (提取 1 个函数切片, 耗时: {lat:.2f}ms)",
                        latency_ms=lat,
                    )
                )
            else:
                items.append(
                    DiagnosticItem(
                        name="Tree-Sitter C 语法切分",
                        status=CheckStatus.WARN,
                        message=f"C 语言解析产出切片数异常: {len(chunks_c)}",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            items.append(
                DiagnosticItem(
                    name="Tree-Sitter C 语法切分",
                    status=CheckStatus.FAIL,
                    message=f"C 语法树解析失败: {exc}",
                    remediation="请核查 tree-sitter-c 动态库版本与编译状态",
                )
            )

        # 2. Tree-Sitter C++ 语法切分测试
        cpp_code = "class Calculator {\npublic:\n    int multiply(int x, int y) { return x * y; }\n};\n"
        try:
            start = time.perf_counter()
            chunks_cpp = split_ast(content=cpp_code, file_path="calc.cpp", repo_name="probe_repo")
            lat = (time.perf_counter() - start) * 1000.0
            if len(chunks_cpp) >= 1:
                items.append(
                    DiagnosticItem(
                        name="Tree-Sitter C++ 语法切分",
                        status=CheckStatus.PASS,
                        message=f"C++ 语言 AST 解析正常 (提取 {len(chunks_cpp)} 个切片, 耗时: {lat:.2f}ms)",
                        latency_ms=lat,
                    )
                )
            else:
                items.append(
                    DiagnosticItem(
                        name="Tree-Sitter C++ 语法切分",
                        status=CheckStatus.WARN,
                        message=f"C++ 语言解析未提取到切片: {len(chunks_cpp)}",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            items.append(
                DiagnosticItem(
                    name="Tree-Sitter C++ 语法切分",
                    status=CheckStatus.FAIL,
                    message=f"C++ 语法树解析失败: {exc}",
                    remediation="请核查 tree-sitter-cpp 动态库版本与编译状态",
                )
            )

        # 3. Tree-Sitter Go 语法切分测试
        go_code = "package main\n\nfunc Greet(name string) string {\n\treturn \"Hello, \" + name\n}\n"
        try:
            start = time.perf_counter()
            chunks_go = split_ast(content=go_code, file_path="main.go", repo_name="probe_repo")
            lat = (time.perf_counter() - start) * 1000.0
            if len(chunks_go) == 1 and chunks_go[0].chunk_type == "function":
                items.append(
                    DiagnosticItem(
                        name="Tree-Sitter Go 语法切分",
                        status=CheckStatus.PASS,
                        message=f"Go 语言 AST 解析正常 (提取 1 个函数切片, 耗时: {lat:.2f}ms)",
                        latency_ms=lat,
                    )
                )
            else:
                items.append(
                    DiagnosticItem(
                        name="Tree-Sitter Go 语法切分",
                        status=CheckStatus.WARN,
                        message=f"Go 语言解析产出切片数异常: {len(chunks_go)}",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            items.append(
                DiagnosticItem(
                    name="Tree-Sitter Go 语法切分",
                    status=CheckStatus.FAIL,
                    message=f"Go 语法树解析失败: {exc}",
                    remediation="请核查 tree-sitter-go 动态库版本与编译状态",
                )
            )

        # 4. Markdown 面包屑提取 (Contextual Chunk Header) 测试
        md_content = "# Section 1\n\n## SubSection 1.1\n\nSome documentation text here.\n"
        try:
            start = time.perf_counter()
            chunks_md = split_markdown(
                content=md_content,
                file_path="docs/spec.md",
                repo_name="probe_repo",
            )
            lat = (time.perf_counter() - start) * 1000.0
            has_breadcrumbs = any(c.enclosing_scope for c in chunks_md)
            if chunks_md and has_breadcrumbs:
                items.append(
                    DiagnosticItem(
                        name="Markdown 面包屑切分 (CCH)",
                        status=CheckStatus.PASS,
                        message=f"Markdown 标题继承与面包屑注入正常 (提取 {len(chunks_md)} 切片, 耗时: {lat:.2f}ms)",
                        latency_ms=lat,
                    )
                )
            else:
                items.append(
                    DiagnosticItem(
                        name="Markdown 面包屑切分 (CCH)",
                        status=CheckStatus.WARN,
                        message="Markdown 切分完成，但未能提取到层级面包屑",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            items.append(
                DiagnosticItem(
                    name="Markdown 面包屑切分 (CCH)",
                    status=CheckStatus.FAIL,
                    message=f"Markdown 切分器执行失败: {exc}",
                    remediation="请检查 langchain-text-splitters 依赖",
                )
            )

        # 5. Fallback 通用切分器测试
        plain_text = "line 1\nline 2\nline 3\nline 4\n" * 10
        try:
            chunks_fb = split_fallback(
                content=plain_text,
                file_path="raw.txt",
                repo_name="probe_repo",
                chunk_size=settings.indexer.chunk_size,
                chunk_overlap=settings.indexer.chunk_overlap,
            )
            items.append(
                DiagnosticItem(
                    name="Fallback 文本切分器",
                    status=CheckStatus.PASS,
                    message=f"通用递归切分正常 (产出 {len(chunks_fb)} 切片)",
                )
            )
        except Exception as exc:  # noqa: BLE001
            items.append(
                DiagnosticItem(
                    name="Fallback 文本切分器",
                    status=CheckStatus.FAIL,
                    message=f"Fallback 切分器执行失败: {exc}",
                )
            )

        return items
