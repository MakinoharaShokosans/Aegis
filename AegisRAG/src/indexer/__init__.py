"""Ingest 侧：语言分发 + 语法感知切分（02）。

模块分工：
- ``dispatch``：按扩展名路由到具体切分器，并处理文件级 AST 解析失败降级（02 §2/§4）；
- ``ast_splitter``：tree-sitter C/C++/Go 语法树切分（02 §4，真 AST 范围仅此三种语言）；
- ``markdown_splitter``：Markdown 标题层级切分（02 §5）；
- ``fallback_splitter``：Python 及未匹配语言的降级切分（02 §3 纠偏后新增）；
- ``metadata``：统一的证据元数据 Schema（02 §6）。

依赖方向：本包只允许依赖 ``embeddings``（详见 07_directory_structure.md §5 依赖矩阵
关于"切分后立即向量化"这一条路径的例外说明——当前实现中该组合发生在 ``api/routes/ingest.py``
的编排层，``indexer`` 各模块本身不直接 import ``embeddings``）。
"""

from __future__ import annotations

__all__: list[str] = []
