import { describe, it, expect } from 'vitest';
import { generateWorkflowMarkdown } from '../exportWorkflow';
import type { Task, Workspace } from '@/types';

describe('exportWorkflow', () => {
  it('handles null/undefined task gracefully', () => {
    const md = generateWorkflowMarkdown(null);
    expect(md).toContain('Aegis 任务报告 (无活动任务)');
  });

  it('exports complete task workflow including metadata, milestones, traces, LLM calls and dialogue', () => {
    const mockTask: Task = {
      id: 'task-test-001',
      session_id: 'sess-test-001',
      title: '重构鉴权模块',
      prompt: '重构鉴权模块并执行测试',
      status: 'completed',
      permissionLevel: 'workspace_write',
      model: 'Dual-Tier: gpt-5.6-terra + gpt-5.4-mini',
      createdAt: '2026-09-18 18:00:00',
      updatedAt: '2026-09-18 18:05:00',
      telemetry: {
        rounds: 1,
        steps: 3,
        tokenSpeed: 120,
        totalTokens: 2500,
        contextTokens: 1100,
        maxContextTokens: 32000,
        maxBudgetTokens: 200000,
        cacheHitRate: 1.0,
        waterLevelPct: 3.4,
        maxWaterLevelPct: 80,
      },
      messages: [
        {
          id: 'msg-1',
          role: 'user',
          content: '重构鉴权模块并执行测试',
          timestamp: '18:00:00',
        },
        {
          id: 'msg-2',
          role: 'assistant',
          content: '已完成鉴权模块重构并通过全部测试。',
          timestamp: '18:05:00',
          milestones: [
            { id: 'm1', title: '读取鉴权契约', status: 'completed' },
            { id: 'm2', title: '修改代码实现', status: 'completed' },
          ],
          fileMutations: [
            { path: 'src/auth.ts', action: 'modify', summary: '重构 token 校验' },
          ],
        },
      ],
      traceSteps: [
        {
          id: 'tr-1',
          node: 'planner',
          step: 1,
          inputSummary: '目标拆解',
          outputSummary: '拆分为2个里程碑',
          durationMs: 120,
          tokenUsage: 1000,
          timestamp: '18:00:01',
        },
        {
          id: 'tr-2',
          node: 'executor',
          step: 2,
          tool: 'write_file',
          toolArgs: { path: 'src/auth.ts' },
          toolResult: 'OK',
          durationMs: 80,
          tokenUsage: 1500,
          timestamp: '18:00:03',
        },
      ],
      llmCalls: [
        {
          id: 'llm-1',
          node: 'planner',
          step: 1,
          tier: 'reasoning',
          model: 'gpt-5.6-terra',
          messages: [{ role: 'user', content: '重构鉴权模块' }],
          response: { content: '{"milestones":[]}', finish_reason: 'stop' },
          tokens: 1000,
          durationMs: 1400,
          timestamp: '18:00:01',
        },
      ],
      subagents: [],
    };

    const mockWs: Workspace = {
      id: 'ws-1',
      name: 'AegisCore',
      root_path: '/home/project/aegis',
      created_at: '2026-09-18',
      updated_at: '2026-09-18',
    };

    const md = generateWorkflowMarkdown(mockTask, mockWs);

    expect(md).toContain('# Aegis 任务执行与思考全流程报告');
    expect(md).toContain('`task-test-001`');
    expect(md).toContain('`AegisCore`');
    expect(md).toContain('2,500 tokens');
    expect(md).toContain('读取鉴权契约');
    expect(md).toContain('Step #1: PLANNER');
    expect(md).toContain('`write_file`');
    expect(md).toContain('gpt-5.6-terra');
    expect(md).toContain('已完成鉴权模块重构并通过全部测试');
  });
});
