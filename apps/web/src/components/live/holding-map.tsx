'use client';

// ⟨1.24⟩ The holding network map (design/LIVE_VIEWS.md §5; HM-1 topology and runner state, HM-2 traffic and the hub's pulse, HM-3
// disconnection; contract §42). The holding seal is the hub at the centre and never moves; every company from data on the ring (capacity
// and folding in lib/live/ring.ts); each company's servers on the outer ring. Edges: the work spoke hub↔company (gold hairline), the runner
// link hub↔server (lapis; dashed over the public road; red and broken when the runner is silent) and the owner's company links as chords
// (they never carry particles: servers do not talk to each other; a request along one makes it glow while it travels through the hub).
// Every particle is one event (gold: the owner's; silver: agents' work; lapis: data and machines), at most three per edge, folded into «×n»
// beyond; nothing moves at rest; a frozen map says «قدیمی». A tap opens the node's or the edge's sheet; the table view (HM-8) shows every
// company and is the reduced-motion default.

import Link from 'next/link';
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { CompanyMark, Monogram } from '@/components/brand/marks';
import { Sheet } from '@/components/ui/overlay';
import { Pill } from '@/components/ui/primitives';
import { useCompanies } from '@/lib/api/hooks';
import { LINK_KIND, useLinks, type CompanyLink } from '@/lib/api/v34';
import { msFig, serverNameOf, useNetwork, viaFa, type NetNode } from '@/lib/api/v26';
import { companyColor, companyOf } from '@/lib/company';
import { activityScore, flowsPerHour, lockedOf, outsideNode, srvNode, type CompanyLive, type Effect, type LiveState, type ServerLive } from '@/lib/live/model';
import { ParticleLayer, type Pt } from '@/lib/live/particles';
import { outward, ringLayout, type RingLayout } from '@/lib/live/ring';
import { useLiveEffects, useLiveState } from '@/lib/live/store';
import { ago, cx, jTime, usd } from '@/lib/format';
import { prefersReducedMotion, useChanges, useReducedMotion, useTick } from './motion';
import { LiveCorner, useBeacon } from './shell';

// ------------------------------------------------------------------------------------------------------ the model --
export type MapServer = {
  id: string; company: string; name: string; state: string; via: string | null; since: string | null; reason: string | null; reason_fa: string | null;
  last_ok_at: string | null; hub_rtt_ms: number | null; open_jobs: number | null; jobs: number; failed_at: string | null;
};
export type MapCompany = { code: string; nameFa: string; servers: MapServer[]; live: CompanyLive | undefined; locked: boolean };

/** Why a server is off, in plain words, and what fixes it (the hub's `reason`; its own `reason_fa` wins for the short line). */
export const REASON: Record<string, { short: string; long: string; fix: string }> = {
  runner_stopped: { short: 'runner روی سرور ایستاده', long: 'خود سرور در شبکه هست (سرورهای دیگر هنوز به پورت‌هایش میرسند) ولی runner آن به هاب سر نمیزند.', fix: 'از Claude همین سرور بخواه سرویس hq-runner را ببیند و دوباره راه بیندازد.' },
  server_unreachable: { short: 'سرور از شبکه در دسترس نیست', long: 'هیچ‌کس به این سرور نمیرسد: نه runner به هاب سر میزند، نه سرورهای دیگر به پورت‌هایش میرسند. سرور خاموش است یا شبکه‌اش قطع.', fix: 'از کنسول هتزنر وضعیت سرور را ببین؛ این تصمیم با توست.' },
  no_poll: { short: 'runner تماس نمیگیرد', long: 'runner این سرور مدتی است به هاب سر نزده و هاب هنوز نمیداند چرا.', fix: 'از Claude همین سرور بخواه hq-runner status را ببیند.' },
  revoked: { short: 'دسترسی runner برداشته شده', long: 'اتصال این سرور به هاب برداشته شده و کاری رویش اجرا نمیشود.', fix: 'اگر لازم است، سرور را از «همه‌ی سرورها» دوباره وصل کن.' },
  fallback_public: { short: 'از راه عمومی وصل است', long: 'راه خصوصی جواب نداد و runner از آدرس عمومی با TLS آمد؛ کار میکند.', fix: 'اگر تکرار شد، از Claude همین سرور بخواه ip addr و hq-runner status را ببیند.' },
  slow: { short: 'راه کند است', long: 'رفت‌وبرگشت تا هاب از حد معمول بیشتر است؛ کار میکند ولی هر فرمان دیرتر جواب میدهد.', fix: 'اگر ماند، شبکه‌ی همان سرور را ببین.' },
};
const reasonOf = (s: MapServer) => REASON[s.reason ?? (s.state === 'offline' ? 'no_poll' : '')] ?? null;
export const reasonShort = (s: MapServer) => s.reason_fa || reasonOf(s)?.short || 'قطع';

/** The map's companies and servers: the companies from data (and any company a server names that the list does not know yet), each server
 *  as `GET /infra/network` reads it, overridden by the stream's `server.state` when that is newer. */
