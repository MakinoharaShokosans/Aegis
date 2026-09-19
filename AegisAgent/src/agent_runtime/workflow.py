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
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Set

from langgraph.graph import StateGraph
from langgraph.types import Command
from loguru import logger

from agent_runtime import routing
from agent_runtime.checkpoint import SqliteCheckpointStore
from agent_runtime.config import AegisConfig, get_config
from agent_runtime.context import ContextManager
from agent_runtime.execution_context import ExecutionContextManager, build_initial_state
from agent_runtime.guardrails.authority import TaskAuthority
from agent_runtime.guardrails.budget_ledger import BudgetLedger
from agent_runtime.guardrails.observation_pruner import ObservationPruner
from agent_runtime.guardrails.physical_budget import PhysicalBudgetGuard
from agent_runtime.llm.client import LLMGateway
from agent_runtime.memory.manager import MemoryManager
from agent_runtime.nodes import (
    build_budget_guard_node,
    build_evaluator_node,
    build_executor_node,
    build_planner_node,
    build_tool_runner_node,
)
from agent_runtime.nodes.base import NodeFn
from agent_runtime.observability.event_bus import TaskEventBus
from agent_runtime.observability.trajectory import TrajectoryRecorder
from agent_runtime.code_search import build_code_search_tool
from agent_runtime.prompt_loader import PromptLibrary
from agent_runtime.research import build_research_tool
from agent_runtime.skills.registry import SkillsRegistry
from agent_runtime.state import AgentState
from agent_runtime.subagent import build_subagent_tool
from agent_runtime.tokenizer import count_tokens
from mcps.adapter import MCPToolAdapter
from mcps.manager import MCPManager
from tools.builtin import build_builtin_tools
from tools.builtin.web_search import WebSearchTool
from tools.core.dispatcher import ToolDispatcher
from tools.core.http_client import ServiceClient
from tools.core.registry import ToolRegistry

