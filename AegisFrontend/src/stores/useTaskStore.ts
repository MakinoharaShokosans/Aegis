import { create } from 'zustand';
import type {
  Task,
  TaskMessage,
  TraceStep,
  SubagentInfo,
  TelemetryStats,
  HITLApprovalRequest,
  PermissionLevel,
} from '@/types';
import { taskApi } from '@/api';

interface TaskState {
  currentTaskId: string | null;
  tasks: Record<string, Task>;
  isLoading: boolean;
  error: string | null;

  setCurrentTaskId: (id: string | null) => void;
  upsertTask: (task: Task) => void;
  appendMessage: (taskId: string, message: TaskMessage) => void;
  appendTraceStep: (taskId: string, step: TraceStep) => void;
  updateSubagents: (taskId: string, subagents: SubagentInfo[]) => void;
  updateTelemetry: (taskId: string, stats: Partial<TelemetryStats>) => void;
  setTaskStatus: (taskId: string, status: Task['status']) => void;
  setPendingApproval: (taskId: string, approval: HITLApprovalRequest | undefined) => void;

  submitTask: (
    sessionId: string,
    prompt: string,
    options?: { permissionLevel?: PermissionLevel; model?: string }
  ) => Promise<string>;
  approveAction: (taskId: string, approvalId: string, decision: 'once' | 'always', feedback?: string) => Promise<void>;
  rejectAction: (taskId: string, approvalId: string, reason: string) => Promise<void>;
  cancelCurrentTask: () => Promise<void>;
}

