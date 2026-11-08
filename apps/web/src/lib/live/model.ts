// ⟨1.24⟩ K-2, the live model (design/LIVE_VIEWS.md §2.1, contract §42): the state every live view reads, seeded from `GET /live/summary`
// and moved by the stream's events, one reducer per view. Pure functions only (no React, no DOM): lib/live/store.tsx runs them, the e2e
// unit checks (e2e/live-model.spec.ts) prove them.
//
// Counts are the summary's, moved by deltas: an event says the new state of one employee, session or server; the delta needs the state it
// left, which is the last one this model saw (or the event's own `prev_state`). When neither is known the event adds to its new bucket and
// takes from none; the summary is read again every two minutes and on every return of the stream, so a guess never lasts. Missing data stays
// null («—»), never zero. ⟨§42.5⟩ Money arrives as a 6-place decimal string; the model holds it as a number of dollars (sums kept to the
// micro-dollar) and the views write it with format.usd.

import type { StreamEvent } from '@/lib/stream';
import type {
  CompanyState42, EmployeeState42, HoldingFlow, LiveSummary, LlmTick, NetworkLink42, PersonState, ServerState42, SessionActivity42,
} from '@/lib/api/v42';
import type { MotionColor } from './particles';

type N = number | null;
export type Badge = 'moving' | 'your_turn' | 'stuck' | 'ready' | 'closed';
const COUNTED: Badge[] = ['moving', 'your_turn', 'stuck', 'ready'];
export const BUSY: PersonState[] = ['thinking', 'working'];
const PEOPLE_BUCKETS: PersonState[] = ['working', 'thinking', 'waiting', 'stuck'];
export const PERSON_STATES: PersonState[] = ['thinking', 'working', 'waiting', 'stuck', 'done', 'idle'];

export type CompanyLive = {
  code: string; name_fa: string | null; working: N; total: N; sessions_open: N; servers_online: N; servers_total: N;
  spend_today_usd: N; budget_usd: N; last_event_at: string | null; state: CompanyState42 | null;
  /** Model calls in flight at the last `llm.tick`, and when that was (ms). */
  in_flight: number; in_flight_at: number;
  /** When each flow touching it happened (ms), the last hour. */
  flows: number[];
};
export type EmployeeLive = {
  id: string; company: string | null; department: string | null; state: PersonState; since: string | null;
  stuck_fa: string | null; work_ref: string | null; root_ref: string | null; at: string;
};
export type ServerLive = {
  id: string; company: string | null; state: string; prev_state: string | null; via: string | null; since: string | null;
  reason: string | null; reason_fa: string | null; hub_rtt_ms: N; open_jobs: N; at: string;
  /** Jobs running on it now (`server.call running` less those that ended), and when the last one failed. */
  jobs: number; failed_at: string | null;
};
export type LinkLive = NetworkLink42 & { key: string; at: string };
export type SessionLive = { ref: string; badge: Badge | null; company: string | null; at: string; last_step_at: string | null; woke_at: string | null };
export type TokenKinds = { input: number; output: number; cache: number; thinking: number };
export type Tick = { at: number; company: string; tokens: number };

export type LiveState = {
  seeded: boolean;
  /** The highest stream sequence applied (or the seed's). */
  seq: number | null;
  /** When the summary was read (ms). */
  seed_at: number | null;
  people: { working: N; thinking: N; waiting: N; stuck: N; total: N };
  sessions: { moving: N; your_turn: N; stuck: N; ready: N };
  approvals: N;
  urgent_unread: N;
  servers: { online: N; offline: N; total: N };
  tokens: { today: N; effective_today: N; per_min: N; equiv_usd_today: N; budget_usd: N; kinds: TokenKinds | null; ticks: Tick[]; ticked: boolean };
  control: { holding: boolean | null; holding_at: string | null; holding_by: string | null; locked: Record<string, { at: string | null; by: string | null }> };
  /** Companies in the summary's order (data order, never alphabetical). */
  order: string[];
  companies: Record<string, CompanyLive>;
  employees: Record<string, EmployeeLive>;
  servers_by_id: Record<string, ServerLive>;
  links: Record<string, LinkLive>;
  sessions_by_ref: Record<string, SessionLive>;
  last_event_at: string | null;
};

