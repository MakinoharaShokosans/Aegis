"""FastAPI HTTP API 全生命周期集成测试 (Workspaces, Sessions, Tasks, Health, Introspection)。"""

from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from agent_runtime.api.app import create_app
from agent_runtime.config import AegisConfig


@pytest.fixture
async def api_client(test_config: AegisConfig):
    """创建绑定 ASGI Lifespan 生命周期的测试客户端。"""
    app = create_app(test_config)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_health_and_introspection_endpoints(api_client: AsyncClient):
    """测试健康检查与自省接口。"""
    # 1. GET /api/v1/health
    resp = await api_client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "uptime_sec" in data
    assert data["checkpoint_ok"] is True
    assert data["metadata_db_ok"] is True

    # 2. GET /api/v1/tools & /api/v1/models
    resp_tools = await api_client.get("/api/v1/tools")
    assert resp_tools.status_code == 200
    tools_data = resp_tools.json()
    assert len(tools_data) >= 1
    tool_names = [t["function"]["name"] for t in tools_data]
    assert "write_file" in tool_names
    assert "view_file" in tool_names

    resp_models = await api_client.get("/api/v1/models")
    assert resp_models.status_code == 200
    models_data = resp_models.json()
    assert "reasoning" in models_data
    assert "fast" in models_data


@pytest.mark.asyncio
async def test_workspace_and_session_lifecycle(api_client: AsyncClient, tmp_path: Path):
    """测试工作区与会话的创建、列表查询与级联删除生命周期。"""
    ws_dir = tmp_path / "api_test_workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)

    # 1. 创建工作区
    create_ws_resp = await api_client.post(
        "/api/v1/workspaces",
        json={
            "name": "API Test WS",
            "root_path": str(ws_dir),
            "description": "Integration testing workspace via HTTP",
        },
    )
    assert create_ws_resp.status_code == 201
    ws_data = create_ws_resp.json()
    workspace_id = ws_data["workspace_id"]
    assert ws_data["name"] == "API Test WS"
    assert ws_data["root_path"] == str(ws_dir)

    # 2. 幂等性：重复创建同路径工作区应返回既有工作区
    idempotent_resp = await api_client.post(
        "/api/v1/workspaces",
        json={"name": "Different Name", "root_path": str(ws_dir)},
    )
    assert idempotent_resp.status_code == 201
    assert idempotent_resp.json()["workspace_id"] == workspace_id

    # 3. 创建会话 (POST /workspaces/{workspace_id}/sessions)
    create_session_resp = await api_client.post(
        f"/api/v1/workspaces/{workspace_id}/sessions",
        json={
            "title": "Session 1",
        },
    )
    assert create_session_resp.status_code == 201
    session_data = create_session_resp.json()
    session_id = session_data["session_id"]
    assert session_data["workspace_id"] == workspace_id

    # 4. 查询工作区下的会话列表
    list_sessions_resp = await api_client.get(f"/api/v1/workspaces/{workspace_id}/sessions")
    assert list_sessions_resp.status_code == 200
    sessions_list = list_sessions_resp.json()
    assert len(sessions_list) >= 1
    assert any(s["session_id"] == session_id for s in sessions_list)

    # 5. 删除工作区（级联清理）
    del_resp = await api_client.delete(f"/api/v1/workspaces/{workspace_id}")
    assert del_resp.status_code == 204

    # 再次查询已不存在
    get_del_resp = await api_client.get(f"/api/v1/workspaces/{workspace_id}")
    assert get_del_resp.status_code == 404


@pytest.mark.asyncio
async def test_task_api_lifecycle(api_client: AsyncClient, tmp_path: Path):
    """测试任务提交、状态轮询与取消生命周期。"""
    ws_dir = tmp_path / "task_api_workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)

    # 1. 准备工作区与会话
    ws_resp = await api_client.post(
        "/api/v1/workspaces",
        json={"name": "Task WS", "root_path": str(ws_dir)},
    )
    ws_id = ws_resp.json()["workspace_id"]

    sess_resp = await api_client.post(
        f"/api/v1/workspaces/{ws_id}/sessions",
        json={"title": "Task Session"},
    )
    session_id = sess_resp.json()["session_id"]

    # 2. 提交任务
    task_resp = await api_client.post(
        f"/api/v1/sessions/{session_id}/tasks",
        json={"task_goal": "HTTP Task Integration Test"},
    )
    assert task_resp.status_code == 202
    task_data = task_resp.json()
    task_id = task_data["task_id"]
    assert task_data["session_id"] == session_id
    assert task_data["status"] in ("queued", "running", "completed", "failed")

    # 3. 轮询任务状态
    query_resp = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert query_resp.status_code == 200
    assert query_resp.json()["task_id"] == task_id

    # 4. 获取时间线
    timeline_resp = await api_client.get(f"/api/v1/tasks/{task_id}/timeline")
    assert timeline_resp.status_code == 200
    assert isinstance(timeline_resp.json(), list)

    # 5. 取消任务
    cancel_resp = await api_client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert cancel_resp.status_code == 202
    assert cancel_resp.json()["task_id"] == task_id
