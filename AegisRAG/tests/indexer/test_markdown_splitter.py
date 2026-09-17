"""Markdown 标题层级切分器单元测试。

验证 H1~H3 标题切分与 Contextual Chunk Header (CCH) 面包屑生成。
"""

from __future__ import annotations

from indexer.markdown_splitter import split_markdown


class TestMarkdownSplitter:
    """Markdown 标题切分测试套件。"""

    def test_markdown_header_hierarchy_and_breadcrumbs(self, sample_markdown_code: str) -> None:
        chunks = split_markdown(
            content=sample_markdown_code,
            file_path="docs/architecture.md",
            repo_name="doc_repo",
            git_commit="commit111",
        )

        assert len(chunks) >= 3

        # 检查各切片的 enclosing_scope (CCH 面包屑)
        qdrant_chunk = next((c for c in chunks if "Qdrant 向量数据库" in (c.enclosing_scope or "")), None)
        assert qdrant_chunk is not None
        assert "系统架构设计" in qdrant_chunk.enclosing_scope
        assert "存储引擎选型" in qdrant_chunk.enclosing_scope
        assert qdrant_chunk.chunk_type == "markdown_section"
        assert qdrant_chunk.language == "markdown"
        assert qdrant_chunk.git_commit == "commit111"

        # 验证行号单调递增
        for c in chunks:
            assert 1 <= c.start_line <= c.end_line

    def test_empty_markdown_returns_empty_list(self) -> None:
        chunks = split_markdown(
            content="   \n\n  ",
            file_path="empty.md",
            repo_name="doc_repo",
        )
        assert chunks == []
