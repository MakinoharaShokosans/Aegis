"""AegisAgent 的 web_search 子系统（同工程独立 FastAPI 服务，默认 :8003）。

职责（依据 ``documents/技术选型/web_search.md``）：
    1. 搜索源适配：``duckduckgo_search``（默认、零 Key）；
    2. 基于 ``httpx`` 的全异步并发抓取与 WAF Fail-Fast 降级；
    3. 基于 ``trafilatura`` 的网页正文降噪清洗（输出 Markdown，保留代码块）；
    4. 基于 MD5 内容指纹的镜像站/转载去重；
    5. 超长正文离线落盘卸载（``storage/artifacts/{task_id}/web_{hash}.md``）。

解耦红线（``10_directory_structure.md`` §1.5 / §5 依赖方向矩阵）：
    本包**禁止** import ``agent_runtime``、``tool_layer`` 或 ``tools``；
    仅允许依赖 ``services.settings``、标准库与第三方 HTTP/清洗库。

典型用法：
    >>> from services.web_search.app import app  # doctest: +SKIP
    >>> from services.web_search.settings import get_settings  # doctest: +SKIP
"""

from __future__ import annotations

__all__ = ["__version__"]

#: 子系统版本号，随 HTTP 健康检查一并暴露，便于运维确认部署版本
__version__ = "0.1.0"
