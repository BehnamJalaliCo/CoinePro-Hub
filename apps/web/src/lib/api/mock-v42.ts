// ⟨1.24⟩ Demo of contract §42 «the holding live» (development only; reached through ./mock-v21, which a production build replaces with a
// stand-in). `GET /live/summary` is read from the demo's own state, so it always agrees with the lists; the scripted stream moves every
// live view: people change state (`employee.state`), busy companies tick their tokens every beat (`llm.tick`), an order goes out from the
// hub, companies ask each other through the hub and deliver back (`holding.flow`), jobs run on servers (`server.call`), and now and then a
// server drops with a reason and comes back (`server.state` with §42's additive fields, `network.link`). The e2e checks drive the same
// script by hand (`window.__hqLive.drive`, set up by ./mock-v21).

import type { HoldingFlow, LiveSummary, PersonState } from './v42';

type Ev = { id: string; type: string; at: string; company: string | null; ref: string | null; data: Record<string, unknown>; seq: number };
type Next = (req: Request) => Promise<Response>;
export type Ctx42 = { stopped: Set<string> };

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
/** Money as the hub writes it (§1, §42.5): a decimal string of 6 places. */
const money = (v: number) => v.toFixed(6);
/** The holding's code: the envelope company of every `holding.flow` (§42.5). */
const HOLDING = 'HQ';
const nowIso = () => new Date().toISOString();
let seq = 0;
let evN = 0;
const ev = (company: string | null, type: string, ref: string | null, data: Record<string, unknown>): Ev => ({ id: `d42-${++evN}`, type, at: nowIso(), company, ref, data, seq: ++seq });

// ------------------------------------------------------------------------------------------------------ people --
type Person = { code: string; company: string; department: string | null; state: PersonState; since: string };
const ROSTER: Record<string, Array<[string, string | null]>> = {
  TY: [['TY-CEO', null], ['TY-TECH-MGR', 'TECH'], ['TY-GROWTH-MGR', 'GROWTH'], ['TY-GROWTH-01', 'GROWTH'], ['TY-CONTENT-01', 'CONTENT'], ['TY-CONTENT-02', 'CONTENT'], ['TY-SUPPORT-01', 'SUPPORT'], ['TY-SEO-02', 'GROWTH']],
  FX: [['FX-CEO', null], ['FX-TECH-MGR', 'TECH'], ['FX-GROWTH-MGR', 'GROWTH'], ['FX-QUANT-01', 'QUANT'], ['FX-QUANT-02', 'QUANT'], ['FX-RISK-01', 'QUANT'], ['FX-SUPPORT-01', 'SUPPORT']],
  PC: [['PC-CEO', null], ['PC-TECH-MGR', 'TECH'], ['PC-GROWTH-MGR', 'GROWTH'], ['PC-MEDIA-MGR', 'MEDIA'], ['PC-MEDIA-01', 'MEDIA'], ['PC-MEDIA-02', 'MEDIA'], ['PC-DESIGN-01', 'MEDIA'], ['PC-EDIT-01', 'MEDIA'], ['PC-QA-01', 'TECH']],
};
const START: Record<string, PersonState> = { 'TY-CEO': 'thinking', 'TY-GROWTH-01': 'working', 'TY-CONTENT-01': 'working', 'FX-CEO': 'working', 'FX-QUANT-02': 'waiting', 'FX-TECH-MGR': 'thinking', 'FX-QUANT-01': 'done' };
const people = new Map<string, Person>(Object.entries(ROSTER).flatMap(([co, list]) => list.map(([code, dept]): [string, Person] => [code, { code, company: co, department: dept, state: START[code] ?? 'idle', since: nowIso() }])));
const NEXT: Record<PersonState, PersonState[]> = {
  idle: ['thinking', 'working'], thinking: ['working', 'working', 'done', 'waiting'], working: ['thinking', 'done', 'idle', 'waiting'],
  waiting: ['working', 'idle'], done: ['idle', 'thinking'], stuck: ['working'],
};
const STUCK_FA = 'سهمیه‌ی ChatGPT تا ساعت ۱۸ پر است؛ صبر میکند یا با Claude ادامه میدهد.';
const busy = (p: Person) => p.state === 'thinking' || p.state === 'working';
let rnd = 7;
/** A small fixed-seed random, so the demo moves the same way each time. */
const rand = () => { rnd = (rnd * 16807) % 2147483647; return (rnd - 1) / 2147483646; };
const pick = <T,>(xs: T[]): T => xs[Math.floor(rand() * xs.length)]!;

