import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LlmInvocationInspector } from '../LlmInvocationInspector';
import type { LlmCallRecord } from '@/types';

describe('LlmInvocationInspector', () => {
  it('renders empty state placeholder when calls array is empty', () => {
    render(<LlmInvocationInspector calls={[]} />);
    expect(screen.getByText('暂无 AI 底层请求记录 (No LLM Calls)')).toBeInTheDocument();
    expect(
      screen.getByText(/当启动任务且状态机流转时，系统将在此实时捕获并结构化呈现/)
    ).toBeInTheDocument();
  });

  it('renders list of LLM calls with step, model, metrics, and inspects message details', () => {
    const mockCalls: LlmCallRecord[] = [
      {
        id: 'llm-call-1',
        task_id: 'task-123',
        node: 'planner',
        step: 1,
        tier: 'reasoning',
        model: 'gpt-5.6-terra',
        messages: [
          { role: 'system', content: 'You are Aegis Agent Planner.' },
          { role: 'user', content: '重构鉴权模块' },
        ],
        response: {
          content: '{"thought": "拆解任务为3个里程碑", "milestone_updates": []}',
          finish_reason: 'stop',
        },
        tokens: 1250,
        durationMs: 1420,
        timestamp: '18:00:01',
      },
      {
        id: 'llm-call-2',
        task_id: 'task-123',
        node: 'executor',
        step: 2,
        tier: 'fast',
        model: 'gpt-5.4-mini',
        messages: [
          { role: 'system', content: 'You are Aegis Executor.' },
          { role: 'user', content: '执行第1步' },
        ],
        tools: [
          {
            type: 'function',
            function: {
              name: 'read_file',
              description: '读取工作区文件',
              parameters: { type: 'object', properties: { path: { type: 'string' } } },
            },
          },
        ],
        response: {
          content: '',
          tool_calls: [
            {
              id: 'call-1',
              name: 'read_file',
              args: { path: 'src/auth.ts' },
            },
          ],
          finish_reason: 'tool_calls',
        },
        tokens: 450,
        durationMs: 380,
        timestamp: '18:00:03',
      },
    ];

    const onSelectMock = vi.fn();
    render(
      <LlmInvocationInspector
        calls={mockCalls}
        selectedCallId="llm-call-1"
        onSelectCall={onSelectMock}
      />
    );

    // 1. Check Header Statistics
    expect(screen.getByText('大模型底层调用透视')).toBeInTheDocument();
    expect(screen.getByText('共 2 次')).toBeInTheDocument();
    expect(screen.getByText(/1,700 tok/)).toBeInTheDocument();

    // 2. Check Call items on the left
    expect(screen.getByText(/Step #1: planner/)).toBeInTheDocument();
    expect(screen.getByText(/Step #2: executor/)).toBeInTheDocument();
    expect(screen.getByText('gpt-5.6-terra')).toBeInTheDocument();
    expect(screen.getByText('gpt-5.4-mini')).toBeInTheDocument();

    // 3. Check selected detail inspection
    expect(screen.getByText('Step #1 : PLANNER')).toBeInTheDocument();
    expect(screen.getByText(/Prompt 消息序列 \(2\)/)).toBeInTheDocument();
    expect(screen.getByText('You are Aegis Agent Planner.')).toBeInTheDocument();
    expect(screen.getByText('重构鉴权模块')).toBeInTheDocument();

    // 4. Test clicking tab '模型原始响应'
    fireEvent.click(screen.getByText('模型原始响应'));
    expect(screen.getAllByText(/拆解任务为3个里程碑/).length).toBeGreaterThanOrEqual(1);

    // 5. Test filtering by node
    fireEvent.click(screen.getByRole('button', { name: 'Executor' }));
    expect(screen.queryByText('gpt-5.6-terra')).not.toBeInTheDocument();
    expect(screen.getByText('gpt-5.4-mini')).toBeInTheDocument();
  });
});
