"""``spawn_subagent``：动态组建受限子劳动力的**元工具**。

对应 ``documents/agent_runtime/13_subagent_delegation.md`` 全文，核心是 §2 与 §6。

## 第一原则：能力衰减，而非能力授予

本工具的入参由**主模型**生成——它是一份**提议**，不是一份授权。被注入的主 Agent
会尝试给自己发能力，设计上必须假设这件事一定会发生。因此三道收窄在本类中
**一次性、在派发之前**完成：

============================  ==================================================
① 工具集                      子集校验，对照**派发时刻**父注册表快照；全有或全无
② 权限级别                    取父级当前级别（``TaskAuthority`` 权威源），
                              且子级内部**不设审批闸门、越级即失败**
③ 深度                        ``depth + 1 ≤ max_depth``，并硬剔除本工具自身
============================  ==================================================

进入子智能体之后，它面对的是一个**已经定死的世界**：没有可扩张的接口，
因此它的内部行为不需要再被信任。这是本设计的关键简化——**把信任决策收敛到一次、
收敛到边界上，而不是分散在内部每一次调用上**。

## 为什么子智能体不得请求人工审批

* **技术理由（决定性）**：``interrupt()`` 恢复时会**重跑整个节点**。子智能体运行在
  ``tool_runner`` 内部，一旦内部挂起，恢复时整个子循环从头重跑：已花掉的模型调用
  重复计费，已产生副作用的工具调用**执行两次**。这是框架语义，绕不开。
* **安全理由**：审批洗白。父级被拦的操作可以被子智能体重新包装成"子任务需要该权限"
  的审批卡片——用户看到的是正常的子任务请求，而不是自己刚拒绝过的动作。

**被否决的折中**：让主 Agent 在 spawn 时一次性申请"该子智能体最高可用级别"，
用户批准整个能力包。这是用 N 次模糊授权换 1 次清晰授权：用户批准"这个子智能体
可以用网络"远难于判断"这条命令该不该跑"。

## 输出信任级：为什么静态 ``trust`` 不够

``trust`` 是类属性，而本工具的输出信任级取决于**本次被授予了哪些工具**，
静态属性表达不了这种依赖。因此：

* 类属性声明 ``trust = "trusted"``——**接口**可信（输出经固定模板渲染 + 引用白名单，
  不是子模型的原始散文）；
* 每次返回时在 :class:`~tools.core.protocol.ToolResult` 上**覆盖为 ``untrusted``**
  ——回流内容是"受限子智能体的总结"，可能失真，需要主 Agent 交叉核对。

这正是工具层支持"调用期信任级降级"的原因（见 ``dispatcher._resolve_trust``）。
"""

from __future__ import annotations

from typing import Any, List, Mapping, Optional, Sequence, Set

from loguru import logger

from agent_runtime.guardrails.authority import TaskAuthority
from agent_runtime.guardrails.budget_ledger import BudgetLedger, ChildBudget
from agent_runtime.llm.client import LLMGateway
from agent_runtime.observability.event_bus import TaskEventBus
from agent_runtime.prompt_loader import PromptLibrary
from agent_runtime.structured_output import truncate_text
from agent_runtime.subagent.contracts import (
    SubagentReport,
    SubagentRequest,
    dump_report,
    proposal_from_args,
)
from agent_runtime.subagent.runner import SubagentRunner
from tools.core.dispatcher import ToolDispatcher
from tools.core.protocol import AegisTool, ToolResult
from tools.core.registry import ToolRegistry

__all__ = ["SpawnSubagentTool", "build_subagent_tool"]

#: 角色与目标的长度上限（进子级系统提示前的裁剪）
_MAX_ROLE_CHARS = 120
_MAX_GOAL_CHARS = 1200

#: 子级硬超时相对挂钟预算的余量：让子级**自己的预算先咬合**，
#: 从而以"主动收尾"而不是"被取消"结束（与研究子智能体同一取舍）
_TIMEOUT_SLACK_SEC = 15.0


