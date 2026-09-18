/**
 * Aegis SSE Streaming Engine
 * Manages Server-Sent Events with automatic auth token propagation and error handling.
 */

import { fetchEventSource } from '@microsoft/fetch-event-source';
import { httpClient } from './client';

export interface SSEOptions {
  onOpen?: (response: Response) => void | Promise<void>;
  onEvent?: (eventName: string, data: unknown) => void;
  onError?: (err: unknown) => void;
  onClose?: () => void;
  signal?: AbortSignal;
}

export function subscribeTaskEvents(taskId: string, options: SSEOptions = {}): () => void {
  const ctrl = new AbortController();
  const token = httpClient.getToken();
  
  // Construct SSE URL with token query param fallback for event streams
  const tokenQuery = token ? `?token=${encodeURIComponent(token)}` : '';
  const url = `/api/v1/tasks/${encodeURIComponent(taskId)}/stream${tokenQuery}`;

  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
  };
  if (token) {
    headers['X-API-Token'] = token;
    headers['Authorization'] = `Bearer ${token}`;
  }

  fetchEventSource(url, {
    signal: options.signal || ctrl.signal,
    headers,
    onopen: async (res) => {
      if (res.ok && (res.headers.get('content-type')?.includes('text/event-stream') || res.status === 200)) {
        await options.onOpen?.(res);
        return;
      }
      throw new Error(`SSE connection failed with status ${res.status}: ${res.statusText}`);
    },
    onmessage: (msg) => {
      try {
        const parsed = msg.data ? JSON.parse(msg.data) : null;
        options.onEvent?.(msg.event || 'message', parsed);
      } catch {
        options.onEvent?.(msg.event || 'message', msg.data);
      }
    },
    onclose: () => {
      options.onClose?.();
    },
    onerror: (err) => {
      options.onError?.(err);
      throw err; // Stop retrying or propagate error
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
