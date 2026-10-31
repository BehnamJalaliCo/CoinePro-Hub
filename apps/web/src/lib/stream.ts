'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { isMock } from './api/client';

export type StreamEvent = { id: string; type: string; at: string; company: string | null; ref: string | null; data: Record<string, unknown> };

// ⟨0.9.1⟩ One connection for every topic (`topics=all`, the hub accepts it from ⟨1.7.5⟩), read with fetch rather than EventSource: every
// named event reaches the panel (EventSource gives a named event only to a listener of that exact name, so a type the panel did not list
// was lost), and a reconnect sends `Last-Event-ID` itself (the hub reads only the header and resumes from that JetStream sequence), so
// nothing that happened while the hub restarted or the network dropped is missed. The Android app reads the stream the same way.
export const STREAM_PATH = '/api/v1/stream?topics=all';
/** No byte (not even the hub's heartbeat comment) for this long: the connection is dead even if the socket says otherwise. */
const SILENCE_MS = 45_000;

// Event type prefix -> query keys to refresh (contract §7, §16).
const INVALIDATE: Array<[string, Array<string | readonly string[]>]> = [
  ['decision.', ['decisions', 'inbox', 'away']],
  ['deliverable.', ['deliverables', 'inbox']],
  ['work.', ['work', 'planner', 'companies']],
  ['message.', ['threads', 'messages', 'inbox']],
  ['notification.', ['notifications', 'inbox']],
  ['control.', ['control', 'companies']],
  ['employee.', ['employees', 'companies']],
  ['presence.', ['presence', 'inbox']],
  ['budget.', ['treasury']],
  // A model call changes the day's totals and the call list, not every treasury view (connections, budgets, what-if).
  ['llm.', [['treasury', 'summary'], ['treasury', 'calls'], ['treasury', 'quota']]],
  ['run.', ['runs']],
  // ⟨1.9⟩ `work.council` is covered by `work.` (the council query lives under `work`).
  // ⟨1.9⟩ `file.transcribed`: the hub's transcript of a voice message (§27.3).
  ['file.', ['messages', 'files']],
  ['workshop.', ['workshop']],
  ['order.', ['orders', 'planner', 'work']],
  ['hiring.', ['hiring']],
  ['story.', ['stories']],
  ['oversight.', ['oversight']],
  ['inquiry.', ['inquiries']],
  ['errand.', ['errands']],
  ['stars.', ['stars']],
  ['skill.', ['skills']],
  ['academy.', ['academy']],
  ['founding.', ['founding']],
  ['provision.', ['founding']],
  ['backup.', ['backups']],
  // A traced or sealed brand: the company's versions, every mark and seal (GET /brands), and the founding's step.
  ['brand.', ['brand', 'brands', 'companies', 'founding']],
  // ⟨1.10⟩ §28.2: a company's catalogue run moved on.
  ['catalogue.', [['companies', 'catalogue']]],
  // ⟨1.5⟩ §19.9: the radar, the desk (queue, conversations, channels), rescue and lifecycle sends, a closed NPS wave (its comments
  // reach the feedback inbox), and feedback items.
  ['revenue.', ['revenue']],
  ['support.', ['support']],
  ['rescue.', ['growth']],
  ['lifecycle.', ['growth']],
  ['nps.', ['growth', 'feedback']],
  ['feedback.', ['feedback']],
  // ⟨1.5⟩ §20.11: a meeting's turns, claims and whispers (the room and the planner); a sealed charter; a stale KPI (cards and the
  // scorecard); OKR and outcome updates; risks; calendar conflicts (the deploy cards carry them too); knowledge and its expiry.
  ['meeting.', ['meetings', 'planner']],
  ['charter.', ['charter']],
  ['kpi.', ['cards', 'scorecards', 'kpis']],
  ['okr.', ['okr']],
  ['outcome.', ['outcomes']],
  ['risk.', ['risks']],
  ['calendar.', ['calendar', 'planner', 'decisions']],
  ['knowledge.', ['knowledge']],
  // ⟨1.5⟩ §21.12: a memo is ready (the card shows it), a proactive note (thread A), an answer, the weekly review, a briefing, ranks and
  // the HR round (its cards), a note, a claim's verdict (the health board), a scored prediction, a substitute's state, a creative.
  // `decision.reminded` is covered by `decision.`.
  ['memo.', ['memos', 'decisions']],
  ['advisor.', ['advisor', 'messages', 'threads']],
  ['ask.', ['ask']],
  ['review.', ['reviews']],
  ['briefing.', ['briefings']],
  ['rankings.', ['rankings']],
  ['hr.', ['hr', 'decisions']],
  ['note.', ['notes']],
  ['claim.', ['claims', 'runs-health']],
  ['dceo.', ['dceo', 'decisions']],
  ['substitute.', ['substitutes', 'treasury']],
  ['creative.', ['creatives']],
  // ⟨1.6⟩ §22.6: an item moved in the pipeline (the board, its series, the cards it raised); a case changed (its thread L and its email
  // cards); a role written on demand changed state (the department's roles, GET /roles for hiring, the story it makes).
  ['media.', ['media', 'decisions']],
  ['legal.', ['legal', 'threads', 'decisions']],
  ['role.', ['roles', 'stories', 'decisions']],
  // ⟨1.7⟩ §23.11: a record filed, changed or sealed; a reminder due; a hold placed or released (its case too); a fixity failure; a schema change.
  ['record.', ['archive']],
  ['reminder.', ['archive']],
  ['hold.', ['archive', 'legal']],
  ['fixity.', ['archive']],
  ['schema.', ['archive', 'decisions']],
  // ⟨1.8⟩ §26.4: a server's runner changed state (the network map too), a job started or ended, a destructive command waits for the seal.
  ['server.awaiting_seal', ['decisions', 'inbox']],
  ['server.state', ['network']],
  ['server.', ['servers']],
];