function setState(p: Person, state: PersonState): Ev {
  p.state = state;
  p.since = nowIso();
  return ev(p.company, 'employee.state', p.code, { employee: p.code, company: p.company, department: p.department, state, since: p.since, work_ref: busy(p) ? 'W-000102' : null, root_ref: busy(p) ? 'F-0007' : null, stuck_fa: state === 'stuck' ? STUCK_FA : null });
}

// ------------------------------------------------------------------------------------------------------ tokens --
type Day = { tokens: number; effective: number; usd: number };
const day: Record<string, Day> = { TY: { tokens: 412_000, effective: 210_000, usd: 4.12 }, FX: { tokens: 596_000, effective: 301_000, usd: 5.95 }, PC: { tokens: 88_000, effective: 44_000, usd: 0.81 } };
const BUDGET_USD = 20;
const COMPANY_BUDGET: Record<string, number> = { TY: 8, FX: 8, PC: 4 };
const ticks: Array<{ at: number; tokens: number }> = [];
const total = () => Object.values(day).reduce((a, d) => ({ tokens: a.tokens + d.tokens, effective: a.effective + d.effective, usd: a.usd + d.usd }), { tokens: 0, effective: 0, usd: 0 });

function tokenTick(co: string, scale = 1): Ev | null {
  const list = [...people.values()].filter((p) => p.company === co);
  const thinking = list.filter((p) => p.state === 'thinking').length;
  const working = list.filter((p) => p.state === 'working').length;
  if (!thinking && !working) return null;
  const base = Math.round((thinking * 2600 + working * 900) * scale);
  const t = { input: Math.round(base * 0.56), output: Math.round(base * 0.1), cache_read: Math.round(base * 0.26), cache_write: Math.round(base * 0.05), thinking: Math.round(base * 0.03) };
  const n = t.input + t.output + t.cache_read + t.cache_write + t.thinking;
  const usd = Math.round(n * 7e-6 * 10_000) / 10_000;
  const d = (day[co] ??= { tokens: 0, effective: 0, usd: 0 });
  d.tokens += n; d.effective += Math.round(n * 0.5); d.usd = Math.round((d.usd + usd) * 10_000) / 10_000;
  ticks.push({ at: Date.now(), tokens: n });
  const cap = COMPANY_BUDGET[co] ?? null;
  return ev(co, 'llm.tick', null, {
    company: co, window_s: 5, calls: thinking + working, in_flight: thinking, tokens: t, equiv_usd: money(usd),
    day: { tokens: d.tokens, effective_tokens: d.effective, equiv_usd: money(d.usd), budget_usd: cap == null ? null : money(cap), pct: cap ? Math.round((1000 * d.usd) / cap) / 10 : null },
  });
}

// ----------------------------------------------------------------------------------------------------- servers --
const SERVERS = [{ id: 'srv-fx-1', company: 'FX' }, { id: 'srv-ty-1', company: 'TY' }, { id: 'srv-pc-1', company: 'PC' }, { id: 'srv-ig-1', company: 'IG' }];
type Down = { since: string; reason: 'runner_stopped' | 'server_unreachable'; last_ok_at: string };
const down = new Map<string, Down>();
const REASON_FA = { runner_stopped: 'runner روی سرور ایستاده', server_unreachable: 'سرور از شبکه در دسترس نیست' } as const;
const jobs: Array<{ server: string; company: string; until: number }> = [];

