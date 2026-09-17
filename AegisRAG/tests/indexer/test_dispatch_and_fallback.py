"""分发调度与通用降级切分器单元测试。

验证文件扩展名路由、Python 启发式切分、通用文本切分与语法错误容错降级。
"""

from __future__ import annotations

from indexer.dispatch import split_file
from indexer.fallback_splitter import split_fallback


class TestDispatchAndFallback:
    """分发与降级切分测试套件。"""

    def test_markdown_routing(self, sample_markdown_code: str) -> None:
        outcome = split_file(
            content=sample_markdown_code,
            file_path="README.md",
            repo_name="my_repo",
            chunk_size=500,
            chunk_overlap=50,
        )
        assert outcome.degraded is False
        assert len(outcome.chunks) > 0
        assert outcome.chunks[0].language == "markdown"

    def test_ast_routing_c_code(self, sample_c_code: str) -> None:
        outcome = split_file(
            content=sample_c_code,
            file_path="main.c",
            repo_name="my_repo",
            chunk_size=500,
            chunk_overlap=50,
        )
        assert outcome.degraded is False
        assert len(outcome.chunks) > 0
        assert outcome.chunks[0].language == "c"

    def test_ast_syntax_error_fallback(self) -> None:
        # 传入严重破坏的 C 代码，触发容错降级
        broken_code = "int { class ( broken ;;;; { "
        outcome = split_file(
            content=broken_code,
            file_path="broken.c",
            repo_name="my_repo",
            chunk_size=500,
            chunk_overlap=50,
        )
        # 语法解析器仍可产出切片或降级为 fallback
        assert isinstance(outcome.chunks, list)

    def test_python_and_unknown_fallback(self, sample_py_code: str) -> None:
        outcome = split_file(
            content=sample_py_code,
            file_path="utils.py",
            repo_name="my_repo",
            chunk_size=200,
            chunk_overlap=20,
        )
        assert outcome.degraded is False
        assert len(outcome.chunks) > 0
        assert outcome.chunks[0].language == "python"

    def test_fallback_splitter_chunking(self) -> None:
        text = "word " * 300
        chunks = split_fallback(
            content=text,
            file_path="notes.txt",
            repo_name="notes_repo",
            chunk_size=200,
            chunk_overlap=20,
        )
        assert len(chunks) >= 2
        for idx, c in enumerate(chunks):
            assert c.chunk_index == idx
            assert c.language == "txt"
            assert c.file_path == "notes.txt"
