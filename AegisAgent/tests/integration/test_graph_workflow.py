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
    resume_agent,
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
        nodes_executed = [ev["node"] for ev in events if "node" in ev]
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


@pytest.mark.asyncio
async def test_workflow_escalation_and_approval_closure(test_config: AegisConfig, mock_gateway_factory, tmp_path: Path):
    """测试越级审批闭环：
    Planner 规划 -> Executor 生成高权限命令 -> ToolRunner 挂起 -> 模拟审批恢复 (once) -> 继续执行 -> Evaluator 验收交付。
    """
    ws_dir = tmp_path / "escalation_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)

    planner_resp_1 = {
        "thought": "准备执行网络下载",
        "milestones": [{"id": 1, "title": "下载文件", "description": "下载 remote.json", "status": "in_progress"}],
        "next_step": "执行 curl 下载",
    }
    executor_resp_1 = LLMResponse(
        content="正在执行 curl",
        tool_calls=[{
            "id": "call_curl_e2e",
            "name": "bash",
            "args": {"command": "curl https://example.com/remote.json"},
        }],
        total_tokens=20,
        endpoint_name="mock-fast",
    )
    planner_resp_2 = {
        "thought": "下载已完成，标记任务结束",
        "milestone_updates": [{"id": 1, "status": "completed"}],
        "next_step": "提交验收",
    }
    evaluator_resp = {
        "milestone_ok": True,
        "task_completed": True,
        "summary": "越级审批恢复后成功交付",
        "confirmed_facts": [],
        "failed_attempts": [],
    }

    mock_gateway = mock_gateway_factory([
        planner_resp_1,
        executor_resp_1,
        planner_resp_2,
        evaluator_resp,
    ])

    store = SqliteMemoryStore(db_path=test_config.runtime.storage.metadata_db_path)
    memory = MemoryManager(store=store)
    await memory.initialize()

    checkpoints = SqliteCheckpointStore(test_config.runtime.storage.checkpoint_db_path)
    await checkpoints.open()

    ws = await memory.create_workspace(name="esc_ws", root_path=str(ws_dir), description="Escalation test workspace")
    session = await memory.create_session(workspace_id=ws.workspace_id, title="Escalation Session")

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

    task_id = "task_escalation_test_1"
    try:
        # 1. 运行流式执行，触发越级挂起
        outcome = await run_streaming(
            deps,
            workspace_id=ws.workspace_id,
            session_id=session.session_id,
            task_goal="下载远程配置",
            task_id=task_id,
            permission_level="workspace_write",
        )

        assert outcome.waiting_for_approval is True
        assert outcome.approval_request is not None
        assert outcome.approval_request["required_level"] == "full_permissions"
        assert outcome.approval_request["current_level"] == "workspace_write"
        assert "curl" in outcome.approval_request["command"]

        # 2. 模拟用户批准恢复执行
        resume_outcome = await resume_agent(
            deps,
            task_id=task_id,
            workspace_id=ws.workspace_id,
            session_id=session.session_id,
            task_goal="下载远程配置",
            approval_decision={"approved": True, "scope": "once"},
        )

        assert resume_outcome.waiting_for_approval is False
        assert resume_outcome.state["should_terminate"] is True
        assert resume_outcome.state["milestones"][0].status == "completed"
    finally:
        await close_runtime(deps)


