"""uvicorn 启动入口（默认 ``127.0.0.1:8001``，host/port/workers 取自 ``[server]`` 配置）。

启动方式（任选其一，均自动把 ``src`` 挂到 ``sys.path``）::

    python -m api            # cwd = AegisRAG/src
    python -m src.api        # cwd = AegisRAG

规范：documents/技术选型/rag_retrieval.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

__all__ = ["main"]


def _bootstrap_sys_path() -> None:
    """确保 ``src`` 目录位于 ``sys.path`` 首位（与 AegisAgent 侧 bash_shell 同构）。

    子系统内部使用 ``api.xxx``/``indexer.xxx`` 等绝对导入，因此从
    ``AegisRAG/`` 根目录以 ``python -m src.api`` 启动时需要补上 ``src``，
    避免依赖调用方的 cwd。
    """
    src_root = Path(__file__).resolve().parents[1]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))


def main() -> None:
    """读取配置、执行启动前置体检并安全拉起 uvicorn 服务。

    Raises:
        FileNotFoundError: 找不到 ``rag_config.toml`` 时抛出。
        pydantic.ValidationError: 配置字段缺失或非法时抛出。
    """
    _bootstrap_sys_path()

    from api.preflight import DiagnosticReporter, PreflightRunner
    from api.settings import get_settings

    settings = get_settings()

    # 1. 启动前置体检与自检门禁
    runner = PreflightRunner()
    report = runner.run(settings)
    print(DiagnosticReporter.format_console(report))

    if not report.is_launch_ready:
        print("\n[✘ 启动中止] 前置自检发现致命错误，拒绝带病启动服务！\n", file=sys.stderr)
        sys.exit(1)

    # 2. 安全拉起服务
    print(f"[🚀 AegisRAG] 正在拉起 HTTP 检索服务: http://{settings.server.host}:{settings.server.port}\n")
    uvicorn.run(
        "api.app:app",
        host=settings.server.host,
        port=settings.server.port,
        workers=settings.server.workers,
        log_level="info",
    )


if __name__ == "__main__":
    main()
