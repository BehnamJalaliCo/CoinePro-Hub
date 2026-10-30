// The owner's control over the holding and every company (0.3.0; contract §9, OPERATING_MODEL §1.12), read at a glance: each company's
// own kill switch, the holding's, and its deploy freezes; and what its agents are doing now, from the live stream. The Android app's
// core/data/Control.kt and LiveActivity.kt.

import type { Schemas } from './api/client';
import type { StreamEvent } from './stream';

type ControlState = Schemas['ControlState'];
type KillSwitch = Schemas['KillSwitch'];
type Freeze = { company: string; until: string; reason: string; created_by?: string | null };
type Company = Schemas['Company'];

export type CoState = {
  code: string; holding: boolean;
  /** Its own switch is engaged. */
  stopped: boolean;
  /** The holding's switch is engaged: every company stops with it. */
  holdingStopped: boolean;
  /** Its own switch as the hub reports it: who changed it, when and why. */
  sw: KillSwitch | null;
  /** The freeze that ends last, while any is active. */
  freeze: Freeze | null;
  running: boolean; frozen: boolean; scope: string;
};

export const scopeOf = (code: string, holding: boolean) => (holding ? 'holding' : `company:${code}`);

/** The state of [code] from `GET /control/state` (who, when, why) and, while that is loading, from the company row itself. */
export function coState(code: string, holding: boolean, control: ControlState | undefined, company?: Company | null, now = Date.now()): CoState {
  const sw = (holding ? control?.holding : control?.companies.find((k) => k.company === code)) ?? null;
  const stopped = sw ? sw.state === 'engaged' : company?.kill_switch === 'engaged';
  const holdingStopped = !holding && control?.holding.state === 'engaged';
  const freezes = (control?.deploy_freezes as Freeze[] | undefined)?.filter((f) => f.company === code && new Date(f.until).getTime() > now) ?? [];
  const freeze = freezes.sort((a, b) => b.until.localeCompare(a.until))[0]
    ?? (!control && company?.deploy_freeze_until && new Date(company.deploy_freeze_until).getTime() > now ? { company: code, until: company.deploy_freeze_until, reason: '' } : null);
  return { code, holding, stopped, holdingStopped: !!holdingStopped, sw, freeze, running: !stopped && !holdingStopped, frozen: !!freeze, scope: scopeOf(code, holding) };
}

/** "به دستور تو", "به دستور مدیرعامل", "خط انتشار". */
export function byFa(code: string | null | undefined): string {
  if (!code) return '—';
  if (code === 'owner') return 'به دستور تو';
  if (code === 'pipeline') return 'خط انتشار';
  if (code.endsWith('-CEO')) return 'به دستور مدیرعامل';
  if (code === 'HQ-OVR') return 'به دستور ناظر کل';
  return `به دستور ${code}`;
}

// --------------------------------------------------------------------------------------------------- live activity --
/** One company's agents right now, as the live stream tells it. */
export type Pulse = { runs: string[]; working: string[]; lastAt: number; recent: StreamEvent[] };
/** Event types a company's feed shows. */
export const FEED = ['run.', 'deliverable.', 'decision.', 'work.', 'control.', 'employee.', 'budget.', 'incident.'];
const MAX = 30;

const s = (v: unknown) => (typeof v === 'string' && v ? v : null);

/** The pulses after one more event: `run.*` (the runtime's runs), `activity.changed` (an employee working or asleep), and the feed. */
export function nextPulses(all: Record<string, Pulse>, e: StreamEvent, now = Date.now()): Record<string, Pulse> {
  const co = e.company;
  if (!co) return all;
  const p = all[co] ?? { runs: [], working: [], lastAt: 0, recent: [] };
  const employee = s(e.data.employee) ?? (e.type === 'activity.changed' ? e.ref : null);
  let runs = p.runs;
  let working = p.working;
  if (e.type === 'run.started' || e.type === 'run.step') {
    if (e.ref && !runs.includes(e.ref)) runs = [...runs, e.ref];
    if (employee && !working.includes(employee)) working = [...working, employee];
  } else if (e.type === 'run.finished') {
    runs = runs.filter((r) => r !== e.ref);
    if (employee) working = working.filter((x) => x !== employee);
  } else if (e.type === 'activity.changed' && employee) {
    working = s(e.data.activity) === 'working' ? (working.includes(employee) ? working : [...working, employee]) : working.filter((x) => x !== employee);
  }
  const readable = FEED.some((f) => e.type.startsWith(f)) && e.type !== 'run.step';
  const recent = readable
    ? [{ ...e, at: e.at || new Date(now).toISOString() }, ...p.recent].filter((x, i, a) => a.findIndex((y) => `${y.type}|${y.ref}|${y.at}` === `${x.type}|${x.ref}|${x.at}`) === i).slice(0, MAX)
    : p.recent;
  return { ...all, [co]: { runs, working, lastAt: now, recent } };
}

/** Something happened in the last 15 s: a short pulse even without a run in progress. */
export const stirred = (p: Pulse | undefined, now = Date.now()) => !!p && p.lastAt > 0 && now - p.lastAt < 15_000;

/** Runs in progress: what was running when the page loaded, plus what the stream says started since, less what finished. */
export function runsOf(code: string, pulses: Record<string, Pulse>, running: Array<{ id: string; company: string; state: string }>): number {
  const loaded = running.filter((r) => r.company === code && r.state === 'running').map((r) => r.id);
  return new Set([...loaded, ...(pulses[code]?.runs ?? [])]).size;
}

export function pctOf(tokens: number, tokenLimit: number | null, usd: string | null, usdLimit: string | null): number | null {
  const p = [tokenLimit && tokenLimit > 0 ? (100 * tokens) / tokenLimit : null, usdLimit && Number(usdLimit) > 0 ? (100 * Number(usd ?? 0)) / Number(usdLimit) : null].filter((x): x is number => x != null);
  return p.length ? Math.round(Math.max(...p) * 10) / 10 : null;
}
