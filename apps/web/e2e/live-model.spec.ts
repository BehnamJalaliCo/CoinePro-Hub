import { expect, test } from '@playwright/test';
import type { StreamEvent } from '../src/lib/stream';
import type { LiveSummary } from '../src/lib/api/v42';
import {
  EMPTY, createDedupe, effectsOf, flowsPerHour, inFlight, peopleBusy, peopleDots, perMin, reduce, seedPeople, seedSessions, seedSummary, seedTokenKinds,
  waitingForOwner, type LiveState,
} from '../src/lib/live/model';
import { NODE_MIN, capacity, ringLayout, type RingItem } from '../src/lib/live/ring';

// ⟨1.24⟩ K-2 and HM-1 as pure functions (no page): the live model's reducers (one per view), the stream's door, the map's effects, and the
// ring layout for 0, 1, 3 and 40 companies. Run with the e2e suite (Playwright's runner, no browser).

const T0 = Date.parse('2026-11-08T10:00:00Z');
const at = (s: number) => new Date(T0 + s * 1000).toISOString();
let n = 0;
const ev = (type: string, data: Record<string, unknown>, o: Partial<StreamEvent> = {}): StreamEvent => ({ id: `t${++n}`, type, at: at(n), company: null, ref: null, data, seq: null, ...o });

const SUMMARY: LiveSummary = {
  seq: 120, at: at(0),
  people: { working: 3, thinking: 1, waiting: 1, stuck: 0, total: 20 },
  sessions: { moving: 2, your_turn: 1, stuck: 0, ready: 1 },
  approvals: 4, urgent_unread: 0,
  servers: { online: 3, offline: 0, total: 3 },
  tokens: { today: 1_000_000, effective_today: 500_000, per_min: 9000, equiv_usd_today: 10, budget_usd: 20 },
  control: { holding: false, companies_locked: ['PC'] },
  companies: [
    { code: 'TY', name_fa: 'تریدیار', working: 2, total: 8, sessions_open: 2, servers_online: 1, servers_total: 1, spend_today_usd: 4, last_event_at: at(0), state: 'busy' },
    { code: 'FX', name_fa: 'کوینه‌پرو FX', working: 2, total: 7, sessions_open: 1, servers_online: 1, servers_total: 1, spend_today_usd: 6, last_event_at: at(0), state: 'busy' },
    { code: 'PC', name_fa: 'پرو-چارت', working: 0, total: 5, sessions_open: 1, servers_online: 1, servers_total: 1, spend_today_usd: 0, last_event_at: null, state: 'locked' },
  ],
};
const seeded = (): LiveState => seedSummary(EMPTY, SUMMARY);
const run = (s: LiveState, ...es: StreamEvent[]) => es.reduce(reduce, s);