export const EMPTY: LiveState = {
  seeded: false, seq: null, seed_at: null,
  people: { working: null, thinking: null, waiting: null, stuck: null, total: null },
  sessions: { moving: null, your_turn: null, stuck: null, ready: null },
  approvals: null, urgent_unread: null,
  servers: { online: null, offline: null, total: null },
  tokens: { today: null, effective_today: null, per_min: null, equiv_usd_today: null, budget_usd: null, kinds: null, ticks: [], ticked: false },
  control: { holding: null, holding_at: null, holding_by: null, locked: {} },
  order: [], companies: {}, employees: {}, servers_by_id: {}, links: {}, sessions_by_ref: {}, last_event_at: null,
};

// ------------------------------------------------------------------------------------------------------ helpers --
const num = (v: unknown): N => (typeof v === 'number' && Number.isFinite(v) ? v : typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v)) ? Number(v) : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);
/** A count moved by [d], never below zero; a missing count stays missing. */
const add = (v: N, d: number): N => (v == null || d === 0 ? v : Math.max(0, v + d));
const ms = (iso: string | null | undefined) => { const t = iso ? Date.parse(iso) : NaN; return Number.isFinite(t) ? t : 0; };
const later = (a: string | null, b: string | null) => (!a ? b : !b ? a : ms(b) >= ms(a) ? b : a);
const isBadge = (v: unknown): v is Badge => typeof v === 'string' && ['moving', 'your_turn', 'stuck', 'ready', 'closed'].includes(v);
const isPerson = (v: unknown): v is PersonState => typeof v === 'string' && (PERSON_STATES as string[]).includes(v);
/** The stream sequence of an event (its SSE id), when it has one. */
export const seqOf = (e: { seq?: number | null; id?: string }) => (e.seq != null && Number.isFinite(e.seq) ? e.seq : null);

function company(s: LiveState, code: string): CompanyLive | null { return s.companies[code] ?? null; }
function setCompany(s: LiveState, c: CompanyLive): LiveState { return { ...s, companies: { ...s.companies, [c.code]: c } }; }
const blankCompany = (code: string): CompanyLive => ({
  code, name_fa: null, working: null, total: null, sessions_open: null, servers_online: null, servers_total: null, spend_today_usd: null, budget_usd: null,
  last_event_at: null, state: null, in_flight: 0, in_flight_at: 0, flows: [],
});

// ------------------------------------------------------------------------------------------------------- seeds --
/** The summary read from the hub (§42.3): every count replaced; what the stream told about single things is kept. A null `seq` (the hub's
 *  event bus is down) keeps the sequence already known. */
export function seedSummary(prev: LiveState, sum: LiveSummary): LiveState {
  const seq = sum.seq == null ? null : num(sum.seq);
  const companies: Record<string, CompanyLive> = { ...prev.companies };
  for (const c of sum.companies ?? []) {
    const old = prev.companies[c.code] ?? blankCompany(c.code);
    companies[c.code] = {
      ...old, code: c.code, name_fa: c.name_fa ?? old.name_fa, working: num(c.working), total: num(c.total), sessions_open: num(c.sessions_open),
      servers_online: num(c.servers_online), servers_total: num(c.servers_total), spend_today_usd: num(c.spend_today_usd) ?? old.spend_today_usd,
      last_event_at: later(old.last_event_at, c.last_event_at ?? null), state: c.state ?? null,
    };
  }
  const lockedNow = new Set(sum.control?.companies_locked ?? []);
  const locked: LiveState['control']['locked'] = {};
  for (const code of lockedNow) locked[code] = prev.control.locked[code] ?? { at: null, by: null };
  const holding = sum.control ? !!sum.control.holding : prev.control.holding;
  return {
    ...prev, seeded: true, seq: seq != null ? Math.max(seq, prev.seq ?? seq) : prev.seq, seed_at: ms(sum.at) || Date.now(),
    people: { working: num(sum.people?.working), thinking: num(sum.people?.thinking), waiting: num(sum.people?.waiting), stuck: num(sum.people?.stuck), total: num(sum.people?.total) },
    sessions: { moving: num(sum.sessions?.moving), your_turn: num(sum.sessions?.your_turn), stuck: num(sum.sessions?.stuck), ready: num(sum.sessions?.ready) },
    approvals: num(sum.approvals), urgent_unread: num(sum.urgent_unread),
    servers: { online: num(sum.servers?.online), offline: num(sum.servers?.offline), total: num(sum.servers?.total) },
    tokens: {
      ...prev.tokens, today: num(sum.tokens?.today), effective_today: num(sum.tokens?.effective_today), per_min: num(sum.tokens?.per_min),
      equiv_usd_today: num(sum.tokens?.equiv_usd_today), budget_usd: num(sum.tokens?.budget_usd),
    },
    control: { ...prev.control, holding, holding_at: holding === prev.control.holding ? prev.control.holding_at : null, holding_by: holding === prev.control.holding ? prev.control.holding_by : null, locked },
    order: (sum.companies ?? []).map((c) => c.code),
    companies,
  };
}

