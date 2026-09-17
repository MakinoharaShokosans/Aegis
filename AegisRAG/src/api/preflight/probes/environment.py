"""系统环境与依赖完整性探针。

检查 Python 版本、平台架构、C 扩展库与核心依赖加载。
"""

from __future__ import annotations

import importlib
import platform
import sys
import time
from typing import TYPE_CHECKING, List

from api.preflight.models import CheckStatus, DiagnosticItem
from api.preflight.probes.base import BaseProbe

if TYPE_CHECKING:
    from api.settings import RagConfig

__all__ = ["EnvironmentProbe"]


class EnvironmentProbe(BaseProbe):
    """系统环境与关键依赖探针。"""

    @property
    def category_name(self) -> str:
        return "系统环境与依赖完整性"

    def run_checks(self, settings: RagConfig) -> List[DiagnosticItem]:
        items: List[DiagnosticItem] = []

        # 1. Python 运行时版本检查 (>= 3.11)
        py_version = sys.version_info
        py_str = f"{py_version.major}.{py_version.minor}.{py_version.micro}"
        if py_version >= (3, 11):
            items.append(
                DiagnosticItem(
                    name="Python 运行时版本",
                    status=CheckStatus.PASS,
                    message=f"Python {py_str} (>= 3.11 满足要求)",
                    details={"platform": platform.platform(), "architecture": platform.machine()},
                )
            )
        else:
            items.append(
                DiagnosticItem(
                    name="Python 运行时版本",
                    status=CheckStatus.FAIL,
                    message=f"当前 Python 版本为 {py_str}，低于最低要求 >= 3.11",
                    remediation="请使用 Python 3.11 或更高版本的虚拟环境重新运行",
                )
            )

        # 2. 核心 C/ONNX/Rust 扩展与依赖模块动态加载验证
        required_modules = [
            ("tree_sitter", "Tree-Sitter 核心语法解析引擎"),
            ("tree_sitter_c", "Tree-Sitter C 语言语法库"),
            ("tree_sitter_cpp", "Tree-Sitter C++ 语言语法库"),
            ("tree_sitter_go", "Tree-Sitter Go 语言语法库"),
            ("fastembed", "FastEmbed ONNX 向量化引擎"),
            ("onnxruntime", "ONNX Runtime 核心推理后端"),
            ("qdrant_client", "Qdrant 向量数据库客户端"),
            ("fastapi", "FastAPI 微服务框架"),
            ("pydantic", "Pydantic 数据验证契约"),
            ("langchain_text_splitters", "LangChain 文本切分器"),
        ]

        for mod_name, desc in required_modules:
            start = time.perf_counter()
            try:
                mod = importlib.import_module(mod_name)
                lat = (time.perf_counter() - start) * 1000.0
                version = getattr(mod, "__version__", "已加载")
                items.append(
                    DiagnosticItem(
                        name=f"依赖模块: {mod_name}",
                        status=CheckStatus.PASS,
                        message=f"{desc} (版本: {version})",
                        latency_ms=lat,
                    )
                )
            except ImportError as exc:
                items.append(
                    DiagnosticItem(
                        name=f"依赖模块: {mod_name}",
                        status=CheckStatus.FAIL,
                        message=f"核心依赖缺失: {desc} ({exc})",
                        remediation=f"请在 AegisRAG 目录下运行 `uv sync` 安装完整依赖",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                items.append(
                    DiagnosticItem(
                        name=f"依赖模块: {mod_name}",
                        status=CheckStatus.FAIL,
                        message=f"模块加载异常 (可能存在 C-ABI 冲突): {exc}",
                        remediation="请检查动态链接库或重新构建虚拟环境",
                    )
                )

        return items
