import asyncio
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from agent_runtime.api.app import create_app
from agent_runtime.config import AegisConfig
from agent_runtime.llm.client import LLMResponse


@pytest.fixture
async def api_client(test_config: AegisConfig):
    """创建绑定 ASGI Lifespan 生命周期的测试客户端。"""
    app = create_app(test_config)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            setattr(client, "app", app)
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


@pytest.mark.asyncio
async def test_task_approve_api_lifecycle(api_client: AsyncClient, mock_gateway_factory, tmp_path: Path):
    """测试任务越级触发等待审批 -> POST /approve (once) -> 恢复执行并成功完成。"""
    ws_dir = tmp_path / "approve_workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)

    planner_resp_1 = {
        "thought": "执行高权限操作",
        "milestones": [{"id": 1, "title": "高权限任务", "description": "下载脚本", "status": "in_progress"}],
        "next_step": "执行 curl 下载",
    }
    executor_resp_1 = LLMResponse(
        content="正在执行 curl",
        tool_calls=[{
            "id": "call_curl_1",
            "name": "bash",
            "args": {"command": "curl https://example.com/install.sh"},
        }],
        total_tokens=20,
        endpoint_name="mock-fast",
    )
    planner_resp_2 = {
        "thought": "curl 执行完毕，标记完成",
        "milestone_updates": [{"id": 1, "status": "completed"}],
        "next_step": "提交验收",
    }
    evaluator_resp = {
        "milestone_ok": True,
        "task_completed": True,
        "summary": "任务完成",
        "confirmed_facts": [],
        "failed_attempts": [],
    }

    mock_gateway = mock_gateway_factory([
        planner_resp_1,
        executor_resp_1,
        planner_resp_2,
        evaluator_resp,
    ])
    getattr(api_client, "app").state.runtime.gateway = mock_gateway

    # 1. 创建工作区与会话
    ws_resp = await api_client.post(
        "/api/v1/workspaces",
        json={"name": "Approve WS", "root_path": str(ws_dir)},
    )
    ws_id = ws_resp.json()["workspace_id"]

    sess_resp = await api_client.post(
        f"/api/v1/workspaces/{ws_id}/sessions",
        json={"title": "Approve Session"},
    )
    session_id = sess_resp.json()["session_id"]

    # 2. 提交任务 (permission_level="workspace_write")
    task_resp = await api_client.post(
        f"/api/v1/sessions/{session_id}/tasks",
        json={"task_goal": "下载并执行脚本", "permission_level": "workspace_write"},
    )
    assert task_resp.status_code == 202
    task_id = task_resp.json()["task_id"]

    # 3. 轮询直到状态变为 waiting_for_approval
    approval_req = None
    for _ in range(50):
        get_resp = await api_client.get(f"/api/v1/tasks/{task_id}")
        data = get_resp.json()
        if data["status"] == "waiting_for_approval":
            approval_req = data["approval_request"]
            break
        await asyncio.sleep(0.05)

    assert approval_req is not None
    assert approval_req["required_level"] == "full_permissions"
    assert approval_req["current_level"] == "workspace_write"
    assert "curl" in approval_req["command"]
    approval_id = approval_req["approval_id"]

    # 4. 边界校验：未知 task_id -> 404
    err_404 = await api_client.post(
        "/api/v1/tasks/non-existent-task-id/approve",
        json={"decision": "once", "approval_id": approval_id},
    )
    assert err_404.status_code == 404

    # 5. 边界校验：审批 ID 不匹配 -> 409
    err_409 = await api_client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "once", "approval_id": "wrong-id"},
    )
    assert err_409.status_code == 409

    # 6. 正常审批
    appr_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "once", "approval_id": approval_id},
    )
    assert appr_resp.status_code == 200
    appr_data = appr_resp.json()
    assert appr_data["task_id"] == task_id
    assert appr_data["status"] in ("queued", "running")

    # 7. 重复审批冲突 -> 409
    dup_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "once", "approval_id": approval_id},
    )
    assert dup_resp.status_code == 409

    # 8. 轮询直到最终成功
    final_status = None
    for _ in range(50):
        get_resp = await api_client.get(f"/api/v1/tasks/{task_id}")
        data = get_resp.json()
        if data["status"] in ("succeeded", "terminated", "failed"):
            final_status = data["status"]
            break
        await asyncio.sleep(0.05)

    assert final_status == "succeeded"