export function useMapModel(): { companies: MapCompany[]; links: CompanyLink[]; loaded: boolean; s: LiveState } {
  const cos = useCompanies();
  const net = useNetwork();
  const canvas = useLinks();
  const s = useLiveState((x) => x);
  const companies = useMemo(() => {
    const list = (cos.data ?? []).filter((c) => c.kind !== 'holding' && c.status !== 'archived');
    const codes = [...list.map((c) => c.code)];
    for (const code of s.order) if (!codes.includes(code)) codes.push(code);
    const nodes: NetNode[] = (net.data?.nodes ?? []).filter((n) => n.id !== 'hub');
    for (const n of nodes) if (!codes.includes(n.company)) codes.push(n.company);
    const netAt = Date.parse(net.data?.at ?? '') || 0;
    const servers: MapServer[] = nodes.map((n) => {
      const live: ServerLive | undefined = s.servers_by_id[n.id];
      const fresh = live && Date.parse(live.at) >= netAt;
      const state = fresh ? live.state : n.state;
      // The stream's when and why hold as long as the state it told is still the state (the map read after it agrees).
      const told = live && live.state === state ? live : null;
      const link = Object.values(s.links).find((l) => l.from === n.id && l.to === 'hub');
      return {
        id: n.id, company: n.company, name: n.name, state, via: told?.via ?? n.via, since: told?.since ?? null,
        reason: told?.reason ?? null, reason_fa: told?.reason_fa ?? null, last_ok_at: link?.last_ok_at ?? null,
        hub_rtt_ms: (fresh ? live.hub_rtt_ms : null) ?? n.hub_rtt_ms, open_jobs: told?.open_jobs ?? null, jobs: live?.jobs ?? 0, failed_at: live?.failed_at ?? null,
      };
    });
    for (const live of Object.values(s.servers_by_id)) {
      if (servers.some((x) => x.id === live.id) || !live.company) continue;
      if (!codes.includes(live.company)) codes.push(live.company);
      servers.push({ id: live.id, company: live.company, name: live.id, state: live.state, via: live.via, since: live.since, reason: live.reason, reason_fa: live.reason_fa, last_ok_at: null, hub_rtt_ms: live.hub_rtt_ms, open_jobs: live.open_jobs, jobs: live.jobs, failed_at: live.failed_at });
    }
    return codes.map((code): MapCompany => {
      const known = list.find((c) => c.code === code);
      const mine = servers.filter((x) => x.company === code);
      const nameFa = known?.name_fa ?? s.companies[code]?.name_fa ?? mine[0]?.name ?? code;
      return { code, nameFa, live: s.companies[code], locked: lockedOf(s, code), servers: mine.map((x) => ({ ...x, name: serverNameOf(code, nameFa, x.name, mine.length).text })) };
    });
  }, [cos.data, net.data, s]);
  return { companies, links: canvas.data?.links ?? [], loaded: !!cos.data || !!net.data, s };
}

// ------------------------------------------------------------------------------------------------------ geometry --
type Node = { x: number; y: number; r: number };
const towards = (a: Pt, b: Pt, d: number): Pt => { const L = Math.hypot(b.x - a.x, b.y - a.y) || 1; return { x: a.x + ((b.x - a.x) / L) * d, y: a.y + ((b.y - a.y) / L) * d }; };
const chordD = (a: Pt, b: Pt, c: Pt) => { const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2; const qx = mx + (c.x - mx) * 0.55, qy = my + (c.y - my) * 0.55; return `M${a.x.toFixed(1)} ${a.y.toFixed(1)} Q${qx.toFixed(1)} ${qy.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}`; };
const octagon = (r: number) => Array.from({ length: 8 }, (_, k) => { const a = Math.PI / 8 + (k * Math.PI) / 4; return `${(r * Math.cos(a)).toFixed(1)},${(r * Math.sin(a)).toFixed(1)}`; }).join(' ');
const star = (r: number, ri: number, n = 24) => Array.from({ length: 2 * n }, (_, k) => { const a = -Math.PI / 2 + (k * Math.PI) / n; const R = k % 2 ? ri : r; return `${(R * Math.cos(a)).toFixed(2)},${(R * Math.sin(a)).toFixed(2)}`; }).join(' ');

function nodeIndex(l: RingLayout, companies: MapCompany[]): Map<string, Node> {
  const m = new Map<string, Node>();
  m.set('hub', { x: l.cx, y: l.cy, r: l.hubR });
  for (const n of l.nodes) m.set(n.code, { x: n.x, y: n.y, r: n.r });
  if (l.rest) for (const code of l.rest.codes) m.set(code, { x: l.rest.x, y: l.rest.y, r: l.rest.r });
  for (const sv of l.servers) m.set(srvNode(sv.id), { x: sv.x, y: sv.y, r: sv.size / 2 });
  // A server not drawn (its company folded, or more than four) travels to its company's node.
  for (const c of companies) for (const sv of c.servers) if (!m.has(srvNode(sv.id)) && m.has(c.code)) m.set(srvNode(sv.id), m.get(c.code)!);
  for (const c of companies) { const at = m.get(c.code); if (at) { const o = outward(l, at.x, at.y); m.set(outsideNode(c.code), { x: o.x, y: o.y, r: 0 }); } }
  return m;
}

/** The points a particle travels for [path] (two or three node ids), from the edge of the first node to the edge of the last. */
function pointsOf(ix: Map<string, Node>, path: string[]): Pt[] | null {
  const nodes = path.map((id) => ix.get(id));
  if (nodes.some((n) => !n)) return null;
  const ns = nodes as Node[];
  const first = ns[0]!, second = ns[1]!, last = ns[ns.length - 1]!, before = ns[ns.length - 2]!;
  const pts: Pt[] = ns.map((n) => ({ x: n.x, y: n.y }));
  pts[0] = towards(first, second, first.r + 2);
  pts[pts.length - 1] = towards(last, before, last.r + 2);
  return pts;
}

// ------------------------------------------------------------------------------------------------------- views --
const subscribeNone = () => () => {};
/** `?view=table` opens the table (the «+n شرکت دیگر» link of the office). */
const useUrlView = () => useSyncExternalStore(subscribeNone, () => { const v = new URLSearchParams(window.location.search).get('view'); return v === 'table' || v === 'map' ? v : null; }, () => null);

type Sel = { kind: 'hub' } | { kind: 'co'; code: string } | { kind: 'srv'; id: string } | { kind: 'chord'; id: string };