__all__ = [
    "RuntimeDeps",
    "TaskOutcome",
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


@dataclass(slots=True)
class TaskOutcome:
    """一次图执行的产出。

    单独成契约的原因：**"任务挂起等待人工审批"是一个必须传给 API 层的事实**，
    而它不是 ``AgentState`` 的一部分——``AgentState`` 只描述执行状态，
    待审批信息由 LangGraph 的 interrupt 机制在 checkpoint 中维护。
    把它塞进 state 会造成"同一事实两处存储"的漂移风险。

    Attributes:
        state: 执行终态（或挂起时的当前状态）。
        approval_request: 待审批请求；``None`` 表示未处于待审批状态。
    """

    state: AgentState
    approval_request: Optional[Dict[str, Any]] = None

    @property
    def waiting_for_approval(self) -> bool:
        """是否正处于"等待人工审批"的挂起状态。"""
        return self.approval_request is not None


def _extract_pending_approval(snapshot: Any) -> Optional[Dict[str, Any]]:
    """从 Checkpoint 快照中提取待审批请求。

    Args:
        snapshot: ``app.aget_state(...)`` 返回的 ``StateSnapshot``。

    Returns:
        审批请求字典；无挂起时返回 ``None``。
    """
    def _scan(interrupts: Any) -> Optional[Dict[str, Any]]:
        for item in interrupts or ():
            value = getattr(item, "value", None)
            if isinstance(value, Mapping) and "approval_id" in value:
                return dict(value)
        return None

    # 先看顶层（LangGraph 会把当前所有挂起中断聚合在这里），再兜底遍历任务
    found = _scan(getattr(snapshot, "interrupts", None))
    if found is not None:
        return found
    for task in getattr(snapshot, "tasks", ()) or ():
        found = _scan(getattr(task, "interrupts", None))
        if found is not None:
            return found
    return None


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

    memory = MemoryManager.from_config(cfg)
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
            workspace_root=Path.cwd(), builtin_dir=builtin_dir, config=cfg.skills
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
    #: 子智能体预算账本（**父级唯一记账方**，见 ``guardrails/budget_ledger.py``）
    ledger: BudgetLedger
    #: 任务授权窗口（父级权限级别的权威来源，供叶子工具只读）
    authority: TaskAuthority
    #: 任务事件总线（叶子工具内部事件 → SSE 事件流的通道）
    event_bus: TaskEventBus
    service_clients: List[ServiceClient] = field(default_factory=list)
    #: 会话级"永久放行"指纹集合（由 TaskRegistry 持有，跨 resume 存活）
    approval_allowlist: Set[str] = field(default_factory=set)


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
    permission_level: Optional[str] = None,
    approval_allowlist: Optional[Set[str]] = None,
) -> TaskRuntime:
    """装配单个任务的运行时上下文（Spawn 阶段）。

    Args:
        deps: 进程级依赖。
        workspace_id: 工作区标识。
        session_id: 会话标识。
        task_goal: 任务目标。
        task_id: 任务 ID；缺省自动生成。
        permission_level: 会话权限基线；缺省取 ``config.permissions.default_level``。
        approval_allowlist: 会话级永久放行集合（可变引用，由调用方持有）。

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
        permission_level=str(permission_level or cfg.permissions.default_level),
    )

    # 3. 任务级护栏与工具
    guard = PhysicalBudgetGuard.from_config(cfg.runtime.guardrails)
    authority = TaskAuthority(permission_level=str(state.get("permission_level") or ""))
    # 账本与守卫同源上限，保证"父任务已用 + 子智能体消耗"不会因为两套口径而打架
    ledger = BudgetLedger(
        cfg.runtime.guardrails.max_total_tokens,
        max_spawns=int(cfg.subagent.max_spawns_per_task),
        min_grant_tokens=int(cfg.subagent.min_token_budget),
    )
    pruner = ObservationPruner.from_config(
        cfg.runtime.context, cfg.runtime.storage.artifacts_dir, count_tokens
    )
    recorder = TrajectoryRecorder(cfg.runtime.storage.traces_dir, state["task_id"])
    # 事件总线在此创建但**不在此绑定**：本轮的事件回调是 run/resume 的入参，
    # 由 _drive_graph 在执行前绑入（与账本、授权窗口同一套"父级推送"手法）
    event_bus = TaskEventBus(state["task_id"])

    clients = _build_service_clients(cfg)
    # 技能以"目标工程"为工作区根，实现工作区级技能覆盖
    skills = SkillsRegistry.from_workspace(
        workspace_root=workspace.root_path,
        builtin_dir=deps.builtin_skills_dir,
        config=cfg.skills,
    )
    skills.scan()

    # MCP 远端工具：先发现（内部已完成描述消毒），再据此构造显式授权清单。
    # 顺序很重要——授权清单必须先于注册表构造，才能"逐名授权"而不是"开关放行"。
    mcp_adapters: List[MCPToolAdapter] = []
    try:
        for definition in await deps.mcp_manager.list_tools():
            mcp_adapters.append(MCPToolAdapter(definition, deps.mcp_manager, state["task_id"]))
    except Exception as exc:  # noqa: BLE001 - MCP 是增强项，失败必须隔离
        logger.error(f"[Workflow] MCP 工具发现失败，已跳过全部 MCP 工具: {exc}")

    # 主工具表：可信工具全放行；不可信工具（MCP 第三方）**逐名授权**。
    # 网络抓取工具不在其中——它属于研究隔离区，注册进来会直接抛错。
    registry = ToolRegistry(
        allow_untrusted=bool(mcp_adapters),
        untrusted_allowlist={adapter.name for adapter in mcp_adapters} if mcp_adapters else None,
    )
    registry.register_all(
        build_builtin_tools(
            workspace_id=workspace.workspace_id,
            workspace_root=workspace.root_path,
            task_id=state["task_id"],
            rag_client=clients["rag"],
            shell_client=clients["shell"],
            skills=skills,
            bash_timeout_sec=60.0,
        )
    )

    # 研究隔离区：独立注册表 + 允许不可信工具 + 唯一外部信息入口
    if cfg.research.enabled:
        research_tools = ToolRegistry(allow_untrusted=True)
        research_tools.register(
            WebSearchTool(
                clients["web"],
                task_id=state["task_id"],
                default_max_results=int(cfg.research.max_sources),
            )
        )
        registry.register(
            build_research_tool(
                gateway=deps.gateway,
                research_tools=research_tools,
                prompts=deps.prompts,
                config=cfg.research,
                event_bus=event_bus,
            )
        )
    else:
        logger.warning("[Workflow] research 已关闭：主 Agent 不具备任何外部信息能力（离线最安全模式）")

    # 专用代码检索子智能体：多轮检索-判别-换词-提炼
    if cfg.code_search.enabled:
        registry.register(
            build_code_search_tool(
                gateway=deps.gateway,
                rag_tool=clients["rag"],
                prompts=deps.prompts,
                config=cfg.code_search,
                event_bus=event_bus,
            )
        )

    # 已通过描述消毒 + 用户在配置中显式开启的 MCP 工具：逐名授权后进入主工具表
    for adapter in mcp_adapters:
        registry.register(adapter)

    # 动态委派：把"组建受限子劳动力"本身做成一个叶子工具（元工具），图拓扑完全不动。
    # 它持有 registry 的**引用**而非快照副本——收窄校验发生在**派发时刻**，
    # 因此这里传同一对象是有意的，见 13_subagent_delegation.md §2.1。
    if cfg.subagent.enabled:
        registry.register(
            build_subagent_tool(
                gateway=deps.gateway,
                parent_registry=registry,
                prompts=deps.prompts,
                config=cfg.subagent,
                permissions_config=cfg.permissions,
                ledger=ledger,
                authority=authority,
                event_bus=event_bus,
            )
        )
    else:
        logger.warning("[Workflow] subagent 已关闭：主 Agent 不具备动态委派能力")

    logger.info(
        f"[Workflow] 工具表就绪: {len(registry)} 个"
        f"（可信 {len(registry) - len(mcp_adapters)} / 已授权不可信 {len(mcp_adapters)}）"
    )

    context = ContextManager(
        prompts=deps.prompts,
        workspace=workspace,
        workspace_memory=workspace_memory,
        skills=skills,
        tools=registry,
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
        ledger=ledger,
        authority=authority,
        event_bus=event_bus,
        service_clients=list(clients.values()),
        approval_allowlist=approval_allowlist if approval_allowlist is not None else set(),
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
        "planner": build_planner_node(
            deps.gateway,
            task.context,
            deps.prompts,
            task.recorder,
            event_bus=task.event_bus,
        ),
        "budget_guard": build_budget_guard_node(task.guard),
        # executor 只生成 tool_calls（不含 LLM 之外的副作用）
        "executor": build_executor_node(
            deps.gateway,
            task.registry,
            deps.prompts,
            task.context,
            task.recorder,
            event_bus=task.event_bus,
        ),
        # tool_runner 承担权限闸门（人工审批挂起点）+ 并发派发 + 观察值治理 + 预算冲销
        "tool_runner": build_tool_runner_node(
            task.dispatcher,
            task.pruner,
            cfg.runtime.guardrails,
            cfg.permissions,
            ledger=task.ledger,
            authority=task.authority,
            approval_allowlist=task.approval_allowlist,
            recorder=task.recorder,
        ),
        "evaluator": build_evaluator_node(
            deps.gateway,
            task.context,
            deps.prompts,
            task.recorder,
            event_bus=task.event_bus,
        ),
    }
    return build_agent_graph(nodes).compile(checkpointer=deps.checkpoints.saver)


async def _drive_graph(
    deps: RuntimeDeps,
    task: TaskRuntime,
    app: Any,
    graph_input: Optional[Any],
    event_sink: Optional[EventSink] = None,
) -> TaskOutcome:
    """驱动图执行并回收终态。

    使用 ``stream_mode="updates"`` 逐节点推送事件（用于 SSE），
    执行结束后再用 ``aget_state`` 取回**权威终态**——
    避免手工合并增量时漏掉 Reducer 语义（尤其是 ``add_messages``）。

    Args:
        deps: 进程级依赖。
        task: 任务运行时。
        app: 已编译的图。
        graph_input: 初始状态；``None`` 表示从 Checkpoint 续跑；
            亦可是 :class:`~langgraph.types.Command`（如 ``Command(resume=...)`` 提交审批决策）。
        event_sink: 可选事件回调。

    Returns:
        终态 ``AgentState``。
    """
    run_config = {"configurable": {"thread_id": task.state["task_id"]}}
    seq = 0

    # 叶子工具（子智能体）看不到本轮事件回调，因此在这里把 sink 推送给事件总线。
    # 绑定必须在 astream 之前——事件是执行期产生的，晚绑就会丢掉开头的事件。
    if event_sink is not None:
        task.event_bus.bind(event_sink, task.state["task_id"])
    try:
        async for chunk in app.astream(graph_input, run_config, stream_mode="updates"):
            for node_name, delta in (chunk or {}).items():
                if node_name == "__interrupt__":
                    continue
                delta_dict = delta if isinstance(delta, dict) else {}
                seq += 1

                messages_in_delta = delta_dict.get("messages") or []
                raw_milestones = delta_dict.get("milestones") or []
                milestones_in_delta = [
                    m.model_dump()
                    if hasattr(m, "model_dump")
                    else (
                        m
                        if isinstance(m, dict)
                        else {
                            "id": getattr(m, "id", 0),
                            "title": getattr(m, "title", ""),
                            "status": getattr(m, "status", "pending"),
                        }
                    )
                    for m in raw_milestones
                ]

                # 1. 针对具体节点派发精准语义事件
                if node_name == "planner":
                    directive = ""
                    if messages_in_delta and hasattr(messages_in_delta[0], "content"):
                        directive = str(messages_in_delta[0].content)
                    elif messages_in_delta and isinstance(messages_in_delta[0], dict):
                        directive = str(messages_in_delta[0].get("content", ""))

                    is_all_completed = bool(
                        milestones_in_delta
                        and all(m.get("status") == "completed" for m in milestones_in_delta)
                    )
                    step_count = int(delta_dict.get("step_count", task.state.get("step_count", 0)))
                    is_direct_done = is_all_completed and step_count == 0

                    if event_sink is not None:
                        await event_sink(
                            {
                                "event": "plan",
                                "thought": delta_dict.get("thought", directive),
                                "directive": directive,
                                "milestones": milestones_in_delta,
                                "step": seq,
                            }
                        )
                        await event_sink(
                            {
                                "event": "node.finished",
                                "node": "planner",
                                "seq": seq,
                                "input_summary": "接收任务目标与上下文，规划下一步动作与里程碑",
                                "output_summary": f"【直接答复交付】{directive[:200]}" if is_direct_done else f"【规划决策】{directive[:200] if directive else '继续推进当前目标'}",
                                "decision": "reply" if is_direct_done else directive,
                                "content": directive if is_direct_done else None,
                                "step_count": step_count,
                                "total_tokens": int(delta_dict.get("total_tokens", task.state.get("total_tokens", 0))),
                                "should_terminate": is_direct_done,
                                "milestones": milestones_in_delta,
                            }
                        )

                elif node_name == "budget_guard":
                    if event_sink is not None:
                        await event_sink(
                            {
                                "event": "node.finished",
                                "node": "budget_guard",
                                "seq": seq,
                                "input_summary": "物理 Token 消耗与执行步数安全阈值巡检",
                                "output_summary": "【看门狗】预算与循环检测正常，准予进入执行节点",
                                "decision": "pass",
                                "step_count": int(delta_dict.get("step_count", task.state.get("step_count", 0))),
                                "total_tokens": int(delta_dict.get("total_tokens", task.state.get("total_tokens", 0))),
                                "should_terminate": False,
                            }
                        )

                elif node_name == "executor":
                    has_tool_call = False
                    for msg in messages_in_delta:
                        tool_calls = (
                            getattr(msg, "tool_calls", None)
                            or (msg.get("tool_calls") if isinstance(msg, dict) else None)
                            or []
                        )
                        content = (
                            getattr(msg, "content", "")
                            if hasattr(msg, "content")
                            else (msg.get("content", "") if isinstance(msg, dict) else "")
                        )
                        if tool_calls:
                            has_tool_call = True
                            for tc in tool_calls:
                                tc_name = (
                                    tc.get("name")
                                    if isinstance(tc, dict)
                                    else getattr(tc, "name", "tool")
                                )
                                tc_args = (
                                    tc.get("args")
                                    if isinstance(tc, dict)
                                    else getattr(tc, "args", {})
                                )
                                if event_sink is not None:
                                    await event_sink(
                                        {
                                            "event": "tool.call",
                                            "tool": tc_name,
                                            "args": tc_args,
                                            "step": seq,
                                        }
                                    )
                        elif content and event_sink is not None:
                            await event_sink(
                                {
                                    "event": "node.finished",
                                    "node": "executor",
                                    "seq": seq,
                                    "input_summary": "Planner 决策落地为自然语言回复",
                                    "output_summary": f"【直接答复】{content[:200]}",
                                    "decision": "reply",
                                    "content": content,
                                    "step_count": int(
                                        delta_dict.get("step_count", task.state.get("step_count", 0))
                                    ),
                                    "total_tokens": int(
                                        delta_dict.get("total_tokens", task.state.get("total_tokens", 0))
                                    ),
                                    "should_terminate": False,
                                }
                            )
                    if has_tool_call and event_sink is not None:
                        await event_sink(
                            {
                                "event": "node.finished",
                                "node": "executor",
                                "seq": seq,
                                "input_summary": "翻译 Planner 决策为具体工具调用",
                                "output_summary": "【动作生成】已生成工具调用并派发至 tool_runner",
                                "decision": "call_tools",
                                "step_count": int(
                                    delta_dict.get("step_count", task.state.get("step_count", 0))
                                ),
                                "total_tokens": int(
                                    delta_dict.get("total_tokens", task.state.get("total_tokens", 0))
                                ),
                                "should_terminate": False,
                            }
                        )

                elif node_name == "tool_runner":
                    for msg in messages_in_delta:
                        t_name = (
                            getattr(msg, "name", None)
                            or (msg.get("name") if isinstance(msg, dict) else "tool")
                        )
                        t_content = (
                            getattr(msg, "content", "")
                            if hasattr(msg, "content")
                            else (msg.get("content", "") if isinstance(msg, dict) else "")
                        )
                        if event_sink is not None:
                            await event_sink(
                                {
                                    "event": "tool.result",
                                    "tool": t_name or "tool",
                                    "result": t_content[:500],
                                    "step": seq,
                                }
                            )
                    if event_sink is not None:
                        await event_sink(
                            {
                                "event": "node.finished",
                                "node": "tool_runner",
                                "seq": seq,
                                "input_summary": "执行工作区受限工具派发与权限校验",
                                "output_summary": "【工具执行完成】结果已回填至状态机上下文",
                                "decision": "executed",
                                "step_count": int(
                                    delta_dict.get("step_count", task.state.get("step_count", 0))
                                ),
                                "total_tokens": int(
                                    delta_dict.get("total_tokens", task.state.get("total_tokens", 0))
                                ),
                                "should_terminate": False,
                            }
                        )

                elif node_name == "evaluator":
                    summary = str(delta_dict.get("rolling_summary", "") or "")
                    should_term = bool(delta_dict.get("should_terminate", False))
                    term_reason = str(delta_dict.get("termination_reason", ""))
                    completed_count = sum(
                        1 for m in milestones_in_delta if m.get("status") == "completed"
                    )
                    total_count = len(milestones_in_delta)
                    if event_sink is not None:
                        await event_sink(
                            {
                                "event": "node.finished",
                                "node": "evaluator",
                                "seq": seq,
                                "input_summary": f"复核阶段达成情况 (里程碑 {completed_count}/{total_count})",
                                "output_summary": f"【验收结论】{'验收通过，准予交付' if should_term else '尚未收敛，继续推进'}。{summary or term_reason}",
                                "decision": "accepted" if should_term else "continue",
                                "step_count": int(
                                    delta_dict.get("step_count", task.state.get("step_count", 0))
                                ),
                                "total_tokens": int(
                                    delta_dict.get("total_tokens", task.state.get("total_tokens", 0))
                                ),
                                "should_terminate": should_term,
                                "milestones": milestones_in_delta,
                            }
                        )
    finally:
        task.event_bus.unbind()

    snapshot = await app.aget_state(run_config)
    final_state: AgentState = dict(snapshot.values)  # type: ignore[assignment]
    approval = _extract_pending_approval(snapshot)

    logger.info(
        f"[Workflow] 任务 {task.state['task_id']} "
        f"{'挂起等待审批' if approval else '执行结束'}: "
        f"步数={final_state.get('step_count')} Token={final_state.get('total_tokens')} "
        f"原因={final_state.get('termination_reason') or '（未标注）'}"
    )
    return TaskOutcome(state=final_state, approval_request=approval)


async def run_streaming(
    deps: RuntimeDeps,
    *,
    workspace_id: str,
    session_id: str,
    task_goal: str,
    task_id: Optional[str] = None,
    permission_level: Optional[str] = None,
    approval_allowlist: Optional[Set[str]] = None,
    event_sink: Optional[EventSink] = None,
) -> TaskOutcome:
    """提交并执行一个新任务（支持流式事件回调）。

    Args:
        deps: 进程级依赖。
        workspace_id: 工作区标识。
        session_id: 会话标识。
        task_goal: 任务目标。
        task_id: 任务 ID（由调用方预分配，便于先返回给客户端）。
        permission_level: 会话权限基线。
        approval_allowlist: 会话级永久放行集合。
        event_sink: 事件回调（SSE 推送）。

    Returns:
        :class:`TaskOutcome`。
    """
    task = await prepare_task(
        deps,
        workspace_id=workspace_id,
        session_id=session_id,
        task_goal=task_goal,
        task_id=task_id,
        permission_level=permission_level,
        approval_allowlist=approval_allowlist,
    )
    app = _compile_app(deps, task)

    try:
        outcome = await _drive_graph(deps, task, app, task.state, event_sink)
    finally:
        for client in task.service_clients:
            await client.aclose()

    # 挂起等待审批时**不**做交付收尾：任务尚未结束，会话记忆不应记入未完成的结论
    if not outcome.waiting_for_approval:
        await task.lifecycle.finalize(
            outcome.state,
            ExecutionContextManager.extract_delivery(outcome.state),
        )
    return outcome


async def run_agent(
    deps: RuntimeDeps,
    *,
    workspace_id: str,
    session_id: str,
    task_goal: str,
    task_id: Optional[str] = None,
) -> AgentState:
    """同步等待任务完成（无事件流），返回终态状态。"""
    outcome = await run_streaming(
        deps,
        workspace_id=workspace_id,
        session_id=session_id,
        task_goal=task_goal,
        task_id=task_id,
    )
    return outcome.state


async def resume_agent(
    deps: RuntimeDeps,
    *,
    task_id: str,
    workspace_id: str,
    session_id: str,
    task_goal: str,
    approval_decision: Optional[Mapping[str, Any]] = None,
    approval_allowlist: Optional[Set[str]] = None,
    event_sink: Optional[EventSink] = None,
) -> TaskOutcome:
    """从最近一次 Checkpoint 续跑任务（亦用于提交人工审批决策）。

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
        approval_decision: 审批决策（``{"approved": bool, "scope": "once|always", "reason": str}``）。
            为 ``None`` 时按普通断点续跑处理。
        approval_allowlist: 会话级永久放行集合。
        event_sink: 事件回调。

    Returns:
        :class:`TaskOutcome`。
    """
    task = await prepare_task(
        deps,
        workspace_id=workspace_id,
        session_id=session_id,
        task_goal=task_goal,
        task_id=task_id,
        approval_allowlist=approval_allowlist,
    )
    app = _compile_app(deps, task)

    # 有决策 → Command(resume=...) 让被挂起的 interrupt() 返回该值；
    # 无决策 → None，表示纯粹的断点续跑
    graph_input: Optional[Any] = (
        Command(resume=dict(approval_decision)) if approval_decision is not None else None
    )

    try:
        outcome = await _drive_graph(deps, task, app, graph_input, event_sink)
    finally:
        for client in task.service_clients:
            await client.aclose()

    if not outcome.waiting_for_approval:
        await task.lifecycle.finalize(
            outcome.state,
            ExecutionContextManager.extract_delivery(outcome.state),
        )
    return outcome