@pytest.mark.asyncio
async def test_workflow_escalation_rejection_and_adaptive_replan(test_config: AegisConfig, mock_gateway_factory, tmp_path: Path):
    """测试审批被拒绝后自适应：
    ToolRunner 拒绝 -> Planner 依据拒绝观察值给出合规替代方案 -> 最终收敛完成。
    """
    ws_dir = tmp_path / "reject_replan_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)

    planner_resp_1 = {
        "thought": "尝试推送远端分支",
        "milestones": [{"id": 1, "title": "交付修改", "description": "提交或生成补丁", "status": "in_progress"}],
        "next_step": "执行 git push",
    }
    executor_resp_1 = LLMResponse(
        content="正在推送远端",
        tool_calls=[{
            "id": "call_git_push",
            "name": "bash",
            "args": {"command": "git push origin feat"},
        }],
        total_tokens=20,
        endpoint_name="mock-fast",
    )
    planner_resp_after_reject = {
        "thought": "远端推送被审批拒绝，根据拒绝理由改在本地生成 patch.diff 补丁文件",
        "milestones": [{"id": 1, "title": "交付修改", "description": "生成本地补丁", "status": "in_progress"}],
        "next_step": "调用 write_file 写入 patch.diff",
    }
    executor_resp_2 = LLMResponse(
        content="写入补丁文件",
        tool_calls=[{
            "id": "call_write_patch",
            "name": "write_file",
            "args": {"path": "patch.diff", "content": "diff --git a/fix.py b/fix.py\n+patched"},
        }],
        total_tokens=20,
        endpoint_name="mock-fast",
    )
    planner_resp_3 = {
        "thought": "补丁文件已成功生成，标记完成",
        "milestone_updates": [{"id": 1, "status": "completed"}],
        "next_step": "提交验收",
    }
    evaluator_resp = {
        "milestone_ok": True,
        "task_completed": True,
        "summary": "依据拒绝反馈自适应生成本地补丁完成任务",
        "confirmed_facts": ["patch.diff 已生成"],
        "failed_attempts": [],
    }

    mock_gateway = mock_gateway_factory([
        planner_resp_1,
        executor_resp_1,
        planner_resp_after_reject,
        executor_resp_2,
        planner_resp_3,
        evaluator_resp,
    ])

    store = SqliteMemoryStore(db_path=test_config.runtime.storage.metadata_db_path)
    memory = MemoryManager(store=store)
    await memory.initialize()

    checkpoints = SqliteCheckpointStore(test_config.runtime.storage.checkpoint_db_path)
    await checkpoints.open()

    ws = await memory.create_workspace(name="rej_ws", root_path=str(ws_dir), description="Rejection adaptive workspace")
    session = await memory.create_session(workspace_id=ws.workspace_id, title="Rejection Session")

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

    task_id = "task_rejection_adaptive_test"
    try:
        # 1. 触发越级挂起
        outcome = await run_streaming(
            deps,
            workspace_id=ws.workspace_id,
            session_id=session.session_id,
            task_goal="交付代码变更",
            task_id=task_id,
            permission_level="workspace_write",
        )
        assert outcome.waiting_for_approval is True

        # 2. 模拟用户拒绝
        resume_outcome = await resume_agent(
            deps,
            task_id=task_id,
            workspace_id=ws.workspace_id,
            session_id=session.session_id,
            task_goal="交付代码变更",
            approval_decision={"approved": False, "reason": "禁止推送远端仓库，请生成本地补丁文件"},
        )

        assert resume_outcome.waiting_for_approval is False
        assert resume_outcome.state["should_terminate"] is True
        assert (ws_dir / "patch.diff").is_file()
        assert "+patched" in (ws_dir / "patch.diff").read_text(encoding="utf-8")
    finally:
        await close_runtime(deps)


@pytest.mark.asyncio
async def test_workflow_always_allowlist_across_steps(test_config: AegisConfig, mock_gateway_factory, tmp_path: Path):
    """测试 always 白名单跨步生效：同一签名动作第二次出现时不再挂起。"""
    ws_dir = tmp_path / "always_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)

    planner_resp_1 = {
        "thought": "规划第一次网络调用",
        "milestones": [
            {"id": 1, "title": "步骤 1", "description": "拉取状态", "status": "in_progress"},
            {"id": 2, "title": "步骤 2", "description": "拉取数据", "status": "pending"},
        ],
        "next_step": "执行 curl 获取状态",
    }
    executor_resp_1 = LLMResponse(
        content="执行第一次 curl",
        tool_calls=[{
            "id": "call_curl_step1",
            "name": "bash",
            "args": {"command": "curl https://api.internal/health"},
        }],
        total_tokens=20,
        endpoint_name="mock-fast",
    )
    planner_resp_2 = {
        "thought": "步骤 1 完成，准备步骤 2 调用同类内部接口",
        "milestone_updates": [
            {"id": 1, "status": "completed"},
            {"id": 2, "status": "in_progress"},
        ],
        "next_step": "再次执行 curl",
    }
    # 第二次使用完全相同的工具调用签名（同一命令）
    executor_resp_2 = LLMResponse(
        content="执行第二次 curl（同签名）",
        tool_calls=[{
            "id": "call_curl_step2",
            "name": "bash",
            "args": {"command": "curl https://api.internal/health"},
        }],
        total_tokens=20,
        endpoint_name="mock-fast",
    )
    planner_resp_3 = {
        "thought": "全部步骤完成",
        "milestone_updates": [{"id": 2, "status": "completed"}],
        "next_step": "提交验收",
    }
    evaluator_resp = {
        "milestone_ok": True,
        "task_completed": True,
        "summary": "全部步骤完成且第二次调用被白名单直接放行",
        "confirmed_facts": [],
        "failed_attempts": [],
    }

    mock_gateway = mock_gateway_factory([
        planner_resp_1,
        executor_resp_1,
        planner_resp_2,
        executor_resp_2,
        planner_resp_3,
        evaluator_resp,
    ])

    store = SqliteMemoryStore(db_path=test_config.runtime.storage.metadata_db_path)
    memory = MemoryManager(store=store)
    await memory.initialize()

    checkpoints = SqliteCheckpointStore(test_config.runtime.storage.checkpoint_db_path)
    await checkpoints.open()

    ws = await memory.create_workspace(name="alw_ws", root_path=str(ws_dir), description="Always allowlist workspace")
    session = await memory.create_session(workspace_id=ws.workspace_id, title="Always Session")

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

    task_id = "task_always_allowlist_test"
    allowlist: set[str] = set()

    try:
        # 1. 第一次流式执行，触发挂起
        outcome = await run_streaming(
            deps,
            workspace_id=ws.workspace_id,
            session_id=session.session_id,
            task_goal="多次调用内部接口",
            task_id=task_id,
            permission_level="workspace_write",
            approval_allowlist=allowlist,
        )
        assert outcome.waiting_for_approval is True

        # 2. 注入 scope="always" 恢复执行 -> 第二次 curl 调用应该被白名单直接放行而不挂起 -> 直至最终完成！
        resume_outcome = await resume_agent(
            deps,
            task_id=task_id,
            workspace_id=ws.workspace_id,
            session_id=session.session_id,
            task_goal="多次调用内部接口",
            approval_decision={"approved": True, "scope": "always"},
            approval_allowlist=allowlist,
        )

        assert resume_outcome.waiting_for_approval is False
        assert resume_outcome.state["should_terminate"] is True
        assert len(allowlist) >= 1
        assert resume_outcome.state["milestones"][1].status == "completed"
    finally:
        await close_runtime(deps)


