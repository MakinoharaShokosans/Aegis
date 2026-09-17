"""tool_runner 节点与 HITL 审批挂起/恢复测试 (nodes/tool_runner.py)。"""

from pathlib import Path
from typing import Any, Mapping
import pytest

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from agent_runtime.config import GuardrailsConfig, PermissionsConfig
from agent_runtime.guardrails.observation_pruner import ObservationPruner
from agent_runtime.nodes.tool_runner import build_tool_runner_node
from agent_runtime.state import AgentState
from tools.core.dispatcher import ToolDispatcher
from tools.core.protocol import AegisTool, ToolResult
from tools.core.registry import ToolRegistry


class DummyTool(AegisTool):
    """测试用 Mock 工具。"""

    def __init__(self, name: str, return_content: str = "ok", succeed: bool = True):
        self.name = name
        self.description = f"Dummy tool {name}"
        self.return_content = return_content
        self.succeed = succeed
        self.invoked_calls = []

    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        self.invoked_calls.append(dict(args))
        if self.succeed:
            return ToolResult(ok=True, content=self.return_content)
        return ToolResult.failure(self.return_content)


@pytest.fixture
def tool_runner_env(tmp_path: Path):
    """构造包含常见工具、Dispatcher 与 Pruner 的测试环境。"""
    registry = ToolRegistry(allow_untrusted=True)
    view_tool = DummyTool("view_file", return_content="file content viewed")
    write_tool = DummyTool("write_file", return_content="file written")
    bash_tool = DummyTool("bash", return_content="bash executed")

    registry.register(view_tool)
    registry.register(write_tool)
    registry.register(bash_tool)

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
        workspace_write_tools=["write_file"],
        bash_tools=["bash"],
    )

    return {
        "registry": registry,
        "dispatcher": dispatcher,
        "pruner": pruner,
        "guardrails_cfg": guardrails_cfg,
        "permissions_cfg": permissions_cfg,
        "view_tool": view_tool,
        "write_tool": write_tool,
        "bash_tool": bash_tool,
    }


def _build_test_graph(tool_runner_node):
    """编译单节点 StateGraph 用于真实验证 interrupt/resume。"""
    graph = StateGraph(AgentState)
    graph.add_node("tool_runner", tool_runner_node)
    graph.set_entry_point("tool_runner")
    graph.add_edge("tool_runner", END)
    return graph.compile(checkpointer=MemorySaver())