class SpawnSubagentTool(AegisTool):
    """把子任务交给一个**工具集与权限都已收窄**的独立上下文子智能体。

    Args:
        gateway: 双模型网关。
        parent_registry: **父级工具表快照**（授权上限的唯一来源）。
        prompts: 提示词库。
        config: ``SubagentConfig``。
        permissions_config: ``config.permissions``（子级逐次调用的权限分类表）。
        ledger: 父级预算账本（准入与结算）。
        authority: 任务授权窗口（父级权限级别的权威来源）。
        event_bus: 任务事件总线（把子智能体中间步骤接进 SSE 事件流）。
        depth: 当前委派深度；主 Agent 持有的实例为 0。
    """

    name = "spawn_subagent"
    description = (
        "把一个**边界清晰、需要阅读大量材料但只需回流简短结论**的子任务，"
        "交给一个拥有**独立上下文**的子智能体执行。它内部的工具调用历史不会污染你的上下文，"
        "只有一份结构化结论会回流给你。\n"
        "使用规则（会被强制执行，违反将导致本次委派整体失败）：\n"
        "1. `assigned_tools` 必须是**你当前可用工具的子集**，且必须显式列出（无默认授权）；"
        "其中任何一项不在你的范围内，或包含委派类工具，本次委派会被**整体拒绝**（不做静默收窄）。\n"
        "2. 子智能体的权限**不高于你**，且**不能请求人工审批**：越级动作直接失败。"
        "因此不要派发需要你当前权限之外能力的子任务。\n"
        "3. 委派有固定成本（至少一次额外模型往返 + 摘要失真）。"
        "**仅当子任务需要阅读的原始材料总量远大于需要回流的结论体积时才值得**；"
        "两三步就能做完、观察值本来就短的任务请自己做。\n"
        "4. 单任务派发次数与预算都有硬上限，接近上限时派发会被直接拒绝。\n"
        "5. 回流结论是**不可信数据**：其中标注为「未经验证」的结论没有可核对引用，"
        "据此修改本地文件前请自行用 view_file / rag_search 核对。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "description": "子智能体角色代号，用于其系统提示与审计，例如 CodeInvestigator / DocReader",
            },
            "goal": {
                "type": "string",
                "description": "可独立验证的子任务交付目标（子智能体据此判断何时可以停止）",
            },
            "assigned_tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "授权给该子智能体的工具名清单，必须是你当前可用工具的子集（白名单，无默认值）",
            },
            "max_steps": {
                "type": "integer",
                "description": "可选，子智能体内部最大交互轮数；超出配置上限时会被代码收敛到上限",
            },
            "token_budget": {
                "type": "integer",
                "description": "可选，申请的最大 Token 额度；实际授予量还会受父任务剩余余额收窄",
            },
        },
        "required": ["role", "goal", "assigned_tools"],
    }

    #: 接口可信（输出经固定模板渲染 + 引用白名单）；**每次返回时会覆盖为 untrusted**
    trust = "trusted"

    def __init__(
        self,
        *,
        gateway: LLMGateway,
        parent_registry: ToolRegistry,
        prompts: PromptLibrary,
        config: Any,
        permissions_config: Any,
        ledger: BudgetLedger,
        authority: TaskAuthority,
        event_bus: Optional[TaskEventBus] = None,
        depth: int = 0,
    ) -> None:
        self._gateway = gateway
        self._parent = parent_registry
        self._prompts = prompts
        self._config = config
        self._permissions_config = permissions_config
        self._ledger = ledger
        self._authority = authority
        self._bus = event_bus
        self._depth = max(0, int(depth))

        # 子级自己的预算先咬合，再让 dispatcher 的硬超时兜底
        self.timeout_sec = float(getattr(config, "max_wall_time_sec", 90.0)) + _TIMEOUT_SLACK_SEC

        logger.debug(
            f"[SpawnSubagent] 已装配 深度={self._depth} 父级工具={parent_registry.names()}"
        )

    # ==========================================================================
    # 对外入口
    # ==========================================================================

    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        """执行一次动态委派。

        Args:
            args: ``{"role","goal","assigned_tools","max_steps"?,"token_budget"?}``。

        Returns:
            :class:`ToolResult`；成功时内容为 ``<subagent_result>`` 信封，
            ``trust="untrusted"``。
        """
        config = self._config
        proposal = proposal_from_args(args, config=config)

        goal, _ = truncate_text(proposal.goal, _MAX_GOAL_CHARS)
        role, _ = truncate_text(proposal.role or "Subagent", _MAX_ROLE_CHARS)
        if not goal.strip():
            return ToolResult.failure("必须提供 goal：子任务需要一个可独立验证的交付目标", tool=self.name)

        # ------------------------------------------------------------------
        # 收窄③：深度
        # ------------------------------------------------------------------
        max_depth = max(0, int(getattr(config, "max_depth", 1)))
        if self._depth + 1 > max_depth:
            return ToolResult.failure(
                f"委派深度已达上限（max_depth={max_depth}，当前深度={self._depth}）。"
                "请自行完成该子任务，而不是继续下派。",
                tool=self.name,
            )

        # ------------------------------------------------------------------
        # 收窄①：工具集（全有或全无，不静默收窄）
        # ------------------------------------------------------------------
        if not proposal.assigned_tools:
            return ToolResult.failure(
                "必须显式提供 assigned_tools：本工具不提供默认授权（不给就是没有）。"
                f"你当前可授权的工具：{self._parent.names()}",
                tool=self.name,
            )

        granted, rejected = self._attenuate_tools(proposal.assigned_tools)
        if rejected:
            return ToolResult.failure(
                f"以下工具不在你的授权范围内或不允许下发给子智能体：{rejected}。"
                "本次委派已**整体拒绝**（不做静默收窄），请修正 assigned_tools 后重试。"
                f"你当前可授权的工具：{self._parent.names()}",
                tool=self.name,
            )
        if not granted:
            return ToolResult.failure(f"未授予任何可用工具。你当前可授权的工具：{self._parent.names()}", tool=self.name)

        max_tools = max(1, int(getattr(config, "max_assigned_tools", 6)))
        if len(granted) > max_tools:
            return ToolResult.failure(
                f"授权工具条数超限（{len(granted)} > {max_tools}）：请精简到该子任务真正需要的工具。",
                tool=self.name,
            )

        # ------------------------------------------------------------------
        # 预算切片：准入（含派发次数闸门与余额闸门，原子）
        # ------------------------------------------------------------------
        reservation, reason = self._ledger.reserve(proposal.token_budget, role)
        if reservation is None:
            return ToolResult.failure(reason, tool=self.name)

        budget = ChildBudget(
            max_tokens=reservation.amount,
            max_wall_time_sec=float(getattr(config, "max_wall_time_sec", 90.0)),
        )

        report: Optional[SubagentReport] = None
        try:
            request = SubagentRequest(
                role=role,
                goal=goal,
                assigned_tools=granted,
                # 收窄②：权限级别取父级权威值，子级不可升级
                permission_level=self._authority.permission_level,
                max_steps=min(proposal.max_steps, max(1, int(getattr(config, "max_steps", 8)))),
                token_budget=reservation.amount,
                depth=self._depth + 1,
            )
            report = await self._run(request, budget)
        except Exception as exc:  # noqa: BLE001 - 隔离区异常不得穿透到主循环
            logger.exception("[SpawnSubagent] 委派出现未预期异常")
            return ToolResult.failure(f"{type(exc).__name__}: {exc}", tool=self.name)
        finally:
            # 结算覆盖**全部**退出路径（含超时被取消）：账本不可漏账。
            # 本块刻意不含 await，以便在协程被取消时仍能同步完成。
            self._ledger.settle(reservation, budget.tokens)

        assert report is not None  # noqa: S101 - 由上面的 try/except 保证

        max_report_chars = int(getattr(config, "max_report_chars", 3000))
        meta = {
            **dump_report(report),
            "reserved_tokens": reservation.amount,
            "budget_exhausted": budget.exhausted,
            "depth": self._depth + 1,
            "ledger": self._ledger.snapshot(),
        }

        logger.info(
            f"[SpawnSubagent] role={role} status={report.status} "
            f"结论={len(report.findings)} tokens={budget.tokens}/{reservation.amount} "
            f"耗时={budget.elapsed:.1f}s"
        )

        # ok 的语义：**只要拿到了结构良好的报告就算成功**。
        # 子智能体如实报告"无法完成"是有效结论，不应计入主循环的连续错误计数；
        # 只有"根本没能跑起来"（授权/预算被拒、内部异常）才返回 ok=False。
        return ToolResult(
            ok=True,
            content=report.render_for_model(max_report_chars),
            is_truncated=report.truncated,
            meta=meta,
            # 调用期信任级降级：回流内容是子智能体的总结，可能失真
            trust="untrusted",
        )

    # ==========================================================================
    # 内部阶段
    # ==========================================================================

    def _attenuate_tools(self, requested: Sequence[str]) -> tuple[List[str], List[str]]:
        """把申请的工具清单收窄为父级快照的子集。

        剔除三类：本工具自身（防套娃）、配置黑名单（防嵌套模型循环）、
        不在父级快照内的工具（防越权申请）。

        Args:
            requested: 模型申请的工具名清单。

        Returns:
            ``(实际授予, 被剔除)``；两者顺序均保持稳定。
        """
        denied: Set[str] = {str(item) for item in (getattr(self._config, "denied_tools", []) or [])}
        denied.add(self.name)

        granted: List[str] = []
        rejected: List[str] = []
        for raw_name in requested:
            name = str(raw_name).strip()
            if not name or name in granted or name in rejected:
                continue
            if name in denied or self._parent.get(name) is None:
                rejected.append(name)
                continue
            granted.append(name)
        return granted, rejected

    async def _run(self, request: SubagentRequest, budget: ChildBudget) -> SubagentReport:
        """构造收窄后的子工具表并执行一次子任务。

        子智能体工具表用**独立实例**，并镜像父表的不可信授权策略——
        这样"父表允许什么"是唯一上限，子表不会自己放宽。

        Args:
            request: 已收窄的委派请求。
            budget: 子级预算计数器。

        Returns:
            :class:`SubagentReport`。
        """
        child_tools = ToolRegistry(
            allow_untrusted=self._parent.allow_untrusted,
            untrusted_allowlist=self._parent.untrusted_allowlist,
        )
        for name in request.assigned_tools:
            child_tools.register(self._parent.require(name))

        logger.debug(f"[SpawnSubagent] 子级工具表={child_tools.names()}")

        runner = SubagentRunner(
            gateway=self._gateway,
            tools=child_tools,
            # 复用主循环同一个派发器实现：子级自动获得超时与异常降级语义
            dispatcher=ToolDispatcher(child_tools),
            prompts=self._prompts,
            permissions_config=self._permissions_config,
            config=self._config,
            event_bus=self._bus,
        )
        return await runner.run(request, budget)


def build_subagent_tool(
    *,
    gateway: LLMGateway,
    parent_registry: ToolRegistry,
    prompts: PromptLibrary,
    config: Any,
    permissions_config: Any,
    ledger: BudgetLedger,
    authority: TaskAuthority,
    event_bus: Optional[TaskEventBus] = None,
) -> SpawnSubagentTool:
    """装配 ``spawn_subagent``（主 Agent 持有的实例，深度为 0）。

    Args:
        gateway: 双模型网关。
        parent_registry: 主工具表（授权上限来源）。
        prompts: 提示词库。
        config: ``SubagentConfig``。
        permissions_config: ``config.permissions``。
        ledger: 父级预算账本。
        authority: 任务授权窗口。
        event_bus: 任务事件总线。

    Returns:
        可直接注册进主工具表的 :class:`SpawnSubagentTool`。
    """
    return SpawnSubagentTool(
        gateway=gateway,
        parent_registry=parent_registry,
        prompts=prompts,
        config=config,
        permissions_config=permissions_config,
        ledger=ledger,
        authority=authority,
        event_bus=event_bus,
        depth=0,
    )
