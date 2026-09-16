"""LangGraph 状态图与多节点流转端到端集成测试。"""

from pathlib import Path
import pytest

from agent_runtime.checkpoint import SqliteCheckpointStore
from agent_runtime.config import AegisConfig
from agent_runtime.llm.client import LLMResponse
from agent_runtime.memory.manager import MemoryManager
from agent_runtime.memory.sqlite_store import SqliteMemoryStore
from agent_runtime.observability.trajectory import TrajectoryRecorder
from agent_runtime.prompt_loader import PromptLibrary
from agent_runtime.skills.registry import SkillsRegistry
from agent_runtime.workflow import (
    RuntimeDeps,
    build_runtime,
    close_runtime,
    run_agent,
    run_streaming,
)
from mcps.manager import MCPManager


@pytest.mark.asyncio
async def test_full_workflow_success_loop(test_config: AegisConfig, mock_gateway_factory, tmp_path: Path):
    """测试正常全流程闭环：
    Planner 规划 -> BudgetGuard 放行 -> Executor 写入文件 -> Planner 标记完成 -> Evaluator 验收结束。
    """
    ws_dir = tmp_path / "target_workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)

    # 1. 预设模型在各阶段的决策响应
    planner_resp_1 = {
        "thought": "创建初始计划并准备写入测试文件",
        "milestones": [{"id": 1, "title": "创建测试文件", "description": "写入 hello.txt 文件", "status": "in_progress"}],
        "next_step": "调用 write_file 写入 hello.txt",
    }
    executor_resp_1 = LLMResponse(
        content="我正在写入 hello.txt",
        tool_calls=[{
            "id": "call_write_1",
            "name": "write_file",
            "args": {"path": "hello.txt", "content": "Hello Aegis Integration Test!"},
        }],
        total_tokens=25,
        endpoint_name="mock-fast",
    )
    planner_resp_2 = {
        "thought": "文件已成功写入，将里程碑 1 标记为已完成",
        "milestone_updates": [{"id": 1, "status": "completed"}],
        "next_step": "所有工作已就绪，提交验收",
    }
    evaluator_resp_1 = {
        "milestone_ok": True,
        "task_completed": True,
        "summary": "成功创建并写入了 hello.txt 测试文件",
        "confirmed_facts": ["hello.txt 内容完整"],
        "failed_attempts": [],
    }

    mock_gateway = mock_gateway_factory([
        planner_resp_1,   # 1. Planner 初始规划
        executor_resp_1,  # 2. Executor 动作翻译
        planner_resp_2,   # 3. Planner 标记完成
        evaluator_resp_1, # 4. Evaluator 验收交付
    ])

    # 2. 初始化持久化与运行时依赖
    store = SqliteMemoryStore(db_path=test_config.runtime.storage.metadata_db_path)
    memory = MemoryManager(store=store)
    await memory.initialize()

    checkpoints = SqliteCheckpointStore(test_config.runtime.storage.checkpoint_db_path)
    await checkpoints.open()

    ws = await memory.create_workspace(name="test_ws", root_path=str(ws_dir), description="Integration test workspace")
    session = await memory.create_session(workspace_id=ws.workspace_id, title="Test Session")

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    deps = RuntimeDeps(
        config=test_config,
        memory=memory,
        gateway=mock_gateway,  # type: ignore[arg-type]
        prompts=PromptLibrary(),
        skills=SkillsRegistry.from_workspace(workspace_root=ws_dir, builtin_dir=skills_dir),
        mcp_manager=MCPManager(test_config.mcp),
        checkpoints=checkpoints,
        builtin_skills_dir=skills_dir,
    )

    events = []
    async def capture_event(ev):
        events.append(ev)

    try:
        # run_streaming 返回 TaskOutcome（含终态与可能的待审批请求）
        outcome = await run_streaming(
            deps,
            workspace_id=ws.workspace_id,
            session_id=session.session_id,
            task_goal="请帮我创建一个 hello.txt 文件并写入内容",
            event_sink=capture_event,
        )
        final_state = outcome.state

        # 3. 校验最终状态与产物
        assert final_state["should_terminate"] is True
        assert len(final_state["milestones"]) == 1
        assert final_state["milestones"][0].status == "completed"
        assert final_state["step_count"] >= 1
        assert (ws_dir / "hello.txt").is_file()
        assert (ws_dir / "hello.txt").read_text(encoding="utf-8") == "Hello Aegis Integration Test!"

        # 校验事件流
        assert len(events) >= 4
        nodes_executed = [ev["node"] for ev in events]
        assert "planner" in nodes_executed
        assert "budget_guard" in nodes_executed
        assert "executor" in nodes_executed
        assert "evaluator" in nodes_executed
    finally:
        await close_runtime(deps)