test.describe('the live model (K-2)', () => {
  test('missing data stays missing: nothing is zero before the seed', () => {
    const s = run(EMPTY, ev('employee.state', { employee: 'TY-01', company: 'TY', state: 'working' }), ev('decision.created', {}));
    expect(s.people.working).toBeNull();
    expect(s.approvals).toBeNull();
    expect(peopleBusy(s)).toBeNull();
    expect(waitingForOwner(s)).toBeNull();
    expect(perMin(s, T0)).toBeNull();
  });

  test('the seed sets every count, the sequence and the companies in the data order', () => {
    const s = seeded();
    expect(s.seeded).toBe(true);
    expect(s.seq).toBe(120);
    expect(s.order).toEqual(['TY', 'FX', 'PC']);
    expect(peopleBusy(s)).toBe(4);
    expect(waitingForOwner(s)).toBe(5);
    expect(s.control.locked).toHaveProperty('PC');
    expect(s.companies.PC!.last_event_at).toBeNull();
  });

  test('OF-1 and CO-1: a person moves from the bucket they left (known from the list) to the one they entered', () => {
    let s = seedPeople(seeded(), [{ code: 'TY-01', company: 'TY', state: 'idle' }, { code: 'TY-02', company: 'TY', state: 'working' }]);
    s = run(s, ev('employee.state', { employee: 'TY-01', company: 'TY', state: 'thinking' }, { company: 'TY' }));
    expect(s.people.thinking).toBe(2);
    expect(s.companies.TY!.working).toBe(3);
    s = run(s, ev('employee.state', { employee: 'TY-02', company: 'TY', state: 'done' }, { company: 'TY' }));
    expect(s.people.working).toBe(2);
    expect(s.companies.TY!.working).toBe(2);
    // The same state again moves nothing; an unknown person only adds to where they went.
    const same = run(s, ev('employee.state', { employee: 'TY-02', company: 'TY', state: 'done' }));
    expect(same.people).toEqual(s.people);
    s = run(s, ev('employee.state', { employee: 'FX-09', company: 'FX', state: 'stuck', stuck_fa: 'سهمیه پر است' }, { company: 'FX' }));
    expect(s.people.stuck).toBe(1);
    expect(s.employees['FX-09']!.stuck_fa).toBe('سهمیه پر است');
    expect(s.companies.FX!.working).toBe(2);
  });

  test('SS-1: a badge moves between the session counts, and a closed session leaves its company', () => {
    let s = seedSessions(seeded(), [{ ref: 'F-0007', badge: 'moving', last_at: at(0), holder: { company: 'TY' } }]);
    s = run(s, ev('session.updated', { ref: 'F-0007', badge: 'your_turn' }, { company: 'TY', ref: 'F-0007' }));
    expect(s.sessions.moving).toBe(1);
    expect(s.sessions.your_turn).toBe(2);
    s = run(s, ev('session.updated', { ref: 'F-0007', badge: 'closed' }, { company: 'TY', ref: 'F-0007' }));
    expect(s.sessions.your_turn).toBe(1);
    expect(s.companies.TY!.sessions_open).toBe(1);
    s = run(s, ev('session.activity', { order: 'F-0008', working: 1, line: { id: 'r-1', at: at(50), who_fa: 'x', text_fa: 'y', kind: 'wake', state: 'done' } }));
    expect(s.sessions_by_ref['F-0008']!.woke_at).toBe(at(50));
    s = run(s, ev('session.activity', { order: 'F-0008', working: 1, line: { id: 'r-2', at: at(60), who_fa: 'x', text_fa: 'z', kind: 'step', state: 'running' } }));
    expect(s.sessions_by_ref['F-0008']!.last_step_at).toBe(at(60));
  });

  test('cards for the seal and urgent alerts count; a figure never goes below zero', () => {
    let s = run(seeded(), ev('decision.created', {}), ev('notification.created', { level: 'urgent' }), ev('notification.created', { level: 'info' }));
    expect(s.approvals).toBe(5);
    expect(s.urgent_unread).toBe(1);
    s = run(s, ...Array.from({ length: 9 }, () => ev('decision.decided', {})));
    expect(s.approvals).toBe(0);
  });

  test('MO-1: a tick adds its tokens by kind and its dollars; the burn rate is the last minute, zero when idle', () => {
    let s = seedTokenKinds(seeded(), { input_tokens: 100, output_tokens: 10, cache_read_tokens: 5, cache_write_tokens: 5, thinking_tokens: 0 });
    const tick = (co: string, sec: number, k: number, usd: number, inFlight = 1) => ev('llm.tick', {
      company: co, window_s: 5, calls: 2, in_flight: inFlight, tokens: { input: k, output: k, cache_read: k, cache_write: k, thinking: k }, equiv_usd: usd,
      day: { tokens: 0, effective_tokens: 0, equiv_usd: usd * 10, budget_usd: 8, pct: null },
    }, { company: co, at: at(sec) });
    expect(perMin(s, T0 + 1000)).toBe(9000);
    s = run(s, tick('TY', 10, 100, 0.5), tick('FX', 20, 200, 0.25));
    expect(s.tokens.today).toBe(1_000_000 + 500 + 1000);
    expect(s.tokens.equiv_usd_today).toBe(10.75);
    expect(s.tokens.kinds).toEqual({ input: 400, output: 310, cache: 610, thinking: 300 });
    expect(perMin(s, T0 + 30_000)).toBe(1500);
    expect(perMin(s, T0 + 200_000)).toBe(0);
    expect(s.companies.TY!.spend_today_usd).toBe(5);
    expect(s.companies.TY!.budget_usd).toBe(8);
    expect(inFlight(s, T0 + 15_000)).toBe(2);
    expect(inFlight(s, T0 + 60_000)).toBe(0);
  });

  test('GL-2: the holding switch and a company switch', () => {
    let s = run(seeded(), ev('control.changed', { scope: 'holding', kill_switch: 'engaged', by: 'owner' }, { ref: 'holding' }));
    expect(s.control.holding).toBe(true);
    expect(s.control.holding_by).toBe('owner');
    s = run(s, ev('control.changed', { scope: 'company:PC', state: 'released' }), ev('control.changed', { scope: 'company:TY', state: 'engaged', by: 'TY-CEO' }));
    expect(Object.keys(s.control.locked)).toEqual(['TY']);
    // A deploy freeze is not a lock.
    expect(run(s, ev('control.changed', { scope: 'company:FX', state: 'frozen' })).control.locked).not.toHaveProperty('FX');
  });

  test('HM-3: a server drops with its reason and comes back; the counts follow', () => {
    let s = seeded();
    const down = ev('server.state', { server: 'srv-ty-1', company: 'TY', state: 'offline', prev_state: 'online', since: at(5), reason: 'runner_stopped', reason_fa: 'runner روی سرور ایستاده', open_jobs: 2 }, { company: 'TY' });
    expect(effectsOf(down, s).map((f) => f.kind)).toEqual(['break', 'ripple']);
    s = run(s, down);
    expect(s.servers).toEqual({ online: 2, offline: 1, total: 3 });
    expect(s.companies.TY!.servers_online).toBe(0);
    expect(s.servers_by_id['srv-ty-1']).toMatchObject({ state: 'offline', reason: 'runner_stopped', since: at(5), open_jobs: 2 });
    s = run(s, ev('network.link', { from: 'srv-ty-1', to: 'hub', port: 443, ok: false, since: at(5), last_ok_at: at(1) }));
    expect(Object.values(s.links)).toHaveLength(1);
    const up = ev('server.state', { server: 'srv-ty-1', company: 'TY', state: 'online', prev_state: 'offline' }, { company: 'TY' });
    expect(effectsOf(up, s).map((f) => f.kind)).toEqual(['heal', 'ripple']);
    s = run(s, up, ev('network.link', { from: 'srv-ty-1', to: 'hub', port: 443, ok: true, since: at(9) }));
    expect(s.servers).toEqual({ online: 3, offline: 0, total: 3 });
    expect(s.servers_by_id['srv-ty-1']!.reason).toBeNull();
    expect(Object.values(s.links)).toHaveLength(0);
  });

  test('HM-2: what each flow draws (§5 «Event → motion»)', () => {
    const s = seeded();
    const fx = (data: Record<string, unknown>) => effectsOf(ev('holding.flow', { via: 'hub', ref: 'W-1', root_ref: null, label_fa: null, ...data }), s);
    expect(fx({ from: 'hub', to: 'TY', kind: 'order' })).toEqual([{ kind: 'ceremony' }, { kind: 'particle', edge: 'hub>TY', path: ['hub', 'TY'], color: 'gold', delay: 420 }]);
    expect(fx({ from: 'TY', to: 'FX', kind: 'request' })[0]).toMatchObject({ path: ['TY', 'hub', 'FX'], color: 'silver', chord: ['TY', 'FX'], through: true });
    expect(fx({ from: 'FX', to: 'hub', kind: 'deliver' })[0]).toMatchObject({ path: ['FX', 'hub'], color: 'silver' });
    expect(fx({ from: 'PC', to: 'TY', kind: 'read' })[0]).toMatchObject({ path: ['PC', 'hub', 'TY'], color: 'lapis' });
    expect(fx({ from: 'TY', to: 'outside', kind: 'publish' })[0]).toMatchObject({ path: ['TY', 'out:TY'] });
    const job = effectsOf(ev('server.call', { server: 'srv-fx-1', state: 'running' }), s);
    expect(job[0]).toMatchObject({ path: ['hub', 'srv:srv-fx-1'], color: 'lapis' });
    const after = run(s, ev('server.call', { server: 'srv-fx-1', state: 'running' }), ev('server.call', { server: 'srv-fx-1', state: 'failed' }));
    expect(after.servers_by_id['srv-fx-1']!.jobs).toBe(0);
    expect(after.servers_by_id['srv-fx-1']!.failed_at).not.toBeNull();
    const flows = run(s, ev('holding.flow', { from: 'TY', to: 'FX', kind: 'request', via: 'hub', ref: 'W-2' }, { at: at(1) }));
    expect(flowsPerHour(flows.companies.TY, T0 + 60_000)).toBe(1);
    expect(flowsPerHour(flows.companies.TY, T0 + 4_000_000)).toBe(0);
  });

  test('the stream\'s door: once by id, and nothing the seed already counted', () => {
    const door = createDedupe(10);
    door.floor(120);
    expect(door.accept({ id: 'a', seq: 119 })).toBe(false);
    expect(door.accept({ id: 'b', seq: 120 })).toBe(false);
    expect(door.accept({ id: 'c', seq: 121 })).toBe(true);
    expect(door.accept({ id: 'c', seq: 121 })).toBe(false);
    expect(door.accept({ id: 'd' })).toBe(true);
    for (let i = 0; i < 30; i++) door.accept({ id: `x${i}` });
    expect(door.accept({ id: 'x29' })).toBe(false);
    // The highest sequence applied is kept.
    expect(run(seeded(), ev('decision.created', {}, { seq: 130 })).seq).toBe(130);
  });

  test('PE-1 on CO-1: twelve dots at most, the stuck first, the rest counted', () => {
    let s = seeded();
    s = seedPeople(s, Array.from({ length: 15 }, (_, i) => ({ code: `TY-${i}`, company: 'TY', state: i === 7 ? 'stuck' : i < 3 ? 'working' : 'idle' })));
    const { dots, more } = peopleDots(s, 'TY');
    expect(dots).toHaveLength(12);
    expect(more).toBe(3);
    expect(dots[0]!.state).toBe('stuck');
    // A company the model knows only by its counts: the busy and then the idle.
    const fx = peopleDots(s, 'FX');
    expect(fx.dots.map((d) => d.state)).toEqual(['working', 'working', 'idle', 'idle', 'idle', 'idle', 'idle']);
  });
});

