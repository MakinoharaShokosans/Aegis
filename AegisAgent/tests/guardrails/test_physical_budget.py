"""PhysicalBudgetGuard 单元测试。"""

import time
import pytest
from agent_runtime.guardrails.physical_budget import PhysicalBudgetGuard, WARNING_RATIO


def test_physical_budget_normal_state():
    """测试预算未超限时的正常状态。"""
    guard = PhysicalBudgetGuard(
        max_steps=10,
        max_total_tokens=10000,
        max_wall_time_sec=60.0,
        start_time=time.time(),
    )
    state = {"step_count": 3, "total_tokens": 2000}

    terminated, reason = guard.check(state)
    assert not terminated
    assert reason is None

    warnings = guard.warnings(state)
    assert len(warnings) == 0


def test_physical_budget_step_limit_exceeded():
    """测试步数达到硬上限触发熔断。"""
    guard = PhysicalBudgetGuard(
        max_steps=5,
        max_total_tokens=10000,
        max_wall_time_sec=60.0,
    )
    state = {"step_count": 5, "total_tokens": 1000}

    terminated, reason = guard.check(state)
    assert terminated
    assert "步数达上限" in reason
    assert "5" in reason


def test_physical_budget_token_limit_exceeded():
    """测试累计 Token 达到硬上限触发熔断。"""
    guard = PhysicalBudgetGuard(
        max_steps=10,
        max_total_tokens=5000,
        max_wall_time_sec=60.0,
    )
    state = {"step_count": 2, "total_tokens": 5001}

    terminated, reason = guard.check(state)
    assert terminated
    assert "Token 达上限" in reason
    assert "5000" in reason


def test_physical_budget_wall_time_exceeded():
    """测试挂钟时间耗尽触发熔断。"""
    # 模拟起点在 100 秒前
    start_time = time.time() - 100.0
    guard = PhysicalBudgetGuard(
        max_steps=10,
        max_total_tokens=10000,
        max_wall_time_sec=60.0,
        start_time=start_time,
    )
    state = {"step_count": 1, "total_tokens": 100}

    terminated, reason = guard.check(state)
    assert terminated
    assert "物理运行时间耗尽" in reason


def test_physical_budget_warnings_threshold():
    """测试达到 90% 阈值时产生软告警但不熔断。"""
    guard = PhysicalBudgetGuard(
        max_steps=10,
        max_total_tokens=10000,
        max_wall_time_sec=100.0,
        start_time=time.time() - 92.0,  # 92 秒，已达 90%
    )
    state = {
        "step_count": 9,      # 9/10 = 90%
        "total_tokens": 9500, # 9500/10000 = 95%
    }

    # 检查熔断：未达到 100%，因此不熔断
    terminated, reason = guard.check(state)
    assert not terminated
    assert reason is None

    # 检查软告警：三项均达 90% 预警线
    alerts = guard.warnings(state)
    assert len(alerts) == 3
    assert any("步数告警" in a for a in alerts)
    assert any("Token 告警" in a for a in alerts)
    assert any("时间告警" in a for a in alerts)