function drop(id: string, reason: Down['reason'] = 'runner_stopped'): Ev[] {
  const s = SERVERS.find((x) => x.id === id);
  if (!s || down.has(id)) return [];
  const since = nowIso();
  const last = new Date(Date.now() - 52_000).toISOString();
  down.set(id, { since, reason, last_ok_at: last });
  const open = jobs.filter((j) => j.server === id).length + 1;
  return [
    ev(s.company, 'server.state', id, { server: id, company: s.company, state: 'offline', via: 'private', prev_state: 'online', since, reason, reason_fa: REASON_FA[reason], hub_rtt_ms: null, open_jobs: open }),
    ev(s.company, 'network.link', id, { from: id, to: 'hub', port: 443, ok: false, ms: null, error_fa: reason === 'runner_stopped' ? 'runner سه بار پشت هم به هاب سر نزد' : 'هیچ راهی به این سرور جواب نداد', since, last_ok_at: last }),
  ];
}
function heal(id: string): Ev[] {
  const s = SERVERS.find((x) => x.id === id);
  if (!s || !down.has(id)) return [];
  down.delete(id);
  const since = nowIso();
  return [
    ev(s.company, 'server.state', id, { server: id, company: s.company, state: 'online', via: 'private', prev_state: 'offline', since, reason: null, reason_fa: null, hub_rtt_ms: 2.4, open_jobs: 0 }),
    ev(s.company, 'network.link', id, { from: id, to: 'hub', port: 443, ok: true, ms: 2.6, error_fa: null, since, last_ok_at: since }),
  ];
}

// ------------------------------------------------------------------------------------------------------- flows --
const flow = (f: Omit<HoldingFlow, 'via' | 'root_ref'> & { root_ref?: string | null }): Ev =>
  ev(HOLDING, 'holding.flow', f.ref, { ...f, via: 'hub', root_ref: f.root_ref ?? null });
const ORDERS = ['ریلز آخر هفته', 'گزارش سئوی فنی', 'بررسی کندی ثبت‌نام', 'خبرنامه‌ی ماه'];
const REQUESTS: Array<[string, string, string]> = [['TY', 'FX', 'سیگنال‌های امروز'], ['FX', 'TY', 'انتشار سیگنال در کانال'], ['TY', 'PC', 'نمودار هفتگی طلا'], ['PC', 'TY', 'متن کپشن']];
let flowN = 0;

// ----------------------------------------------------------------------------------------------------- the beat --
let tickNo = 0;
const pending: Array<{ at: number; make: () => Ev[] }> = [];
const queue: Ev[] = [];
const later = (beats: number, make: () => Ev[]) => pending.push({ at: tickNo + beats, make });
const live = (co: string, ctx: Ctx42) => !ctx.stopped.has(co) && !ctx.stopped.has('HQ');

/** One beat of the demo's stream (every 2.4 s). */
export function tick42(ctx: Ctx42): Ev[] {
  tickNo += 1;
  const out: Ev[] = queue.splice(0);
  for (const p of pending.filter((x) => x.at <= tickNo)) { pending.splice(pending.indexOf(p), 1); out.push(...p.make()); }
  // People: one or two change what they are doing (none in a stopped company).
  const movable = [...people.values()].filter((p) => live(p.company, ctx));
  for (let i = 0; i < (tickNo % 3 === 0 ? 2 : 1) && movable.length; i++) {
    const p = pick(movable);
    out.push(setState(p, tickNo % 17 === 0 ? 'stuck' : pick(NEXT[p.state])));
  }
  // Tokens: every busy company says what it spent in the window.
  for (const co of Object.keys(ROSTER)) { if (!live(co, ctx)) continue; const t = tokenTick(co); if (t) out.push(t); }
  // Every third beat a flow between companies, a read, or a job on a server.
  if (tickNo % 3 === 1) {
    const k = flowN++ % 3;
    const reqs = REQUESTS.filter(([a, b]) => live(a, ctx) && live(b, ctx));
    if (k === 0 && reqs.length) {
      const [a, b, label] = pick(reqs);
      const ref = `W-${String(300 + flowN).padStart(6, '0')}`;
      out.push(flow({ from: a, to: b, kind: 'request', ref, label_fa: label }));
      later(2, () => (live(b, ctx) ? [flow({ from: b, to: a, kind: 'deliver', ref, label_fa: label })] : []));
    } else if (k === 1 && reqs.length) {
      const [a, b, label] = pick(reqs);
      out.push(flow({ from: b, to: a, kind: 'read', ref: `W-${String(300 + flowN).padStart(6, '0')}`, label_fa: label }));
    } else {
      const s = pick(SERVERS.filter((x) => !down.has(x.id) && live(x.company, ctx)));
      if (s) {
        const id = `job-d42-${flowN}`;
        jobs.push({ server: s.id, company: s.company, until: tickNo + 2 });
        out.push(ev(s.company, 'server.call', s.id, { server: s.id, company: s.company, actor: `${s.company}-TECH-MGR`, tool: 'server.exec', summary_fa: 'سلامت سرویس‌ها', state: 'running', job: id }));
        later(2, () => {
          jobs.splice(jobs.findIndex((j) => j.server === s.id), 1);
          return down.has(s.id) ? [] : [ev(s.company, 'server.call', s.id, { server: s.id, company: s.company, actor: `${s.company}-TECH-MGR`, tool: 'server.exec', summary_fa: 'سلامت سرویس‌ها', state: 'done', exit_code: 0, duration_ms: 4100, job: id })];
        });
      }
    }
  }
  // An order goes out from the hub now and then (the seal pulses, a gold particle to the holder).
  if (tickNo % 12 === 5) {
    const to = pick(Object.keys(ROSTER).filter((c) => live(c, ctx)));
    if (to) out.push(flow({ from: 'hub', to, kind: 'order', ref: 'F-0007', label_fa: pick(ORDERS) }));
  }
  // A server drops with its reason, and comes back about half a minute later.
  if (tickNo % 50 === 14) { out.push(...drop('srv-ty-1', 'runner_stopped')); later(12, () => heal('srv-ty-1')); }
  return out;
}