# ==============================================================================
# 1. 场景 A：无需审批的只读工具直接执行
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_runner_allowed_without_interrupt(tool_runner_env):
    """测试权限内工具（read_only）直接并发派发，不触发任何 interrupt。"""
    env = tool_runner_env
    allowlist = set()
    node = build_tool_runner_node(
        env["dispatcher"],
        env["pruner"],
        env["guardrails_cfg"],
        env["permissions_cfg"],
        approval_allowlist=allowlist,
    )
    app = _build_test_graph(node)

    initial_state = {
        "task_id": "t_1",
        "permission_level": "workspace_write",
        "step_count": 1,
        "messages": [
            AIMessage(
                content="查看文件",
                tool_calls=[{"id": "c1", "name": "view_file", "args": {"path": "a.txt"}}],
            )
        ],
        "fingerprint_history": [],
        "artifacts": {},
        "consecutive_errors": 0,
        "total_tokens": 10,
    }

    config = {"configurable": {"thread_id": "thread_1"}}
    final = await app.ainvoke(initial_state, config)

    # 验证工具直接执行，没有挂起
    assert len(env["view_tool"].invoked_calls) == 1
    tool_msgs = [m for m in final["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_call_id == "c1"
    assert "file content viewed" in tool_msgs[0].content


# ==============================================================================
# 2. 场景 B：越级触发 interrupt -> 单次批准 (Approve Once)
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_runner_escalation_and_approve_once(tool_runner_env):
    """测试越级操作挂起 -> 注入批准决策 -> 恢复执行并回填观察值。"""
    env = tool_runner_env
    allowlist = set()
    node = build_tool_runner_node(
        env["dispatcher"],
        env["pruner"],
        env["guardrails_cfg"],
        env["permissions_cfg"],
        approval_allowlist=allowlist,
    )
    app = _build_test_graph(node)

    initial_state = {
        "task_id": "t_2",
        "permission_level": "workspace_write",
        "step_count": 1,
        "messages": [
            AIMessage(
                content="推送代码",
                tool_calls=[{"id": "c_push", "name": "bash", "args": {"command": "git push origin main"}}],
            )
        ],
        "fingerprint_history": [],
        "artifacts": {},
        "consecutive_errors": 0,
        "total_tokens": 10,
    }

    config = {"configurable": {"thread_id": "thread_2"}}

    # 1. 首次调用触发 interrupt 挂起
    await app.ainvoke(initial_state, config)
    snapshot = await app.aget_state(config)

    # 验证中断信息捕获
    assert len(snapshot.tasks) > 0
    interrupts = snapshot.tasks[0].interrupts
    assert len(interrupts) > 0
    approval_payload = interrupts[0].value
    assert approval_payload["required_level"] == "full_permissions"
    assert approval_payload["action_type"] == "network_egress"
    assert "git push" in approval_payload["command"]
    assert len(env["bash_tool"].invoked_calls) == 0  # 挂起前未执行工具

    # 2. 注入批准决策恢复执行 (Approve Once)
    final = await app.ainvoke(Command(resume={"approved": True, "scope": "once"}), config)

    # 恢复后工具被执行
    assert len(env["bash_tool"].invoked_calls) == 1
    tool_msgs = [m for m in final["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_call_id == "c_push"
    assert "bash executed" in tool_msgs[0].content
    # 单次批准不写入白名单
    assert len(allowlist) == 0


# ==============================================================================
# 3. 场景 C：越级触发 interrupt -> 拒绝执行 (Reject)
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_runner_escalation_and_reject(tool_runner_env):
    """测试越级操作被人工拒绝 -> 工具不派发并合成包含拒绝原因的 ToolMessage。"""
    env = tool_runner_env
    allowlist = set()
    node = build_tool_runner_node(
        env["dispatcher"],
        env["pruner"],
        env["guardrails_cfg"],
        env["permissions_cfg"],
        approval_allowlist=allowlist,
    )
    app = _build_test_graph(node)

    initial_state = {
        "task_id": "t_3",
        "permission_level": "workspace_write",
        "step_count": 1,
        "messages": [
            AIMessage(
                content="执行外联",
                tool_calls=[{"id": "c_curl", "name": "bash", "args": {"command": "curl http://external.api"}}],
            )
        ],
        "fingerprint_history": [],
        "artifacts": {},
        "consecutive_errors": 0,
        "total_tokens": 10,
    }

    config = {"configurable": {"thread_id": "thread_3"}}

    # 1. 触发挂起
    await app.ainvoke(initial_state, config)

    # 2. 注入拒绝决策
    final = await app.ainvoke(
        Command(resume={"approved": False, "reason": "禁止访问外网，请使用本地测试用例"}), config
    )

    # 验证工具未被执行
    assert len(env["bash_tool"].invoked_calls) == 0
    tool_msgs = [m for m in final["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_call_id == "c_curl"
    assert "已被人工审核拒绝" in tool_msgs[0].content


# ==============================================================================
# 4. 场景 D：永久放行 (Always) 写入白名单且后续免审
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_runner_escalation_always_allowlist(tool_runner_env):
    """测试 scope=always 时写入 allowlist，第二次同签名调用不再触发挂起。"""
    env = tool_runner_env
    allowlist = set()
    node = build_tool_runner_node(
        env["dispatcher"],
        env["pruner"],
        env["guardrails_cfg"],
        env["permissions_cfg"],
        approval_allowlist=allowlist,
    )
    app = _build_test_graph(node)

    cmd_args = {"command": "git push origin dev"}
    state_1 = {
        "task_id": "t_4",
        "permission_level": "workspace_write",
        "step_count": 1,
        "messages": [AIMessage(content="第一次推送", tool_calls=[{"id": "c_first", "name": "bash", "args": cmd_args}])],
        "fingerprint_history": [],
        "artifacts": {},
        "consecutive_errors": 0,
        "total_tokens": 10,
    }
    config_1 = {"configurable": {"thread_id": "thread_4_1"}}

    # 1. 首次调用触发挂起
    await app.ainvoke(state_1, config_1)

    # 2. 批准并选择 always
    await app.ainvoke(Command(resume={"approved": True, "scope": "always"}), config_1)
    assert len(allowlist) == 1

    # 3. 第二轮任务中再次执行相同命令 -> 直接通过，不再挂起
    state_2 = {
        "task_id": "t_4",
        "permission_level": "workspace_write",
        "step_count": 2,
        "messages": [AIMessage(content="第二次推送", tool_calls=[{"id": "c_second", "name": "bash", "args": cmd_args}])],
        "fingerprint_history": [],
        "artifacts": {},
        "consecutive_errors": 0,
        "total_tokens": 20,
    }
    config_2 = {"configurable": {"thread_id": "thread_4_2"}}
    final_2 = await app.ainvoke(state_2, config_2)

    # 第二次无需 resume 直接完成
    tool_msgs = [m for m in final_2["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_call_id == "c_second"


# ==============================================================================
# 5. 场景 E：指纹死循环整批拦截与原子对完整性 (Atomic Pair)
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_runner_fingerprint_loop_and_atomic_pairs(tool_runner_env):
    """测试命中死循环指纹时整批拦截，且严格保持 tool_call_id 与 ToolMessage 1:1 配对。"""
    env = tool_runner_env
    allowlist = set()
    node = build_tool_runner_node(
        env["dispatcher"],
        env["pruner"],
        env["guardrails_cfg"],
        env["permissions_cfg"],
        approval_allowlist=allowlist,
    )
    app = _build_test_graph(node)

    # 预设已经连续出现 2 次相同指纹
    from agent_runtime.guardrails.loop_detector import compute_fingerprint
    repeated_fp = compute_fingerprint("view_file", {"path": "stuck.txt"})

    initial_state = {
        "task_id": "t_5",
        "permission_level": "workspace_write",
        "step_count": 3,
        "messages": [
            AIMessage(
                content="死循环调用",
                tool_calls=[
                    {"id": "call_1", "name": "view_file", "args": {"path": "stuck.txt"}},
                    {"id": "call_2", "name": "view_file", "args": {"path": "stuck.txt"}},
                ],
            )
        ],
        "fingerprint_history": [repeated_fp, repeated_fp],
        "artifacts": {},
        "consecutive_errors": 0,
        "total_tokens": 30,
    }

    config = {"configurable": {"thread_id": "thread_5"}}
    final = await app.ainvoke(initial_state, config)

    tool_msgs = [m for m in final["messages"] if isinstance(m, ToolMessage)]
    # 严格保持原子对：2 个 tool_call 对应 2 个 ToolMessage
    assert len(tool_msgs) == 2
    assert {m.tool_call_id for m in tool_msgs} == {"call_1", "call_2"}
    assert all("已拦截：相同工具与参数连续重复" in m.content for m in tool_msgs)


# ==============================================================================
# 6. 场景 F：批量工具调用中混杂越级动作（Batch Escalation Collusion）
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_runner_batch_escalation_collusion(tool_runner_env):
    """测试单批包含 1 个高危越级动作 + 2 个合规动作时的审批与执行分支。"""
    env = tool_runner_env
    allowlist = set()
    node = build_tool_runner_node(
        env["dispatcher"],
        env["pruner"],
        env["guardrails_cfg"],
        env["permissions_cfg"],
        approval_allowlist=allowlist,
    )
    app = _build_test_graph(node)

    batch_tool_calls = [
        {"id": "call_view", "name": "view_file", "args": {"path": "readme.md"}},
        {"id": "call_write", "name": "write_file", "args": {"path": "out.txt", "content": "hello"}},
        {"id": "call_push", "name": "bash", "args": {"command": "git push origin main"}},
    ]

    initial_state = {
        "task_id": "t_batch",
        "permission_level": "workspace_write",
        "step_count": 1,
        "messages": [AIMessage(content="批量操作", tool_calls=batch_tool_calls)],
        "fingerprint_history": [],
        "artifacts": {},
        "consecutive_errors": 0,
        "total_tokens": 10,
    }

    # 1. 触发挂起，断言批次摘要与越级统计
    config = {"configurable": {"thread_id": "thread_batch_1"}}
    await app.ainvoke(initial_state, config)
    snapshot = await app.aget_state(config)
    assert len(snapshot.tasks[0].interrupts) > 0
    payload = snapshot.tasks[0].interrupts[0].value
    assert payload["required_level"] == "full_permissions"
    assert payload["escalation_count"] == 1
    assert "git push" in payload["command"]

    # 2. 批准：全部 3 个工具均执行并返回 3 个 ToolMessage
    final_appr = await app.ainvoke(Command(resume={"approved": True, "scope": "once"}), config)
    tool_msgs_appr = [m for m in final_appr["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs_appr) == 3
    assert {m.tool_call_id for m in tool_msgs_appr} == {"call_view", "call_write", "call_push"}
    assert any("bash executed" in m.content for m in tool_msgs_appr)

    # 3. 拒绝分支测试（新线程）：合规工具正常派发，越级工具回填拒绝观察值，原子对保持 3:3
    config_rej = {"configurable": {"thread_id": "thread_batch_2"}}
    await app.ainvoke(initial_state, config_rej)
    final_rej = await app.ainvoke(
        Command(resume={"approved": False, "reason": "不允许推送到远端"}), config_rej
    )
    tool_msgs_rej = [m for m in final_rej["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs_rej) == 3
    assert {m.tool_call_id for m in tool_msgs_rej} == {"call_view", "call_write", "call_push"}
    rej_msg = next(m for m in tool_msgs_rej if m.tool_call_id == "call_push")
    assert "已被人工审核拒绝" in rej_msg.content
    assert "不允许推送到远端" in rej_msg.content


# ==============================================================================
# 7. 场景 G：挂起期间权限快照稳定性 (Snapshot Stability)
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_runner_snapshot_stability_during_wait(tool_runner_env):
    """测试挂起期间中断载荷中的快照字段（current_level、required_level）完整稳定。"""
    env = tool_runner_env
    node = build_tool_runner_node(
        env["dispatcher"],
        env["pruner"],
        env["guardrails_cfg"],
        env["permissions_cfg"],
    )
    app = _build_test_graph(node)

    initial_state = {
        "task_id": "t_snap",
        "permission_level": "workspace_write",
        "step_count": 1,
        "messages": [
            AIMessage(
                content="执行外联",
                tool_calls=[{"id": "call_net", "name": "bash", "args": {"command": "curl http://api.com"}}],
            )
        ],
        "fingerprint_history": [],
        "artifacts": {},
        "consecutive_errors": 0,
        "total_tokens": 10,
    }

    config = {"configurable": {"thread_id": "thread_snap"}}
    await app.ainvoke(initial_state, config)

    snapshot = await app.aget_state(config)
    payload = snapshot.tasks[0].interrupts[0].value
    assert payload["current_level"] == "workspace_write"
    assert payload["required_level"] == "full_permissions"
    assert payload["action_type"] == "network_egress"
    assert "approval_id" in payload


# ==============================================================================
# 8. 场景 H：畸形/恶意 resume payload 防御 (Malformed Resume Defense)
# ==============================================================================

@pytest.mark.parametrize(
    "malformed_resume",
    [
        "approved",
        ["approved"],
        12345,
        {"approved": "invalid_string_truthy"},  # 字符串非严格 bool
        {"approved": False, "scope": 9999},
        {"random_key": "some_value"},
    ],
)
@pytest.mark.asyncio
async def test_tool_runner_malformed_resume_defense(tool_runner_env, malformed_resume):
    """验证各种畸形 resume 输入均能安全回退为未批准，不引发未捕获异常或图崩溃。"""
    import uuid
    env = tool_runner_env
    node = build_tool_runner_node(
        env["dispatcher"],
        env["pruner"],
        env["guardrails_cfg"],
        env["permissions_cfg"],
    )
    app = _build_test_graph(node)

    initial_state = {
        "task_id": "t_malformed",
        "permission_level": "workspace_write",
        "step_count": 1,
        "messages": [
            AIMessage(
                content="高危命令",
                tool_calls=[{"id": "call_x", "name": "bash", "args": {"command": "git push"}}],
            )
        ],
        "fingerprint_history": [],
        "artifacts": {},
        "consecutive_errors": 0,
        "total_tokens": 10,
    }

    thread_id = f"thread_malformed_{uuid.uuid4().hex}"
    config = {"configurable": {"thread_id": thread_id}}

    # 1. 触发挂起
    await app.ainvoke(initial_state, config)

    # 2. 注入畸形 payload 恢复，断言安全完成且未执行高危工具
    final = await app.ainvoke(Command(resume=malformed_resume), config)
    assert len(env["bash_tool"].invoked_calls) == 0

    tool_msgs = [m for m in final["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_call_id == "call_x"
    # 当 approved 不为严格 True 时，回填拒绝说明
    assert "已被人工审核拒绝" in tool_msgs[0].content