test.describe('the ring layout (HM-1, §5 «Scale»)', () => {
  const items = (k: number, servers = 1): RingItem[] => Array.from({ length: k }, (_, i) => ({ code: `C${i}`, score: i % 7, servers: Array.from({ length: servers }, (_, j) => ({ id: `s${i}-${j}`, state: j === 0 && i === k - 1 ? 'offline' : 'online' })) }));
  const apart = (l: ReturnType<typeof ringLayout>) => {
    let min = Infinity;
    const all = [...l.nodes, ...(l.rest ? [l.rest] : [])];
    for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) min = Math.min(min, Math.hypot(all[i]!.x - all[j]!.x, all[i]!.y - all[j]!.y) - all[i]!.r - all[j]!.r);
    return min;
  };
  const inside = (l: ReturnType<typeof ringLayout>) => [...l.nodes, ...l.servers.map((s) => ({ x: s.x, y: s.y, r: s.size / 2 }))].every((p) => p.x - p.r >= 0 && p.x + p.r <= l.width && p.y - p.r >= 0 && p.y + p.r <= l.height);

  test('no company: the hub alone, in the middle', () => {
    const l = ringLayout([], 800);
    expect(l.nodes).toHaveLength(0);
    expect(l.rest).toBeNull();
    expect(l.servers).toHaveLength(0);
    expect(l.cx).toBe(400);
    expect(l.hubR).toBeGreaterThanOrEqual(26);
  });

  test('one company: at the top, full size, its server straight out', () => {
    const l = ringLayout(items(1), 800);
    expect(l.nodes).toHaveLength(1);
    const [c] = l.nodes;
    expect(Math.round(c!.x)).toBe(Math.round(l.cx));
    expect(c!.y).toBeLessThan(l.cy);
    expect(c!.r * 2).toBe(64);
    expect(l.servers[0]!.y).toBeLessThan(c!.y);
  });

  test('three companies: 120° apart, the busiest on top, nothing overlaps, servers by their company', () => {
    const l = ringLayout([{ code: 'TY', score: 1, servers: [{ id: 'a', state: 'online' }] }, { code: 'FX', score: 5, servers: [] }, { code: 'PC', score: 3, servers: [{ id: 'b', state: 'online' }, { id: 'c', state: 'offline' }] }], 800);
    expect(l.nodes.map((n) => n.code)).toEqual(['FX', 'PC', 'TY']);
    expect(l.nodes[0]!.y).toBeLessThan(l.cy);
    const deg = l.nodes.map((n) => Math.round((n.angle * 180) / Math.PI));
    expect(deg).toEqual([-90, 30, 150]);
    expect(apart(l)).toBeGreaterThan(0);
    expect(inside(l)).toBe(true);
    // The offline server is drawn first, on the company's side of the ring.
    const pc = l.servers.filter((s) => s.code === 'PC');
    expect(pc.map((s) => s.id)).toEqual(['c', 'b']);
    expect(pc.every((s) => Math.abs(s.angle - l.nodes[1]!.angle) < 0.3)).toBe(true);
  });

  for (const width of [800, 360]) {
    test(`forty companies at ${width} px: shrunk to the legible minimum, a second ring, the least active folded, none lost`, () => {
      const its = items(40, 2);
      const l = ringLayout(its, width);
      expect(l.nodes.length + (l.rest?.codes.length ?? 0)).toBe(40);
      expect(new Set([...l.nodes.map((x) => x.code), ...(l.rest?.codes ?? [])]).size).toBe(40);
      expect(l.nodes.every((x) => x.r * 2 === NODE_MIN)).toBe(true);
      expect(apart(l)).toBeGreaterThanOrEqual(0);
      expect(inside(l)).toBe(true);
      // The busiest are on the outer ring; whatever is folded is no busier than anything drawn.
      const score = new Map(its.map((x) => [x.code, x.score]));
      const drawn = Math.min(...l.nodes.map((x) => score.get(x.code)!));
      for (const c of l.rest?.codes ?? []) expect(score.get(c)!).toBeLessThanOrEqual(drawn);
      const outer = l.nodes.filter((x) => x.ring === 0).map((x) => score.get(x.code)!);
      const inner = l.nodes.filter((x) => x.ring === 1).map((x) => score.get(x.code)!);
      if (inner.length) expect(Math.min(...outer)).toBeGreaterThanOrEqual(Math.max(...inner));
      expect(l.nodes.length).toBeLessThanOrEqual(capacity(l.R1, NODE_MIN) + (l.R1b ? capacity(l.R1b, NODE_MIN) : 0));
      // At most four servers a company are drawn; more fold into «+n».
      expect(l.servers.length + l.more.reduce((a, m) => a + m.n, 0)).toBe(l.nodes.length * 2);
    });
  }
});
