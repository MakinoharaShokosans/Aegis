"""Go AST 语法感知切分器单元测试。

验证函数定义、结构体方法、类型声明边界切分。
"""

from __future__ import annotations

from indexer.ast_splitter import split_ast


class TestAstSplitterGo:
    """Go AST 切分测试套件。"""

    def test_go_function_and_method_splitting(self, sample_go_code: str) -> None:
        chunks = split_ast(
            content=sample_go_code,
            file_path="pkg/service/user.go",
            repo_name="go_repo",
            git_commit="git987",
        )

        assert len(chunks) == 3

        # 1. 类型定义 type User struct
        type_chunk = next((c for c in chunks if "type User struct" in c.content), None)
        assert type_chunk is not None
        assert type_chunk.chunk_type == "struct"
        assert type_chunk.language == "go"

        # 2. 结构体方法 (u *User) String()
        method_chunk = next((c for c in chunks if "String() string" in c.content), None)
        assert method_chunk is not None
        assert method_chunk.chunk_type == "function"

        # 3. 构造函数 NewUser
        fn_chunk = next((c for c in chunks if "NewUser" in c.content), None)
        assert fn_chunk is not None
        assert fn_chunk.chunk_type == "function"
