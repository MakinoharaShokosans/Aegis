"""真实 LLM 测试环境与安全沙箱夹具 (tests/real_llm/conftest.py)。

对应 `documents/深度测试路线.md` §0（安全与成本前提）与 §8（测试基础设施）。
提供强制隔离于 tmp_path 的工作区、受限的预算与权限配置，以及真实 LLMGateway 实例。
"""

import os
from pathlib import Path
from typing import Any, Dict
import pytest
from dotenv import load_dotenv

from agent_runtime.checkpoint import SqliteCheckpointStore
from agent_runtime.config import AegisConfig, get_config
from agent_runtime.llm.client import LLMGateway
from agent_runtime.memory.manager import MemoryManager
from agent_runtime.memory.sqlite_store import SqliteMemoryStore
from agent_runtime.prompt_loader import PromptLibrary
from agent_runtime.skills.registry import SkillsRegistry
from agent_runtime.workflow import RuntimeDeps
from mcps.manager import MCPManager

# 加载项目根目录下的 .env
load_dotenv()

TERRA_KEY = os.getenv("TERRA_KEY")
LUNA_KEY = os.getenv("LUNA_KEY")
HAS_LIVE_KEYS = bool(TERRA_KEY and LUNA_KEY)


def pytest_collection_modifyitems(config, items):
    """自动给 tests/real_llm 下的所有用例附加 real_llm marker。"""
    for item in items:
        if "real_llm" in str(item.fspath):
            item.add_marker(pytest.mark.real_llm)


@pytest.fixture(scope="session")
def check_live_keys():
    """无 key 时自动跳过，保证非开发环境不报错。"""
    if not HAS_LIVE_KEYS:
        pytest.skip("未检测到有效 TERRA_KEY 或 LUNA_KEY，跳过真实 LLM 测试")


@pytest.fixture
def live_config(tmp_path: Path, check_live_keys) -> AegisConfig:
    """构造强制隔离在 tmp_path 的真实测试配置。"""
    cfg = get_config()

    # 1. 严格重定向所有持久化与产物路径到 tmp_path，严禁污染真实仓库
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    cfg.runtime.storage.checkpoint_db_path = str(storage_dir / "checkpoints.db")
    cfg.runtime.storage.metadata_db_path = str(storage_dir / "meta.db")
    cfg.runtime.storage.traces_dir = str(storage_dir / "traces")
    cfg.runtime.storage.artifacts_dir = str(storage_dir / "artifacts")

    # 2. 真实测试物理预算硬顶保护（单用例步数限制 ≤ 10，防死循环刷 Token）
    cfg.runtime.guardrails.max_steps = 10
    cfg.runtime.guardrails.max_total_tokens = 50000
    cfg.runtime.guardrails.max_wall_time_sec = 300.0

    return cfg


@pytest.fixture
def live_gateway(live_config: AegisConfig) -> LLMGateway:
    """构造直连真实 OpenLux API (gpt-5.6-terra / gpt-5.6-luna) 的 Gateway 实例。"""
    return LLMGateway.from_config(live_config.models, live_config.runtime.retry)


@pytest.fixture
async def live_deps(tmp_path: Path, live_config: AegisConfig, live_gateway: LLMGateway):
    """构造包含真实 Gateway、隔离存储与基本工具集的 RuntimeDeps。"""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)

    checkpoint_store = SqliteCheckpointStore(live_config.runtime.storage.checkpoint_db_path)
    await checkpoint_store.open()

    memory_store = SqliteMemoryStore(live_config.runtime.storage.metadata_db_path)
    await memory_store.initialize()
    memory = MemoryManager(store=memory_store)

    # 预先创建隔离工作区，确保每个 workspace_id 拥有唯一的物理根路径
    for ws_id in ["default", "ws_live_001", "ws_live_002", "ws_hitl_001", "ws_002", "ws_live_compact_01"]:
        ws_root = tmp_path / "workspaces" / ws_id
        ws_root.mkdir(parents=True, exist_ok=True)
        await memory.create_workspace(
            workspace_id=ws_id,
            name=f"Isolated Workspace {ws_id}",
            root_path=str(ws_root),
        )

    builtin_dir = Path(__file__).resolve().parent.parent.parent / "src" / "skills"
    mcp_manager = MCPManager(live_config.mcp)

    deps = RuntimeDeps(
        config=live_config,
        memory=memory,
        gateway=live_gateway,
        prompts=PromptLibrary(),
        skills=SkillsRegistry.from_workspace(
            workspace_root=workspace_root, builtin_dir=builtin_dir, config=live_config.skills
        ),
        mcp_manager=mcp_manager,
        checkpoints=checkpoint_store,
        builtin_skills_dir=builtin_dir,
    )

    try:
        yield deps
    finally:
        await mcp_manager.shutdown_all()
        await checkpoint_store.close()
