"""Sidecar微服务客户端与工具适配集成测试 (BashTool, WebSearchTool, ServiceClient)。"""

from typing import Any, Mapping
import httpx
import pytest

from agent_runtime.errors import DependencyUnavailableError
from tools.builtin.bash import BashTool
from tools.builtin.web_search import WebSearchTool
from tools.core.http_client import ServiceClient


class MockServiceClient(ServiceClient):
    """使用 httpx.MockTransport 的测试客户端。"""

    def __init__(self, handler, base_url: str = "http://mock-service", timeout_sec: float = 5.0) -> None:
        super().__init__(base_url=base_url, timeout_sec=timeout_sec)
        self._handler = handler

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                transport=httpx.MockTransport(self._handler),
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_sec),
            )
        return self._client


@pytest.mark.asyncio
async def test_bash_tool_service_integration():
    """测试 BashTool 与 Bash Shell 微服务的通信交互与结果蒸馏。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/shell/execute"
        import json
        payload = json.loads(request.content)
        assert payload["command"] == "ls -la"
        return httpx.Response(
            200,
            json={
                "exit_code": 0,
                "distilled_stdout": "total 12\n-rw-r--r-- 1 root root file.py",
                "distilled_stderr": "",
                "status": "COMPLETED",
                "is_truncated": False,
                "execution_time_ms": 25,
            },
        )

    client = MockServiceClient(handler, base_url="http://127.0.0.1:8002")
    tool = BashTool(
        client=client,
        workspace_id="ws_1",
        workspace_root="/workspace",
        task_id="task_1",
    )

    result = await tool.invoke({"command": "ls -la"})
    assert result.ok is True
    assert result.exit_code == 0
    assert "file.py" in result.content
    assert result.meta.get("execution_time_ms") == 25
    await client.aclose()


@pytest.mark.asyncio
async def test_web_search_tool_service_integration():
    """测试 WebSearchTool 与 Web Search 微服务的通信交互与结果汇总。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/search/query"
        import json
        payload = json.loads(request.content)
        assert payload["query"] == "python async tutorial"
        return httpx.Response(
            200,
            json={
                "query": "python async tutorial",
                "results": [
                    {
                        "title": "Python AsyncIO Docs",
                        "url": "https://docs.python.org/3/library/asyncio.html",
                        "snippet": "Asynchronous I/O, event loop, and coroutines.",
                        "status": "OK",
                    },
                    {
                        "title": "Blocked Page",
                        "url": "https://example.com/blocked",
                        "snippet": "Cloudflare challenge",
                        "status": "BLOCKED",
                    },
                ],
            },
        )

    client = MockServiceClient(handler, base_url="http://127.0.0.1:8003")
    tool = WebSearchTool(client=client, task_id="task_1")

    result = await tool.invoke({"query": "python async tutorial"})
    assert result.ok is True
    assert "Python AsyncIO Docs" in result.content
    assert "https://docs.python.org/3/library/asyncio.html" in result.content
    assert "Blocked Page" in result.content
    await client.aclose()


@pytest.mark.asyncio
async def test_sidecar_error_and_timeout_degradation():
    """测试微服务抛出 500 错误或网络异常时，工具层平稳降级为 ToolResult.failure。"""

    def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "Internal Shell Error"})

    client = MockServiceClient(error_handler, base_url="http://127.0.0.1:8002")
    tool = BashTool(
        client=client,
        workspace_id="ws_err",
        workspace_root="/workspace",
        task_id="task_err",
    )

    result = await tool.invoke({"command": "bad command"})
    assert result.ok is False
    assert "sidecar 返回异常状态码" in result.content
    await client.aclose()