/** HM-1…HM-3 with the table (HM-8): the map card's body. [compact] for the companies page. */
export function HoldingMap({ compact = false, onRoutes }: { compact?: boolean; onRoutes?: (serverId: string) => void }) {
  const model = useMapModel();
  const rm = useReducedMotion();
  const urlView = useUrlView();
  const [pick, setPick] = useState<'map' | 'table' | null>(null);
  const view = pick ?? urlView ?? (rm ? 'table' : 'map');
  const [sel, setSel] = useState<Sel | null>(null);
  const box = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver((es) => setWidth(Math.round(es[0]!.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const n = model.companies.length;
  return (
    <div className="flex flex-col gap-3" data-testid="holding-map" data-view={view}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-0 flex-1 text-[12px] text-muted">{n ? `${n} شرکت، از داده؛ هر ذره یک رویداد است. هر چیزی را لمس کن.` : 'هنوز شرکتی روی نقشه نیست.'}</span>
        <LiveCorner />
        <div role="radiogroup" aria-label="نما" className="flex flex-none rounded-full bg-tile p-0.5">
          {(['map', 'table'] as const).map((v) => (
            <button key={v} type="button" role="radio" aria-checked={view === v} onClick={() => setPick(v)} className={cx('h-7 rounded-full px-3 text-[12px]', view === v ? 'bg-raised font-semibold text-ink' : 'text-sec hover:text-ink')}>{v === 'map' ? 'نقشه' : 'جدول'}</button>
          ))}
        </div>
      </div>
      <div ref={box} className="w-full min-w-0">
        {view === 'table' ? <MapTable companies={model.companies} onSelect={(code) => setSel({ kind: 'co', code })} />
          : width > 0 ? <MapCanvas model={model} width={width} compact={compact} sel={sel} onSelect={setSel} onRest={() => setPick('table')} />
          : <div className="aspect-square w-full max-h-[640px]" aria-hidden />}
      </div>
      {view === 'map' ? <MapLegend /> : null}
      <MapSheet sel={sel} model={model} onClose={() => setSel(null)} onRoutes={onRoutes} />
    </div>
  );
}

function MapCanvas({ model, width, compact, sel, onSelect, onRest }: { model: ReturnType<typeof useMapModel>; width: number; compact: boolean; sel: Sel | null; onSelect: (s: Sel) => void; onRest: () => void }) {
  const { companies, links, s } = model;
  const uid = useId().replace(/:/g, '');
  const now = useTick(60_000);
  // Ordered by live activity, never alphabetical; ranked again once a minute, or when a company or a server's state comes or goes (an
  // offline server is never folded away), so the action stays on top without the ring jumping at every event.
  const setSig = companies.map((c) => `${c.code}:${c.servers.map((x) => `${x.id}=${x.state}`).join(',')}`).join('|');
  const [rank, setRank] = useState<{ sig: string; at: number; order: string[] }>({ sig: '', at: 0, order: [] });
  if (rank.sig !== setSig || rank.at !== now) {
    const order = companies.map((c, i) => ({ code: c.code, i, sc: activityScore(c.live, c.servers.filter((x) => x.state === 'offline').length, now) }))
      .sort((a, b) => b.sc - a.sc || a.i - b.i).map((x) => x.code);
    setRank({ sig: setSig, at: now, order });
  }
  const items = useMemo(() => {
    const by = new Map(companies.map((c) => [c.code, c]));
    return rank.order.filter((code) => by.has(code)).map((code, i, all) => ({ code, score: all.length - i, servers: by.get(code)!.servers.map((x) => ({ id: x.id, state: x.state })) }));
    // The servers' states are in the rank's signature; the people at work only move the rank once a minute.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rank]);
  const l = useMemo(() => ringLayout(items, compact ? Math.min(width, 560) : width), [items, width, compact]);
  const ix = useMemo(() => nodeIndex(l, companies), [l, companies]);
  const narrow = l.width < 520;
  const dense = l.nodes.length > 8;
  const byCode = useMemo(() => new Map(companies.map((c) => [c.code, c])), [companies]);
  const allServers = useMemo(() => companies.flatMap((c) => c.servers), [companies]);
  const beacon = useBeacon();
  const rm = useReducedMotion();
  const { data: cosList } = useCompanies();
  const clock = useTick(1000, allServers.some((x) => !!x.failed_at));

  // The particle layer: one per screen, its two groups in this SVG.
  const svg = useRef<SVGSVGElement | null>(null);
  const parts = useRef<SVGGElement | null>(null);
  const chips = useRef<SVGGElement | null>(null);
  const gem = useRef<SVGCircleElement | null>(null);
  const rim = useRef<SVGPolygonElement | null>(null);
  const layer = useRef<ParticleLayer | null>(null);
  const geo = useRef({ ix, l });
  const [healed, setHealed] = useState<Record<string, number>>({});
  const [said, setSaid] = useState('');
  useLayoutEffect(() => { geo.current = { ix, l }; });
  useEffect(() => {
    if (!parts.current || !chips.current) return;
    const root = svg.current;
    const lyr = new ParticleLayer(parts.current, chips.current, {
      reduced: prefersReducedMotion,
      edges: (edge) => {
        if (!root) return [];
        if (edge.startsWith('chord:')) { const [a, b] = edge.slice(6).split('|'); return [...root.querySelectorAll(`[data-chord="${a}|${b}"],[data-chord="${b}|${a}"]`)]; }
        return edge.split('>').filter((e) => e !== 'hub' && !e.startsWith('out:')).flatMap((e) => [...root.querySelectorAll(`[data-node-edge="${CSS.escape(e)}"]`)]);
      },
    });
    layer.current = lyr;
    const onVis = () => { if (document.hidden) lyr.clear(); };
    document.addEventListener('visibilitychange', onVis);
    return () => { document.removeEventListener('visibilitychange', onVis); lyr.destroy(); layer.current = null; };
  }, []);
  // A new layout drops what is in flight (its points no longer exist).
  useEffect(() => { layer.current?.clear(); }, [l]);

  useLiveEffects((fx: Effect[]) => {
    const lyr = layer.current;
    if (!lyr) return;
    const { ix: at, l: lay } = geo.current;
    const words: string[] = [];
    for (const f of fx) {
      if (f.kind === 'particle') {
        const pts = pointsOf(at, f.path);
        if (!pts) continue;
        lyr.emit(f.edge, pts, f.color, {
          delay: f.delay,
          onMid: f.through ? () => { const r = rim.current; if (r) { r.setAttribute('data-pass', ''); setTimeout(() => r.removeAttribute('data-pass'), 200); } } : undefined,
        });
        if (f.chord && links.some((k) => k.state === 'on' && ((k.from === f.chord![0] && k.to === f.chord![1]) || (k.from === f.chord![1] && k.to === f.chord![0])))) lyr.tint(`chord:${f.chord[0]}|${f.chord[1]}`, 'silver');
      } else if (f.kind === 'ceremony') {
        lyr.ring({ x: lay.cx, y: lay.cy }, lay.hubR - 6, 'var(--hq-gold-ink)', { ceremony: true });
        const g = gem.current;
        if (g) { g.setAttribute('data-lit', ''); setTimeout(() => g.removeAttribute('data-lit'), 520); }
      } else if (f.kind === 'ripple') {
        const n = at.get(f.node);
        if (n) lyr.ring({ x: n.x, y: n.y }, n.r + 4, f.tone === 'neg' ? 'var(--hq-negative)' : f.tone === 'pos' ? 'var(--hq-positive)' : 'var(--hq-silver-ink)');
      } else if (f.kind === 'heal') {
        const id = f.server;
        setHealed((h) => ({ ...h, [id]: Date.now() }));
        setTimeout(() => setHealed((h) => { const rest = { ...h }; delete rest[id]; return rest; }), 2000);
        const sv = allServers.find((x) => x.id === id);
        if (sv) words.push(`${sv.name} دوباره وصل شد`);
      } else if (f.kind === 'break') {
        const sv = allServers.find((x) => x.id === f.server);
        if (sv) words.push(`${sv.name} قطع شد`);
      }
    }
    if (words.length) setSaid(words.join('. '));
  });

  const hub = { x: l.cx, y: l.cy };
  const hatch = `hatch-${uid}`;
  const chordsDrawn = links.filter((k) => ix.has(k.from) && ix.has(k.to) && l.nodes.some((n) => n.code === k.from) && l.nodes.some((n) => n.code === k.to));
  const slot = (2 * Math.PI) / Math.max(1, l.nodes.length + (l.rest ? 1 : 0));
  const offline = allServers.filter((x) => x.state === 'offline');
  const failingPairs = Object.values(s.links).filter((k) => k.to !== 'hub' && ix.has(srvNode(k.from)) && ix.has(srvNode(k.to)));
  const k = narrow ? 1.12 : 1;

  return (
    <div className="relative mx-auto" style={{ width: l.width, height: l.height }} data-map-width={l.width} data-stale={beacon.state !== 'live' || undefined}>
      <svg ref={svg} width={l.width} height={l.height} viewBox={`0 0 ${l.width} ${l.height}`} className="absolute inset-0 overflow-visible" role="img"
        aria-label={`نقشه‌ی زنده‌ی شبکه: هاب، ${companies.length} شرکت و ${allServers.length} سرور${offline.length ? `؛ ${offline.length} سرور قطع` : ''}`}>
        <defs>
          <pattern id={hatch} patternUnits="userSpaceOnUse" width={6} height={6} patternTransform="rotate(45)">
            <line x1={0} y1={0} x2={0} y2={6} stroke="var(--hq-negative)" strokeWidth={1.5} opacity={0.3} />
          </pattern>
        </defs>
        {/* Locked companies: their sector hatched (GL-2 on the map). */}
        {l.nodes.filter((n) => byCode.get(n.code)?.locked).map((n) => {
          const half = Math.min(slot * 0.42, Math.asin(Math.min(1, (n.r + 16) / (n.ring === 1 && l.R1b ? l.R1b : l.R1)))), a0 = n.angle - half, a1 = n.angle + half;
          const r0 = Math.max(l.hubR + 6, (n.ring === 1 && l.R1b ? l.R1b : l.R1) - n.r - 12), r1 = l.R2 + 14;
          const p = (r: number, a: number) => `${(l.cx + r * Math.cos(a)).toFixed(1)} ${(l.cy + r * Math.sin(a)).toFixed(1)}`;
          return <path key={`h-${n.code}`} d={`M${p(r0, a0)} L${p(r1, a0)} A${r1} ${r1} 0 0 1 ${p(r1, a1)} L${p(r0, a1)} A${r0} ${r0} 0 0 0 ${p(r0, a0)}Z`} fill={`url(#${hatch})`} data-locked-sector={n.code} />;
        })}
        {/* The owner's company links (§35.6): chords through the inner ring; never a road themselves. */}
        <g>
          {chordsDrawn.map((c) => {
            const a = ix.get(c.from)!, b = ix.get(c.to)!;
            const d = chordD(a, b, hub);
            return (
              <g key={c.id}>
                <path d={d} fill="none" data-chord={`${c.from}|${c.to}`} className="hq-m2" stroke={c.state === 'on' ? 'var(--hq-gold-ink)' : 'var(--hq-text-muted)'} strokeOpacity={c.state === 'on' ? 0.45 : 0.7} strokeWidth={1.2} strokeDasharray={c.state === 'on' ? undefined : '1 5'} />
                <path d={d} fill="none" stroke="transparent" strokeWidth={14} className="cursor-pointer" onClick={() => onSelect({ kind: 'chord', id: c.id })} />
              </g>
            );
          })}
        </g>
        {/* Work spokes, hub ↔ company. */}
        <g>
          {l.nodes.map((n) => {
            const locked = byCode.get(n.code)?.locked;
            const a = towards(hub, n, l.hubR + 2), b = towards(n, hub, n.r + 7);
            return <line key={n.code} x1={a.x} y1={a.y} x2={b.x} y2={b.y} data-node-edge={n.code} className="hq-m2" stroke={locked ? 'var(--hq-negative)' : 'var(--hq-gold-ink)'} strokeOpacity={locked ? 0.5 : 0.35} strokeWidth={1.3} strokeDasharray={locked ? '2 4' : undefined} />;
          })}
        </g>
        {/* Runner links, hub ↔ server: lapis; dashed over the public road; red and broken (M9) while the runner is silent. */}
        <g>
          {l.servers.map((p) => {
            const sv = allServers.find((x) => x.id === p.id);
            if (!sv) return null;
            const a = towards(hub, p, l.hubR), b = towards(p, hub, p.size / 2 + 3);
            const L = Math.hypot(b.x - a.x, b.y - a.y);
            const off = sv.state === 'offline' || Object.values(s.links).some((x) => x.from === sv.id && x.to === 'hub');
            const ok = !!healed[sv.id];
            // The gap opens between the company's node and the server (the line's middle sits under the company's octagon).
            const g = Math.max(L * 0.55, L - Math.max(12, (l.R2 - l.R1) / 2 - 6));
            const dash = off ? `${(g - 4).toFixed(1)} 8 ${L.toFixed(1)}` : sv.via === 'public' ? '5 4' : `${g.toFixed(1)} 0 ${L.toFixed(1)}`;
            return <line key={p.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} data-node-edge={srvNode(p.id)} data-runner={off ? 'broken' : sv.via === 'public' ? 'public' : 'private'} className="hq-m9"
              stroke={off ? 'var(--hq-negative)' : ok ? 'var(--hq-positive)' : sv.state === 'revoked' ? 'var(--hq-text-muted)' : 'var(--hq-lapis)'} strokeOpacity={off || ok ? 1 : 0.55} strokeWidth={off || ok ? 1.6 : 1.1}
              style={{ strokeDasharray: dash }} />;
          })}
          {failingPairs.map((x) => {
            const a = ix.get(srvNode(x.from))!, b = ix.get(srvNode(x.to))!;
            return <line key={x.key} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="var(--hq-negative)" strokeWidth={1.2} strokeDasharray="3 3" data-failing-link={x.key} />;
          })}
        </g>
        {/* Activity arcs (share of people at work, the company's chart colour) around each company. */}
        <g>
          {l.nodes.map((n) => {
            const c = byCode.get(n.code)!;
            const share = c.live?.total ? Math.min(1, (c.live.working ?? 0) / c.live.total) : 0;
            const r = n.r + 5, C = 2 * Math.PI * r;
            return (
              <g key={n.code} transform={`translate(${n.x.toFixed(1)} ${n.y.toFixed(1)})`}>
                <circle r={r} fill="none" stroke="var(--hq-line-divider)" strokeWidth={3} />
                <circle r={r} fill="none" stroke={companyColor(cosList, n.code)} strokeWidth={3} strokeLinecap="round" transform="rotate(-90)" strokeDasharray={`${(share * C).toFixed(1)} ${C.toFixed(1)}`} className="hq-m12" data-arc={n.code} />
              </g>
            );
          })}
        </g>
        {/* Servers on the outer ring: a shape per state, never colour alone. */}
        <g>
          {l.servers.map((p) => {
            const sv = allServers.find((x) => x.id === p.id);
            if (!sv) return null;
            const h = p.size / 2;
            const state = sv.state === 'online' ? 'online' : sv.state === 'offline' ? 'offline' : sv.state === 'revoked' ? 'revoked' : 'pending';
            const stroke = state === 'online' ? 'var(--hq-positive)' : state === 'offline' ? 'var(--hq-negative)' : state === 'pending' ? 'var(--hq-warning)' : 'var(--hq-text-muted)';
            const failed = sv.failed_at && clock - Date.parse(sv.failed_at) < 4000;
            const isSel = sel?.kind === 'srv' && sel.id === sv.id;
            return (
              <g key={p.id} transform={`translate(${p.x.toFixed(1)} ${p.y.toFixed(1)})`} role="button" tabIndex={0} data-server={sv.id} data-state={state}
                aria-label={`سرور ${sv.name}: ${state === 'online' ? 'وصل' : state === 'offline' ? `قطع، ${reasonShort(sv)}` : state === 'pending' ? 'در انتظار' : 'برداشته شده'}`}
                className="cursor-pointer outline-none [&:focus-visible_rect]:stroke-[var(--hq-gold-bright)]"
                onClick={() => onSelect({ kind: 'srv', id: sv.id })} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect({ kind: 'srv', id: sv.id }); } }}>
                {sv.jobs > 0 && state === 'online' ? <circle r={h + 6} fill="none" stroke="var(--hq-lapis)" strokeWidth={1.6} strokeDasharray="10 30" className={rm ? undefined : 'hq-m7'} data-job /> : null}
                <rect x={-h} y={-h} width={p.size} height={p.size} rx={4} fill="var(--hq-surface-tile)" stroke={isSel ? 'var(--hq-gold-bright)' : stroke} strokeWidth={isSel ? 2 : 1.6} strokeDasharray={state === 'pending' ? '3 2' : undefined} className="hq-m2" />
                {state === 'offline' ? <path d={`M${-h / 2} ${-h / 2}L${h / 2} ${h / 2}M${h / 2} ${-h / 2}L${-h / 2} ${h / 2}`} stroke="var(--hq-negative)" strokeWidth={1.6} /> : null}
                {sv.via === 'public' && state === 'online' ? (
                  <g transform={`translate(${h + 4} ${-h - 4})`} fill="none" stroke="var(--hq-warning)" strokeWidth={1} data-globe><circle r={5} /><path d="M-5 0H5M0 -5C-2.4 -2 -2.4 2 0 5M0 -5C2.4 -2 2.4 2 0 5" /></g>
                ) : null}
                {failed ? <path d={`M${h + 2} ${h - 2}l3 3l5 -6`} fill="none" stroke="var(--hq-negative)" strokeWidth={1.6} /> : null}
              </g>
            );
          })}
          {l.more.map((m) => <text key={`more-${m.code}`} x={m.x} y={m.y + 4} textAnchor="middle" fontSize={10.5} fill="var(--hq-text-muted)">+{m.n}</text>)}
        </g>
        <g ref={parts} data-particles />
        {/* Disconnects: a chip that stays — «قطع · when · why» (HM-3). */}
        <g>
          {offline.map((sv) => {
            const p = ix.get(srvNode(sv.id));
            if (!p) return null;
            const o = towards({ x: l.cx, y: l.cy }, p, Math.hypot(p.x - l.cx, p.y - l.cy) + (narrow ? 26 : 32));
            const text = narrow ? `قطع · ${sv.since ? jTime(sv.since) : '—'}` : `قطع · ${sv.since ? jTime(sv.since) : '—'} · ${reasonShort(sv)}`;
            const w = Math.min(l.width - 8, text.length * 6.1 + 18);
            const x = Math.max(4 + w / 2, Math.min(l.width - 4 - w / 2, o.x));
            const y = Math.max(12, Math.min(l.height - 12, o.y));
            return (
              <g key={sv.id} transform={`translate(${x.toFixed(1)} ${y.toFixed(1)})`} className="cursor-pointer" data-break-chip={sv.id} onClick={() => onSelect({ kind: 'srv', id: sv.id })}>
                {/* Settles in by opacity only: a CSS transform would replace the SVG one. */}
                <g className="hq-m2-in">
                  <rect x={-w / 2} y={-10} width={w} height={20} rx={10} fill="var(--hq-soft-negative)" stroke="var(--hq-negative)" />
                  <text y={4} textAnchor="middle" fontSize={10.5 * k} fontWeight={600} fill="var(--hq-negative)">{text}</text>
                </g>
              </g>
            );
          })}
        </g>
        <g ref={chips} data-chips />
      </svg>

      {/* The hub: the holding seal (24 rays, the lapis gem, the monogram). It never moves; its gem brightens for the owner's acts only. */}
      <button type="button" onClick={() => onSelect({ kind: 'hub' })} aria-label="هاب · ستاد"
        className="absolute flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-[var(--hq-gold-bright)]"
        style={{ left: l.cx, top: l.cy, width: l.hubR * 2, height: l.hubR * 2 }} data-hub>
        <svg width={l.hubR * 2} height={l.hubR * 2} viewBox={`${-l.hubR} ${-l.hubR} ${l.hubR * 2} ${l.hubR * 2}`} aria-hidden className="absolute inset-0">
          <polygon ref={rim} points={star(l.hubR, l.hubR * 0.84)} fill="var(--hq-gold-fill)" className="opacity-85 transition-opacity duration-200 [&[data-pass]]:opacity-100" />
          <circle ref={gem} r={l.hubR * 0.75} className="transition-[fill] duration-[480ms] [fill:color-mix(in_srgb,var(--hq-lapis)_22%,var(--hq-surface-page))] [&[data-lit]]:[fill:color-mix(in_srgb,var(--hq-lapis)_62%,var(--hq-surface-page))]" data-gem />
          <circle r={l.hubR * 0.66} fill="none" stroke="var(--hq-gold-fill)" strokeOpacity={0.55} />
        </svg>
        <span className="relative"><Monogram size={Math.round(l.hubR * 0.8)} /></span>
      </button>
      {!narrow ? <span className="pointer-events-none absolute -translate-x-1/2 whitespace-nowrap text-[11px] text-muted" style={{ left: l.cx, top: l.cy + l.hubR + 4 }}>ستاد · هاب</span> : null}

      {/* Companies: their own mark in an octagon, the name under it. */}
      {l.nodes.map((n) => {
        const c = byCode.get(n.code)!;
        const isSel = sel?.kind === 'co' && sel.code === n.code;
        const working = c.live?.working;
        return (
          <button key={n.code} type="button" onClick={() => onSelect({ kind: 'co', code: n.code })} data-company={n.code} data-locked={c.locked || undefined}
            aria-label={`${c.nameFa}${c.locked ? '، قفل' : ''}: ${working == null ? '—' : working} نفر در کار${c.servers.some((x) => x.state === 'offline') ? '، سروری قطع است' : ''}`}
            className="hq-m11 absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center rounded-full"
            style={{ left: n.x, top: n.y }}>
            <span className="relative flex items-center justify-center" style={{ width: n.r * 2, height: n.r * 2 }}>
              <svg width={n.r * 2} height={n.r * 2} viewBox={`${-n.r} ${-n.r} ${n.r * 2} ${n.r * 2}`} aria-hidden className="absolute inset-0">
                <polygon points={octagon(n.r)} fill={c.locked ? `url(#${hatch})` : 'var(--hq-surface-tile)'} stroke={isSel ? 'var(--hq-gold-bright)' : 'var(--hq-line-strong)'} strokeWidth={isSel ? 2 : 1} />
                {c.locked ? <polygon points={octagon(n.r)} fill="var(--hq-surface-tile)" opacity={0.55} /> : null}
              </svg>
              <span className="relative text-ink"><CompanyMark code={n.code} height={Math.round(n.r * 0.9)} /></span>
            </span>
            {n.r >= 18 ? (
              <span className="pointer-events-none absolute top-full mt-2 flex flex-col items-center whitespace-nowrap">
                <span className="text-[12px] font-semibold text-ink [paint-order:stroke] [-webkit-text-stroke:3px_var(--hq-surface-card)]">{c.nameFa}</span>
                {!narrow && !dense ? <span className="text-[10.5px] text-sec">{working == null ? '—' : working} در کار از {c.live?.total ?? '—'}</span> : null}
              </span>
            ) : null}
          </button>
        );
      })}
      {l.rest ? (
        <button type="button" onClick={onRest} data-rest={l.rest.codes.length} aria-label={`بقیه، ${l.rest.codes.length} شرکت؛ در نمای جدول`}
          className="absolute flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-strong bg-tile text-[10.5px] font-semibold text-sec"
          style={{ left: l.rest.x, top: l.rest.y, width: l.rest.r * 2 + 18, height: l.rest.r * 2 }}>
          بقیه · {l.rest.codes.length}
        </button>
      ) : null}
      {beacon.state !== 'live' ? <span className="pointer-events-none absolute end-2 top-2 rounded-full border border-warn bg-warn-soft px-2.5 text-[12px] leading-6 text-warn" data-map-stale>قدیمی</span> : null}
      <div className="sr-only" aria-live="polite">{said}</div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------- HM-8 --
type SortKey = 'name' | 'servers' | 'working' | 'sessions' | 'flows' | 'last';
function TableRow({ c, now, onSelect }: { c: MapCompany; now: number; onSelect: () => void }) {
  const on = c.servers.filter((x) => x.state === 'online').length;
  const total = c.servers.length || (c.live?.servers_total ?? 0);
  const sig = `${on}/${total}|${c.live?.working}|${c.live?.sessions_open}|${c.locked}`;
  const changes = useChanges(sig);
  return (
    <tr className={cx('cursor-pointer border-b border-div hover:bg-hover', changes > 0 && (changes % 2 ? 'hq-tint' : 'hq-tint-b'))} onClick={onSelect} data-row={c.code}>
      <td className="px-2 py-2"><span className="flex items-center gap-2"><CompanyMark code={c.code} height={13} mono /><span className="font-semibold text-ink">{c.nameFa}</span>{c.locked ? <Pill tone="neg" className="h-5 text-[11px]">قفل</Pill> : null}</span></td>
      <td className={cx('px-2 py-2', on < total ? 'font-semibold text-neg' : 'text-sec')}>{total ? `${on} از ${total}${on < total ? ' · قطع' : ''}` : '—'}</td>
      <td className="px-2 py-2 text-sec">{c.live?.working == null ? '—' : `${c.live.working} از ${c.live.total ?? '—'}`}</td>
      <td className="px-2 py-2 text-sec">{c.live?.sessions_open ?? '—'}</td>
      <td className="px-2 py-2 text-sec">{c.live ? flowsPerHour(c.live, now) : '—'}</td>
      <td className="px-2 py-2 text-muted">{c.live?.last_event_at ? ago(c.live.last_event_at, now) : '—'}</td>
    </tr>
  );
}

function MapTable({ companies, onSelect }: { companies: MapCompany[]; onSelect: (code: string) => void }) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'working', desc: true });
  const now = useTick(30_000);
  const val = (c: MapCompany): number | string => {
    if (sort.key === 'name') return c.nameFa;
    if (sort.key === 'servers') return c.servers.filter((x) => x.state === 'offline').length * -1000 + c.servers.length;
    if (sort.key === 'working') return c.live?.working ?? -1;
    if (sort.key === 'sessions') return c.live?.sessions_open ?? -1;
    if (sort.key === 'flows') return c.live ? flowsPerHour(c.live, now) : -1;
    return c.live?.last_event_at ? Date.parse(c.live.last_event_at) : 0;
  };
  const rows = companies.map((c, i) => ({ c, i })).sort((a, b) => {
    const x = val(a.c), y = val(b.c);
    const d = typeof x === 'string' ? x.localeCompare(String(y), 'fa') : x - (y as number);
    return (sort.desc ? -d : d) || a.i - b.i;
  });
  const head = (key: SortKey, fa: string) => (
    <th scope="col" aria-sort={sort.key === key ? (sort.desc ? 'descending' : 'ascending') : 'none'} className="px-2 py-1.5 text-start text-[11.5px] font-medium text-muted">
      <button type="button" onClick={() => setSort((o) => ({ key, desc: o.key === key ? !o.desc : true }))} className="hover:text-ink">{fa}{sort.key === key ? (sort.desc ? ' ↓' : ' ↑') : ''}</button>
    </th>
  );
  if (!companies.length) return <p className="py-6 text-center text-[13px] text-muted">هنوز شرکتی نیست.</p>;
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full min-w-[520px] border-collapse text-[13px]" aria-label="جدول زنده‌ی شرکت‌ها" data-testid="map-table">
        <thead><tr className="border-b border-div">{head('name', 'شرکت')}{head('servers', 'سرورها')}{head('working', 'در کار')}{head('sessions', 'سشن باز')}{head('flows', 'جریان در ساعت')}{head('last', 'آخرین رویداد')}</tr></thead>
        <tbody>{rows.map(({ c }) => <TableRow key={c.code} c={c} now={now} onSelect={() => onSelect(c.code)} />)}</tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------- legend --
export function MapLegend() {
  const dot = (color: string) => <i aria-hidden className="inline-block size-2 rounded-full" style={{ background: color }} />;
  const line = (color: string, dash?: string) => <svg width={22} height={4} aria-hidden><line x1={0} y1={2} x2={22} y2={2} stroke={color} strokeWidth={1.6} strokeDasharray={dash} /></svg>;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[11.5px] text-sec" aria-label="راهنمای نقشه">
      <span className="inline-flex items-center gap-1.5">{dot('var(--hq-gold-ink)')}فرمان تو</span>
      <span className="inline-flex items-center gap-1.5">{dot('var(--hq-silver-ink)')}کار ایجنت‌ها</span>
      <span className="inline-flex items-center gap-1.5">{dot('var(--hq-lapis)')}خواندن داده · کار روی سرور</span>
      <span className="inline-flex items-center gap-1.5">{line('var(--hq-lapis)')}runner · شبکه‌ی خصوصی</span>
      <span className="inline-flex items-center gap-1.5">{line('var(--hq-warning)', '4 3')}راه عمومی</span>
      <span className="inline-flex items-center gap-1.5">{line('var(--hq-negative)')}قطع</span>
      <span className="inline-flex items-center gap-1.5">{line('var(--hq-gold-ink)')}پیوند دو شرکت</span>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------- sheets --
function Rows({ children }: { children: ReactNode }) { return <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[13px] leading-6">{children}</dl>; }
function Row({ k, children }: { k: string; children: ReactNode }) { return <><dt className="text-muted">{k}</dt><dd className="m-0 min-w-0 text-ink">{children}</dd></>; }
const durFa = (ms: number) => { const s = Math.max(0, Math.round(ms / 1000)); const m = Math.floor(s / 60); return m ? `${m} دقیقه و ${s % 60} ثانیه` : `${s} ثانیه`; };

function MapSheet({ sel, model, onClose, onRoutes }: { sel: Sel | null; model: ReturnType<typeof useMapModel>; onClose: () => void; onRoutes?: (id: string) => void }) {
  const { data: companies } = useCompanies();
  const beacon = useBeacon();
  const srv = sel?.kind === 'srv' ? model.companies.flatMap((c) => c.servers).find((x) => x.id === sel.id) ?? null : null;
  const now = useTick(1000, !!srv && srv.state === 'offline');
  const s = model.s;
  let title: ReactNode = '';
  let body: ReactNode = null;
  if (sel?.kind === 'hub') {
    const all = model.companies.flatMap((c) => c.servers);
    title = 'ستاد · هاب';
    body = (
      <Rows>
        <Row k="سرورهای وصل">{all.filter((x) => x.state === 'online').length} از {all.length}</Row>
        <Row k="الان کار میکنند">{s.people.working == null ? '—' : (s.people.working ?? 0) + (s.people.thinking ?? 0)} از {s.people.total ?? '—'}</Row>
        <Row k="سشن در جریان">{s.sessions.moving ?? '—'}</Row>
        <Row k="منتظر مُهر تو">{s.approvals ?? '—'}</Row>
        <Row k="جریان‌ها در ساعت گذشته">{model.companies.reduce((a, c) => a + flowsPerHour(c.live, now), 0)}</Row>
        <Row k="استریم">{beacon.label}</Row>
      </Rows>
    );
  } else if (sel?.kind === 'co') {
    const c = model.companies.find((x) => x.code === sel.code);
    title = c?.nameFa ?? companyOf(companies, sel.code).nameFa;
    const links = model.links.filter((k) => k.from === sel.code || k.to === sel.code);
    body = c ? (
      <div className="flex flex-col gap-4">
        <Rows>
          <Row k="حال">{c.locked ? <Pill tone="neg">قفل · کلید توقف</Pill> : <Pill tone="pos">روشن</Pill>}</Row>
          <Row k="در کار">{c.live?.working == null ? '—' : `${c.live.working} از ${c.live.total ?? '—'} نفر`}</Row>
          <Row k="سشن‌های باز">{c.live?.sessions_open ?? '—'}</Row>
          <Row k="خرج امروز"><span className="fig">{usd(c.live?.spend_today_usd)}{c.live?.budget_usd ? ` / ${usd(c.live.budget_usd, 0)}` : ''}</span></Row>
          <Row k="سرورها">{c.servers.length ? c.servers.map((x) => `${x.name} · ${x.state === 'online' ? 'وصل' : x.state === 'offline' ? 'قطع' : x.state === 'revoked' ? 'برداشته شده' : 'در انتظار'}`).join('، ') : 'سروری وصل نیست'}</Row>
          <Row k="پیوندها">{links.length ? links.map((k) => `${companyOf(companies, k.from === sel.code ? k.to : k.from).nameFa} (${LINK_KIND[k.kind]}${k.state === 'off' ? '، خاموش' : ''})`).join('، ') : 'فقط با هاب'}</Row>
          <Row k="آخرین رویداد">{c.live?.last_event_at ? ago(c.live.last_event_at, now) : '—'}</Row>
        </Rows>
        <Link href={`/companies/${sel.code}`} className="self-start text-[13px] font-semibold text-gold-ink hover:underline">صفحه‌ی شرکت</Link>
      </div>
    ) : null;
  } else if (srv) {
    const off = srv.state === 'offline';
    const r = reasonOf(srv);
    title = srv.name;
    body = (
      <div className="flex flex-col gap-4" data-server-sheet={srv.id}>
        <Rows>
          <Row k="حال">{off ? <Pill tone="neg">قطع</Pill> : srv.state === 'online' ? (srv.via === 'public' ? <Pill tone="warn">وصل از راه عمومی</Pill> : <Pill tone="pos">وصل</Pill>) : <Pill tone="neutral">{srv.state === 'revoked' ? 'برداشته شده' : 'در انتظار'}</Pill>}</Row>
          {off ? (
            <>
              <Row k="از کی"><span className="fig">{srv.since ? jTime(srv.since) : '—'}</span>{srv.since ? <span className="text-sec"> · {durFa(now - Date.parse(srv.since))}</span> : null}</Row>
              <Row k="آخرین تماس سالم"><span className="fig">{srv.last_ok_at ? jTime(srv.last_ok_at) : '—'}</span></Row>
              <Row k="چرا"><span className="font-semibold">{reasonShort(srv)}</span>{r ? <span className="block text-sec">{r.long}</span> : null}</Row>
              <Row k="چه چیزی معطل است">{srv.open_jobs ? `${srv.open_jobs} کار در صف این سرور` : 'کاری در صف نیست'}</Row>
              <Row k="راه حل">{r?.fix ?? REASON.no_poll!.fix}</Row>
            </>
          ) : (
            <>
              <Row k="وصل از"><span className="fig">{srv.since ? jTime(srv.since) : '—'}</span></Row>
              <Row k="راه">{srv.via === 'public' ? 'عمومی (راه خصوصی جواب نداد)' : srv.via === 'private' ? 'شبکه‌ی خصوصی هلدینگ' : viaFa(srv.via)}</Row>
              <Row k="تأخیر تا هاب"><span className="fig">{msFig(srv.hub_rtt_ms) ?? '—'}</span></Row>
              <Row k="کار در حال اجرا">{srv.jobs ? srv.jobs : 'هیچ'}</Row>
            </>
          )}
        </Rows>
        <div className="flex flex-wrap gap-3">
          <Link href={`/servers/${encodeURIComponent(srv.id)}`} className="text-[13px] font-semibold text-gold-ink hover:underline">صفحه‌ی سرور</Link>
          {onRoutes ? <button type="button" onClick={() => { onRoutes(srv.id); onClose(); }} className="text-[13px] font-semibold text-gold-ink hover:underline">راه‌های این سرور، پورت به پورت</button> : null}
        </div>
        <span className="text-[11px] text-muted">نام سرور به نام شرکت است؛ نام میزبان و نشانی فقط در صفحه‌ی خود سرور.</span>
      </div>
    );
  } else if (sel?.kind === 'chord') {
    const k = model.links.find((x) => x.id === sel.id);
    if (k) {
      title = `${companyOf(companies, k.from).nameFa} ← ${companyOf(companies, k.to).nameFa}`;
      body = (
        <div className="flex flex-col gap-3">
          <Rows>
            <Row k="نوع">{companyOf(companies, k.from).nameFa} {LINK_KIND[k.kind]}</Row>
            <Row k="کاربرد">{k.purpose_fa || '—'}</Row>
            <Row k="حال">{k.state === 'on' ? <Pill tone="pos">روشن</Pill> : <Pill tone="neutral">خاموش</Pill>}</Row>
            <Row k="کار باز روی آن">{k.open_works}</Row>
          </Rows>
          <span className="text-[12px] text-muted">کار میان دو شرکت همیشه از هاب میگذرد؛ این خط فقط رابطه را نشان میدهد.</span>
        </div>
      );
    }
  }
  return (
    <Sheet open={!!sel && !!body} onOpenChange={(v) => { if (!v) onClose(); }} title={title || 'نقشه'} description={sel?.kind === 'srv' ? 'سرور' : sel?.kind === 'co' ? 'شرکت' : sel?.kind === 'chord' ? 'پیوند دو شرکت' : 'هلدینگ'} width={420}>
      {body}
    </Sheet>
  );
}
