import { fetchEventSource } from '@microsoft/fetch-event-source';

export interface SSEOptions {
  onEvent?: (eventName: string, data: unknown) => void;
  onError?: (err: unknown) => void;
  onClose?: () => void;
}

export function subscribeTaskEvents(taskId: string, options: SSEOptions = {}) {
  const ctrl = new AbortController();

  fetchEventSource(`/api/v1/tasks/${taskId}/events`, {
    signal: ctrl.signal,
    onopen: async (res) => {
      if (res.ok && res.status === 200) {
        return; // connected successfully
      }
      throw new Error(`SSE connection failed with status ${res.status}`);
    },
    onmessage: (msg) => {
      try {
        const parsed = msg.data ? JSON.parse(msg.data) : null;
        options.onEvent?.(msg.event || 'message', parsed);
      } catch (err) {
        console.warn('Failed to parse SSE event data', err);
      }
    },
    onclose: () => {
      options.onClose?.();
    },
    onerror: (err) => {
      options.onError?.(err);
      throw err; // rethrow to stop retry or let fetchEventSource retry
    },
  }).catch((err) => {
    if (!ctrl.signal.aborted) {
      options.onError?.(err);
    }
  });

  return () => {
    ctrl.abort();
  };
}
