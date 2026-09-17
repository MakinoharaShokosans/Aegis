"""Tree-sitter AST 语法感知切分：C/C++/Go（02 §4）。

真 AST 范围锁定为 C/C++/Go（已锁定的 ``tree-sitter-c/cpp/go`` 依赖），不含
Python/Rust（见 02 §3 的纠偏裁决——不为它们额外引入新的 C 扩展重依赖）。
切分沿语法树节点边界走，不允许把一个函数体/结构体从中腰斩。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import tree_sitter_c
import tree_sitter_cpp
import tree_sitter_go
from tree_sitter import Language, Node, Parser

from indexer.metadata import ChunkMetadata, ChunkType

__all__ = ["AST_EXTENSIONS", "split_ast"]


@dataclass(frozen=True)
class _LanguageSpec:
    """单个语言的 tree-sitter 语法树配置。"""

    label: str
    language: Language
    #: 节点类型 → 切片类型标签；出现在此表中的节点类型即为切分边界，
    #: 不在表中的节点一律继续向下递归寻找边界（见 :func:`_collect_boundaries`）。
    boundary_types: Dict[str, ChunkType]
    #: 捕获后尝试吸收的紧邻尾随 token（如 struct/class 定义后的分号）
    trailing_tokens: Set[str]


_C_BOUNDARIES: Dict[str, ChunkType] = {
    "function_definition": "function",
    "struct_specifier": "struct",
    "enum_specifier": "struct",
    "union_specifier": "struct",
    "type_definition": "struct",
    "preproc_def": "generic",
    "preproc_function_def": "generic",
}

_CPP_BOUNDARIES: Dict[str, ChunkType] = {
    **_C_BOUNDARIES,
    "class_specifier": "struct",
    "template_declaration": "generic",
}

_GO_BOUNDARIES: Dict[str, ChunkType] = {
    "function_declaration": "function",
    "method_declaration": "function",
    "type_declaration": "struct",
}

#: 扩展名 → 语言键
_EXTENSION_TO_KEY = {
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".go": "go",
}

#: 供 dispatch.py 判断"是否应该走 AST 路径"
AST_EXTENSIONS = set(_EXTENSION_TO_KEY)

#: 近似 token 长度估算（与 AegisAgent 侧 observation_pruner 等模块的 len(text)//4 启发式一致）
_CHARS_PER_TOKEN = 4

#: 语言键 → 已构造的 _LanguageSpec（延迟构造，避免模块导入期就加载语法库）
_LANGUAGE_SPECS: Dict[str, _LanguageSpec] = {}


def _build_spec(key: str) -> _LanguageSpec:
    """按语言键构造 tree-sitter 语法规格（首次访问时才真正加载语法库）。"""
    if key == "c":
        return _LanguageSpec("c", Language(tree_sitter_c.language()), _C_BOUNDARIES, {";"})
    if key == "cpp":
        return _LanguageSpec("cpp", Language(tree_sitter_cpp.language()), _CPP_BOUNDARIES, {";"})
    if key == "go":
        return _LanguageSpec("go", Language(tree_sitter_go.language()), _GO_BOUNDARIES, set())
    raise ValueError(f"未知语言键: {key!r}")


def _spec_for(ext: str) -> Optional[_LanguageSpec]:
    """按扩展名取语言规格（首次访问时构造并缓存）。"""
    key = _EXTENSION_TO_KEY.get(ext)
    if key is None:
        return None
    if key not in _LANGUAGE_SPECS:
        _LANGUAGE_SPECS[key] = _build_spec(key)
    return _LANGUAGE_SPECS[key]


def split_ast(
    *,
    content: str,
    file_path: str,
    repo_name: str,
    git_commit: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> List[ChunkMetadata]:
    """对源码做 tree-sitter AST 语法感知切分。

    Args:
        content: 文件原文。
        file_path: 相对仓库根目录的路径。
        repo_name: 仓库标识。
        git_commit: 索引时刻的提交哈希。
        max_tokens: 超过此 token 近似值的切片标记 ``oversized=True``（见 02 §4），
            ``None`` 时不标记。

    Returns:
        切片列表；全局变量声明、import/include、注释等非边界节点不产出切片，
        这是刻意的范围裁剪（见 02 §4），不是遗漏。

    Raises:
        ValueError: 扩展名不在 AST 支持范围内。
    """
    ext = _extension_of(file_path)
    spec = _spec_for(ext)
    if spec is None:
        raise ValueError(f"{file_path} 的扩展名不在 AST 切分支持范围内: {ext!r}")

    source = content.encode("utf-8")
    parser = Parser(spec.language)
    tree = parser.parse(source)

    boundary_nodes: List[Node] = []
    _collect_boundaries(tree.root_node, spec.boundary_types, boundary_nodes)

    chunks: List[ChunkMetadata] = []
    for index, node in enumerate(boundary_nodes):
        start_byte, end_byte = _absorb_trailing_token(node, spec.trailing_tokens)
        text = source[start_byte:end_byte].decode("utf-8", errors="replace")
        if not text.strip():
            continue
        oversized = max_tokens is not None and (len(text) // _CHARS_PER_TOKEN) > max_tokens
        chunks.append(
            ChunkMetadata.build(
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                content=text,
                language=spec.label,
                repo_name=repo_name,
                git_commit=git_commit,
                chunk_index=index,
                chunk_type=spec.boundary_types[node.type],
                oversized=oversized,
            )
        )
    return chunks


def _collect_boundaries(node: Node, boundary_types: Dict[str, ChunkType], out: List[Node]) -> None:
    """深度优先遍历语法树，收集边界节点；命中边界后不再继续下探。

    这一条"命中即停"规则同时处理了两类情况而无需额外分支：
    - 顶层非边界容器（``namespace_definition``/``declaration_list`` 等）会被
      自然递归穿透，直到找到内部真正的边界节点；
    - ``template_declaration`` 这种"边界包住边界"的场景（模板类/模板函数）
      整体作为一个切片，不会同时把内部的 class/function 又切一遍。
    """
    if node.type in boundary_types:
        out.append(node)
        return
    for child in node.children:
        _collect_boundaries(child, boundary_types, out)


def _absorb_trailing_token(node: Node, trailing_tokens: Set[str]) -> Tuple[int, int]:
    """把紧邻的尾随 token（如 struct 定义后的分号）并入切片范围。

    Args:
        node: 边界节点。
        trailing_tokens: 需要吸收的 token 文本集合。

    Returns:
        ``(start_byte, end_byte)``，必要时 ``end_byte`` 已扩展到吸收的 token 之后。
    """
    end_byte = node.end_byte
    sibling = node.next_sibling
    if sibling is not None and sibling.type in trailing_tokens:
        end_byte = sibling.end_byte
    return node.start_byte, end_byte


def _extension_of(file_path: str) -> str:
    """提取文件扩展名（小写，含前导点）。"""
    idx = file_path.rfind(".")
    return file_path[idx:].lower() if idx != -1 else ""
