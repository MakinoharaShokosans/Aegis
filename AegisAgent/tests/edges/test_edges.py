"""条件边路由逻辑单元测试 (route_after_* 纯函数决策)。"""

from types import SimpleNamespace
from langgraph.graph import END

from agent_runtime.edges.after_planner import route_after_planner
from agent_runtime.edges.after_budget_guard import route_after_budget_guard
from agent_runtime.edges.after_executor import route_after_executor
from agent_runtime.edges.after_tool_runner import route_after_tool_runner
from agent_runtime.edges.after_evaluator import route_after_evaluator


def test_route_after_planner():
    """测试 planner 节点的路由决策。"""
    # 1. 硬熔断直接去往 END
    state_terminated = {
        "should_terminate": True,
        "termination_reason": "LLM 认证失败",
    }
    assert route_after_planner(state_terminated) == END

    # 2. 里程碑已全部完成 -> 若执行过工具(step_count > 0)进入 evaluator 复核；若无工具执行(step_count == 0)直接交付到 END
    state_all_done_with_steps = {
        "should_terminate": False,
        "step_count": 1,
        "milestones": [
            SimpleNamespace(status="completed"),
            SimpleNamespace(status="completed"),
        ],
    }
    assert route_after_planner(state_all_done_with_steps) == "evaluator"

    state_direct_done = {
        "should_terminate": False,
        "step_count": 0,
        "milestones": [
            SimpleNamespace(status="completed"),
        ],
    }
    assert route_after_planner(state_direct_done) == END

    # 3. 里程碑部分完成或为空 -> 前往 budget_guard 继续执行主循环
    state_in_progress = {
        "should_terminate": False,
        "milestones": [
            SimpleNamespace(status="completed"),
            SimpleNamespace(status="pending"),
        ],
    }
    assert route_after_planner(state_in_progress) == "budget_guard"

    state_empty_milestones = {
        "should_terminate": False,
        "milestones": [],
    }
    assert route_after_planner(state_empty_milestones) == "budget_guard"


def test_route_after_budget_guard():
    """测试 budget_guard 节点的路由决策。"""
    # 1. 预算守卫触发熔断
    state_terminated = {
        "should_terminate": True,
        "termination_reason": "超过最大步数上限",
    }
    assert route_after_budget_guard(state_terminated) == END

    # 2. 正常放行至 executor
    state_ok = {"should_terminate": False}
    assert route_after_budget_guard(state_ok) == "executor"


def test_route_after_executor():
    """测试 executor 节点的路由决策。"""
    from langchain_core.messages import AIMessage

    # 1. 致命错误熔断
    state_terminated = {
        "should_terminate": True,
        "termination_reason": "致命工具异常",
    }
    assert route_after_executor(state_terminated) == END

    # 2. 产生工具调用 -> 进入 tool_runner 执行派发
    state_with_tools = {
        "should_terminate": False,
        "messages": [AIMessage(content="调用工具", tool_calls=[{"id": "call_1", "name": "bash", "args": {}}])],
    }
    assert route_after_executor(state_with_tools) == "tool_runner"

    # 3. 未产生工具调用（直接文本答复/无工具需求）-> 进入 evaluator 验收与收敛
    state_no_tools = {
        "should_terminate": False,
        "messages": [AIMessage(content="你好！请问有什么我可以帮您？")],
    }
    assert route_after_executor(state_no_tools) == "evaluator"


def test_route_after_tool_runner():
    """测试 tool_runner 节点的路由决策。"""
    # 1. 硬熔断直接去往 END
    state_terminated = {
        "should_terminate": True,
        "termination_reason": "安全熔断",
    }
    assert route_after_tool_runner(state_terminated) == END

    # 2. 正常流转（含工具成功、工具被拒绝、指纹死循环拦截）-> 回流 planner
    state_ok = {"should_terminate": False}
    assert route_after_tool_runner(state_ok) == "planner"


def test_route_after_evaluator():
    """测试 evaluator 节点的路由决策。"""
    # 1. 验收通过，交付并结束任务
    state_done = {
        "should_terminate": True,
        "termination_reason": "全部里程碑验收合格",
    }
    assert route_after_evaluator(state_done) == END

    # 2. 验收不合格，打回 planner 重新修正
    state_rejected = {
        "should_terminate": False,
    }
    assert route_after_evaluator(state_rejected) == "planner"