export type StreamState = 'connecting' | 'live' | 'offline';

/** The query keys an event refreshes (a prefix each). */
export function keysFor(type: string): Array<readonly string[]> {
  const out: Array<readonly string[]> = [];
  for (const [prefix, keys] of INVALIDATE) if (type.startsWith(prefix)) for (const k of keys) out.push(typeof k === 'string' ? [k] : k);
  return out;
}

/** An SSE message as the panel uses it: the hub's envelope, its type from the `event:` line when the data leaves it out. */
export function eventOf(m: { event: string | null; data: string; id: string | null }): StreamEvent | null {
  if (!m.data) return null;
  let o: Partial<StreamEvent>;
  try { o = JSON.parse(m.data) as Partial<StreamEvent>; } catch { return null; }
  const type = o.type ?? m.event;
  if (!type || type === 'message') return null;
  return { id: String(o.id ?? m.id ?? ''), type, at: o.at ?? new Date().toISOString(), company: o.company ?? null, ref: o.ref ?? null, data: o.data ?? {} };
}

type Line = { event: string | null; data: string; id: string | null };
/** A minimal SSE reader (the WHATWG rules the panel needs): `event`, `data` (joined), `id`; comments and `retry` are skipped. */
class Reader {
  private event: string | null = null;
  private id: string | null = null;
  private data: string[] = [];
  private rest = '';
  push(chunk: string, emit: (m: Line) => void) {
    const lines = (this.rest + chunk).split(/\r\n|\n|\r/);
    this.rest = lines.pop() ?? '';
    for (const l of lines) {
      if (!l) { if (this.data.length || this.event) emit({ event: this.event, data: this.data.join('\n'), id: this.id }); this.event = null; this.data = []; this.id = null; continue; }
      if (l.startsWith(':')) continue;
      const i = l.indexOf(':');
      const k = i < 0 ? l : l.slice(0, i);
      const v = i < 0 ? '' : l.slice(i + 1).replace(/^ /, '');
      if (k === 'event') this.event = v; else if (k === 'data') this.data.push(v); else if (k === 'id' && !v.includes('\0')) this.id = v;
    }
  }
}

/**
 * Keeps one connection to the hub's stream for as long as [signal] lives: reconnects with a growing pause (1 s doubling to 32 s, a little
 * jitter, at once when the browser comes back online) and resumes from the last event id it saw. [onState] hears live and offline.
 */
