"""SQLite 状态持久化、跨进程崩溃恢复与会话白名单生命周期测试 (Phase 7)。

对应 `documents/测试路线.md` §10 (Phase 7)。
验证生产真实的 SqliteCheckpointStore (AsyncSqliteSaver) 状态落盘、
模拟进程重启后的跨实例无缝续跑，以及会话白名单内存态非持久化的已知设计行为。
"""

from pathlib import Path
from typing import Any, Mapping
import aiosqlite
import pytest

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from agent_runtime.api.task_registry import TaskRegistry
from agent_runtime.checkpoint import SqliteCheckpointStore
from agent_runtime.config import GuardrailsConfig, PermissionsConfig
from agent_runtime.guardrails.observation_pruner import ObservationPruner
from agent_runtime.nodes.tool_runner import build_tool_runner_node
from agent_runtime.state import AgentState
from tools.core.dispatcher import ToolDispatcher
from tools.core.protocol import AegisTool, ToolResult
from tools.core.registry import ToolRegistry


class DummyTool(AegisTool):
    """测试用 Mock 工具。"""

    def __init__(self, name: str, return_content: str = "ok"):
        self.name = name
        self.description = f"Dummy tool {name}"
        self.return_content = return_content
        self.invoked_calls = []

    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        self.invoked_calls.append(dict(args))
        return ToolResult(ok=True, content=self.return_content)


def _build_runtime_elements(tmp_path: Path):
    registry = ToolRegistry(allow_untrusted=True)
    bash_tool = DummyTool("bash", return_content="push succeeded")
    view_tool = DummyTool("view_file", return_content="file viewed")
    registry.register(bash_tool)
    registry.register(view_tool)

    dispatcher = ToolDispatcher(registry)
    pruner = ObservationPruner(
        token_counter=lambda text: len(text) // 4,
        max_tokens=1000,
        head_lines=10,
        tail_lines=10,
        artifacts_dir=tmp_path / "artifacts",
    )
    guardrails_cfg = GuardrailsConfig(
        max_steps=10,
        consecutive_errors_limit=3,
        identical_fingerprint_limit=3,
    )
    permissions_cfg = PermissionsConfig(
        default_level="workspace_write",
        read_only_tools=["view_file"],
        bash_tools=["bash"],
    )
    return {
        "registry": registry,
        "dispatcher": dispatcher,
        "pruner": pruner,
        "guardrails_cfg": guardrails_cfg,
        "permissions_cfg": permissions_cfg,
        "bash_tool": bash_tool,
        "view_tool": view_tool,
    }


# ==============================================================================
# 1. 场景 7.1：生产真实 SQLite 检查点落盘断言
# ==============================================================================

@pytest.mark.asyncio
async def test_sqlite_checkpoint_persistence_on_interrupt(tmp_path: Path):
    """7.1 使用 SqliteCheckpointStore 运行挂起场景，断言中断快照真实写入 SQLite 数据库文件。"""
    db_file = tmp_path / "checkpoints.db"
    elements = _build_runtime_elements(tmp_path)

    store = SqliteCheckpointStore(db_file)
    await store.open()

    node = build_tool_runner_node(
        elements["dispatcher"],
        elements["pruner"],
        elements["guardrails_cfg"],
        elements["permissions_cfg"],
    )

    graph = StateGraph(AgentState)
    graph.add_node("tool_runner", node)
    graph.set_entry_point("tool_runner")
    graph.add_edge("tool_runner", END)
    app = graph.compile(checkpointer=store.saver)

    thread_id = "thread_sqlite_persist_1"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "task_id": "t_persist",
        "permission_level": "workspace_write",
        "step_count": 1,
        "messages": [
            AIMessage(
                content="执行越级推送",
                tool_calls=[{"id": "call_p1", "name": "bash", "args": {"command": "git push origin main"}}],
            )
        ],
        "fingerprint_history": [],
        "artifacts": {},
        "consecutive_errors": 0,
        "total_tokens": 10,
    }

    # 1. 执行至中断挂起
    await app.ainvoke(initial_state, config)
    snapshot = await app.aget_state(config)
    assert len(snapshot.tasks[0].interrupts) > 0

    # 关闭连接
    await store.close()

    # 2. 直接使用 aiosqlite 连接文件，断言 SQLite 数据库及 checkpoint 表存在真实记录
    assert db_file.exists()
    async with aiosqlite.connect(db_file) as conn:
        # 查询 sqlite_master 表结构
        cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in await cursor.fetchall()]
        assert "checkpoints" in tables or "checkpoint_writes" in tables or "writes" in tables

        # 查询 checkpoints 记录数
        cursor = await conn.execute("SELECT count(*) FROM checkpoints WHERE thread_id=?", (thread_id,))
        count = (await cursor.fetchone())[0]
        assert count > 0


