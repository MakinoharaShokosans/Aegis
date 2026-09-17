import { create } from 'zustand';
import type { Task, TaskMessage, TraceStep, SubagentInfo, TelemetryStats, HITLApprovalRequest, PermissionLevel } from '@/types';
import { api } from '@/services/api';

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

  // Real backend or mock run
  submitTask: (
    sessionId: string,
    prompt: string,
    options?: { permissionLevel?: PermissionLevel; model?: string }
  ) => Promise<string>;
  approveAction: (taskId: string, approvalId: string, decision: 'once' | 'always', feedback?: string) => Promise<void>;
  rejectAction: (taskId: string, approvalId: string, reason: string) => Promise<void>;
  cancelCurrentTask: () => Promise<void>;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  currentTaskId: 'task-mock-default',
  tasks: {
    'task-mock-default': {
      id: 'task-mock-default',
      session_id: 'sess-auth-gate',
      title: '接入层三道安全闸门与鉴权中间件落地',
      prompt: '请在 AegisAgent 中设计并实现接入层 Host、Origin 与 Token 三道安全闸门，并添加对应单测。',
      status: 'completed',
      permissionLevel: 'workspace_write',
      model: 'Reasoning: DeepSeek-R1 / Fast: DeepSeek-V3',
      createdAt: new Date(Date.now() - 3600000).toISOString(),
      updatedAt: new Date().toISOString(),
      messages: [
        {
          id: 'msg-1',
          role: 'user',
          content: '请在 AegisAgent 中设计并实现接入层 Host、Origin 与 Token 三道安全闸门，并添加对应单测。',
          timestamp: '18:30',
        },
        {
          id: 'msg-2',
          role: 'assistant',
          content: `### Planner 阶段目标与里程碑推进 (LangGraph State Machine)\n\n已成功分析需求，并启动双模型分层网关。Reasoning 思考模型生成全局计划，Fast 动作模型并行分派专用子智能体：`,
          timestamp: '18:31',
          durationMs: 35800,
          tokensUsed: 24850,
          milestones: [
            { id: 'm1', title: '调用 delegate_doc_search 检索 11_http_api.md 鉴权规范', status: 'completed' },
            { id: 'm2', title: '在 auth.py 落地 Host -> Origin -> Token 三道安全闸门中间件', status: 'completed' },
            { id: 'm3', title: '运行 pytest 验证 234 个测试用例，达成 100% 覆盖通过', status: 'completed' },
          ],
          subagentReports: [
            {
              type: 'doc_search',
              title: 'Doc & Knowledge Search Subagent (3轮自适应改词 RAG)',
              queries: ['11_http_api.md 鉴权规范', 'SecurityGateMiddleware 接入层设计'],
              citations: ['documents/agent_runtime/11_http_api.md:25-60', 'documents/agent_runtime/01_architecture_overview.md:120-145'],
              summary: '成功命中 HTTP API 契约与接入层架构规范，确认三道闸门执行次序与恒定时间比较安全纪律。',
              isExternal: false,
            },
          ],
          fileMutations: [
            {
              path: 'AegisAgent/src/agent_runtime/api/auth.py',
              action: 'modify',
              summary: '实现 SecurityGateMiddleware：Host 防 DNS 重绑定、Origin 跨站校验与 secrets.compare_digest 令牌鉴权',
            },
            {
              path: 'AegisAgent/src/agent_runtime/api/routes/files.py',
              action: 'create',
              summary: '工作区文件管理路由：提供递归文件树与受限读写（严格防御 Path Traversal 越界）',
            },
            {
              path: 'documents/agent_runtime/11_http_api.md',
              action: 'modify',
              summary: 'HTTP API 权威契约：补充 §4.6 Files 与 §4.7 RAG 网关代理规范',
            },
          ],
        },
      ],
      traceSteps: [
        {
          id: 'tr-1',
          node: 'planner',
          step: 1,
          inputSummary: '分析任务并拆解 3 个阶段里程碑',
          outputSummary: '里程碑列表生成，派发 doc_search 子智能体',
          durationMs: 1200,
          tokenUsage: 1420,
          timestamp: '18:30:05',
        },
        {
          id: 'tr-2',
          node: 'subagent',
          step: 2,
          inputSummary: 'delegate_doc_search("接入层三道闸门规范")',
          outputSummary: '命中 11_http_api.md#L25-60，提炼三道闸门要求',
          durationMs: 850,
          tokenUsage: 890,
          timestamp: '18:30:07',
        },
        {
          id: 'tr-3',
          node: 'executor',
          step: 3,
          inputSummary: 'Fast 模型编写 auth.py 与 files.py',
          outputSummary: '生成 2 个文件改动，触发文件修改通知',
          durationMs: 2400,
          tokenUsage: 3100,
          timestamp: '18:30:12',
        },
        {
          id: 'tr-4',
          node: 'evaluator',
          step: 4,
          inputSummary: '运行 pytest 验证 234 个测试套件',
          outputSummary: '234 passed in 6.11s, 判定任务目标圆满达成',
          durationMs: 6110,
          tokenUsage: 560,
          timestamp: '18:30:20',
        },
      ],
      subagents: [
        {
          id: 'sub-doc',
          name: 'Doc & Knowledge Search',
          role: '文档与技术规范知识检索 (3轮改词 RAG)',
          status: 'completed',
          stepCount: 3,
          summary: '命中 11_http_api.md:25-60',
        },
        {
          id: 'sub-res',
          name: 'Research Subagent',
          role: '外部网页隔离研究 (DDG / Trafilatura)',
          status: 'idle',
          stepCount: 0,
        },
      ],
      telemetry: {
        rounds: 5,
        steps: 14,
        tokenSpeed: 271,
        totalTokens: 28500,
        cacheHitRate: 0.998,
        waterLevelPct: 32,
        maxWaterLevelPct: 80,
      },
    },
  },
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
    const taskId = `task-${Date.now()}`;
    const newTask: Task = {
      id: taskId,
      session_id: sessionId,
      title: prompt.slice(0, 36),
      prompt,
      status: 'running',
      permissionLevel: options?.permissionLevel || 'workspace_write',
      model: options?.model || 'Reasoning: DeepSeek-R1 / Fast: DeepSeek-V3',
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
          outputSummary: '规划状态机推进中...',
          durationMs: 450,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ],
      subagents: [
        {
          id: 'sub-doc',
          name: 'Doc & Knowledge Search',
          role: '文档与技术规范检索',
          status: 'running',
          stepCount: 1,
        },
        {
          id: 'sub-res',
          name: 'Research Subagent',
          role: '外部网页隔离研究',
          status: 'idle',
          stepCount: 0,
        },
      ],
      telemetry: {
        rounds: 1,
        steps: 3,
        tokenSpeed: 285,
        totalTokens: 1820,
        cacheHitRate: 0.999,
        waterLevelPct: 24,
        maxWaterLevelPct: 80,
      },
    };

    get().upsertTask(newTask);
    get().setCurrentTaskId(taskId);

    try {
      await api.createTask(sessionId, {
        prompt,
        permission_level: options?.permissionLevel,
        model: options?.model,
      });
    } catch {
      // Offline / fallback simulated response
      setTimeout(() => {
        get().appendMessage(taskId, {
          id: `msg-resp-${Date.now()}`,
          role: 'assistant',
          content: `### 智能体执行完毕 (LangGraph State Machine)\n\n已成功调起 **Fast 动作层模型** 与 **文档检索子智能体**。根据工作区架构定论与规范，已完成分析与对应文件操作。`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          durationMs: 1480,
          milestones: [
            { id: 'm-1', title: '解析输入需求并加载工作区共享记忆', status: 'completed' },
            { id: 'm-2', title: '调用 RAG 索引检索关联技术规范与 API 契约', status: 'completed' },
            { id: 'm-3', title: '完成代码/文档改动并执行语法与安全性校验', status: 'completed' },
          ],
          fileMutations: [
            {
              path: 'documents/agent_runtime/11_http_api.md',
              action: 'modify',
              summary: '更新接口定义与鉴权配置规范',
            },
          ],
        });
        get().setTaskStatus(taskId, 'completed');
      }, 1500);
    }

    return taskId;
  },

  approveAction: async (taskId, approvalId, decision, feedback) => {
    try {
      await api.approveAction(taskId, { approval_id: approvalId, decision, feedback });
    } catch {
      // ignore
    }
    get().setPendingApproval(taskId, undefined);
    get().setTaskStatus(taskId, 'running');
    get().appendMessage(taskId, {
      id: `msg-hitl-${Date.now()}`,
      role: 'system',
      content: `🛡 **人机协同审批通过** (决策: \`${decision}\`${feedback ? `，附言: ${feedback}` : ''})。状态机已解除阻塞继续执行。`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    });
  },

  rejectAction: async (taskId, approvalId, reason) => {
    try {
      await api.rejectAction(taskId, { approval_id: approvalId, reason });
    } catch {
      // ignore
    }
    get().setPendingApproval(taskId, undefined);
    get().setTaskStatus(taskId, 'running');
    get().appendMessage(taskId, {
      id: `msg-hitl-rej-${Date.now()}`,
      role: 'system',
      content: `⚠️ **人机协同审批拒绝** (理由: "${reason}")。已反馈给 Planner 触发动态重规划。`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    });
  },

  cancelCurrentTask: async () => {
    const id = get().currentTaskId;
    if (!id) return;
    try {
      await api.cancelTask(id);
    } catch {
      // ignore
    }
    get().setTaskStatus(id, 'cancelled');
  },
}));
