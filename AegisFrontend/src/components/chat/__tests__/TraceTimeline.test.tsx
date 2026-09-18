import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TraceTimeline } from '../TraceTimeline';
import type { TraceStep } from '@/types';

describe('TraceTimeline', () => {
  it('renders empty state placeholder when steps array is empty', () => {
    render(<TraceTimeline steps={[]} />);
    expect(screen.getByText('暂无执行轨迹 (No Active Trace)')).toBeInTheDocument();
    expect(
      screen.getByText('启动任务后，此处将实时呈现 LangGraph 状态机跃迁流水、受限工具调用细节与节点决策结果。')
    ).toBeInTheDocument();
  });

  it('renders full LangGraph state machine node transitions, tool calls, and decisions', () => {
    const mockSteps: TraceStep[] = [
      {
        id: 'step-1',
        node: 'planner',
        step: 1,
        inputSummary: '接收任务目标: "重构登录鉴权模块"',
        outputSummary: '【规划决策】拆分为：1. 检查 contracts/auth.md；2. 实现 token 签发；3. 运行单元测试',
        decision: '拆解为3个里程碑并派发执行',
        durationMs: 120,
        tokenUsage: 1250,
        timestamp: '14:30:01',
      },
      {
        id: 'step-2',
        node: 'budget_guard',
        step: 2,
        inputSummary: '物理 Token 与步数阈值安全巡检',
        outputSummary: '【看门狗】预算正常（当前 1,250 / 32,000），准予放行',
        decision: 'pass',
        durationMs: 5,
        tokenUsage: 1250,
        timestamp: '14:30:02',
      },
      {
        id: 'step-3',
        node: 'executor',
        step: 3,
        inputSummary: '翻译 Planner 指令为具体工具调用',
        outputSummary: '【动作生成】已生成 read_file 工具调用',
        decision: 'call_tools',
        durationMs: 80,
        tokenUsage: 1420,
        timestamp: '14:30:03',
      },
      {
        id: 'step-4',
        node: 'tool_runner',
        step: 4,
        tool: 'read_file',
        toolArgs: { path: 'documents/contracts/auth.md' },
        toolResult: 'JWT Token 格式规范：Bearer <token>',
        inputSummary: '准备调用受限工具: read_file',
        outputSummary: '返回产物: JWT Token 格式规范：Bearer <token>',
        durationMs: 45,
        tokenUsage: 1580,
        timestamp: '14:30:04',
      },
      {
        id: 'step-5',
        node: 'evaluator',
        step: 5,
        inputSummary: '复核阶段达成情况 (里程碑 1/3)',
        outputSummary: '【验收结论】尚未收敛，继续推进下一阶段实现',
        decision: 'continue',
        durationMs: 60,
        tokenUsage: 1750,
        timestamp: '14:30:05',
      },
    ];

    const { container } = render(<TraceTimeline steps={mockSteps} />);

    // Check header and step count
    expect(screen.getByText('LangGraph 状态机流转与因果时序流水')).toBeInTheDocument();
    expect(screen.getByText('共 5 个轨迹步')).toBeInTheDocument();

    // Check all node names rendered
    expect(screen.getByText(/Step #1: Planner/)).toBeInTheDocument();
    expect(screen.getByText(/Step #2: BudgetGuard/)).toBeInTheDocument();
    expect(screen.getByText(/Step #3: Executor/)).toBeInTheDocument();
    expect(screen.getByText(/Step #4: ToolRunner/)).toBeInTheDocument();
    expect(screen.getByText(/Step #5: Evaluator/)).toBeInTheDocument();

    // Check tool name and args
    expect(screen.getByText('read_file')).toBeInTheDocument();
    expect(screen.getByText(/documents\/contracts\/auth\.md/)).toBeInTheDocument();
    expect(screen.getByText(/JWT Token 格式规范/)).toBeInTheDocument();

    // Check decisions rendered
    expect(screen.getByText(/规划决策与指令 \(Planner Decision\):/)).toBeInTheDocument();
    expect(screen.getByText(/验收结论与收敛判定 \(Evaluator Verdict\):/)).toBeInTheDocument();

    // Verify zero emoji characters in text content
    const textContent = container.textContent || '';
    const emojiRegex = /[\u{1F000}-\u{1FAFF}\u{2300}-\u{23FF}\u{2600}-\u{27BF}]/u;
    expect(emojiRegex.test(textContent)).toBe(false);
  });
});