@pytest.mark.asyncio
async def test_workflow_budget_guard_step_limit_termination(test_config: AegisConfig, mock_gateway_factory, tmp_path: Path):
    """测试达到最大步数上限时，BudgetGuard 节点强制熔断并流转至 END。"""
    ws_dir = tmp_path / "budget_workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)

    # 设置最大步数为 2 步
    test_config.runtime.guardrails.max_steps = 2

    # 模拟一个永远无法完成任务的无限循环响应
    loop_planner_resp = {
        "thought": "正在进行持续尝试...",
        "milestones": [{"id": 1, "description": "无法完成的任务", "status": "in_progress"}],
        "next_step": "查看文件",
    }
    loop_executor_resp = LLMResponse(
        content="查看不存在的文件",
        tool_calls=[{
            "id": "call_view_none",
            "name": "view_file",
            "args": {"path": "non_existent.txt"},
        }],
        total_tokens=10,
        endpoint_name="mock-fast",
    )

    mock_gateway = mock_gateway_factory([
        loop_planner_resp,
        loop_executor_resp,
        loop_planner_resp,
        loop_executor_resp,
        loop_planner_resp,
        loop_executor_resp,
    ])

    store = SqliteMemoryStore(db_path=test_config.runtime.storage.metadata_db_path)
    memory = MemoryManager(store=store)
    await memory.initialize()

    checkpoints = SqliteCheckpointStore(test_config.runtime.storage.checkpoint_db_path)
    await checkpoints.open()

    ws = await memory.create_workspace(name="budget_ws", root_path=str(ws_dir), description="Budget test workspace")
    session = await memory.create_session(workspace_id=ws.workspace_id, title="Budget Session")

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    deps = RuntimeDeps(
        config=test_config,
        memory=memory,
        gateway=mock_gateway,  # type: ignore[arg-type]
        prompts=PromptLibrary(),
        skills=SkillsRegistry.from_workspace(workspace_root=ws_dir, builtin_dir=skills_dir),
        mcp_manager=MCPManager(test_config.mcp),
        checkpoints=checkpoints,
        builtin_skills_dir=skills_dir,
    )

    try:
        final_state = await run_agent(
            deps,
            workspace_id=ws.workspace_id,
            session_id=session.session_id,
            task_goal="运行直到触发预算上限",
        )

        assert final_state["should_terminate"] is True
        assert "步数" in str(final_state.get("termination_reason", ""))
    finally:
        await close_runtime(deps)


@pytest.mark.asyncio
async def test_workflow_loop_detection_and_replan(test_config: AegisConfig, mock_gateway_factory, tmp_path: Path):
    """测试连续错误与死循环检测触发重规划通知并最终修正。"""
    ws_dir = tmp_path / "replan_workspace"
    ws_dir.mkdir(parents=True, exist_ok=True)

    # 1. 模拟连续失败 -> 注入重规划通知 -> Planner 收到后更换方案 -> 成功交付
    planner_resp_1 = {
        "thought": "尝试通过错误路径读取配置",
        "milestones": [{"id": 1, "title": "读取配置", "description": "读取 app.conf", "status": "in_progress"}],
        "next_step": "查看 /root/forbidden.txt",
    }
    # 连续调用越界路径导致失败
    executor_fail_resp = LLMResponse(
        content="读取越界路径",
        tool_calls=[{
            "id": "call_escape",
            "name": "view_file",
            "args": {"path": "../outside.txt"},
        }],
        total_tokens=10,
        endpoint_name="mock-fast",
    )
    planner_resp_after_replan = {
        "thought": "收到重规划通知，放弃越界路径，改在当前工作区创建默认配置",
        "milestone_updates": [{"id": 1, "status": "completed"}],
        "next_step": "创建 local.conf",
    }
    evaluator_resp = {
        "milestone_ok": True,
        "task_completed": True,
        "summary": "重规划成功并完成任务",
        "confirmed_facts": [],
        "failed_attempts": [],
    }

    mock_gateway = mock_gateway_factory([
        planner_resp_1,
        executor_fail_resp,
        planner_resp_after_replan,
        evaluator_resp,
    ])

    store = SqliteMemoryStore(db_path=test_config.runtime.storage.metadata_db_path)
    memory = MemoryManager(store=store)
    await memory.initialize()

    checkpoints = SqliteCheckpointStore(test_config.runtime.storage.checkpoint_db_path)
    await checkpoints.open()

    ws = await memory.create_workspace(name="replan_ws", root_path=str(ws_dir), description="Replan workspace")
    session = await memory.create_session(workspace_id=ws.workspace_id, title="Replan Session")

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    deps = RuntimeDeps(
        config=test_config,
        memory=memory,
        gateway=mock_gateway,  # type: ignore[arg-type]
        prompts=PromptLibrary(),
        skills=SkillsRegistry.from_workspace(workspace_root=ws_dir, builtin_dir=skills_dir),
        mcp_manager=MCPManager(test_config.mcp),
        checkpoints=checkpoints,
        builtin_skills_dir=skills_dir,
    )

    try:
        final_state = await run_agent(
            deps,
            workspace_id=ws.workspace_id,
            session_id=session.session_id,
            task_goal="尝试并修正策略",
        )

        assert final_state["should_terminate"] is True
        # 验证经历过工具失败并留存 ToolMessage 观察值
        from langchain_core.messages import ToolMessage
        assert any(isinstance(msg, ToolMessage) and "越出工作区" in str(msg.content) for msg in final_state["messages"])
    finally:
        await close_runtime(deps)
