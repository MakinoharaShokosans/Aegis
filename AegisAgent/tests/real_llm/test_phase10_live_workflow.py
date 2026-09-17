"""Phase 10: 真实端到端工作流闭环与 AgentBench 评测基线 (Phase 10)。

对应 `documents/深度测试路线.md` §3 (Phase 10)。
运行真实端到端多步自主任务，验证 planner-executor-tool_runner-evaluator 全链路真实自主收敛，
并将真实运行轨迹接入 evaluation/agent_bench/runner.py 产出首份真实基线评测报告。

预估消耗：约 8~12 次模型交互。
"""

from pathlib import Path
import pytest

from agent_runtime.workflow import run_streaming
from evaluation.agent_bench.runner import run_benchmark


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_live_workflow_e2e_and_agent_bench_baseline(live_deps, tmp_path: Path):
    """10.1 & 10.2 & 10.3 真实端到端任务执行，验证产物落盘与自主收敛，并运行 AgentBench 生成基线。"""
    deps = live_deps
    task_id = "live_task_math_001"
    workspace_id = "ws_live_001"
    session_id = "sess_live_001"
    task_goal = "在工作区根目录下创建 math_utils.py 并实现 add(a, b) 函数，然后使用 view_file 查看确认内容无误。"

    events = []

    async def event_sink(event):
        events.append(event)

    # 1. 运行真实工作流
    outcome = await run_streaming(
        deps,
        workspace_id=workspace_id,
        session_id=session_id,
        task_goal=task_goal,
        task_id=task_id,
        permission_level="workspace_write",
        event_sink=event_sink,
    )

    # 2. 结构级与产物级断言
    state = outcome.state
    assert not outcome.waiting_for_approval
    assert state.get("step_count", 0) > 0
    assert state.get("total_tokens", 0) > 0

    # 验证物理文件确实生成在工作区中
    created_file = tmp_path / "workspaces" / workspace_id / "math_utils.py"
    assert created_file.exists(), f"预期文件 math_utils.py 未生成在 {created_file}"
    content = created_file.read_text(encoding="utf-8")
    assert "def add" in content or "add" in content

    # 3. 运行 AgentBench 评测 harness 产生基线报告
    traces_dir = deps.config.runtime.storage.traces_dir
    report = run_benchmark(traces_dir)

    assert report["num_tasks"] >= 1
    assert report["task_completion_rate"] is not None
    assert "per_task" in report

    # 打印格式化基线报告
    from evaluation.agent_bench.runner import render_report
    rendered = render_report(report)
    print("\n" + "=" * 40 + " AGENT BENCH 基线评测报告 " + "=" * 40)
    print(rendered)
    print("=" * 102)


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_live_workflow_error_recovery(live_deps, tmp_path: Path):
    """10.4 验证真实模型在遇到工具初始报错时的错误分析与自愈调整能力 (Error Recovery Rate)。"""
    deps = live_deps
    task_id = "live_task_recovery_002"
    workspace_id = "ws_live_002"
    session_id = "sess_live_002"
    task_goal = "使用 view_file 尝试查看 nonexistent_config.json 文件；若文件不存在，则使用 write_file 创建 fallback_config.json 写入 {'mode': 'safe'}。"

    outcome = await run_streaming(
        deps,
        workspace_id=workspace_id,
        session_id=session_id,
        task_goal=task_goal,
        task_id=task_id,
        permission_level="workspace_write",
    )

    state = outcome.state
    # 验证未被连续错误熔断强杀
    assert not state.get("should_terminate", False) or state.get("termination_reason") == "task_goal achieved"

    # 验证自愈产物 fallback_config.json 存在
    fallback_file = tmp_path / "workspaces" / workspace_id / "fallback_config.json"
    assert fallback_file.exists(), "模型在读取失败后未能自愈创建 fallback_config.json"
