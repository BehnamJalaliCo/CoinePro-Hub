'use client';

// ⟨1.24⟩ Contract §42 «the holding live: one stream the whole app moves with»: `GET /live/summary` (the seed every live view starts from,
// with the stream's sequence to resume after) and the shapes of the five new events and the additive `server.state`. Until the OpenAPI file
// carries them the shapes live here, written from §42 exactly. A hub from before §42 answers 404/405/501: the hook answers null, the views
// show «—» and the stream starts live (no resume point). Missing data is null, shown «—», never zero.

import { useQuery } from '@tanstack/react-query';
import { call } from './v13';
import { notServed } from './v28';

type N = number | null;

// ============================================================================================== §42.3 the seed ==
export type CompanyState42 = 'ok' | 'busy' | 'stuck' | 'locked';
export type LiveCompany = {
  code: string; name_fa: string | null; working: N; total: N; sessions_open: N; servers_online: N; servers_total: N;
  spend_today_usd: N; last_event_at: string | null; state: CompanyState42 | null;
};
export type LiveSummary = {
  /** The stream's last sequence when read: the stream resumes exactly after it (`Last-Event-ID`). */
  seq: number | string | null;
  at: string;
  people: { working: N; thinking: N; waiting: N; stuck: N; total: N };
  sessions: { moving: N; your_turn: N; stuck: N; ready: N };
  approvals: N;
  urgent_unread: N;
  servers: { online: N; offline: N; total: N };
  tokens: { today: N; effective_today: N; per_min: N; equiv_usd_today: N; budget_usd: N };
  control: { holding: boolean; companies_locked: string[] };
  companies: LiveCompany[];
};

export const liveSummary = () => call<LiveSummary>('GET', '/live/summary');

/** `GET /live/summary`: once on open, again every two minutes (the counts are folded from the stream in between). Null before §42. */
export const useLiveSummary = () => useQuery({
  queryKey: ['live', 'summary'], staleTime: 60_000, refetchInterval: 120_000, refetchOnWindowFocus: true,
  queryFn: async (): Promise<LiveSummary | null> => { try { return await liveSummary(); } catch (e) { if (notServed(e)) return null; throw e; } },
});

// ============================================================================================= §42.2 the events ==
export type LineKind = 'start' | 'step' | 'end' | 'wake' | 'ask' | 'join' | 'task' | 'memory';
export type LineState = 'running' | 'done' | 'failed';
/** `session.activity` (topic `orders`), additive to §41.1: `line.id` = run id + step n, so a step's end updates its line. */
export type SessionActivity42 = {
  order: string; working: number;
  line: { id?: string | null; at: string; who_fa: string; company?: string | null; text_fa: string; kind?: LineKind | null; state?: LineState | null; task_n?: number | null };
};

export type FlowKind = 'order' | 'request' | 'accept' | 'deliver' | 'read' | 'playbook' | 'publish';
/** `holding.flow` (topic `holding`): `from`/`to` = "hub", a company code, or "outside". */
export type HoldingFlow = { from: string; to: string; kind: FlowKind; via: 'hub'; ref: string; root_ref: string | null; label_fa: string | null };

/** `network.link` (topic `servers`): a measured link changed `ok` or crossed the slow threshold. */
export type NetworkLink42 = { from: string; to: string; port: number | null; ok: boolean; ms: N; error_fa: string | null; since: string; last_ok_at: string | null };

export type PersonState = 'idle' | 'thinking' | 'working' | 'waiting' | 'stuck' | 'done';
/** `employee.state` (topic `activity`): at most one per employee per 2 s (`stuck` and `done` at once). */
export type EmployeeState42 = {
  employee: string; company: string; department: string | null; state: PersonState; since: string;
  work_ref: string | null; root_ref: string | null; stuck_fa: string | null;
};

export type TokenSplit = { input: number; output: number; cache_read: number; cache_write: number; thinking: number };
/** `llm.tick` (topic `llm`): every 5 s for each company that had a call in the window; nothing when idle. */
export type LlmTick = {
  company: string; window_s: number; calls: number; in_flight: number; tokens: TokenSplit; equiv_usd: number;
  day: { tokens: number; effective_tokens: number; equiv_usd: number; budget_usd: N; pct: N };
};

export type ServerReason = 'no_poll' | 'runner_stopped' | 'server_unreachable' | 'revoked' | 'fallback_public' | 'slow';
/** `server.state` (topic `servers`) with §42.2's additive fields. A client never infers offline from silence. */
export type ServerState42 = {
  server: string; company?: string | null; state: string; via?: 'private' | 'public' | null;
  prev_state?: string | null; since?: string | null; reason?: ServerReason | null; reason_fa?: string | null; hub_rtt_ms?: N; open_jobs?: N;
};