export function runStream(onEvent: (e: StreamEvent) => void, onState: (s: StreamState) => void, signal: AbortSignal, url: string = STREAM_PATH) {
  let lastId: string | null = null;
  let failures = 0;
  let wake: (() => void) | null = null;
  const online = () => wake?.();
  window.addEventListener('online', online);
  signal.addEventListener('abort', () => { window.removeEventListener('online', online); wake?.(); });
  const pause = (ms: number) => new Promise<void>((r) => { const t = setTimeout(() => { wake = null; r(); }, ms); wake = () => { clearTimeout(t); wake = null; r(); }; });
  void (async () => {
    while (!signal.aborted) {
      const ctl = new AbortController();
      const stop = () => ctl.abort();
      signal.addEventListener('abort', stop);
      let watchdog: ReturnType<typeof setTimeout> | undefined;
      const quiet = () => { clearTimeout(watchdog); watchdog = setTimeout(stop, SILENCE_MS); };
      let opened = false;
      try {
        const headers: Record<string, string> = { Accept: 'text/event-stream' };
        if (lastId) headers['Last-Event-ID'] = lastId;
        quiet();
        const res = await fetch(url, { headers, credentials: 'same-origin', cache: 'no-store', signal: ctl.signal });
        if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
        opened = true;
        failures = 0;
        onState('live');
        const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
        const sse = new Reader();
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          quiet();
          sse.push(value, (m) => {
            if (m.id) lastId = m.id;
            const e = eventOf(m);
            if (e) onEvent(e);
          });
        }
      } catch { /* dropped, refused or aborted: reconnect below */ }
      finally { clearTimeout(watchdog); signal.removeEventListener('abort', stop); }
      if (signal.aborted) return;
      // A stream that ended cleanly is reconnected before anyone would notice; only a failed attempt shows the panel offline.
      if (!opened) onState('offline');
      // A stream that ended after it opened (a deploy closing it) comes back at once; a failing one waits longer each time.
      const wait = opened ? 500 : Math.min(1000 * 2 ** failures, 32_000) * (0.8 + Math.random() * 0.4);
      if (!opened) failures = Math.min(failures + 1, 5);
      await pause(wait);
    }
  })();
}

/** Coalesces refreshes: each query key at most once per [ms] while events keep coming. */
function coalescer(run: (key: readonly string[]) => void, ms = 1000) {
  const pending = new Map<string, readonly string[]>();
  let timer: ReturnType<typeof setTimeout> | null = null;
  return (keys: Array<readonly string[]>) => {
    for (const k of keys) pending.set(k.join('\u0000'), k);
    if (timer || !pending.size) return;
    timer = setTimeout(() => { timer = null; const all = [...pending.values()]; pending.clear(); for (const k of all) run(k); }, ms);
  };
}

/** Whether the demo should read the real stream (the e2e checks of the stream code set it; the demo's own beat stops then). */
const realStreamInMock = () => { try { return isMock && typeof window !== 'undefined' && window.localStorage.getItem('hq.e2e.stream') === '1'; } catch { return false; } };

/** The app's one SSE connection (every topic), resuming with Last-Event-ID; each event refreshes its queries, coalesced. */
export function useHoldingStream(onEvent?: (e: StreamEvent) => void): StreamState {
  const qc = useQueryClient();
  const [state, setState] = useState<StreamState>(isMock ? 'live' : 'connecting');
  const cb = useRef(onEvent);
  useLayoutEffect(() => { cb.current = onEvent; });

  useEffect(() => {
    const refresh = coalescer((key) => void qc.invalidateQueries({ queryKey: key }));
    const handle = (e: StreamEvent) => { refresh(keysFor(e.type)); cb.current?.(e); };
    if (isMock && !realStreamInMock()) {
      let n = 0;
      const t = setInterval(() => {
        n += 1;
        cb.current?.({ id: String(n), type: 'activity.changed', at: new Date().toISOString(), company: ['TY', 'FX', 'PC'][n % 3] ?? null, ref: null, data: { pulse: n } });
        // ⟨1.8⟩ the demo's `servers` topic: what the owner's calls caused, the agents' calls, the runners' answers to a network check.
        if (process.env.NEXT_PUBLIC_HQ_MOCK === '1') {
          void import('@/lib/api/mock').then((m) => { for (const e of m.drainServerEvents() as StreamEvent[]) handle(e); });
          // 0.3.0–0.6.0: the demo holding's runs, outputs and cards, the owner's orders moving on, and (with the tab hidden) its alerts.
          void import('@/lib/api/mock-v21').then((m) => { for (const e of m.tick21() as StreamEvent[]) handle(e); });
        }
      }, 2400);
      return () => clearInterval(t);
    }
    const ctl = new AbortController();
    runStream(handle, setState, ctl.signal);
    return () => ctl.abort();
  }, [qc]);

  return state;
}
