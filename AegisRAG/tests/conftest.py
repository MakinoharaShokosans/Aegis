"""Pytest 全局共享 Fixtures 与测试基础设施。

规范：提供配置沙箱、临时存储路径隔离与典型测试代码夹具。
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest

from api.settings import RagConfig, get_settings


@pytest.fixture
def base_settings() -> RagConfig:
    """获取当前只读配置单例。"""
    return get_settings()


@pytest.fixture
def sandbox_settings(tmp_path: Path, base_settings: RagConfig) -> RagConfig:
    """生成隔离的沙箱测试配置（Qdrant 存储与 FastEmbed 缓存均指向 tmp_path）。"""
    qdrant_dir = tmp_path / "qdrant_test_data"
    cache_dir = tmp_path / "fastembed_test_cache"

    qdrant_cfg = base_settings.qdrant.model_copy(update={"storage_path": str(qdrant_dir)})
    embedding_cfg = base_settings.embedding.model_copy(update={"cache_dir": str(cache_dir)})
    rerank_cfg = base_settings.rerank.model_copy(update={"cache_dir": str(cache_dir)})

    return base_settings.model_copy(
        update={
            "qdrant": qdrant_cfg,
            "embedding": embedding_cfg,
            "rerank": rerank_cfg,
        }
    )


@pytest.fixture
def fixtures_dir() -> Path:
    """定位 tests/fixtures 目录路径。"""
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def sample_c_code() -> str:
    """标准 C 语言测试代码片段。"""
    return (
        "#include <stdio.h>\n\n"
        "#define MAX_BUFFER 1024\n\n"
        "struct Point {\n"
        "    int x;\n"
        "    int y;\n"
        "};\n\n"
        "int calculate_sum(int a, int b) {\n"
        "    return a + b;\n"
        "}\n\n"
        "int main() {\n"
        "    printf(\"Sum: %d\\n\", calculate_sum(10, 20));\n"
        "    return 0;\n"
        "}\n"
    )


@pytest.fixture
def sample_cpp_code() -> str:
    """标准 C++ 语言测试代码片段（含类与模板）。"""
    return (
        "#include <iostream>\n"
        "#include <vector>\n\n"
        "template <typename T>\n"
        "class Container {\n"
        "public:\n"
        "    void add(const T& item) {\n"
        "        items_.push_back(item);\n"
        "    }\n"
        "    size_t size() const {\n"
        "        return items_.size();\n"
        "    }\n"
        "private:\n"
        "    std::vector<T> items_;\n"
        "};\n"
    )


@pytest.fixture
def sample_go_code() -> str:
    """标准 Go 语言测试代码片段。"""
    return (
        "package service\n\n"
        "import \"fmt\"\n\n"
        "type User struct {\n"
        "\tID   int64\n"
        "\tName string\n"
        "}\n\n"
        "func (u *User) String() string {\n"
        "\treturn fmt.Sprintf(\"User(%d, %s)\", u.ID, u.Name)\n"
        "}\n\n"
        "func NewUser(id int64, name string) *User {\n"
        "\treturn &User{ID: id, Name: name}\n"
        "}\n"
    )


@pytest.fixture
def sample_py_code() -> str:
    """标准 Python 测试代码片段。"""
    return (
        "from dataclasses import dataclass\n\n"
        "@dataclass\n"
        "class Document:\n"
        "    doc_id: str\n"
        "    text: str\n\n"
        "def format_document(doc: Document) -> str:\n"
        "    return f'[{doc.doc_id}] {doc.text}'\n"
    )


@pytest.fixture
def sample_markdown_code() -> str:
    """标准 Markdown 测试文档片段（多级标题与面包屑）。"""
    return (
        "# 系统架构设计\n\n"
        "这是架构概览介绍。\n\n"
        "## 存储引擎选型\n\n"
        "### Qdrant 向量数据库\n\n"
        "Qdrant 支持 Dense 与 Sparse 双路混合检索与 RRF 原生融合。\n\n"
        "### 本地缓存策略\n\n"
        "使用 FastEmbed 进行本地 ONNX 推理与权重缓存。\n"
    )