/** The sessions list (`GET /sessions`) tells each session's badge: the state an event's delta starts from. Counts are not touched. */
export function seedSessions(prev: LiveState, cards: Array<{ ref: string; badge: string; last_at: string; holder?: { company: string } | null }>): LiveState {
  let by = prev.sessions_by_ref;
  for (const c of cards) {
    const old = by[c.ref];
    if (old && ms(old.at) > ms(c.last_at)) continue;
    if (!isBadge(c.badge)) continue;
    by = { ...by, [c.ref]: { ref: c.ref, badge: c.badge, company: c.holder?.company ?? old?.company ?? null, at: c.last_at, last_step_at: later(old?.last_step_at ?? null, c.last_at), woke_at: old?.woke_at ?? null } };
  }
  return by === prev.sessions_by_ref ? prev : { ...prev, sessions_by_ref: by };
}

/** The employees list tells each person's state (§29.14): the dots of a company card start from it. Counts are not touched. */
export function seedPeople(prev: LiveState, list: Array<{ code: string; company: string; department?: string | null; state?: string | null; activity?: string | null; activity_at?: string | null }>): LiveState {
  let emp = prev.employees;
  for (const e of list) {
    if (emp[e.code]) continue;
    const st: PersonState = isPerson(e.state) ? e.state : e.activity === 'working' ? 'working' : e.activity === 'waiting' ? 'waiting' : e.activity === 'error' ? 'stuck' : 'idle';
    emp = { ...emp, [e.code]: { id: e.code, company: e.company, department: e.department ?? null, state: st, since: e.activity_at ?? null, stuck_fa: null, work_ref: null, root_ref: null, at: e.activity_at ?? '' } };
  }
  return emp === prev.employees ? prev : { ...prev, employees: emp };
}

/** Today's tokens by kind (`GET /treasury/summary?period=day`): the meter's four segments start from it; ticks add to it. */
export function seedTokenKinds(prev: LiveState, t: { input_tokens: number; output_tokens: number; cache_read_tokens: number; cache_write_tokens: number; thinking_tokens: number }): LiveState {
  return { ...prev, tokens: { ...prev.tokens, kinds: { input: t.input_tokens, output: t.output_tokens, cache: t.cache_read_tokens + t.cache_write_tokens, thinking: t.thinking_tokens } } };
}

// ----------------------------------------------------------------------------------------------- the reducers --
// One per view. They run in this order on every event: the counting views (pulse, companies, network counts) read the state a thing is
// leaving from the maps, which the atom reducers (sessions, people) update last.

