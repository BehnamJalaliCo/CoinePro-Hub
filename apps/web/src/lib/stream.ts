'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { isMock } from './api/client';

export type StreamEvent = { id: string; type: string; at: string; company: string | null; ref: string | null; data: Record<string, unknown> };

// Every named SSE event of contract §7 and §16 (EventSource only delivers named events to their listeners).
const EVENT_TYPES = [
  'work.created', 'work.updated', 'work.delegated', 'work.completed',
  'decision.created', 'decision.decided', 'deliverable.created', 'deliverable.rated',
  'message.created', 'notification.created', 'presence.changed', 'control.changed',
  'employee.updated', 'activity.changed', 'llm.call.started', 'llm.call.finished',
  'budget.alert', 'run.started', 'run.step', 'run.finished',
  // ⟨1.3⟩ §17.6
  'file.ready', 'file.failed', 'workshop.session', 'workshop.approval', 'order.routed',
] as const;

// Event type prefix -> query keys to refresh (contract §7, §16).
const INVALIDATE: Array<[string, string[]]> = [
  ['decision.', ['decisions', 'inbox', 'away']],
  ['deliverable.', ['deliverables', 'inbox']],
  ['work.', ['work', 'planner', 'companies']],
  ['message.', ['threads', 'messages', 'inbox']],
  ['notification.', ['notifications', 'inbox']],
  ['control.', ['control', 'companies']],
  ['employee.', ['employees', 'companies']],
  ['presence.', ['presence', 'inbox']],
  ['budget.', ['treasury']],
  ['llm.', ['treasury']],
  ['run.', ['runs']],
  ['file.', ['messages']],
  ['workshop.', ['workshop']],
  ['order.', ['orders', 'planner', 'work']],
];

export type StreamState = 'connecting' | 'live' | 'offline';

/** One SSE connection for the whole app; resumes with Last-Event-ID (the browser does it). */
export function useHoldingStream(onEvent?: (e: StreamEvent) => void): StreamState {
  const qc = useQueryClient();
  const [state, setState] = useState<StreamState>(isMock ? 'live' : 'connecting');
  const cb = useRef(onEvent);
  useLayoutEffect(() => { cb.current = onEvent; });

  useEffect(() => {
    if (isMock) {
      let n = 0;
      const t = setInterval(() => {
        n += 1;
        cb.current?.({ id: String(n), type: 'activity.changed', at: new Date().toISOString(), company: ['TY', 'FX', 'PC'][n % 3] ?? null, ref: null, data: { pulse: n } });
      }, 2400);
      return () => clearInterval(t);
    }
    let es: EventSource | null = null;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    const open = () => {
      es = new EventSource('/api/v1/stream?topics=work,decisions,deliverables,messages,notifications,activity,llm,control,files,workshop,orders', { withCredentials: true });
      es.onopen = () => { retry = 0; setState('live'); };
      es.onerror = () => {
        setState('offline');
        es?.close();
        if (closed) return;
        retry = Math.min(retry + 1, 6);
        timer = setTimeout(open, 1000 * 2 ** retry);
      };
      es.onmessage = (m) => handle(m);
      for (const t of EVENT_TYPES) es.addEventListener(t, handle as EventListener);
    };
    const handle = (m: MessageEvent) => {
      let e: StreamEvent;
      try { e = JSON.parse(m.data) as StreamEvent; } catch { return; }
      for (const [prefix, keys] of INVALIDATE) if (e.type.startsWith(prefix)) for (const k of keys) void qc.invalidateQueries({ queryKey: [k] });
      cb.current?.(e);
    };
    open();
    return () => { closed = true; if (timer) clearTimeout(timer); es?.close(); };
  }, [qc]);

  return state;
}