@pytest.mark.asyncio
async def test_workflow_conversational_direct_reply_closure(test_config: AegisConfig, mock_gateway_factory, tmp_path: Path):
    """测试纯对话/无工具调用场景（如发送'你好'）：
    Planner 决策 -> BudgetGuard 放行 -> Executor 直接输出问候文本（无 tool_calls） -> Evaluator 验收收敛 -> 1 步完成，不进入死循环。
    """
    ws_dir = tmp_path / "chat_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)

    planner_resp = {
        "thought": "用户向我打招呼，回复问候并询问需要什么帮助",
        "milestones": [],
        "next_step": "你好！我是 Aegis 研发助手，有什么我可以帮您的吗？",
    }
    executor_resp = LLMResponse(
        content="你好！我是 Aegis 研发助手，很高兴为你服务。请问今天有什么开发任务需要我协助？",
        tool_calls=[],
        total_tokens=15,
        endpoint_name="mock-fast",
    )
    evaluator_resp = {
        "milestone_ok": True,
        "task_completed": True,
        "summary": "已向用户打招呼并等待指令",
        "confirmed_facts": [],
        "failed_attempts": [],
    }

    mock_gateway = mock_gateway_factory([
        planner_resp,
        executor_resp,
        evaluator_resp,
    ])

    store = SqliteMemoryStore(db_path=test_config.runtime.storage.metadata_db_path)
    memory = MemoryManager(store=store)
    await memory.initialize()

    checkpoints = SqliteCheckpointStore(test_config.runtime.storage.checkpoint_db_path)
    await checkpoints.open()

    ws = await memory.create_workspace(name="chat_ws", root_path=str(ws_dir), description="Chat workspace")
    session = await memory.create_session(workspace_id=ws.workspace_id, title="Chat Session")

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
        outcome = await run_streaming(
            deps,
            workspace_id=ws.workspace_id,
            session_id=session.session_id,
            task_goal="你好",
            event_sink=capture_event,
        )
        final_state = outcome.state

        # 校验：单步收敛、should_terminate 为 True、不循环
        assert final_state["should_terminate"] is True
        assert final_state["termination_reason"] == "task_goal achieved"
        assert final_state["step_count"] == 1

        nodes_executed = [ev["node"] for ev in events if ev.get("event") == "node.finished"]
        assert nodes_executed == ["planner", "budget_guard", "executor", "evaluator"]
        assert "tool_runner" not in nodes_executed

        llm_calls = [ev for ev in events if ev.get("event") == "llm.call"]
        assert len(llm_calls) == 3
        assert [c["node"] for c in llm_calls] == ["planner", "executor", "evaluator"]

        # 校验提取的交付答复包含 executor 输出
        from agent_runtime.execution_context import ExecutionContextManager
        delivery = ExecutionContextManager.extract_delivery(final_state)
        assert "Aegis 研发助手" in delivery
    finally:
        await close_runtime(deps)