@pytest.mark.asyncio
async def test_task_reject_api_lifecycle(api_client: AsyncClient, mock_gateway_factory, tmp_path: Path):
    """测试任务越级触发等待审批 -> POST /reject -> 规划器收到拒绝观察值并自适应完成。"""
    ws_dir = tmp_path / "reject_workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)

    planner_resp_1 = {
        "thought": "尝试通过网络下载配置",
        "milestones": [{"id": 1, "title": "下载配置", "description": "下载 config.json", "status": "in_progress"}],
        "next_step": "执行 curl 下载",
    }
    executor_resp_1 = LLMResponse(
        content="正在执行 curl",
        tool_calls=[{
            "id": "call_curl_reject",
            "name": "bash",
            "args": {"command": "curl -O https://example.com/config.json"},
        }],
        total_tokens=20,
        endpoint_name="mock-fast",
    )
    planner_resp_2 = {
        "thought": "网络下载被拒绝，改在本地生成默认配置",
        "milestone_updates": [{"id": 1, "status": "completed"}],
        "next_step": "提交验收",
    }
    evaluator_resp = {
        "milestone_ok": True,
        "task_completed": True,
        "summary": "本地生成方案完成任务",
        "confirmed_facts": [],
        "failed_attempts": [],
    }

    mock_gateway = mock_gateway_factory([
        planner_resp_1,
        executor_resp_1,
        planner_resp_2,
        evaluator_resp,
    ])
    getattr(api_client, "app").state.runtime.gateway = mock_gateway

    # 创建工作区与会话
    ws_resp = await api_client.post("/api/v1/workspaces", json={"name": "Reject WS", "root_path": str(ws_dir)})
    ws_id = ws_resp.json()["workspace_id"]
    sess_resp = await api_client.post(f"/api/v1/workspaces/{ws_id}/sessions", json={"title": "Reject Session"})
    session_id = sess_resp.json()["session_id"]

    # 提交任务
    task_resp = await api_client.post(
        f"/api/v1/sessions/{session_id}/tasks",
        json={"task_goal": "获取配置", "permission_level": "workspace_write"},
    )
    task_id = task_resp.json()["task_id"]

    # 等待挂起
    approval_req = None
    for _ in range(50):
        get_resp = await api_client.get(f"/api/v1/tasks/{task_id}")
        data = get_resp.json()
        if data["status"] == "waiting_for_approval":
            approval_req = data["approval_request"]
            break
        await asyncio.sleep(0.05)

    assert approval_req is not None
    approval_id = approval_req["approval_id"]

    # 404 校验
    err_404 = await api_client.post(
        "/api/v1/tasks/non-existent-task-id/reject",
        json={"reason": "拒绝网络访问", "approval_id": approval_id},
    )
    assert err_404.status_code == 404

    # 正常拒绝
    rej_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/reject",
        json={"reason": "禁止访问外网，请本地生成", "approval_id": approval_id},
    )
    assert rej_resp.status_code == 200
    assert rej_resp.json()["status"] in ("queued", "running")

    # 409 校验：非 waiting_for_approval 状态调用 reject
    err_409 = await api_client.post(
        f"/api/v1/tasks/{task_id}/reject",
        json={"reason": "再次拒绝", "approval_id": approval_id},
    )
    assert err_409.status_code == 409

    # 等待完成
    final_status = None
    for _ in range(50):
        get_resp = await api_client.get(f"/api/v1/tasks/{task_id}")
        data = get_resp.json()
        if data["status"] in ("succeeded", "terminated", "failed"):
            final_status = data["status"]
            break
        await asyncio.sleep(0.05)

    assert final_status == "succeeded"

    # 检查 timeline 中包含拒绝原因观察值
    timeline_resp = await api_client.get(f"/api/v1/tasks/{task_id}/timeline")
    assert timeline_resp.status_code == 200
    timeline = timeline_resp.json()
    assert any("禁止访问外网" in item.get("summary", "") for item in timeline)