/** OF-1 «نبض دفتر»: people at work, sessions by badge, what waits for the owner. */
export function reducePulse(s: LiveState, e: StreamEvent): LiveState {
  if (e.type === 'employee.state') {
    const d = e.data as Partial<EmployeeState42>;
    if (!d.employee || !isPerson(d.state)) return s;
    const prev = s.employees[d.employee]?.state ?? null;
    if (prev === d.state) return s;
    const p = { ...s.people };
    if (prev && (PEOPLE_BUCKETS as string[]).includes(prev)) p[prev as 'working'] = add(p[prev as 'working'], -1);
    if ((PEOPLE_BUCKETS as string[]).includes(d.state)) p[d.state as 'working'] = add(p[d.state as 'working'], 1);
    return { ...s, people: p };
  }
  if (e.type === 'session.updated') {
    const ref = str(e.data.ref) ?? e.ref;
    const badge = e.data.badge;
    if (!ref || !isBadge(badge)) return s;
    const prev = s.sessions_by_ref[ref]?.badge ?? null;
    if (prev === badge) return s;
    const c = { ...s.sessions };
    if (prev && prev !== 'closed') c[prev] = add(c[prev], -1);
    if (badge !== 'closed') c[badge] = add(c[badge], 1);
    return { ...s, sessions: c };
  }
  if (e.type === 'decision.created') return { ...s, approvals: add(s.approvals, 1) };
  if (e.type === 'decision.decided') return { ...s, approvals: add(s.approvals, -1) };
  if (e.type === 'notification.created' && e.data.level === 'urgent') return { ...s, urgent_unread: add(s.urgent_unread, 1) };
  return s;
}

/** CO-1 «کارت زنده‌ی شرکت»: each company's people at work, open sessions, servers, today's spend and its last event. */
export function reduceCompanies(s: LiveState, e: StreamEvent): LiveState {
  let out = s;
  const at = e.at || null;
  if (e.company && out.companies[e.company]) {
    const c = out.companies[e.company]!;
    if (at && ms(at) > ms(c.last_event_at)) out = setCompany(out, { ...c, last_event_at: at });
  }
  if (e.type === 'employee.state') {
    const d = e.data as Partial<EmployeeState42>;
    const code = d.company ?? e.company;
    const c = code ? company(out, code) : null;
    if (!c || !d.employee || !isPerson(d.state)) return out;
    const prev = out.employees[d.employee]?.state ?? null;
    const was = prev != null && BUSY.includes(prev);
    const is = BUSY.includes(d.state);
    if (prev === d.state || was === is) return out;
    return setCompany(out, { ...c, working: c.total != null && c.working != null ? Math.min(c.total, Math.max(0, c.working + (is ? 1 : -1))) : add(c.working, is ? 1 : -1) });
  }
  if (e.type === 'session.updated') {
    const ref = str(e.data.ref) ?? e.ref;
    const c = e.company ? company(out, e.company) : null;
    if (!ref || !c || !isBadge(e.data.badge)) return out;
    const prev = out.sessions_by_ref[ref]?.badge ?? null;
    const wasOpen = prev != null && prev !== 'closed';
    const isOpen = e.data.badge !== 'closed';
    if (wasOpen === isOpen && prev != null) return out;
    if (prev == null && !isOpen) return out;
    return setCompany(out, { ...c, sessions_open: add(c.sessions_open, isOpen ? 1 : -1) });
  }
  if (e.type === 'server.state') {
    const d = e.data as Partial<ServerState42>;
    const id = d.server ?? e.ref;
    const code = d.company ?? e.company;
    const c = code ? company(out, code) : null;
    if (!id || !c || !d.state) return out;
    const prev = out.servers_by_id[id]?.state ?? d.prev_state ?? null;
    if (prev == null || prev === d.state) return out;
    const delta = (d.state === 'online' ? 1 : 0) - (prev === 'online' ? 1 : 0);
    return delta ? setCompany(out, { ...c, servers_online: add(c.servers_online, delta) }) : out;
  }
  if (e.type === 'llm.tick') {
    const d = e.data as Partial<LlmTick>;
    const code = d.company ?? e.company;
    if (!code) return out;
    const c = company(out, code) ?? blankCompany(code);
    return setCompany(out, { ...c, spend_today_usd: num(d.day?.equiv_usd) ?? c.spend_today_usd, budget_usd: d.day ? num(d.day.budget_usd) : c.budget_usd, in_flight: num(d.in_flight) ?? 0, in_flight_at: ms(e.at) });
  }
  if (e.type === 'holding.flow') {
    const d = e.data as Partial<HoldingFlow>;
    const t = ms(e.at);
    for (const code of [d.from, d.to]) {
      const c = code ? company(out, code) : null;
      if (c) out = setCompany(out, { ...c, flows: [...c.flows.filter((x) => t - x < 3_600_000), t].slice(-200) });
    }
    return out;
  }
  return out;
}