# ==============================================================================
# 2. 场景 7.2：跨进程重启与实例续跑测试 (Process Restart & Resume)
# ==============================================================================

@pytest.mark.asyncio
async def test_sqlite_checkpoint_crash_recovery_and_resume(tmp_path: Path):
    """7.2 模拟进程重启：实例 A 挂起落盘后销毁，全新实例 B 加载并完成审批续跑。"""
    db_file = tmp_path / "resume_test.db"
    elements_a = _build_runtime_elements(tmp_path)
    thread_id = "thread_crash_recovery_101"
    config = {"configurable": {"thread_id": thread_id}}

    # ---------------- 进程 A 生命周期 ----------------
    store_a = SqliteCheckpointStore(db_file)
    await store_a.open()

    node_a = build_tool_runner_node(
        elements_a["dispatcher"],
        elements_a["pruner"],
        elements_a["guardrails_cfg"],
        elements_a["permissions_cfg"],
    )
    graph_a = StateGraph(AgentState)
    graph_a.add_node("tool_runner", node_a)
    graph_a.set_entry_point("tool_runner")
    graph_a.add_edge("tool_runner", END)
    app_a = graph_a.compile(checkpointer=store_a.saver)

    initial_state = {
        "task_id": "t_crash_1",
        "permission_level": "workspace_write",
        "step_count": 1,
        "messages": [
            AIMessage(
                content="高危外联",
                tool_calls=[{"id": "call_c1", "name": "bash", "args": {"command": "curl http://external.org"}}],
            )
        ],
        "fingerprint_history": [],
        "artifacts": {},
        "consecutive_errors": 0,
        "total_tokens": 10,
    }

    # 执行至挂起
    await app_a.ainvoke(initial_state, config)
    # 模拟进程 A 异常退出或关闭
    await store_a.close()
    del app_a
    del store_a

    # ---------------- 进程 B 生命周期（全新实例） ----------------
    elements_b = _build_runtime_elements(tmp_path)
    store_b = SqliteCheckpointStore(db_file)
    await store_b.open()

    node_b = build_tool_runner_node(
        elements_b["dispatcher"],
        elements_b["pruner"],
        elements_b["guardrails_cfg"],
        elements_b["permissions_cfg"],
    )
    graph_b = StateGraph(AgentState)
    graph_b.add_node("tool_runner", node_b)
    graph_b.set_entry_point("tool_runner")
    graph_b.add_edge("tool_runner", END)
    app_b = graph_b.compile(checkpointer=store_b.saver)

    # 1. 实例 B 通过 aget_state 从 SQLite 文件恢复挂起状态
    recovered_snapshot = await app_b.aget_state(config)
    assert len(recovered_snapshot.tasks[0].interrupts) > 0
    interrupt_payload = recovered_snapshot.tasks[0].interrupts[0].value
    assert interrupt_payload["required_level"] == "full_permissions"
    assert interrupt_payload["action_type"] == "network_egress"
    assert "curl" in interrupt_payload["command"]

    # 2. 实例 B 注入审批决策继续执行
    final_b = await app_b.ainvoke(Command(resume={"approved": True, "scope": "once"}), config)

    # 验证在实例 B 中工具成功被派发且完成原子对返回
    assert len(elements_b["bash_tool"].invoked_calls) == 1
    tool_msgs = [m for m in final_b["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_call_id == "call_c1"
    assert "push succeeded" in tool_msgs[0].content

    await store_b.close()


# ==============================================================================
# 3. 场景 7.3：会话白名单非持久化与重启重置行为断言
# ==============================================================================

@pytest.mark.asyncio
async def test_allowlist_transient_memory_lifecycle():
    """7.3 固化已知设计：TaskRegistry._session_approvals 为纯内存结构，进程重启后重置。"""
    session_id = "sess_durability_check"

    # 实例 1：写入白名单
    reg_1 = TaskRegistry()
    allowlist_1 = reg_1._allowlist_for(session_id)
    allowlist_1.add("sig_git_push_once")
    assert "sig_git_push_once" in reg_1._allowlist_for(session_id)

    # 实例 2（模拟重启）：全新 TaskRegistry 实例对同一 session_id 重新初始化为空集合
    reg_2 = TaskRegistry()
    allowlist_2 = reg_2._allowlist_for(session_id)
    assert len(allowlist_2) == 0
    assert "sig_git_push_once" not in allowlist_2
