'use client';

// ⟨1.23⟩ Contract §41 «the session shows its work live and never stalls»: what the session is doing right now (`GET /orders/{ref}/activity`,
// kept fresh by the stream's `session.activity`), and «ادامه بده» (`POST /orders/{ref}/nudge`). Until the OpenAPI file carries them the shapes
// live here, written from §41. A hub from before §41 answers 404/405/501: the hook answers null and the page shows no panel.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { call } from './v13';
import { notServed } from './v28';
import { useLive } from '@/lib/live';

const enc = encodeURIComponent;

/** ⟨1.0.1⟩ §55.1 «چراغ حال»: the session's mood, by the hub's own code. */
export type Mood = 'thinking' | 'working' | 'waiting' | 'stuck' | 'idle';
/** ⟨1.0.1⟩ §55.1 what works: an agent's run, the workshop's turn, the holder's own direct turn (§54), a company server's turn;
 *  ⟨2026-11-11⟩ an outside model or voice working for the session (`call`: ChatGPT drafting the text, the AI narrator), its
 *  `started_at` the moment it was asked and its `cap_s` its deadline. */
export type WorkerKind = 'run' | 'workshop' | 'direct' | 'server' | 'call';
/**
 * ⟨1.0.1⟩ §55.1 adds `kind`, `cap_s` (a turn's time cap in seconds, null for a run: the build ring fills against it) and `last_fa`,
 * `last_at` (the last thing a live turn did, in the owner's words; null when it said nothing he can read: `doing_fa` is shown). An
 * older hub sends none of them.
 */
export type Worker = {
  who_fa: string; company_fa: string; work_title_fa: string; started_at: string; step: number; doing_fa: string;
  kind?: WorkerKind | null; cap_s?: number | null; last_fa?: string | null; last_at?: string | null;
};
/** ⟨1.24⟩ §42.2 adds `id` (run id + step n: a step's end updates its own line), `kind`, `state` and `task_n`; an older hub sends none. */
export type ActivityLine = {
  at: string; who_fa: string; text_fa: string;
  id?: string | null; company?: string | null; kind?: 'start' | 'step' | 'end' | 'wake' | 'ask' | 'join' | 'task' | 'memory' | null;
  state?: 'running' | 'done' | 'failed' | null; task_n?: number | null;
};

/** The lines after one more: a line whose id is known replaces it where it stands (the step ended); a new one goes last. */
export function foldLine(lines: ActivityLine[], line: ActivityLine): ActivityLine[] {
  if (line.id) {
    const i = lines.findIndex((l) => l.id === line.id);
    if (i >= 0) return lines.map((l, k) => (k === i ? { ...l, ...line, at: l.at } : l));
  } else if (lines.some((l) => l.at === line.at && l.text_fa === line.text_fa)) return lines;
  return [...lines, line].slice(-LINES_MAX);
}
/** ⟨1.0.1⟩ §55.1 adds `mood` and `mood_fa`; on an older hub the mood is read from the rest (stuck, waiting, working, else calm). */
export type SessionActivity = {
  working: Worker[]; last: ActivityLine[]; idle_since?: string | null; waiting_fa?: string | null; stuck_fa?: string | null;
  mood?: Mood | null; mood_fa?: string | null;
};

/** The hub keeps at most this many lines; so does the panel. */
export const LINES_MAX = 30;
const key = (ref: string) => ['orders', 'activity', ref] as const;

/** The activity of a session: one GET on open, then every `session.activity` of this order is folded in as it arrives. Null on a hub before §41. */
export function useSessionActivity(ref: string, on = true) {
  const qc = useQueryClient();
  const { feed } = useLive();
  const seen = useRef(new Set<string>());
  const q = useQuery({
    queryKey: key(ref), enabled: on, staleTime: 20_000, refetchInterval: on ? 30_000 : false,
    queryFn: async (): Promise<SessionActivity | null> => {
      try { return await call<SessionActivity>('GET', `/orders/${enc(ref)}/activity`); } catch (e) { if (notServed(e)) return null; throw e; }
    },
  });
  useEffect(() => {
    if (!on) return;
    for (const e of [...feed].reverse()) {
      if (e.type !== 'session.activity' || seen.current.has(e.id)) continue;
      seen.current.add(e.id);
      const d = e.data as { order?: string; line?: ActivityLine; working?: number };
      if ((d.order ?? e.ref) !== ref || !d.line) continue;
      const line = d.line;
      let drift = false;
      qc.setQueryData<SessionActivity | null>(key(ref), (a) => {
        if (!a) return a;
        const last = foldLine(a.last, line);
        if (last === a.last) return a;
        const n = d.working ?? a.working.length;
        // ⟨1.24⟩ A step's end only updates its line; a new step (or a line from an older hub) moves the worker on.
        const ended = !!line.id && last.length === a.last.length && a.last.some((l) => l.id === line.id);
        // ⟨1.0.1⟩ §55.1 a live turn (the workshop's, the holder's own) says its newest line as `last_fa`; a run moves to its next step.
        const working = n === 0 ? [] : ended ? a.working : a.working.map((w) => (w.who_fa !== line.who_fa ? w
          : w.kind === 'workshop' || w.kind === 'direct' ? { ...w, step: w.step + 1, last_fa: line.text_fa, last_at: line.at } : { ...w, step: w.step + 1, doing_fa: line.text_fa }));
        drift = n !== working.length;
        return { ...a, last, working, ...(n === 0 ? { idle_since: line.at } : { idle_since: null, stuck_fa: null }) };
      });
      // A worker started or ended that this copy does not know: look again.
      if (drift) void qc.invalidateQueries({ queryKey: key(ref) });
    }
    if (seen.current.size > 400) seen.current = new Set([...seen.current].slice(-100));
  }, [feed, on, qc, ref]);
  return q;
}

/** The key every «ادامه بده» of one session runs under (the session page ends the owner's hold on any of them that succeeds). */
export const nudgeKey = (ref: string) => ['orders', 'nudge', ref] as const;

/** «ادامه بده»: the holder is woken now with the plan's next task; the answer is the new activity. */
export function useNudge(ref: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: nudgeKey(ref),
    mutationFn: () => call<SessionActivity>('POST', `/orders/${enc(ref)}/nudge`, {}, { 'Idempotency-Key': crypto.randomUUID() }),
    onSuccess: (a) => { if (a) qc.setQueryData(key(ref), a); },
    onSettled: () => Promise.all(['orders', 'office', 'talk'].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}