/** MO-1 «کنتور توکن»: today's tokens and dollars, by kind, and the burn rate. */
export function reduceTokens(s: LiveState, e: StreamEvent): LiveState {
  if (e.type !== 'llm.tick') return s;
  const d = e.data as Partial<LlmTick>;
  const t = d.tokens;
  if (!t || !d.company) return s;
  const total = (t.input ?? 0) + (t.output ?? 0) + (t.cache_read ?? 0) + (t.cache_write ?? 0) + (t.thinking ?? 0);
  const at = ms(e.at) || Date.now();
  const k = s.tokens.kinds;
  return {
    ...s,
    tokens: {
      ...s.tokens,
      today: add(s.tokens.today, total),
      effective_today: s.tokens.effective_today,
      equiv_usd_today: s.tokens.equiv_usd_today == null ? null : Math.round((s.tokens.equiv_usd_today + (num(d.equiv_usd) ?? 0)) * 1_000_000) / 1_000_000,
      kinds: k ? { input: k.input + (t.input ?? 0), output: k.output + (t.output ?? 0), cache: k.cache + (t.cache_read ?? 0) + (t.cache_write ?? 0), thinking: k.thinking + (t.thinking ?? 0) } : null,
      ticks: [...s.tokens.ticks.filter((x) => at - x.at < 70_000), { at, company: d.company, tokens: total }],
      ticked: true,
    },
  };
}

/** GL-2 «نوار کلید توقف»: the holding's switch and each company's. */
export function reduceControl(s: LiveState, e: StreamEvent): LiveState {
  if (e.type !== 'control.changed') return s;
  const k = str(e.data.kill_switch) ?? (['engaged', 'released'].includes(str(e.data.state) ?? '') ? str(e.data.state) : null);
  if (!k) return s;
  const scope = str(e.data.scope) ?? e.ref ?? 'holding';
  const by = str(e.data.by);
  if (scope === 'holding') return { ...s, control: { ...s.control, holding: k === 'engaged', holding_at: e.at, holding_by: by } };
  const code = scope.replace(/^company:/, '');
  const locked = { ...s.control.locked };
  if (k === 'engaged') locked[code] = { at: e.at, by }; else delete locked[code];
  return { ...s, control: { ...s.control, locked } };
}