/** The e2e checks' hand on the script: what one call does, now. */
export function drive42(what: string, ctx: Ctx42): Ev[] {
  if (what === 'drop') return drop('srv-ty-1', 'runner_stopped');
  if (what === 'unreachable') return drop('srv-fx-1', 'server_unreachable');
  if (what === 'heal') return [...heal('srv-ty-1'), ...heal('srv-fx-1')];
  if (what === 'order') return [flow({ from: 'hub', to: 'TY', kind: 'order', ref: 'F-0007', label_fa: 'ریلز آخر هفته' })];
  if (what === 'request') return [flow({ from: 'TY', to: 'FX', kind: 'request', ref: 'W-000399', label_fa: 'سیگنال‌های امروز' })];
  if (what === 'stuck') { const p = people.get('TY-GROWTH-01')!; return [setState(p, 'stuck')]; }
  // A quiet session starts moving (its badge on the stream; the work band runs under it).
  if (what === 'moving') return [ev(null, 'session.updated', 'F-0006', { ref: 'F-0006', badge: 'moving' })];
  if (what === 'work') { const p = people.get('TY-SUPPORT-01')!; return [setState(p, 'working')]; }
  if (what === 'tokens') { const t = tokenTick('TY', 40); return t ? [t] : []; }
  // Many events at once (a burst): people flicker in the companies that run.
  if (what === 'burst') return Array.from({ length: 30 }, (_, i) => { const list = [...people.values()].filter((p) => live(p.company, ctx)); const p = list[i % list.length]!; return setState(p, i % 2 ? 'thinking' : 'working'); });
  return [];
}

// ------------------------------------------------------------------------------------------------------ routes --
const listOf = (x: any): any[] => (Array.isArray(x) ? x : x?.items ?? []);
async function read(next: Next, req: Request, path: string): Promise<any> {
  const res = await next(new Request(new URL(`/api/v1${path}`, new URL(req.url).origin), { headers: req.headers }));
  return res.ok ? res.json() : null;
}
/** A server's own state where the demo dropped it. */
function patchServers(x: any): any {
  const fix = (s: any) => (s && typeof s === 'object' && typeof s.id === 'string' && down.has(s.id) ? { ...s, state: 'offline', hub_rtt_ms: null, last_seen_at: down.get(s.id)!.last_ok_at } : s);
  if (Array.isArray(x)) return x.map(fix);
  if (x && Array.isArray(x.items)) return { ...x, items: x.items.map(fix) };
  if (x && Array.isArray(x.nodes)) return { ...x, nodes: x.nodes.map(fix), links: (x.links ?? []).map((l: any) => (down.has(l.from) && l.to === 'hub' ? { ...l, ok: false, ms: null, error: 'offline' } : l)) };
  return fix(x);
}
const perMin = () => { const now = Date.now(); return ticks.filter((t) => now - t.at < 60_000).reduce((a, t) => a + t.tokens, 0); };

