"""工作区文件树与内容端点测试 (tests/api/test_files_routes.py)。"""

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
        token = str(getattr(app.state, "api_token", "") or "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8000", headers=headers
        ) as client:
            setattr(client, "app", app)
            yield client


@pytest.mark.asyncio
async def test_file_tree_and_content_lifecycle(api_client: AsyncClient, tmp_path: Path):
    """测试文件树获取、文件内容读取、保存与路径越界防护。"""
    ws_dir = tmp_path / "files_test_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)

    # 构造目录结构与测试文件
    docs_dir = ws_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    sample_doc = docs_dir / "spec.md"
    sample_doc.write_text("# API Spec\n\nThis is a sample spec.", encoding="utf-8")

    src_dir = ws_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    sample_code = src_dir / "main.py"
    sample_code.write_text("print('hello aegis')", encoding="utf-8")

    # 创建工作区
    create_ws_resp = await api_client.post(
        "/api/v1/workspaces",
        json={
            "name": "Files Test Workspace",
            "root_path": str(ws_dir),
            "description": "Testing files API",
        },
    )
    assert create_ws_resp.status_code == 201
    workspace_id = create_ws_resp.json()["workspace_id"]

    # 1. GET /workspaces/{id}/files/tree
    tree_resp = await api_client.get(f"/api/v1/workspaces/{workspace_id}/files/tree")
    assert tree_resp.status_code == 200
    tree_data = tree_resp.json()
    assert tree_data["workspace_id"] == workspace_id
    assert len(tree_data["items"]) >= 2
    item_names = [item["name"] for item in tree_data["items"]]
    assert "docs" in item_names
    assert "src" in item_names

    # 2. GET /workspaces/{id}/files/content
    content_resp = await api_client.get(
        f"/api/v1/workspaces/{workspace_id}/files/content",
        params={"path": "docs/spec.md"},
    )
    assert content_resp.status_code == 200
    content_data = content_resp.json()
    assert content_data["path"] == "docs/spec.md"
    assert "# API Spec" in content_data["content"]
    assert content_data["language"] == "markdown"

    # 3. PUT /workspaces/{id}/files/content (更新既有文件)
    update_resp = await api_client.put(
        f"/api/v1/workspaces/{workspace_id}/files/content",
        json={
            "path": "docs/spec.md",
            "content": "# Updated Spec\n\nUpdated content.",
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "ok"
    assert sample_doc.read_text(encoding="utf-8") == "# Updated Spec\n\nUpdated content."

    # 4. PUT /workspaces/{id}/files/content (创建新文件)
    new_file_resp = await api_client.put(
        f"/api/v1/workspaces/{workspace_id}/files/content",
        json={
            "path": "docs/new_doc.md",
            "content": "# Brand New Doc",
        },
    )
    assert new_file_resp.status_code == 200
    assert (docs_dir / "new_doc.md").is_file()

    # 5. 防御测试：路径越界尝试访问父级目录
    escape_resp = await api_client.get(
        f"/api/v1/workspaces/{workspace_id}/files/content",
        params={"path": "../../etc/passwd"},
    )
    assert escape_resp.status_code == 422
    assert escape_resp.json()["error"]["code"] == "PATH_ESCAPE_DETECTED"

    # 6. 防御测试：写入路径越界
    escape_put_resp = await api_client.put(
        f"/api/v1/workspaces/{workspace_id}/files/content",
        json={
            "path": "../evil.txt",
            "content": "evil content",
        },
    )
    assert escape_put_resp.status_code == 422
    assert escape_put_resp.json()["error"]["code"] == "PATH_ESCAPE_DETECTED"

    # 7. 404 测试：读取不存在的文件
    not_found_resp = await api_client.get(
        f"/api/v1/workspaces/{workspace_id}/files/content",
        params={"path": "docs/non_existent.md"},
    )
    assert not_found_resp.status_code == 404


@pytest.mark.asyncio
async def test_browse_directories(api_client: AsyncClient, tmp_path: Path):
    """测试本地目录浏览与选择接口。"""
    sample_dir = tmp_path / "browse_root"
    (sample_dir / "project_a").mkdir(parents=True, exist_ok=True)
    (sample_dir / "project_b").mkdir(parents=True, exist_ok=True)
    (sample_dir / ".git").mkdir(parents=True, exist_ok=True)
    (sample_dir / "regular_file.txt").write_text("hello", encoding="utf-8")

    resp = await api_client.get(
        "/api/v1/system/fs/directories",
        params={"path": str(sample_dir)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_path"] == str(sample_dir)
    assert len(data["directories"]) == 2
    dir_names = [d["name"] for d in data["directories"]]
    assert "project_a" in dir_names
    assert "project_b" in dir_names
    assert ".git" not in dir_names
    assert "regular_file.txt" not in dir_names
    assert len(data["quick_locations"]) > 0


@pytest.mark.asyncio
async def test_pick_native_directory(api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """测试原生文件管理器目录选择端点。"""
    from agent_runtime.api.routes import files

    async def mock_dialog(path=None):
        return "/home/Skualeilu/Projects/Aegis"

    monkeypatch.setattr(files, "_open_native_directory_dialog", mock_dialog)

    resp = await api_client.post("/api/v1/system/fs/pick-directory")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["path"] == "/home/Skualeilu/Projects/Aegis"
    assert data["name"] == "Aegis"
    assert data["cancelled"] is False