/** HM-1, HM-3: each server's state with when and why, the jobs on it, and the measured links that fail. */
export function reduceNetwork(s: LiveState, e: StreamEvent): LiveState {
  if (e.type === 'server.state') {
    const d = e.data as Partial<ServerState42>;
    const id = d.server ?? e.ref;
    if (!id || !d.state) return s;
    const old = s.servers_by_id[id];
    const prev = old?.state ?? d.prev_state ?? null;
    const changed = prev != null && prev !== d.state;
    const srv: ServerLive = {
      id, company: d.company ?? e.company ?? old?.company ?? null, state: d.state, prev_state: d.prev_state ?? (changed ? prev : old?.prev_state ?? null),
      via: d.via ?? old?.via ?? null, since: d.since ?? (changed || !old ? e.at : old.since),
      // §42.5: the hub always says the reason (null when it has none, and then `reason_fa` is null too); an older hub leaves it out.
      reason: 'reason' in d ? d.reason ?? null : d.state === 'online' ? null : old?.reason ?? null,
      reason_fa: 'reason' in d ? (d.reason ? d.reason_fa ?? null : null) : d.state === 'online' ? null : old?.reason_fa ?? null,
      hub_rtt_ms: d.hub_rtt_ms !== undefined ? num(d.hub_rtt_ms) : old?.hub_rtt_ms ?? null,
      open_jobs: d.open_jobs !== undefined ? num(d.open_jobs) : old?.open_jobs ?? null, at: e.at, jobs: d.state === 'online' ? old?.jobs ?? 0 : 0, failed_at: old?.failed_at ?? null,
    };
    let servers = s.servers;
    if (changed) {
      const b = (x: string) => (x === 'online' ? 'online' : x === 'offline' ? 'offline' : null);
      const from = b(prev!), to = b(d.state);
      if (from !== to) servers = { ...servers, ...(from ? { [from]: add(servers[from], -1) } : {}), ...(to ? { [to]: add(servers[to], 1) } : {}) };
    }
    return { ...s, servers, servers_by_id: { ...s.servers_by_id, [id]: srv } };
  }
  if (e.type === 'server.call') {
    const id = str(e.data.server) ?? e.ref;
    const st = str(e.data.state);
    if (!id || !st) return s;
    const old = s.servers_by_id[id];
    const base: ServerLive = old ?? { id, company: e.company, state: 'online', prev_state: null, via: null, since: null, reason: null, reason_fa: null, hub_rtt_ms: null, open_jobs: null, at: e.at, jobs: 0, failed_at: null };
    const jobs = st === 'running' ? base.jobs + 1 : Math.max(0, base.jobs - 1);
    return { ...s, servers_by_id: { ...s.servers_by_id, [id]: { ...base, jobs, failed_at: st === 'failed' ? e.at : base.failed_at } } };
  }
  if (e.type === 'network.link') {
    const d = e.data as Partial<NetworkLink42>;
    if (!d.from || !d.to) return s;
    const key = `${d.from}>${d.to}${d.port != null ? `:${d.port}` : ''}`;
    const links = { ...s.links };
    if (d.ok === false) links[key] = { from: d.from, to: d.to, port: d.port ?? null, ok: false, ms: num(d.ms), error_fa: d.error_fa ?? null, since: d.since ?? e.at, last_ok_at: d.last_ok_at ?? null, key, at: e.at };
    else delete links[key];
    return { ...s, links };
  }
  return s;
}

/** SS-1 «نگهبان توقف»: each session's badge and when it last took a step (an atom: the counting views read it before it moves). */
export function reduceSessions(s: LiveState, e: StreamEvent): LiveState {
  if (e.type === 'session.updated') {
    const ref = str(e.data.ref) ?? e.ref;
    if (!ref || !isBadge(e.data.badge)) return s;
    const old = s.sessions_by_ref[ref];
    return { ...s, sessions_by_ref: { ...s.sessions_by_ref, [ref]: { ref, badge: e.data.badge, company: e.company ?? old?.company ?? null, at: e.at, last_step_at: old?.last_step_at ?? null, woke_at: old?.woke_at ?? null } } };
  }
  if (e.type === 'session.activity') {
    const d = e.data as Partial<SessionActivity42>;
    const ref = d.order ?? e.ref;
    if (!ref || !d.line) return s;
    const old = s.sessions_by_ref[ref];
    const at = d.line.at || e.at;
    return {
      ...s,
      sessions_by_ref: {
        ...s.sessions_by_ref,
        [ref]: { ref, badge: old?.badge ?? null, company: old?.company ?? e.company ?? null, at: old?.at ?? at, last_step_at: d.line.kind === 'wake' ? old?.last_step_at ?? null : later(old?.last_step_at ?? null, at), woke_at: d.line.kind === 'wake' ? at : old?.woke_at ?? null },
      },
    };
  }
  return s;
}

/** PE-1 «چراغ حال هر نفر»: each person's state, since when, and why when stuck (an atom, last). */
export function reducePeople(s: LiveState, e: StreamEvent): LiveState {
  if (e.type !== 'employee.state') return s;
  const d = e.data as Partial<EmployeeState42>;
  if (!d.employee || !isPerson(d.state)) return s;
  const old = s.employees[d.employee];
  return {
    ...s,
    employees: {
      ...s.employees,
      [d.employee]: {
        id: d.employee, company: d.company ?? e.company ?? old?.company ?? null, department: d.department ?? old?.department ?? null, state: d.state,
        since: d.since ?? e.at, stuck_fa: d.state === 'stuck' ? d.stuck_fa ?? null : null, work_ref: d.work_ref ?? null, root_ref: d.root_ref ?? null, at: e.at,
      },
    },
  };
}

