import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useTaskStore } from '../useTaskStore';
import { taskApi } from '@/api';

describe('useTaskStore', () => {
  beforeEach(() => {
    useTaskStore.setState({
      currentTaskId: null,
      tasks: {},
      isLoading: false,
      error: null,
    });
    vi.restoreAllMocks();
  });

  it('should stack conversation messages across multiple task submissions in the same session', async () => {
    vi.spyOn(taskApi, 'create')
      .mockResolvedValueOnce({
        task_id: 'real-task-1',
        session_id: 'sess-abc',
        status: 'running',
      })
      .mockResolvedValueOnce({
        task_id: 'real-task-2',
        session_id: 'sess-abc',
        status: 'running',
      });

    vi.spyOn(taskApi, 'subscribe').mockReturnValue(() => {});

    const store = useTaskStore.getState();

    // Turn 1: User sends first message
    const taskId1 = await store.submitTask('sess-abc', '第一轮指令：分析项目结构');
    expect(taskId1).toBe('real-task-1');
    expect(useTaskStore.getState().currentTaskId).toBe('real-task-1');

    const task1 = useTaskStore.getState().tasks['real-task-1'];
    expect(task1.messages.length).toBe(1);
    expect(task1.messages[0].content).toBe('第一轮指令：分析项目结构');

    // Simulate assistant responding in Turn 1
    useTaskStore.getState().appendMessage('real-task-1', {
      id: 'msg-assistant-1',
      role: 'assistant',
      content: '项目结构包含 AegisAgent, AegisFrontend, AegisRAG',
      timestamp: '12:00',
    });

    const task1WithResp = useTaskStore.getState().tasks['real-task-1'];
    expect(task1WithResp.messages.length).toBe(2);

    // Turn 2: User sends second message in the same session
    const taskId2 = await store.submitTask('sess-abc', '第二轮指令：请在这个结构下创建 files.py');
    expect(taskId2).toBe('real-task-2');
    expect(useTaskStore.getState().currentTaskId).toBe('real-task-2');

    const task2 = useTaskStore.getState().tasks['real-task-2'];
    // Crucial check: All 3 messages (User1, Assistant1, User2) must be preserved in sequence!
    expect(task2.messages.length).toBe(3);
    expect(task2.messages[0].content).toBe('第一轮指令：分析项目结构');
    expect(task2.messages[1].content).toBe('项目结构包含 AegisAgent, AegisFrontend, AegisRAG');
    expect(task2.messages[2].content).toBe('第二轮指令：请在这个结构下创建 files.py');
    expect(task2.telemetry.rounds).toBe(2);
  });

  it('should handle cancelCurrentTask cleanly', async () => {
    const mockCancel = vi.spyOn(taskApi, 'cancel').mockResolvedValue({
      success: true,
      task_status: 'cancelled',
    });

    useTaskStore.setState({
      currentTaskId: 'task-to-cancel',
      tasks: {
        'task-to-cancel': {
          id: 'task-to-cancel',
          session_id: 'sess-1',
          title: '运行测试',
          prompt: '运行测试',
          status: 'running',
          permissionLevel: 'workspace_write',
          model: 'fast',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          messages: [],
          traceSteps: [],
          subagents: [],
          telemetry: { rounds: 1, steps: 1, tokenSpeed: 0, totalTokens: 10, cacheHitRate: 1, waterLevelPct: 1, maxWaterLevelPct: 80 },
        },
      },
    });

    await useTaskStore.getState().cancelCurrentTask();

    expect(mockCancel).toHaveBeenCalledWith('task-to-cancel');
    const task = useTaskStore.getState().tasks['task-to-cancel'];
    expect(task.status).toBe('cancelled');
    expect(task.messages.some((m) => m.content.includes('任务已被用户手动终止'))).toBe(true);
  });

  it('should process node.finished, tool.call, and tool.result SSE events into rich TraceSteps', async () => {
    let capturedHandler: ((event: string, data: any) => void) | undefined;
    vi.spyOn(taskApi, 'create').mockResolvedValue({
      task_id: 'task-trace-test',
      session_id: 'sess-1',
      status: 'running',
    });
    vi.spyOn(taskApi, 'subscribe').mockImplementation((_taskId, callbacks) => {
      capturedHandler = callbacks?.onEvent;
      return () => {};
    });

    const store = useTaskStore.getState();
    await store.submitTask('sess-1', '测试执行追踪');
    expect(capturedHandler).not.toBeNull();

    // 1. Planner finished event
    capturedHandler!('node.finished', {
      node: 'planner',
      seq: 1,
      input_summary: '接收目标: 测试执行追踪',
      output_summary: '【规划决策】派发执行',
      decision: 'dispatch_action',
      total_tokens: 1200,
      step_count: 1,
    });

    // 2. Executor tool call event
    capturedHandler!('tool.call', {
      tool: 'read_file',
      args: { path: 'src/main.py' },
      step: 2,
    });

    // 3. Tool result event
    capturedHandler!('tool.result', {
      tool: 'read_file',
      result: 'def main(): pass',
      step: 3,
    });

    // 4. Evaluator finished event
    capturedHandler!('node.finished', {
      node: 'evaluator',
      seq: 4,
      input_summary: '复核阶段完成度',
      output_summary: '【验收结论】验收通过，准予交付',
      decision: 'accepted',
      total_tokens: 2100,
      step_count: 4,
      should_terminate: true,
    });

    const task = useTaskStore.getState().tasks['task-trace-test'];
    expect(task.traceSteps.length).toBeGreaterThanOrEqual(4);

    // Verify trace step nodes and decisions
    const plannerStep = task.traceSteps.find((s) => s.node === 'planner' && s.decision === 'dispatch_action');
    expect(plannerStep).toBeDefined();
    expect(plannerStep?.inputSummary).toBe('接收目标: 测试执行追踪');

    const toolCallStep = task.traceSteps.find((s) => s.tool === 'read_file' && s.toolArgs);
    expect(toolCallStep).toBeDefined();

    const evaluatorStep = task.traceSteps.find((s) => s.node === 'evaluator' && s.decision === 'accepted');
    expect(evaluatorStep).toBeDefined();
    expect(evaluatorStep?.outputSummary).toContain('验收通过');

    // Verify telemetry updated
    expect(task.telemetry.totalTokens).toBe(2100);
    expect(task.telemetry.steps).toBe(4);
  });
});
