import { create } from 'zustand';
import type { Task, TaskMessage, TraceStep, SubagentInfo, TelemetryStats } from '@/types';

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
}

export const useTaskStore = create<TaskState>((set) => ({
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
}));