export const REDUCERS = [reducePulse, reduceCompanies, reduceTokens, reduceControl, reduceNetwork, reduceSessions, reducePeople] as const;

/** One event through every view's reducer, in order. */
export function reduce(s: LiveState, e: StreamEvent): LiveState {
  let out = s;
  for (const r of REDUCERS) out = r(out, e);
  const q = seqOf(e);
  if (q != null && (out.seq == null || q > out.seq)) out = { ...out, seq: q };
  if (e.at && ms(e.at) > ms(out.last_event_at)) out = { ...out, last_event_at: e.at };
  return out;
}

// ----------------------------------------------------------------------------------------------- de-duplication --
/**
 * The stream's door: an event is taken once (by its id), and nothing the seed already counted (a sequence at or below the seed's) is taken
 * again. [limit] ids are remembered.
 */
export function createDedupe(limit = 2000) {
  const seen = new Set<string>();
  let floor: number | null = null;
  return {
    /** Sequences at or below [seq] are in the seed already. */
    floor(seq: number | null) { floor = seq; },
    accept(e: { id: string; seq?: number | null }): boolean {
      const q = seqOf(e);
      if (q != null && floor != null && q <= floor) return false;
      if (e.id) {
        if (seen.has(e.id)) return false;
        seen.add(e.id);
        if (seen.size > limit) { const keep = [...seen].slice(-Math.floor(limit / 2)); seen.clear(); for (const k of keep) seen.add(k); }
      }
      return true;
    },
  };
}

// ------------------------------------------------------------------------------------------------- selectors --
/** Tokens in the last minute: from the ticks once any came (zero when the holding is idle), the seed's figure until then. */
export function perMin(s: LiveState, now = Date.now()): N {
  const fresh = s.seed_at != null && now - s.seed_at < 60_000;
  if (!s.tokens.ticked && fresh) return s.tokens.per_min;
  if (!s.tokens.ticked && !s.seeded) return null;
  return s.tokens.ticks.filter((t) => now - t.at < 60_000).reduce((a, t) => a + t.tokens, 0);
}
/** Model calls in flight across the holding (a company's last tick counts for 10 s). */
export const inFlight = (s: LiveState, now = Date.now()) => Object.values(s.companies).reduce((a, c) => a + (now - c.in_flight_at < 10_000 ? c.in_flight : 0), 0);
/** «الان کار میکنند»: a model thinks or a tool works for them. */
export const peopleBusy = (s: LiveState): N => (s.people.working == null && s.people.thinking == null ? null : (s.people.working ?? 0) + (s.people.thinking ?? 0));
/** «منتظر تو»: cards for the seal and sessions on the owner's turn. */
export const waitingForOwner = (s: LiveState): N => (s.approvals == null && s.sessions.your_turn == null ? null : (s.approvals ?? 0) + (s.sessions.your_turn ?? 0));
/** A company is locked by its own switch or the holding's. */
export const lockedOf = (s: LiveState, code: string) => !!s.control.holding || !!s.control.locked[code];
/** Flows of the last hour touching [code]. */
export const flowsPerHour = (c: CompanyLive | undefined, now = Date.now()) => (c ? c.flows.filter((t) => now - t < 3_600_000).length : 0);

/** How busy a company is, for the ring's order: an offline server first (it must stay on the map), then people at work, sessions, flows. */
export function activityScore(c: CompanyLive | undefined, offlineServers: number, now = Date.now()): number {
  if (!c) return offlineServers * 1000;
  return offlineServers * 1000 + (c.working ?? 0) * 10 + (c.sessions_open ?? 0) * 3 + flowsPerHour(c, now) + (c.in_flight && now - c.in_flight_at < 10_000 ? 5 : 0);
}

/**
 * The dots of a company card (PE-1 on CO-1): every person the model knows by name with their state, then as many working as the count
 * says beyond them, the rest idle; [max] shown, the rest counted.
 */
