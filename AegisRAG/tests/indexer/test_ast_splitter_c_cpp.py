"""C / C++ AST 语法感知切分器单元测试。

验证函数边界、结构体/类边界、尾随分号吸收、宏定义与超大切片标记。
"""

from __future__ import annotations

import pytest

from indexer.ast_splitter import split_ast


class TestAstSplitterCCpp:
    """C/C++ AST 语法感知切分测试套件。"""

    def test_c_function_and_struct_splitting(self, sample_c_code: str) -> None:
        chunks = split_ast(
            content=sample_c_code,
            file_path="src/main.c",
            repo_name="c_repo",
            git_commit="abc1234",
        )

        assert len(chunks) >= 3
        # 1. 结构体 (struct Point)
        struct_chunk = next((c for c in chunks if "struct Point" in c.content), None)
        assert struct_chunk is not None
        assert struct_chunk.chunk_type == "struct"
        assert struct_chunk.language == "c"
        assert struct_chunk.file_path == "src/main.c"
        assert struct_chunk.git_commit == "abc1234"
        # 尾随分号必须被完整吸收
        assert struct_chunk.content.strip().endswith("};")

        # 2. 宏定义 (#define MAX_BUFFER)
        macro_chunk = next((c for c in chunks if "MAX_BUFFER" in c.content), None)
        assert macro_chunk is not None
        assert macro_chunk.chunk_type == "generic"

        # 3. 函数 (calculate_sum, main)
        fn_chunk = next((c for c in chunks if "calculate_sum" in c.content), None)
        assert fn_chunk is not None
        assert fn_chunk.chunk_type == "function"
        assert fn_chunk.start_line < fn_chunk.end_line

    def test_cpp_template_class_splitting(self, sample_cpp_code: str) -> None:
        chunks = split_ast(
            content=sample_cpp_code,
            file_path="include/container.hpp",
            repo_name="cpp_repo",
        )

        assert len(chunks) >= 1
        template_chunk = chunks[0]
        assert "template <typename T>" in template_chunk.content
        assert "class Container" in template_chunk.content
        assert template_chunk.language == "cpp"
        # 尾随分号吸收
        assert template_chunk.content.strip().endswith("};")

    def test_oversized_chunk_flagging(self) -> None:
        large_code = "int process_data() {\n" + "    int x = 1;\n" * 200 + "    return x;\n}\n"
        # 启发式 token 限制较小
        chunks = split_ast(
            content=large_code,
            file_path="large.c",
            repo_name="c_repo",
            max_tokens=20,
        )
        assert len(chunks) == 1
        assert chunks[0].oversized is True

    def test_unsupported_extension_raises_error(self) -> None:
        with pytest.raises(ValueError, match="不在 AST 切分支持范围内"):
            split_ast(
                content="var x = 1;",
                file_path="script.js",
                repo_name="js_repo",
            )