async function summary(req: Request, next: Next): Promise<LiveSummary> {
  const [cos, sessions, inbox, control, net] = await Promise.all([
    read(next, req, '/companies'), read(next, req, '/sessions?state=open&limit=100'), read(next, req, '/inbox/summary'), read(next, req, '/control/state'), read(next, req, '/infra/network'),
  ]);
  const cards = listOf(sessions);
  const nodes = (patchServers(net)?.nodes ?? []).filter((n: any) => n.id !== 'hub' && n.state !== 'revoked');
  const locked: string[] = (control?.companies ?? []).filter((k: any) => k.state === 'engaged').map((k: any) => k.company);
  const all = [...people.values()];
  const count = (st: PersonState, co?: string) => all.filter((p) => p.state === st && (!co || p.company === co)).length;
  const badge = (b: string) => cards.filter((c: any) => c.badge === b).length;
  const list = listOf(cos).filter((c: any) => c.kind !== 'holding' && (c.status === 'active' || c.status === 'paused'));
  const t = total();
  // The e2e checks set the sequence the summary answers; «null» is the hub with its event bus down (§42.5).
  const stored = (() => { try { return window.localStorage.getItem('hq.e2e.seq'); } catch { return null; } })();
  return {
    seq: stored === 'null' ? null : stored ? Number(stored) : seq, at: nowIso(),
    people: { working: count('working'), thinking: count('thinking'), waiting: count('waiting'), stuck: count('stuck'), total: all.length },
    sessions: { moving: badge('moving'), your_turn: badge('your_turn'), stuck: badge('stuck'), ready: badge('ready') },
    approvals: inbox?.decisions_pending ?? null, urgent_unread: inbox?.notifications?.urgent ?? null,
    servers: { online: nodes.filter((n: any) => n.state === 'online').length, offline: nodes.filter((n: any) => n.state === 'offline').length, total: nodes.length },
    tokens: { today: t.tokens, effective_today: t.effective, per_min: perMin(), equiv_usd_today: money(t.usd), budget_usd: money(BUDGET_USD) },
    control: { holding: control?.holding?.state === 'engaged', companies_locked: locked },
    companies: list.map((c: any) => {
      const mine = nodes.filter((n: any) => n.company === c.code);
      const roster = all.filter((p) => p.company === c.code);
      return {
        // An operating company's row (§42.5): `working` is its people thinking or working.
        code: c.code, name_fa: c.name_fa ?? c.code, working: roster.filter(busy).length, total: roster.length,
        sessions_open: cards.filter((s: any) => s.holder?.company === c.code).length, servers_online: mine.filter((n: any) => n.state === 'online').length, servers_total: mine.length,
        spend_today_usd: money(day[c.code]?.usd ?? 0), last_event_at: nowIso(),
        state: locked.includes(c.code) ? 'locked' : count('stuck', c.code) ? 'stuck' : roster.some(busy) ? 'busy' : 'ok',
      };
    }),
  };
}

/** §42's route, and the demo's dropped servers wherever a server's state is read. */
export async function handle42(req: Request, p: string, next: Next): Promise<Response | null> {
  const m = req.method;
  if (p === '/live/summary' && m === 'GET') return json(await summary(req, next));
  if (m === 'GET' && (p === '/infra/network' || p === '/servers' || /^\/servers\/[^/]+$/.test(p)) && down.size) {
    const res = await next(req);
    if (!res.ok) return res;
    return json(patchServers(await res.json()), res.status);
  }
  // The owner's order: the hub routes it to its holder's company (a gold particle from the seal) and its session starts moving.
  if (p === '/orders' && m === 'POST') {
    const res = await next(req);
    if (!res.ok) return res;
    const out = (await res.clone().json()) as any;
    const to = out.routes?.[0]?.company ?? out.route?.companies?.[0] ?? 'TY';
    if (out.ref) queue.push(flow({ from: 'hub', to, kind: 'order', ref: out.ref, label_fa: null }), ev(to, 'session.updated', out.ref, { ref: out.ref, badge: 'moving' }));
    return res;
  }
  return null;
}