export function peopleDots(s: LiveState, code: string, max = 12): { dots: Array<{ id: string | null; state: PersonState }>; more: number } {
  const known = Object.values(s.employees).filter((e) => e.company === code);
  const c = s.companies[code];
  const knownBusy = known.filter((e) => BUSY.includes(e.state)).length;
  const extraBusy = Math.max(0, (c?.working ?? 0) - knownBusy);
  const total = Math.max(known.length + extraBusy, c?.total ?? 0);
  const order: Record<PersonState, number> = { stuck: 0, thinking: 1, working: 2, waiting: 3, done: 4, idle: 5 };
  const all: Array<{ id: string | null; state: PersonState }> = [
    ...known.map((e) => ({ id: e.id, state: e.state })),
    ...Array.from({ length: extraBusy }, () => ({ id: null, state: 'working' as PersonState })),
  ];
  while (all.length < total) all.push({ id: null, state: 'idle' });
  all.sort((a, b) => order[a.state] - order[b.state]);
  return { dots: all.slice(0, max), more: Math.max(0, all.length - max) };
}

// --------------------------------------------------------------------------------------------------- effects --
/** What the map draws for an event (§5 «Event → motion»); the store forwards these only while the tab is on screen and the stream is live. */
export type Effect =
  | { kind: 'particle'; edge: string; path: string[]; color: MotionColor; delay?: number; chord?: [string, string]; through?: boolean }
  | { kind: 'ceremony' }
  | { kind: 'ripple'; node: string; tone: 'pos' | 'neg' | 'silver' }
  | { kind: 'break'; server: string }
  | { kind: 'heal'; server: string };

export const srvNode = (id: string) => `srv:${id}`;
export const outsideNode = (code: string) => `out:${code}`;

const FLOW_COLOR: Record<string, MotionColor> = { order: 'gold', playbook: 'gold', request: 'silver', accept: 'silver', deliver: 'silver', publish: 'silver', read: 'lapis' };

/** The motion of one event, given the state before it. */
export function effectsOf(e: StreamEvent, before: LiveState): Effect[] {
  if (e.type === 'holding.flow') {
    const d = e.data as Partial<HoldingFlow>;
    if (!d.from || !d.to || !d.kind) return [];
    const color = FLOW_COLOR[d.kind] ?? 'silver';
    if (d.kind === 'order') {
      const to = d.to === 'hub' ? d.from : d.to;
      return [{ kind: 'ceremony' }, { kind: 'particle', edge: `hub>${to}`, path: ['hub', to], color: 'gold', delay: 420 }];
    }
    const from = d.from === 'outside' ? outsideNode(d.to) : d.from;
    const to = d.to === 'outside' ? outsideNode(d.from) : d.to;
    const path = from === 'hub' || to === 'hub' || to.startsWith('out:') || from.startsWith('out:') ? [from, to] : [from, 'hub', to];
    const chord: [string, string] | undefined = d.kind === 'request' && path.length === 3 ? [d.from, d.to] : undefined;
    return [{ kind: 'particle', edge: `${from}>${to}`, path, color, chord, through: path.length === 3 }];
  }
  if (e.type === 'server.call') {
    const id = str(e.data.server) ?? e.ref;
    const st = str(e.data.state);
    if (!id) return [];
    if (st === 'running') return [{ kind: 'particle', edge: `hub>${srvNode(id)}`, path: ['hub', srvNode(id)], color: 'lapis' }];
    if (st === 'done' || st === 'failed') return [{ kind: 'particle', edge: `${srvNode(id)}>hub`, path: [srvNode(id), 'hub'], color: 'silver' }];
    return [];
  }
  if (e.type === 'server.state') {
    const d = e.data as Partial<ServerState42>;
    const id = d.server ?? e.ref;
    if (!id || !d.state) return [];
    const prev = before.servers_by_id[id]?.state ?? d.prev_state ?? null;
    if (prev === 'online' && d.state === 'offline') return [{ kind: 'break', server: id }, { kind: 'ripple', node: srvNode(id), tone: 'neg' }];
    if (prev === 'offline' && d.state === 'online') return [{ kind: 'heal', server: id }, { kind: 'ripple', node: srvNode(id), tone: 'pos' }];
    if (prev != null && prev !== d.state) return [{ kind: 'ripple', node: srvNode(id), tone: 'silver' }];
    return [];
  }
  return [];
}
