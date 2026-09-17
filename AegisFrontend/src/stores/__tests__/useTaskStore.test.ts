import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useTaskStore } from '../useTaskStore';
import { taskApi } from '@/api';

describe('useTaskStore', () => {
  beforeEach(() => {
    // Reset Zustand store state
    useTaskStore.setState({
      currentTaskId: null,
      tasks: {},
      isLoading: false,
      error: null,
    });
    vi.restoreAllMocks();
  });

  it('should initialize and set currentTaskId', () => {
    const store = useTaskStore.getState();
    expect(store.currentTaskId).toBeNull();

    store.setCurrentTaskId('task-100');
    expect(useTaskStore.getState().currentTaskId).toBe('task-100');
  });

  it('should submit task, create task state and call taskApi.create', async () => {
    const mockCreate = vi.spyOn(taskApi, 'create').mockResolvedValue({
      task_id: 'task-new-1',
      status: 'running',
      stream_url: '/api/v1/tasks/task-new-1/events',
    });

    const store = useTaskStore.getState();
    const taskId = await store.submitTask('sess-1', '测试任务目标', {
      permissionLevel: 'workspace_write',
      model: 'Reasoning: DeepSeek-R1',
    });

    expect(taskId).toBeTruthy();
    expect(mockCreate).toHaveBeenCalledTimes(1);

    const task = useTaskStore.getState().tasks[taskId];
    expect(task).toBeDefined();
    expect(task.prompt).toBe('测试任务目标');
    expect(task.status).toBe('running');
    expect(task.messages.length).toBe(1);
    expect(task.messages[0].role).toBe('user');
  });

  it('should append message and trace steps to an existing task', () => {
    const store = useTaskStore.getState();
    store.upsertTask({
      id: 'task-test',
      title: 'Test',
      prompt: 'Prompt',
      status: 'running',
      permissionLevel: 'workspace_write',
      model: 'Fast',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messages: [],
      traceSteps: [],
      subagents: [],
      telemetry: {
        rounds: 1,
        steps: 1,
        tokenSpeed: 200,
        totalTokens: 1000,
        cacheHitRate: 0.99,
        waterLevelPct: 20,
        maxWaterLevelPct: 80,
      },
    });

    store.appendMessage('task-test', {
      id: 'msg-1',
      role: 'assistant',
      content: '规划完成',
      timestamp: '10:00',
    });

    store.appendTraceStep('task-test', {
      id: 'tr-1',
      node: 'planner',
      step: 1,
      inputSummary: 'Input',
      outputSummary: 'Output',
      durationMs: 300,
      timestamp: '10:00:01',
    });

    const task = useTaskStore.getState().tasks['task-test'];
    expect(task.messages.length).toBe(1);
    expect(task.messages[0].content).toBe('规划完成');
    expect(task.traceSteps.length).toBe(1);
    expect(task.traceSteps[0].node).toBe('planner');
  });

  it('should handle HITL approval request, approve action, and resume task', async () => {
    const mockApprove = vi.spyOn(taskApi, 'approve').mockResolvedValue({
      success: true,
      task_status: 'running',
    });

    const store = useTaskStore.getState();
    store.upsertTask({
      id: 'task-hitl',
      title: 'HITL Test',
      prompt: 'Do dangerous action',
      status: 'running',
      permissionLevel: 'workspace_write',
      model: 'Fast',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messages: [],
      traceSteps: [],
      subagents: [],
      telemetry: {
        rounds: 1,
        steps: 1,
        tokenSpeed: 200,
        totalTokens: 1000,
        cacheHitRate: 0.99,
        waterLevelPct: 20,
        maxWaterLevelPct: 80,
      },
    });

    // Set pending approval
    store.setPendingApproval('task-hitl', {
      approval_id: 'appr-999',
      task_id: 'task-hitl',
      action_type: 'privileged_exec',
      command: 'sudo systemctl restart',
      reason: '需要重启服务',
      created_at: new Date().toISOString(),
    });

    expect(useTaskStore.getState().tasks['task-hitl'].status).toBe('waiting_for_approval');

    // Approve action
    await store.approveAction('task-hitl', 'appr-999', 'once', '放行测试');

    expect(mockApprove).toHaveBeenCalledWith('task-hitl', {
      approval_id: 'appr-999',
      decision: 'once',
      feedback: '放行测试',
    });

    const updatedTask = useTaskStore.getState().tasks['task-hitl'];
    expect(updatedTask.pendingApproval).toBeUndefined();
    expect(updatedTask.status).toBe('running');
    expect(updatedTask.messages.some((m) => m.content.includes('人机协同审批通过'))).toBe(true);
  });

  it('should handle HITL reject action and notify state machine', async () => {
    const mockReject = vi.spyOn(taskApi, 'reject').mockResolvedValue({
      success: true,
      task_status: 'running',
    });

    const store = useTaskStore.getState();
    store.upsertTask({
      id: 'task-rej',
      title: 'Reject Test',
      prompt: 'Bad action',
      status: 'waiting_for_approval',
      permissionLevel: 'workspace_write',
      model: 'Fast',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messages: [],
      traceSteps: [],
      subagents: [],
      telemetry: {
        rounds: 1,
        steps: 1,
        tokenSpeed: 200,
        totalTokens: 1000,
        cacheHitRate: 0.99,
        waterLevelPct: 20,
        maxWaterLevelPct: 80,
      },
    });

    await store.rejectAction('task-rej', 'appr-123', '风险过高，禁止操作');

    expect(mockReject).toHaveBeenCalledWith('task-rej', {
      approval_id: 'appr-123',
      reason: '风险过高，禁止操作',
    });

    const updatedTask = useTaskStore.getState().tasks['task-rej'];
    expect(updatedTask.status).toBe('running');
    expect(updatedTask.messages.some((m) => m.content.includes('审批拒绝'))).toBe(true);
  });

  it('should cancel running task upon emergency breaker', async () => {
    const mockCancel = vi.spyOn(taskApi, 'cancel').mockResolvedValue({
      success: true,
      task_status: 'cancelled',
    });

    const store = useTaskStore.getState();
    store.upsertTask({
      id: 'task-cancel',
      title: 'Cancel Test',
      prompt: 'Long running',
      status: 'running',
      permissionLevel: 'workspace_write',
      model: 'Fast',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messages: [],
      traceSteps: [],
      subagents: [],
      telemetry: {
        rounds: 1,
        steps: 1,
        tokenSpeed: 200,
        totalTokens: 1000,
        cacheHitRate: 0.99,
        waterLevelPct: 20,
        maxWaterLevelPct: 80,
      },
    });
    store.setCurrentTaskId('task-cancel');

    await store.cancelCurrentTask();
    expect(mockCancel).toHaveBeenCalledWith('task-cancel');
    expect(useTaskStore.getState().tasks['task-cancel'].status).toBe('cancelled');
  });
});
