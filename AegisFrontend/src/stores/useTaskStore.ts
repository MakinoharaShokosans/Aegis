import { create } from 'zustand';
import type {
  Task,
  TaskMessage,
  TraceStep,
  LlmCallRecord,
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
  appendLlmCall: (taskId: string, call: LlmCallRecord) => void;
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

/**
 * 估算当前会话在活跃上下文滑动窗口中送入大模型 Prompt 的总 Token 规模
 * 对应四层上下文架构：
 * Layer 1 (底模 System Prompt & Canary 纪律): ~850 Token
 * Layer 2 (工作区共享记忆与用户画像): 动态估算
 * Layer 3 & 4 (会话记忆与活跃滑窗轮次): 轮次 Token 累计
 */
export function estimateSessionContextTokens(messages: TaskMessage[] = [], memoryCount: number = 0): number {
  const baseSystemTokens = 850;
  const memoryTokens = memoryCount * 60;
  const turnsTokens = messages.reduce((acc, m) => {
    if (m.tokensUsed && m.tokensUsed > 0) {
      return acc + m.tokensUsed;
    }
    const est = Math.max(8, Math.ceil((m.content || '').length / 2));
    return acc + est;
  }, 0);
  return baseSystemTokens + memoryTokens + turnsTokens;
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
            content: `### Planner 思考与目标拆解\n\n${thought || '正在分解任务目标与里程碑执行路径...'}`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            milestones,
          });
        }
      }
      break;
    }

    case 'node.finished': {
      const nodeName = data.node || 'executor';
      const seq = data.seq || data.step_count || 1;
      const rawMilestones = data.milestones || [];
      const milestones = rawMilestones.map((m: any, idx: number) => ({
        id: String(m.id || `m-${idx + 1}`),
        title: m.title || m.description || '执行阶段',
        status: m.status === 'completed' ? 'completed' : m.status === 'in_progress' ? 'in_progress' : 'pending',
      }));

      // 1. 同步遥测指标 (对齐：totalTokens 为任务执行累计物理消耗，contextTokens 为会话当前活跃窗口水位)
      if (data.total_tokens !== undefined || data.step_count !== undefined) {
        const task = get().tasks[taskId];
        const currentMsgs = task?.messages || [];
        const ctxTokens = estimateSessionContextTokens(currentMsgs);
        get().updateTelemetry(taskId, {
          totalTokens: data.total_tokens ?? task?.telemetry?.totalTokens ?? 0,
          steps: data.step_count ?? seq,
          contextTokens: ctxTokens,
          maxContextTokens: 32000,
          maxBudgetTokens: 200000,
          waterLevelPct: Number(((ctxTokens / 32000) * 100).toFixed(1)),
        });
      }

      // 2. 更新最新 assistant 消息的里程碑（若有）
      if (milestones.length > 0) {
        const task = get().tasks[taskId];
        if (task && task.messages.length > 0) {
          const lastMsg = task.messages[task.messages.length - 1];
          if (lastMsg && lastMsg.role === 'assistant') {
            set((state: any) => {
              const current = state.tasks[taskId];
              if (!current) return state;
              const msgs = [...current.messages];
              msgs[msgs.length - 1] = {
                ...lastMsg,
                milestones,
              };
              return {
                tasks: {
                  ...state.tasks,
                  [taskId]: { ...current, messages: msgs },
                },
              };
            });
          }
        }
      }

      // 3. 若为 executor 或 planner 直接答复，更新/写入面向用户的最终对话气泡
      if ((nodeName === 'executor' || (nodeName === 'planner' && data.decision === 'reply')) && data.content) {
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
                content: data.content,
                tokensUsed: data.total_tokens,
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
              id: `msg-${nodeName}-${Date.now()}`,
              role: 'assistant',
              content: data.content,
              tokensUsed: data.total_tokens,
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            });
          }
        }
      }

      // 4. 追加或替换初始 pending 的执行轨迹 step
      set((state: any) => {
        const current = state.tasks[taskId];
        if (!current) return state;
        const steps = [...current.traceSteps];
        const newStepObj = {
          id: `tr-finished-${nodeName}-${seq}-${Date.now()}`,
          node: nodeName as any,
          step: seq,
          inputSummary: data.input_summary || `节点 [${nodeName}] 执行`,
          outputSummary: data.output_summary || (data.decision ? `决策结果: ${data.decision}` : ''),
          decision: data.decision,
          tokenUsage: data.total_tokens,
          durationMs: data.duration_ms || 0,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        };

        const pendingIdx = steps.findIndex(
          (s) => s.id?.startsWith('tr-pending-') || s.outputSummary === '正在连接 Agent 状态机执行引擎...'
        );
        if (pendingIdx !== -1 && (seq === 1 || nodeName === 'planner')) {
          steps[pendingIdx] = newStepObj;
        } else {
          const existingFinishedIdx = steps.findIndex(
            (s) => s.node === nodeName && s.step === seq && s.id?.startsWith('tr-finished-')
          );
          if (existingFinishedIdx !== -1) {
            steps[existingFinishedIdx] = newStepObj;
          } else {
            steps.push(newStepObj);
          }
        }
        return {
          tasks: {
            ...state.tasks,
            [taskId]: { ...current, traceSteps: steps },
          },
        };
      });
      break;
    }

    case 'node.started': {
      const stepNum = data.step || 1;
      const nodeName = data.node || 'executor';
      get().appendTraceStep(taskId, {
        id: `tr-start-${stepNum}-${Date.now()}`,
        node: nodeName as any,
        step: stepNum,
        inputSummary: `节点 [${nodeName}] 开始执行步骤 #${stepNum}`,
        durationMs: 0,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      });
      break;
    }

    case 'tool.call': {
      const toolName = data.tool || 'tool';
      const argsSummary = data.args ? (typeof data.args === 'object' ? JSON.stringify(data.args, null, 2) : String(data.args)) : '';
      get().appendTraceStep(taskId, {
        id: `tr-call-${toolName}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        node: 'tool_runner',
        step: data.step || 1,
        tool: toolName,
        toolArgs: data.args,
        inputSummary: `准备调用受限工具: ${toolName}`,
        outputSummary: `入参: ${argsSummary.length > 200 ? argsSummary.slice(0, 200) + '...' : argsSummary}`,
        durationMs: 0,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      });
      break;
    }

    case 'tool.result': {
      const toolName = data.tool || '';
      const resultStr = data.result ? (typeof data.result === 'object' ? JSON.stringify(data.result, null, 2) : String(data.result)) : '';

      get().appendTraceStep(taskId, {
        id: `tr-res-${toolName}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        node: 'tool_runner',
        step: data.step || 1,
        tool: toolName,
        toolResult: resultStr,
        inputSummary: `工具 [${toolName}] 执行完成`,
        outputSummary: `返回产物: ${resultStr.length > 300 ? resultStr.slice(0, 300) + '...' : resultStr}`,
        durationMs: 0,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      });

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
        content: `**人机协同审批通过** (决策: \`${data.decision || 'once'}\`)。任务已继续执行。`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      });
      break;
    }

    case 'task.rejected': {
      get().setPendingApproval(taskId, undefined);
      get().setTaskStatus(taskId, 'running');
      get().appendMessage(taskId, {
        id: `msg-rej-${Date.now()}`,
        role: 'system',
        content: `**人机协同审批拒绝** (理由: "${data.reason || '用户已取消本次执行'}")。已通知 Planner 调整规划。`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      });
      break;
    }

    case 'llm.call': {
      const callRecord: LlmCallRecord = {
        id: data.id || `llm-${data.node || 'node'}-${data.step || 1}-${Date.now()}`,
        task_id: taskId,
        node: data.node || 'unknown',
        step: data.step || 1,
        tier: data.tier || 'reasoning',
        model: data.model || 'model',
        messages: Array.isArray(data.messages) ? data.messages : [],
        tools: Array.isArray(data.tools) ? data.tools : undefined,
        response: data.response || { content: data.content || '' },
        tokens: data.tokens || 0,
        durationMs: data.duration_ms || data.durationMs || 0,
        timestamp: data.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        error: data.error,
      };
      get().appendLlmCall(taskId, callRecord);
      break;
    }

    case 'task.finished': {
      const finalStatus = data.status === 'succeeded' || data.status === 'completed' ? 'completed' : 'failed';
      get().setTaskStatus(taskId, finalStatus);
      const totalTokens = data.total_tokens || 0;
      const task = get().tasks[taskId];
      const currentMsgs = task?.messages || [];
      const ctxTokens = estimateSessionContextTokens(currentMsgs);
      get().updateTelemetry(taskId, {
        totalTokens,
        steps: data.step_count || 0,
        contextTokens: ctxTokens,
        maxContextTokens: 32000,
        maxBudgetTokens: 200000,
        waterLevelPct: Number(((ctxTokens / 32000) * 100).toFixed(1)),
      });

      // 提取最终交付结论
      const deliveryText = data.delivery && data.delivery !== 'task_goal achieved' && data.delivery !== '任务结束' ? data.delivery : '';

      if (task) {
        const lastMsg = task.messages[task.messages.length - 1];
        if (lastMsg && lastMsg.role === 'assistant') {
          if (deliveryText) {
            set((state: any) => {
              const current = state.tasks[taskId];
              if (!current) return state;
              const msgs = [...current.messages];
              msgs[msgs.length - 1] = {
                ...lastMsg,
                content: deliveryText,
                tokensUsed: data.total_tokens,
              };
              return {
                tasks: {
                  ...state.tasks,
                  [taskId]: { ...current, messages: msgs },
                },
              };
            });
          }
        } else if (deliveryText) {
          get().appendMessage(taskId, {
            id: `msg-delivery-${Date.now()}`,
            role: 'assistant',
            content: deliveryText,
            tokensUsed: data.total_tokens,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
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
        content: `**执行异常**: ${data.message || data.code || '未知错误'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
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

  appendLlmCall: (taskId, call) =>
    set((state) => {
      const task = state.tasks[taskId];
      if (!task) return state;
      const existingCalls = task.llmCalls || [];
      const existingIdx = existingCalls.findIndex((c) => c.id === call.id);
      const nextCalls =
        existingIdx >= 0
          ? existingCalls.map((c, idx) => (idx === existingIdx ? call : c))
          : [...existingCalls, call];
      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            llmCalls: nextCalls,
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
      const currentTel = task.telemetry || {
        rounds: 1,
        steps: 1,
        tokenSpeed: 0,
        totalTokens: 0,
        contextTokens: 850,
        maxContextTokens: 32000,
        maxBudgetTokens: 200000,
        cacheHitRate: 1.0,
        waterLevelPct: 2.7,
        maxWaterLevelPct: 80,
      };
      const newTotalTokens = stats.totalTokens !== undefined ? stats.totalTokens : currentTel.totalTokens;
      const newContextTokens =
        stats.contextTokens !== undefined
          ? stats.contextTokens
          : currentTel.contextTokens ?? estimateSessionContextTokens(task.messages);
      const maxCtx = stats.maxContextTokens ?? currentTel.maxContextTokens ?? 32000;
      const newWaterPct =
        stats.waterLevelPct !== undefined
          ? stats.waterLevelPct
          : Number(((newContextTokens / maxCtx) * 100).toFixed(1));

      return {
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...task,
            telemetry: {
              ...currentTel,
              ...stats,
              totalTokens: newTotalTokens,
              contextTokens: newContextTokens,
              maxContextTokens: maxCtx,
              maxBudgetTokens: stats.maxBudgetTokens ?? currentTel.maxBudgetTokens ?? 200000,
              waterLevelPct: newWaterPct,
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
    // 1. 获取该会话已有的历史消息与轮次（支持多轮对话层叠堆叠）
    const currentId = get().currentTaskId;
    const currentTask = currentId ? get().tasks[currentId] : null;
    const sessionTask =
      currentTask && currentTask.session_id === sessionId
        ? currentTask
        : Object.values(get().tasks).find((t) => t.session_id === sessionId);

    const existingMessages: TaskMessage[] = sessionTask ? [...sessionTask.messages] : [];
    const previousRounds =
      sessionTask?.telemetry?.rounds || existingMessages.filter((m) => m.role === 'user').length;
    const previousTokens = sessionTask?.telemetry?.totalTokens || 0;

    const userMessage: TaskMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: prompt,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    const allMessages = [...existingMessages, userMessage];
    const initialCtxTokens = estimateSessionContextTokens(allMessages);

    const tempTaskId = `task-${Date.now()}`;
    const newTask: Task = {
      id: tempTaskId,
      session_id: sessionId,
      title: sessionTask?.title || prompt.slice(0, 36),
      prompt,
      status: 'running',
      permissionLevel: options?.permissionLevel || 'workspace_write',
      model: options?.model || 'Dual-Tier: gpt-5.6-terra + gpt-5.4-mini',
      createdAt: sessionTask?.createdAt || new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messages: allMessages,
      traceSteps: [
        ...(sessionTask?.traceSteps || []),
        {
          id: `tr-pending-${Date.now()}`,
          node: 'planner',
          step: (sessionTask?.traceSteps.length || 0) + 1,
          inputSummary: `接收任务目标: "${prompt.slice(0, 50)}..."`,
          outputSummary: '正在连接 Agent 状态机执行引擎...',
          durationMs: 0,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ],
      llmCalls: sessionTask?.llmCalls ? [...sessionTask.llmCalls] : [],
      subagents: [],
      telemetry: {
        rounds: previousRounds + 1,
        steps: (sessionTask?.telemetry?.steps || 0) + 1,
        tokenSpeed: 0,
        totalTokens: previousTokens,
        contextTokens: initialCtxTokens,
        maxContextTokens: 32000,
        maxBudgetTokens: 200000,
        cacheHitRate: 1.0,
        waterLevelPct: Number(((initialCtxTokens / 32000) * 100).toFixed(1)),
        maxWaterLevelPct: 80,
      },
    };

    set((state) => {
      const nextTasks = { ...state.tasks };
      if (sessionTask && sessionTask.id !== tempTaskId) {
        delete nextTasks[sessionTask.id];
      }
      nextTasks[tempTaskId] = newTask;
      return {
        tasks: nextTasks,
        currentTaskId: tempTaskId,
      };
    });

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
        content: `**任务执行失败**: ${errorMsg}`,
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
      content: `**人机协同审批通过** (决策: \`${decision}\`${feedback ? `, 备注: ${feedback}` : ''})。任务已继续执行。`,
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
      content: `**人机协同审批拒绝** (理由: "${reason}")。已通知 Planner 调整规划。`,
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
    get().appendMessage(id, {
      id: `msg-cancel-${Date.now()}`,
      role: 'system',
      content: '**任务已被用户手动终止**。',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    });
  },
}));