function handleIncomingEvent(
  taskId: string,
  event: string,
  data: any,
  set: any,
  get: () => TaskState
) {
  if (!data && event !== 'task.started') return;

  switch (event) {
    case 'task.started':
      get().setTaskStatus(taskId, 'running');
      break;

    case 'plan': {
      const thought = data.thought || '';
      const rawMilestones = data.milestones || [];
      const milestones = rawMilestones.map((m: any, idx: number) => ({
        id: String(m.id || `m-${idx + 1}`),
        title: m.title || m.description || '执行阶段',
        status: m.status === 'completed' ? 'completed' : m.status === 'in_progress' ? 'in_progress' : 'pending',
      }));

      // 查找或追加 assistant 消息
      const task = get().tasks[taskId];
      if (task) {
        const lastMsg = task.messages[task.messages.length - 1];
        if (lastMsg && lastMsg.role === 'assistant') {
          set((state: any) => {
            const current = state.tasks[taskId];
            if (!current) return state;
            const msgs = [...current.messages];
            msgs[msgs.length - 1] = {
              ...lastMsg,
              content: thought ? `### Planner 思考与目标拆解\n\n${thought}` : lastMsg.content,
              milestones: milestones.length > 0 ? milestones : lastMsg.milestones,
            };
            return {
              tasks: {
                ...state.tasks,
                [taskId]: { ...current, messages: msgs },
              },
            };
          });
        } else {
          get().appendMessage(taskId, {
            id: `msg-plan-${Date.now()}`,
            role: 'assistant',
            content: `### Planner 思考与目标拆解\n\n${thought || '正在分解任务目标与里程碑执行路径...' }`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            milestones,
          });
        }
      }
      break;
    }

    case 'node.started': {
      const stepNum = data.step || 1;
      const nodeName = data.node || 'executor';
      get().appendTraceStep(taskId, {
        id: `tr-${stepNum}-${Date.now()}`,
        node: nodeName as any,
        step: stepNum,
        inputSummary: `节点 [${nodeName}] 开始执行步骤 #${stepNum}`,
        durationMs: 0,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      });
      break;
    }

    case 'tool.call': {
      const toolName = data.tool || 'tool';
      const argsSummary = data.args ? JSON.stringify(data.args) : '';
      get().appendTraceStep(taskId, {
        id: `tr-tool-${Date.now()}`,
        node: 'tool_runner',
        step: data.step || 1,
        inputSummary: `调用工具: ${toolName}`,
        outputSummary: argsSummary.slice(0, 120),
        durationMs: 0,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      });
      break;
    }

    case 'tool.result': {
      const toolName = data.tool || '';
      if (toolName === 'write_file' && data.args?.path) {
        const task = get().tasks[taskId];
        if (task) {
          const lastMsg = task.messages[task.messages.length - 1];
          if (lastMsg && lastMsg.role === 'assistant') {
            const mutations = lastMsg.fileMutations || [];
            mutations.push({
              path: data.args.path,
              action: 'modify',
              summary: '修改/创建文件内容',
            });
            set((state: any) => ({
              tasks: {
                ...state.tasks,
                [taskId]: {
                  ...state.tasks[taskId],
                  messages: state.tasks[taskId].messages.map((m: any, idx: number) =>
                    idx === state.tasks[taskId].messages.length - 1 ? { ...m, fileMutations: mutations } : m
                  ),
                },
              },
            }));
          }
        }
      }
      break;
    }

    case 'task.waiting_for_approval': {
      get().setPendingApproval(taskId, {
        approval_id: data.approval_id || '',
        task_id: taskId,
        action_type: (data.action_type as any) || 'privileged_exec',
        command: data.command || '',
        reason: data.reason || '检测到敏感/越级操作，需要人工审批确认。',
        created_at: new Date().toISOString(),
      });
      get().setTaskStatus(taskId, 'waiting_for_approval');
      break;
    }

    case 'task.approved': {
      get().setPendingApproval(taskId, undefined);
      get().setTaskStatus(taskId, 'running');
      get().appendMessage(taskId, {
        id: `msg-appr-${Date.now()}`,
        role: 'system',
        content: `🛡 **人机协同审批通过** (决策: \`${data.decision || 'once'}\`)。任务已继续执行。`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      });
      break;
    }

    case 'task.rejected': {
      get().setPendingApproval(taskId, undefined);
      get().setTaskStatus(taskId, 'running');
      get().appendMessage(taskId, {
        id: `msg-rej-${Date.now()}`,
        role: 'system',
        content: `⚠️ **人机协同审批拒绝** (理由: "${data.reason || '用户已取消本次执行'}")。已通知 Planner 调整规划。`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      });
      break;
    }

    case 'task.finished': {
      const finalStatus = data.status === 'succeeded' || data.status === 'completed' ? 'completed' : 'failed';
      get().setTaskStatus(taskId, finalStatus);
      get().updateTelemetry(taskId, {
        totalTokens: data.total_tokens || 0,
        steps: data.step_count || 0,
      });

      const task = get().tasks[taskId];
      if (task) {
        const lastMsg = task.messages[task.messages.length - 1];
        if (!lastMsg || lastMsg.role !== 'assistant') {
          get().appendMessage(taskId, {
            id: `msg-fin-${Date.now()}`,
            role: 'assistant',
            content: `### 智能体执行完毕\n\n任务已顺利完成。\n- **总消耗 Token**: ${data.total_tokens || 0}\n- **执行步数**: ${data.step_count || 0}\n- **终止原因**: \`${data.termination_reason || 'task_goal achieved'}\``,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          });
        }
      }
      break;
    }

    case 'task.error': {
      get().setTaskStatus(taskId, 'failed');
      get().appendMessage(taskId, {
        id: `msg-err-${Date.now()}`,
        role: 'system',
        content: `❌ **执行异常**: ${data.message || data.code || '未知错误'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      });
      break;
    }
  }
}

export const useTaskStore = create<TaskState>((set, get) => ({
  currentTaskId: null,
  tasks: {},
  isLoading: false,
  error: null,

  setCurrentTaskId: (id) => set({ currentTaskId: id }),

  upsertTask: (task) =>
    set((state) => ({
      tasks: {
        ...state.tasks,
        [task.id]: task,
      },
    })),

  appendMessage: (taskId, message) =>
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;
      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            messages: [...task.messages, message],
            updatedAt: new Date().toISOString(),
          },
        },
      };
    }),

  appendTraceStep: (taskId, step) =>
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;
      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            traceSteps: [...task.traceSteps, step],
            updatedAt: new Date().toISOString(),
          },
        },
      };
    }),

  updateSubagents: (taskId, subagents) =>
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;
      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            subagents,
            updatedAt: new Date().toISOString(),
          },
        },
      };
    }),

  updateTelemetry: (taskId, stats) =>
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;
      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            telemetry: {
              ...task.telemetry,
              ...stats,
            },
            updatedAt: new Date().toISOString(),
          },
        },
      };
    }),

  setTaskStatus: (taskId, status) =>
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;
      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            status,
            updatedAt: new Date().toISOString(),
          },
        },
      };
    }),

  setPendingApproval: (taskId, approval) =>
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;
      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            status: approval ? 'waiting_for_approval' : task.status,
            pendingApproval: approval,
            updatedAt: new Date().toISOString(),
          },
        },
      };
    }),

  submitTask: async (sessionId, prompt, options) => {
    const tempTaskId = `task-${Date.now()}`;
    const newTask: Task = {
      id: tempTaskId,
      session_id: sessionId,
      title: prompt.slice(0, 36),
      prompt,
      status: 'running',
      permissionLevel: options?.permissionLevel || 'workspace_write',
      model: options?.model || 'Dual-Tier: gpt-5.6-terra + gpt-5.4-mini',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messages: [
        {
          id: `msg-${Date.now()}`,
          role: 'user',
          content: prompt,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ],
      traceSteps: [
        {
          id: `tr-${Date.now()}`,
          node: 'planner',
          step: 1,
          inputSummary: `接收任务目标: "${prompt.slice(0, 50)}..."`,
          outputSummary: '正在连接 Agent 状态机执行引擎...',
          durationMs: 0,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ],
      subagents: [],
      telemetry: {
        rounds: 1,
        steps: 0,
        tokenSpeed: 0,
        totalTokens: 0,
        cacheHitRate: 1.0,
        waterLevelPct: 0,
        maxWaterLevelPct: 80,
      },
    };

    get().upsertTask(newTask);
    get().setCurrentTaskId(tempTaskId);

    try {
      const res = await taskApi.create(sessionId, {
        task_goal: prompt,
        permission_level: options?.permissionLevel,
      });

      const realTaskId = res.task_id;
      // 用 realTaskId 替换 tempTaskId
      set((state) => {
        const existing = state.tasks[tempTaskId];
        const newTasks = { ...state.tasks };
        delete newTasks[tempTaskId];
        if (existing) {
          newTasks[realTaskId] = { ...existing, id: realTaskId };
        }
        return {
          tasks: newTasks,
          currentTaskId: realTaskId,
        };
      });

      // 订阅真实 SSE 事件流
      taskApi.subscribe(realTaskId, {
        onEvent: (event, data) => {
          handleIncomingEvent(realTaskId, event, data, set, get);
        },
        onError: (err) => {
          console.error('[SSE Error]', err);
        },
      });

      return realTaskId;
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : '提交任务失败';
      get().setTaskStatus(tempTaskId, 'failed');
      get().appendMessage(tempTaskId, {
        id: `msg-err-${Date.now()}`,
        role: 'system',
        content: `❌ **任务执行失败**: ${errorMsg}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      });
      return tempTaskId;
    }
  },

  approveAction: async (taskId, approvalId, decision, feedback) => {
    try {
      await taskApi.approve(taskId, { approval_id: approvalId, decision, feedback });
    } catch {
      // ignore
    }
    get().setPendingApproval(taskId, undefined);
    get().setTaskStatus(taskId, 'running');
    get().appendMessage(taskId, {
      id: `msg-appr-${Date.now()}`,
      role: 'system',
      content: `🛡 **人机协同审批通过** (决策: \`${decision}\`${feedback ? `, 备注: ${feedback}` : ''})。任务已继续执行。`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    });
  },

  rejectAction: async (taskId, approvalId, reason) => {
    try {
      await taskApi.reject(taskId, { approval_id: approvalId, reason });
    } catch {
      // ignore
    }
    get().setPendingApproval(taskId, undefined);
    get().setTaskStatus(taskId, 'running');
    get().appendMessage(taskId, {
      id: `msg-rej-${Date.now()}`,
      role: 'system',
      content: `⚠️ **人机协同审批拒绝** (理由: "${reason}")。已通知 Planner 调整规划。`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    });
  },

  cancelCurrentTask: async () => {
    const id = get().currentTaskId;
    if (!id) return;
    try {
      await taskApi.cancel(id);
    } catch {
      // ignore
    }
    get().setTaskStatus(id, 'cancelled');
  },
}));
