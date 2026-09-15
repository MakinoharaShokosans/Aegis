"""运行时装配、图构建与执行入口。

对应 ``documents/agent_runtime/04_routing_and_control_flow.md`` §3–§4。

**两个层次的装配**：

1. :func:`build_runtime` —— **进程级**单例（配置、记忆、模型网关、技能、检查点、MCP）。
   由应用 lifespan 调用一次，进程退出时 :func:`close_runtime` 释放。
2. :func:`prepare_task` —— **任务级**对象（预算守卫、裁剪器、轨迹记录器、上下文装配器、
   工具注册表）。**每个任务重建**，因为它们的生命周期天然绑定单次任务。

**为什么每个任务重新编译图**：任务级依赖（守卫的挂钟起点、绑定 ``task_id`` 的裁剪器与
轨迹记录器）通过闭包注入节点。LangGraph 编译开销在毫秒量级，远低于把任务级状态塞进
Checkpoint 带来的语义污染。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

from langgraph.graph import StateGraph
from loguru import logger

from agent_runtime import routing
from agent_runtime.checkpoint import SqliteCheckpointStore
from agent_runtime.config import AegisConfig, get_config
from agent_runtime.context import ContextManager
from agent_runtime.execution_context import ExecutionContextManager, build_initial_state
from agent_runtime.guardrails.observation_pruner import ObservationPruner
from agent_runtime.guardrails.physical_budget import PhysicalBudgetGuard
from agent_runtime.llm.client import LLMGateway
from agent_runtime.memory.manager import MemoryManager
from agent_runtime.nodes import (
    build_budget_guard_node,
    build_evaluator_node,
    build_executor_node,
    build_planner_node,
)
from agent_runtime.nodes.base import NodeFn
from agent_runtime.observability.trajectory import TrajectoryRecorder
from agent_runtime.prompt_loader import PromptLibrary
from agent_runtime.skills.registry import SkillsRegistry
from agent_runtime.state import AgentState
from agent_runtime.tokenizer import count_tokens
from mcps.adapter import MCPToolAdapter
from mcps.manager import MCPManager
from tools.builtin import build_builtin_tools
from tools.core.dispatcher import ToolDispatcher
from tools.core.http_client import ServiceClient
from tools.core.registry import ToolRegistry

__all__ = [
    "RuntimeDeps",
    "TaskRuntime",
    "build_agent_graph",
    "build_runtime",
    "close_runtime",
    "prepare_task",
    "resume_agent",
    "run_agent",
    "run_streaming",
]

#: 流式事件回调：接收结构化事件字典（供 API 层转发 SSE）
EventSink = Callable[[Dict[str, Any]], Awaitable[None]]


# ==============================================================================
# 进程级运行时
# ==============================================================================

@dataclass
class RuntimeDeps:
    """进程级依赖容器（由 lifespan 构造一次）。"""

    config: AegisConfig
    memory: MemoryManager
    gateway: LLMGateway
    prompts: PromptLibrary
    skills: SkillsRegistry
    mcp_manager: MCPManager
    checkpoints: SqliteCheckpointStore
    builtin_skills_dir: Path = field(default_factory=lambda: Path("src/skills"))


async def build_runtime(config: Optional[AegisConfig] = None) -> RuntimeDeps:
    """装配进程级运行时。

    Args:
        config: 全局配置；缺省从 ``config.toml`` 加载。

    Returns:
        已初始化完毕的 :class:`RuntimeDeps`。
    """
    cfg = config or get_config()

    memory = MemoryManager()
    await memory.initialize()

    checkpoints = SqliteCheckpointStore(cfg.runtime.storage.checkpoint_db_path)
    await checkpoints.open()

    builtin_dir = Path(__file__).resolve().parent.parent / "skills"
    deps = RuntimeDeps(
        config=cfg,
        memory=memory,
        gateway=LLMGateway.from_config(cfg.models, cfg.runtime.retry),
        prompts=PromptLibrary(),
        skills=SkillsRegistry.from_workspace(
            workspace_root=Path.cwd(), builtin_dir=builtin_dir
        ),
        mcp_manager=MCPManager(cfg.mcp),
        checkpoints=checkpoints,
        builtin_skills_dir=builtin_dir,
    )
    logger.info("[Workflow] 进程级运行时装配完成")
    return deps


async def close_runtime(deps: RuntimeDeps) -> None:
    """释放进程级资源（由 lifespan 关闭阶段调用）。

    Args:
        deps: 运行时容器。
    """
    await deps.mcp_manager.shutdown_all()
    await deps.checkpoints.close()
    logger.info("[Workflow] 进程级运行时已释放")


# ==============================================================================
# 任务级运行时
# ==============================================================================

@dataclass
class TaskRuntime:
    """单个任务的运行时上下文。"""

    state: AgentState
    guard: PhysicalBudgetGuard
    context: ContextManager
    recorder: TrajectoryRecorder
    registry: ToolRegistry
    dispatcher: ToolDispatcher
    pruner: ObservationPruner
    lifecycle: ExecutionContextManager
    service_clients: List[ServiceClient] = field(default_factory=list)


def _build_service_clients(config: AegisConfig) -> Dict[str, ServiceClient]:
    """构造指向三个 sidecar 的 HTTP 客户端。"""
    services = config.services
    return {
        "rag": ServiceClient(services.rag_url, services.timeout_sec),
        "shell": ServiceClient(services.shell_url, services.timeout_sec),
        "web": ServiceClient(services.web_url, services.timeout_sec),
    }


async def prepare_task(
    deps: RuntimeDeps,
    *,
    workspace_id: str,
    session_id: str,
    task_goal: str,
    task_id: Optional[str] = None,
) -> TaskRuntime:
    """装配单个任务的运行时上下文（Spawn 阶段）。

    Args:
        deps: 进程级依赖。
        workspace_id: 工作区标识。
        session_id: 会话标识。
        task_goal: 任务目标。
        task_id: 任务 ID；缺省自动生成。

    Returns:
        已就绪的 :class:`TaskRuntime`。
    """
    cfg = deps.config

    # 1. 读取工作区四层记忆资产
    workspace, workspace_memory, session_memory, active_turns = await deps.memory.load_session_context(
        session_id, workspace_id=workspace_id
    )

    # 2. 构造初始状态（记忆继承在这里发生）
    state = build_initial_state(
        workspace_id=workspace.workspace_id,
        workspace_path=workspace.root_path,
        session_id=session_id,
        task_goal=task_goal,
        task_id=task_id,
        active_turns=active_turns,
        rolling_summary=session_memory.summary,
        confirmed_facts=session_memory.confirmed_facts,
        failed_attempts=session_memory.failed_attempts,
    )

    # 3. 任务级护栏与工具
    guard = PhysicalBudgetGuard.from_config(cfg.runtime.guardrails)
    pruner = ObservationPruner.from_config(
        cfg.runtime.context, cfg.runtime.storage.artifacts_dir, count_tokens
    )
    recorder = TrajectoryRecorder(cfg.runtime.storage.traces_dir, state["task_id"])

    clients = _build_service_clients(cfg)
    # 技能以"目标工程"为工作区根，实现工作区级技能覆盖
    skills = SkillsRegistry.from_workspace(
        workspace_root=workspace.root_path,
        builtin_dir=deps.builtin_skills_dir,
    )
    skills.scan()

    registry = ToolRegistry()
    registry.register_all(
        build_builtin_tools(
            workspace_id=workspace.workspace_id,
            workspace_root=workspace.root_path,
            task_id=state["task_id"],
            rag_client=clients["rag"],
            shell_client=clients["shell"],
            web_client=clients["web"],
            skills=skills,
            bash_timeout_sec=float(getattr(cfg, "server", None) and 60.0 or 60.0),
        )
    )
    # MCP 远端工具按需发现并转译为本地工具（失败会被隔离，不影响内置工具）
    try:
        for definition in await deps.mcp_manager.list_tools():
            registry.register(MCPToolAdapter(definition, deps.mcp_manager, state["task_id"]))
    except Exception as exc:  # noqa: BLE001 - MCP 是增强项，失败必须隔离
        logger.error(f"[Workflow] MCP 工具发现失败，已跳过全部 MCP 工具: {exc}")

    context = ContextManager(
        prompts=deps.prompts,
        workspace=workspace,
        workspace_memory=workspace_memory,
        skills=skills,
        workspace_path=workspace.root_path,
    )

    return TaskRuntime(
        state=state,
        guard=guard,
        context=context,
        recorder=recorder,
        registry=registry,
        dispatcher=ToolDispatcher(registry),
        pruner=pruner,
        lifecycle=ExecutionContextManager(deps.memory, recorder),
        service_clients=list(clients.values()),
    )


# ==============================================================================
# 图构建
# ==============================================================================

def build_agent_graph(nodes: Mapping[str, NodeFn]) -> StateGraph:
    """按边的声明装配 LangGraph 状态图。

    条件边完全由 :data:`agent_runtime.routing.EDGE_TABLE` 驱动——
    新增一条边只需加一个 ``edges/after_*.py`` 并登记，**不必修改本函数**。

    Args:
        nodes: ``节点名 -> 节点函数`` 映射。

    Returns:
        未编译的 :class:`StateGraph`。
    """
    graph = StateGraph(AgentState)

    for name, node_fn in nodes.items():
        graph.add_node(name, node_fn)  # type: ignore[arg-type]

    graph.set_entry_point("planner")

    for source, (router, targets) in routing.EDGE_TABLE.items():
        graph.add_conditional_edges(source, router, dict(targets))  # type: ignore[arg-type]

    return graph


def _compile_app(deps: RuntimeDeps, task: TaskRuntime) -> Any:
    """装配节点并编译为可执行图。"""
    cfg = deps.config
    nodes: Dict[str, NodeFn] = {
        "planner": build_planner_node(deps.gateway, task.context, deps.prompts, task.recorder),
        "budget_guard": build_budget_guard_node(task.guard),
        "executor": build_executor_node(
            deps.gateway,
            task.registry,
            task.dispatcher,
            task.pruner,
            deps.prompts,
            task.context,
            cfg.runtime.guardrails,
            task.recorder,
        ),
        "evaluator": build_evaluator_node(deps.gateway, task.context, deps.prompts, task.recorder),
    }
    return build_agent_graph(nodes).compile(checkpointer=deps.checkpoints.saver)


async def _drive_graph(
    deps: RuntimeDeps,
    task: TaskRuntime,
    app: Any,
    graph_input: Optional[Mapping[str, Any]],
    event_sink: Optional[EventSink] = None,
) -> AgentState:
    """驱动图执行并回收终态。

    使用 ``stream_mode="updates"`` 逐节点推送事件（用于 SSE），
    执行结束后再用 ``aget_state`` 取回**权威终态**——
    避免手工合并增量时漏掉 Reducer 语义（尤其是 ``add_messages``）。

    Args:
        deps: 进程级依赖。
        task: 任务运行时。
        app: 已编译的图。
        graph_input: 初始状态；``None`` 表示从 Checkpoint 续跑。
        event_sink: 可选事件回调。

    Returns:
        终态 ``AgentState``。
    """
    run_config = {"configurable": {"thread_id": task.state["task_id"]}}
    seq = 0

    async for chunk in app.astream(graph_input, run_config, stream_mode="updates"):
        for node_name, delta in (chunk or {}).items():
            seq += 1
            if event_sink is not None:
                await event_sink(
                    {
                        "event": "node.finished",
                        "node": node_name,
                        "seq": seq,
                        "step_count": int((delta or {}).get("step_count", task.state.get("step_count", 0))),
                        "total_tokens": int((delta or {}).get("total_tokens", task.state.get("total_tokens", 0))),
                        "should_terminate": bool((delta or {}).get("should_terminate", False)),
                    }
                )

    snapshot = await app.aget_state(run_config)
    final_state: AgentState = dict(snapshot.values)  # type: ignore[assignment]
    logger.info(
        f"[Workflow] 任务 {task.state['task_id']} 执行结束: "
        f"步数={final_state.get('step_count')} Token={final_state.get('total_tokens')} "
        f"原因={final_state.get('termination_reason') or '（未标注）'}"
    )
    return final_state


async def run_streaming(
    deps: RuntimeDeps,
    *,
    workspace_id: str,
    session_id: str,
    task_goal: str,
    task_id: Optional[str] = None,
    event_sink: Optional[EventSink] = None,
) -> AgentState:
    """提交并执行一个新任务（支持流式事件回调）。

    Args:
        deps: 进程级依赖。
        workspace_id: 工作区标识。
        session_id: 会话标识。
        task_goal: 任务目标。
        task_id: 任务 ID（由调用方预分配，便于先返回给客户端）。
        event_sink: 事件回调（SSE 推送）。

    Returns:
        终态 ``AgentState``。
    """
    task = await prepare_task(
        deps,
        workspace_id=workspace_id,
        session_id=session_id,
        task_goal=task_goal,
        task_id=task_id,
    )
    app = _compile_app(deps, task)

    try:
        final_state = await _drive_graph(deps, task, app, task.state, event_sink)
    finally:
        for client in task.service_clients:
            await client.aclose()

    await task.lifecycle.finalize(
        final_state,
        ExecutionContextManager.extract_delivery(final_state),
    )
    return final_state


async def run_agent(
    deps: RuntimeDeps,
    *,
    workspace_id: str,
    session_id: str,
    task_goal: str,
    task_id: Optional[str] = None,
) -> AgentState:
    """同步等待任务完成（无事件流）。"""
    return await run_streaming(
        deps,
        workspace_id=workspace_id,
        session_id=session_id,
        task_goal=task_goal,
        task_id=task_id,
    )


async def resume_agent(
    deps: RuntimeDeps,
    *,
    task_id: str,
    workspace_id: str,
    session_id: str,
    task_goal: str,
    event_sink: Optional[EventSink] = None,
) -> AgentState:
    """从最近一次 Checkpoint 续跑任务。

    .. note::
       **挂钟预算语义**：``PhysicalBudgetGuard`` 会随本函数重新实例化，
       因此恢复后的挂钟计时从"恢复时刻"重新开始。这是刻意取舍——
       否则进程重启本身就会吃掉全部时间预算。

    Args:
        deps: 进程级依赖。
        task_id: 原任务 ID（必须与 Checkpoint 的 thread_id 一致）。
        workspace_id: 工作区标识。
        session_id: 会话标识。
        task_goal: 任务目标（用于重建上下文与记忆回写）。
        event_sink: 事件回调。

    Returns:
        终态 ``AgentState``。
    """
    task = await prepare_task(
        deps,
        workspace_id=workspace_id,
        session_id=session_id,
        task_goal=task_goal,
        task_id=task_id,
    )
    app = _compile_app(deps, task)

    try:
        # graph_input=None 表示"从该 thread 的最近 Checkpoint 继续"
        final_state = await _drive_graph(deps, task, app, None, event_sink)
    finally:
        for client in task.service_clients:
            await client.aclose()

    return final_state