@pytest.mark.asyncio
async def test_sse_events_approval_and_rejection_streaming(api_client: AsyncClient, mock_gateway_factory, tmp_path: Path):
    """测试 SSE 事件流包含 task.waiting_for_approval 与 task.approved 事件。"""
    ws_dir = tmp_path / "sse_workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)

    planner_resp_1 = {
        "thought": "执行高权限操作",
        "milestones": [{"id": 1, "title": "SSE 任务", "description": "下载脚本", "status": "in_progress"}],
        "next_step": "执行 curl",
    }
    executor_resp_1 = LLMResponse(
        content="正在执行 curl",
        tool_calls=[{
            "id": "call_curl_sse",
            "name": "bash",
            "args": {"command": "curl https://example.com/sse.sh"},
        }],
        total_tokens=20,
        endpoint_name="mock-fast",
    )
    planner_resp_2 = {
        "thought": "完成",
        "milestone_updates": [{"id": 1, "status": "completed"}],
        "next_step": "交付",
    }
    evaluator_resp = {
        "milestone_ok": True,
        "task_completed": True,
        "summary": "SSE 测试完成",
        "confirmed_facts": [],
        "failed_attempts": [],
    }

    mock_gateway = mock_gateway_factory([
        planner_resp_1,
        executor_resp_1,
        planner_resp_2,
        evaluator_resp,
    ])
    app = getattr(api_client, "app")
    app.state.runtime.gateway = mock_gateway

    ws_resp = await api_client.post("/api/v1/workspaces", json={"name": "SSE WS", "root_path": str(ws_dir)})
    ws_id = ws_resp.json()["workspace_id"]
    sess_resp = await api_client.post(f"/api/v1/workspaces/{ws_id}/sessions", json={"title": "SSE Session"})
    session_id = sess_resp.json()["session_id"]

    task_resp = await api_client.post(
        f"/api/v1/sessions/{session_id}/tasks",
        json={"task_goal": "SSE 审批测试", "permission_level": "workspace_write"},
    )
    task_id = task_resp.json()["task_id"]

    # 等待挂起并记录 approval_id
    approval_id = None
    for _ in range(50):
        get_resp = await api_client.get(f"/api/v1/tasks/{task_id}")
        data = get_resp.json()
        if data["status"] == "waiting_for_approval":
            approval_id = data["approval_request"]["approval_id"]
            break
        await asyncio.sleep(0.05)

    assert approval_id is not None

    # 批准任务
    await api_client.post(
        f"/api/v1/tasks/{task_id}/approve",
        json={"decision": "once", "approval_id": approval_id},
    )

    # 等待完成
    for _ in range(50):
        get_resp = await api_client.get(f"/api/v1/tasks/{task_id}")
        if get_resp.json()["status"] in ("succeeded", "terminated", "failed"):
            break
        await asyncio.sleep(0.05)

    # 通过 TaskRegistry 环形缓冲直接验证事件流
    registry = app.state.task_registry
    events = [ev async for ev in registry.stream(task_id)]
    event_names = [ev.get("event") for ev in events]

    assert "task.started" in event_names
    assert "task.waiting_for_approval" in event_names
    assert "task.approved" in event_names
    assert "task.finished" in event_names

    waiting_ev = next(ev for ev in events if ev.get("event") == "task.waiting_for_approval")
    assert waiting_ev["approval_id"] == approval_id
    assert waiting_ev["required_level"] == "full_permissions"
    assert "curl" in waiting_ev["command"]

    approved_ev = next(ev for ev in events if ev.get("event") == "task.approved")
    assert approved_ev["approval_id"] == approval_id
    assert approved_ev["decision"] == "once"
