"""切片元数据契约单元测试。

验证 ChunkMetadata 必填字段校验、SHA-256 哈希计算与工厂方法 build()。
"""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from indexer.metadata import ChunkMetadata


class TestChunkMetadata:
    """ChunkMetadata 契约测试套件。"""

    def test_chunk_metadata_build_factory(self) -> None:
        content = "int add(int a, int b) { return a + b; }"
        expected_hash = hashlib.sha1(content.encode("utf-8")).hexdigest()

        chunk = ChunkMetadata.build(
            file_path="src/math.c",
            start_line=10,
            end_line=12,
            content=content,
            language="c",
            repo_name="demo_repo",
            chunk_index=0,
            chunk_type="function",
            enclosing_scope="math_module",
        )

        assert chunk.content_hash == expected_hash
        assert chunk.file_path == "src/math.c"
        assert chunk.start_line == 10
        assert chunk.end_line == 12
        assert chunk.chunk_type == "function"
        assert chunk.enclosing_scope == "math_module"
        assert chunk.oversized is False

    def test_missing_required_fields_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            # 缺失 content_hash / language / repo_name 等必填项
            ChunkMetadata(
                file_path="src/math.c",
                start_line=1,
                end_line=2,
                content="test",
            )
