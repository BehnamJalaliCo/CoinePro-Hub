'use client';

// ⟨1.8⟩ Contract §26.6: the holding's network map. The hub in the centre, each company's server around it, the road from each to the hub
// coloured by its health and labelled with the road (private or public) and its round trip; a server's own checks of the others, port by
// port, a click away; «بررسی دوباره» asks every runner to check now and follows the results as they come (Android: Network.kt).

import Link from 'next/link';
import { useCallback, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Button, IconButton } from '@/components/ui/button';
import { Bar, Card, Pill } from '@/components/ui/primitives';
import { useCompanies } from '@/lib/api/hooks';
import {
  hubLine, isHub, msFig, netErrorFa, netLastAt, netLink, netNode, netServers, netSummary, nextFreeIp, nodeOutside, ringAngles, serverNameOf, useNetwork, viaFa,
  checkFraction, linkHealth, NET_PORTS, SLOW_MS, HUB,
  type CheckProgress, type HubLine, type LinkHealth, type NetNode, type NetPath, type NetSummary, type NetworkMap, type ServerName,
} from '@/lib/api/v26';
import { companyColor, companyOf } from '@/lib/company';
import { ago, cx, jTime } from '@/lib/format';
import { Iso, Notice, ServerTitle } from './bits';

/** A check the owner started: how far it is (which runners answered) and whether it has ended, done or out of time. */
export type NetCheckRun = { before: NetworkMap | null; progress: CheckProgress; waitedMs: number; ended: boolean };
export const timedOut = (x: NetCheckRun) => x.ended && !(x.progress.expected.size > 0 && [...x.progress.expected].every((id) => x.progress.reported.has(id)));

/** Every node's name as the owner's rule says (the company; the server's own name too when the company has several). */
export function useNetNames(m: NetworkMap | null | undefined): (n: NetNode) => ServerName {
  const { data: companies } = useCompanies();
  return useCallback((n: NetNode) => {
    if (isHub(n)) return { company: 'HQ', companyFa: 'هاب', server: null, text: 'هاب' };
    const known = companies?.find((c) => c.code === n.company);
    // A company the list does not know yet (a server paired before its company was founded in the hub) goes by its server's name.
    if (!known) { const t = n.name || n.company; return { company: n.company, companyFa: t, server: null, text: t }; }
    return serverNameOf(n.company, companyOf(companies, n.company).nameFa, n.name, (m ? netServers(m) : []).filter((x) => x.company === n.company).length);
  }, [companies, m]);
}

const HEALTH_COLOR: Record<LinkHealth, string> = { ok: 'var(--hq-positive)', slow: 'var(--hq-warning)', fail: 'var(--hq-negative)', unknown: 'var(--hq-text-muted)' };

// ------------------------------------------------------------------ the summary --
/** What the summary card says, in words: its headline and its tone. */
export function headline(s: NetSummary): { fa: string; tone: 'pos' | 'neg' | 'warn' | 'neutral' } {
  if (s.servers === 0) return { fa: 'هنوز سروری روی شبکه نیست', tone: 'neutral' };
  if (s.failed.length) return { fa: `${s.failed.length} مسیر قطع است`, tone: 'neg' };
  if (s.allOk) return { fa: 'همه‌ی سرورها به هاب وصل‌اند', tone: 'pos' };
  if (s.slow.length && !s.outside.length && !s.fellBack.length) return { fa: `همه‌ی سرورها به هاب وصل‌اند؛ ${s.slow.length} راه کند است`, tone: 'warn' };
  return { fa: 'همه‌ی سرورها به هاب وصل‌اند', tone: 'warn' };
}

/** What to do about a broken road, in plain words. */
function pathHint(p: NetPath, names: (n: NetNode) => ServerName): string {
  if (p.toHub && p.error === 'offline') return 'runner این سرور تماس نمیگیرد: سرور خاموش است، سرویس hq-runner ایستاده یا به شبکه نمیرسد. Claude همان سرور با hq-runner status علتش را ببیند.';
  if (p.toHub) return `${netErrorFa(p.error)}؛ runner این سرور به هاب نمیرسد و کاری رویش اجرا نمیشود.`;
  return `${netErrorFa(p.error)}؛ ${names(p.from).text} روی پورت ${p.ports.join(' و ')} به ${names(p.to).text} نمیرسد. اگر این راه لازم است، از Claude سرور ${names(p.to).text} بخواه فایروال همان سرور را ببیند. کار میان شرکت‌ها به این راه نیاز ندارد و همیشه از هاب میگذرد.`;
}

/** A server outside the private network: the owner adds it from the Hetzner console (§26.1a), at the next free address. */
const outsideHint = (ip: string | null) => `یعنی هنوز در شبکه‌ی خصوصی نیست: از کنسول هتزنر، Networks، این سرور را به شبکه‌ی هلدینگ اضافه کن${ip ? ` (آدرس آزاد بعدی ${ip})` : ''}. تا آن موقع از آدرس عمومی با TLS کار میکند.`;

function Issue({ color, children }: { color: string; children: ReactNode }) {
  return (
    <div className="flex gap-2.5">
      <span className="mt-1.5 size-2 flex-none rounded-full" style={{ background: color }} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">{children}</div>
    </div>
  );
}

export function SummaryCard({ s, names }: { s: NetSummary; names: (n: NetNode) => ServerName }) {
  const h = headline(s);
  const tone = { pos: ['bg-pos-soft', 'text-pos'], neg: ['bg-neg-soft', 'text-neg'], warn: ['bg-warn-soft', 'text-warn'], neutral: ['bg-tile', 'text-sec'] }[h.tone];
  const title = 'text-[13px] font-semibold text-ink';
  const body = 'text-[12px] leading-6 text-sec';
  return (
    <Card className="flex flex-col gap-3 p-4" aria-label="خلاصه‌ی شبکه">
      <div className="flex items-center gap-3">
        <span className={cx('flex size-10 flex-none items-center justify-center rounded-full', tone[0], tone[1])}><Icon name={h.tone === 'neg' ? 'urgent' : h.tone === 'pos' ? 'seal' : 'globe'} size={20} /></span>
        <div className="flex min-w-0 flex-1 flex-col">
          <h2 className="text-h3 font-semibold text-ink">{h.fa}</h2>
          <span className="text-[12px] text-sec">
            {s.servers === 0 ? <Iso text="وقتی runner اولین سرور وصل شد، راهش به هاب اینجا دیده میشود." />
              : s.allOk ? `هر ${s.servers} سرور از شبکه‌ی خصوصی به هاب میرسند و به هم راه دارند.`
              : !s.failed.length ? 'هیچ راهی قطع نیست؛ ولی این‌ها را ببین:' : 'این راه‌ها جواب ندادند:'}
          </span>
        </div>
      </div>
      {!s.allOk && s.servers > 0 ? (
        <div className="flex flex-col gap-2.5">
          {s.failed.map((p, i) => (
            <Issue key={`f${i}`} color="var(--hq-negative)">
              <span className={title}>{names(p.from).text} ← {names(p.to).text}{!p.toHub ? <> · پورت <span className="fig">{p.ports.join(', ')}</span></> : null}</span>
              <span className={body}><Iso text={pathHint(p, names)} /></span>
            </Issue>
          ))}
          {s.outside.map((n) => (
            <Issue key={`o${n.id}`} color="var(--hq-warning)">
              <span className={title}>{names(n).text} از راه عمومی به هاب وصل است</span>
              <span className={body}><Iso text={outsideHint(s.nextFreeIp)} /></span>
            </Issue>
          ))}
          {s.fellBack.map((n) => (
            <Issue key={`b${n.id}`} color="var(--hq-warning)">
              <span className={title}>{names(n).text} این بار از راه عمومی آمد</span>
              <span className={body}><Iso text="در شبکه‌ی خصوصی هست، ولی آدرس خصوصی هاب جواب نداد و runner به آدرس عمومی برگشت. اگر تکرار شد، Claude همان سرور با hq-runner status و ip addr علتش را ببیند." /></span>
            </Issue>
          ))}
          {s.slow.map((l) => (
            <Issue key={`s${l.node.id}`} color="var(--hq-warning)">
              <span className={title}>{names(l.node).text} کند به هاب میرسد · <span className="fig">{msFig(l.rttMs) ?? '—'}</span></span>
              <span className={body}>بیشتر از <span className="fig">{SLOW_MS} ms</span>؛ کار میکند ولی هر فرمان دیرتر جواب میدهد.</span>
            </Issue>
          ))}
          {s.unknown.map((n) => (
            <Issue key={`u${n.id}`} color="var(--hq-text-muted)">
              <span className={title}>{names(n).text}: <Iso text="runner هنوز تماس نگرفته" /></span>
              <span className={body}><Iso text="راهش به هاب بعد از اولین تماس runner دیده میشود." /></span>
            </Issue>
          ))}
        </div>
      ) : null}
    </Card>
  );
}

// ------------------------------------------------------------------ the check --
export function CheckCard({ x, names }: { x: NetCheckRun; names: (n: NetNode) => ServerName }) {
  const n = x.progress.expected.size;
  const got = [...x.progress.expected].filter((id) => x.progress.reported.has(id)).length;
  const late = timedOut(x);
  return (
    <Card role="status" className={cx('flex flex-col gap-2 p-4', x.ended && !late && 'bg-pos-soft')}>
      <div className="flex items-center gap-2.5">
        <span className={x.ended && !late ? 'text-pos' : 'text-gold-ink'}><Icon name={x.ended ? (late ? 'time' : 'seal') : 'refresh'} size={18} /></span>
        <span className="flex-1 text-[13px] font-semibold text-ink">
          {!x.ended ? `در حال بررسی… ${got} از ${n} سرور جواب دادند` : late ? `بررسی تمام شد؛ ${got} از ${n} سرور در یک دقیقه جواب دادند` : `بررسی تمام شد؛ هر ${n} سرور جواب دادند`}
        </span>
        {!x.ended ? <span className="fig text-[12px] text-muted">{Math.floor(x.waitedMs / 1000)}s</span> : null}
      </div>
      {!x.ended ? <Bar pct={checkFraction(x.progress) * 100} tone="gold" height={5} label="پیشرفت بررسی" /> : null}
      {!x.ended ? <span className="text-[11px] text-muted"><Iso text="هر runner در تماس بعدی‌اش میسنجد؛ حداکثر یک دقیقه." /></span> : null}
      {late ? <span className="text-[12px] text-sec">جواب ندادند: {[...x.progress.expected].filter((id) => !x.progress.reported.has(id)).map((id) => { const nd = x.before ? netNode(x.before, id) : null; return nd ? names(nd).text : id; }).join('، ')}</span> : null}
    </Card>
  );
}

// ------------------------------------------------------------------ the map --
const NODE = 48;
const HUB_NODE = 60;
const NODE_W = 100;
const MAP_H = 380;

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setW(el.clientWidth);
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** A spoke between [a] and [b] cut back by the two circles it joins. */
function trim(a: [number, number], b: [number, number], ra: number, rb: number): [[number, number], [number, number]] | null {
  const dx = b[0] - a[0]; const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy);
  if (len <= ra + rb) return null;
  const ux = dx / len; const uy = dy / len;
  return [[a[0] + ux * ra, a[1] + uy * ra], [b[0] - ux * rb, b[1] - uy * rb]];
}

/** A drawn ✓ or ✗ (no font has to carry the glyph). */
export function Tick({ ok, color, size = 12 }: { ok: boolean; color: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" aria-hidden className="flex-none">
      {ok ? <path d="M1.4 6.6 4.8 9.8 10.8 2.4" fill="none" stroke={color} strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" />
        : <path d="M2.2 2.2 9.8 9.8M9.8 2.2 2.2 9.8" fill="none" stroke={color} strokeWidth={1.9} strokeLinecap="round" />}
    </svg>
  );
}

function SpokeLabel({ l, color }: { l: HubLine; color: string }) {
  return (
    <span className="inline-flex flex-col items-center rounded-[9px] border bg-card px-1.5 py-px leading-4" style={{ borderColor: `color-mix(in srgb, ${color} 60%, transparent)` }}>
      {l.health === 'fail' ? <span className="text-[11px] font-semibold" style={{ color }}>{l.error === 'offline' ? 'آفلاین' : 'قطع'}</span>
        : l.health === 'unknown' ? <span className="text-[11px]" style={{ color }}>نامعلوم</span>
        : <><span className="text-[11px] text-sec">{viaFa(l.via)}</span>{msFig(l.rttMs) ? <span className="fig text-[11px]" style={{ color }}>{msFig(l.rttMs)}</span> : null}</>}
    </span>
  );
}

export function NetworkMapView({ m, names, selected, waiting, onSelect }: { m: NetworkMap; names: (n: NetNode) => ServerName; selected: string | null; waiting: Set<string>; onSelect: (id: string) => void }) {
  const { data: companies } = useCompanies();
  const [ref, w] = useWidth<HTMLDivElement>();
  const order = (companies ?? []).map((c) => c.code);
  const idxOf = (co: string) => { const i = order.indexOf(co); return i < 0 ? Number.MAX_SAFE_INTEGER : i; };
  // Companies are data: one group per company, in the companies' own order, those the list does not know at the end.
  const servers = [...netServers(m)].sort((a, b) => idxOf(a.company) - idxOf(b.company) || a.company.localeCompare(b.company) || a.name.localeCompare(b.name));
  const lines = servers.map((n) => hubLine(m, n));
  const angles = ringAngles(servers);
  // The broken roads between servers, drawn as thin red chords (the hub's own roads are the spokes).
  const chords = netSummary(m).failed.filter((p) => !p.toHub);
  const cx0 = w / 2; const cy0 = MAP_H / 2;
  const rx = Math.max(60, w / 2 - NODE_W / 2); const ry = MAP_H / 2 - 58;
  const pos = angles.map((a): [number, number] => [cx0 + rx * Math.cos((a * Math.PI) / 180), cy0 + ry * Math.sin((a * Math.PI) / 180)]);
  const idx = new Map(servers.map((n, i) => [n.id, i]));
  return (
    // Every piece is placed from the top left, whatever the page's direction: the map is a picture, not a line of text.
    <div ref={ref} dir="ltr" className="relative w-full" style={{ height: MAP_H }} role="group" aria-label="نقشه‌ی شبکه‌ی هلدینگ">
      {w > 0 ? <>
        <svg width={w} height={MAP_H} className="absolute inset-0" aria-hidden>
          <defs>
            <marker id="hq-net-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" fill="var(--hq-negative)" /></marker>
          </defs>
          {lines.map((l, i) => {
            const t = trim([cx0, cy0], pos[i]!, HUB_NODE / 2 + 4, NODE / 2 + 4);
            if (!t) return null;
            const faint = waiting.has(servers[i]!.id);
            const color = HEALTH_COLOR[l.health];
            return (
              <g key={servers[i]!.id}>
                <line x1={t[0][0]} y1={t[0][1]} x2={t[1][0]} y2={t[1][1]} stroke={color} strokeOpacity={faint ? 0.3 : l.health === 'unknown' ? 0.6 : 0.9} strokeWidth={servers[i]!.id === selected ? 4 : 2.5} strokeLinecap="round" strokeDasharray={l.via === 'public' || l.health === 'unknown' ? '10 7' : undefined} />
                {/* While a check runs, a spark travels out to every runner that has not answered yet. */}
                {faint ? <circle r={4} fill="var(--hq-gold-ink)" className="motion-reduce:hidden"><animate attributeName="cx" from={t[0][0]} to={t[1][0]} dur="1.2s" repeatCount="indefinite" /><animate attributeName="cy" from={t[0][1]} to={t[1][1]} dur="1.2s" repeatCount="indefinite" /></circle> : null}
              </g>
            );
          })}
          {chords.map((p, k) => {
            const i = idx.get(p.from.id); const j = idx.get(p.to.id);
            if (i == null || j == null) return null;
            const t = trim(pos[i]!, pos[j]!, NODE / 2 + 6, NODE / 2 + 6);
            return t ? <line key={k} x1={t[0][0]} y1={t[0][1]} x2={t[1][0]} y2={t[1][1]} stroke="var(--hq-negative)" strokeOpacity={0.75} strokeWidth={1.5} strokeDasharray="4 4" strokeLinecap="round" markerEnd="url(#hq-net-arrow)" /> : null;
          })}
          {selected && idx.has(selected) ? <circle cx={pos[idx.get(selected)!]![0]} cy={pos[idx.get(selected)!]![1]} r={NODE / 2 + 5} fill="none" stroke="var(--hq-gold-ink)" strokeWidth={2} /> : null}
        </svg>
        {/* The labels on the spokes: the road and the round trip. */}
        {lines.map((l, i) => (
          <span key={`l${servers[i]!.id}`} className="absolute flex w-[60px] justify-center" style={{ left: cx0 + (pos[i]![0] - cx0) * 0.52 - 30, top: cy0 + (pos[i]![1] - cy0) * 0.52 - 17 }}>
            <SpokeLabel l={l} color={HEALTH_COLOR[l.health]} />
          </span>
        ))}
        {chords.map((p, k) => {
          const i = idx.get(p.from.id); const j = idx.get(p.to.id);
          if (i == null || j == null) return null;
          return (
            <span key={`c${k}`} className="absolute flex w-14 justify-center" style={{ left: (pos[i]![0] + pos[j]![0]) / 2 - 28, top: (pos[i]![1] + pos[j]![1]) / 2 - 10 }}>
              <span className="inline-flex items-center gap-1 rounded-[10px] bg-neg-soft px-1.5"><Tick ok={false} color="var(--hq-negative)" size={9} /><span className="fig text-[11px] text-neg">{p.ports.join(',')}</span></span>
            </span>
          );
        })}
        {/* The hub. */}
        <div className="absolute flex flex-col items-center" style={{ left: cx0 - NODE_W / 2, top: cy0 - HUB_NODE / 2, width: NODE_W }}>
          <span role="img" aria-label="هاب" className="flex flex-col items-center justify-center rounded-full border-2 border-[var(--hq-gold-ink)] bg-gold-soft text-gold-ink" style={{ width: HUB_NODE, height: HUB_NODE }}>
            <Icon name="holding" size={20} /><span dir="rtl" className="text-[11px] font-semibold">هاب</span>
          </span>
        </div>
        {/* The servers. */}
        {servers.map((n, i) => {
          const name = names(n);
          const col = companyColor(companies, n.company);
          return (
            <button key={n.id} type="button" onClick={() => onSelect(n.id)} aria-pressed={selected === n.id} aria-label={`راه‌های ${name.text}`}
              className="absolute flex flex-col items-center rounded-[14px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--hq-gold-ink)]" style={{ left: pos[i]![0] - NODE_W / 2, top: pos[i]![1] - NODE / 2, width: NODE_W }}>
              <span className="flex items-center justify-center rounded-full border-2 text-ink" style={{ width: NODE, height: NODE, borderColor: HEALTH_COLOR[lines[i]!.health], background: `color-mix(in srgb, ${col} 16%, transparent)` }}>
                <CompanyMark code={n.company} height={20} />
              </span>
              <span dir="rtl" className="mt-1 max-w-full truncate text-[12px] font-semibold text-ink">{name.companyFa}</span>
              {name.server ? <span className="fig text-[11px] text-muted">{name.server}</span> : null}
            </button>
          );
        })}
      </> : null}
    </div>
  );
}

export function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11px] text-sec">
      {(['ok', 'slow', 'fail', 'unknown'] as const).map((h) => (
        <span key={h} className="flex items-center gap-1"><span className="h-[3px] w-3.5 rounded-sm" style={{ background: HEALTH_COLOR[h] }} />{{ ok: 'سالم', slow: 'کند', fail: 'قطع', unknown: 'نامعلوم' }[h]}</span>
      ))}
      <span className="flex items-center gap-1"><svg width="18" height="3" aria-hidden><line x1="0" y1="1.5" x2="18" y2="1.5" stroke="var(--hq-text-secondary)" strokeWidth="3" strokeDasharray="4 3" /></svg>از راه عمومی</span>
      <span className="flex items-center gap-1 text-muted"><span className="fig">&gt;{SLOW_MS} ms</span>یعنی کند</span>
    </div>
  );
}

// ------------------------------------------------------------------ a server's roads --
function Cell({ ok, ms, error, applies }: { ok: boolean | null | undefined; ms: number | null | undefined; error: string | null | undefined; applies: boolean }) {
  if (!applies) return <span className="text-muted">·</span>;
  if (ok == null) return <span className="text-muted">—</span>;
  if (ok) return <span className="inline-flex items-center gap-1"><Tick ok color={HEALTH_COLOR[linkHealth(true, ms)]} size={11} />{msFig(ms) ? <span className="fig text-[11px] text-sec">{msFig(ms)!.replace(/ ms$/, '')}</span> : null}</span>;
  const fa = netErrorFa(error);
  return <span className="inline-flex items-center gap-1" title={fa} aria-label={fa}><Tick ok={false} color="var(--hq-negative)" size={11} /><span className="text-[11px] text-neg">{fa.length > 10 ? 'قطع' : fa}</span></span>;
}

/** The selected server: its road to the hub, then from it to every other server on 22, 80 and 443 (✓ with the time, ✗ with why), the
 *  roads that failed towards it, and when it last checked. */
export function NodeDetail({ m, n, names, onClose }: { m: NetworkMap; n: NetNode; names: (n: NetNode) => ServerName; onClose: () => void }) {
  const hub = hubLine(m, n);
  const others = netServers(m).filter((x) => x.id !== n.id);
  const last = m.links.filter((l) => l.from === n.id && l.at).map((l) => l.at!).sort().at(-1) ?? null;
  const pill = hub.health === 'ok' ? { fa: `به هاب: ${viaFa(hub.via)}`, tone: 'pos' as const } : hub.health === 'slow' ? { fa: 'به هاب: کند', tone: 'warn' as const } : hub.health === 'fail' ? { fa: `به هاب: ${netErrorFa(hub.error)}`, tone: 'neg' as const } : { fa: 'به هاب: نامعلوم', tone: 'neutral' as const };
  const rows = [netNode(m, HUB)!, ...others];
  const incoming = [...new Set(m.links.filter((l) => l.to === n.id && l.ok === false && netLink(m, l.from, l.to, l.port)?.ok === false).map((l) => l.from))]
    .map((from) => ({ node: netNode(m, from), ports: [...new Set(m.links.filter((l) => l.from === from && l.to === n.id && l.ok === false).map((l) => l.port))].sort((a, b) => a - b) }))
    .filter((x): x is { node: NetNode; ports: number[] } => !!x.node);
  return (
    <Card className="flex flex-col gap-3 p-4" aria-label={`راه‌های ${names(n).text}`}>
      <div className="flex items-center gap-2">
        <ServerTitle name={names(n)} className="flex-1 text-h3" markHeight={16} />
        <IconButton icon="close" label="بستن" size={36} onClick={onClose} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={pill.tone} dot>{pill.fa}</Pill>
        {msFig(hub.rttMs) ? <span className="fig text-[12px] text-sec">{msFig(hub.rttMs)}</span> : null}
        {n.private_ip?.trim() ? <span className="fig text-[12px] text-muted">{n.private_ip}</span> : <span className="text-[11px] text-warn">بیرون از شبکه‌ی خصوصی</span>}
      </div>
      {nodeOutside(n) ? <Notice icon="globe" tone="warn" title="بیرون از شبکه‌ی خصوصی"><Iso text={outsideHint(nextFreeIp(m))} /></Notice> : null}
      <h3 className="text-[12px] font-semibold text-gold-ink">از این سرور به سرورهای دیگر</h3>
      <div className="overflow-x-auto rounded-[12px] bg-tile">
        <table className="w-full min-w-[360px] border-collapse text-[12px]">
          <thead><tr className="text-muted"><th className="px-2.5 py-2 text-start font-normal">مقصد</th>{NET_PORTS.map((p) => <th key={p} className="fig px-2 py-2 text-center font-semibold text-sec">{p}</th>)}</tr></thead>
          <tbody>
            {rows.map((to) => (
              <tr key={to.id} className="border-t border-div">
                <td className="px-2.5 py-2">
                  <span className="flex items-center gap-1.5">
                    {isHub(to) ? <span className="text-gold-ink"><Icon name="holding" size={13} /></span> : <span className="text-sec"><CompanyMark code={to.company} height={12} mono /></span>}
                    <span className="truncate text-ink">{names(to).text}</span>
                  </span>
                </td>
                {NET_PORTS.map((p) => {
                  // The hub is checked on 443 only (§26.6).
                  const applies = !(isHub(to) && p !== 443);
                  const l = applies ? netLink(m, n.id, to.id, p) : null;
                  return <td key={p} className="px-2 py-2 text-center"><Cell ok={l?.ok} ms={l?.ms} error={l?.error} applies={applies} /></td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <span className="text-[11px] text-muted">زمان‌ها به <span className="fig">ms</span>؛ «—» یعنی هنوز بررسی نشده و «·» یعنی هاب روی آن پورت سنجیده نمیشود.</span>
      {incoming.length ? <>
        <h3 className="text-[12px] font-semibold text-neg">به این سرور نرسیدند</h3>
        {incoming.map((x) => <span key={x.node.id} className="flex items-center gap-1.5 text-[12px] text-sec"><Tick ok={false} color="var(--hq-negative)" size={10} />{names(x.node).text} · پورت <span className="fig">{x.ports.join(', ')}</span></span>)}
      </> : null}
      <div className="flex items-center gap-2">
        <span className="flex-1 text-[11px] text-muted">{last ? <>آخرین بررسی این سرور <span className="fig">{jTime(last)}</span> · {ago(last)}</> : 'این سرور هنوز چیزی نسنجیده'}</span>
        <Link href={`/servers/${n.id}`} className="inline-flex h-8 items-center gap-1 rounded-[8px] px-2 text-[12px] font-semibold text-gold-ink hover:bg-gold-soft">باز کردن سرور<Icon name="next" size={16} mirror /></Link>
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ the entry point --
/** «شبکه‌ی هلدینگ» as a line on «همه‌ی سرورها»: the headline and a way in. */
export function NetworkLink() {
  const q = useNetwork();
  const h = q.data ? headline(netSummary(q.data)) : { fa: 'راه هر سرور به هاب و به سرورهای دیگر', tone: 'neutral' as const };
  return (
    <Link href="/network" aria-label="شبکه‌ی هلدینگ" className="group block">
      <Card className="flex items-center gap-3 p-4 transition-colors group-hover:bg-tile">
        <span className="flex size-10 flex-none items-center justify-center rounded-[12px] bg-gold-soft text-gold-ink"><Icon name="globe" size={20} /></span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-[14px] font-semibold text-ink">شبکه‌ی هلدینگ</span>
          <span className={cx('text-[12px]', { neg: 'text-neg', warn: 'text-warn', pos: 'text-pos', neutral: 'text-muted' }[h.tone])}>{h.fa}</span>
        </div>
        <span className="text-muted"><Icon name="next" size={16} mirror /></span>
      </Card>
    </Link>
  );
}

export { netLastAt };
export const CheckButton = ({ checking, disabled, onClick }: { checking: boolean; disabled: boolean; onClick: () => void }) => (
  <Button variant="primary" size="sm" icon="refresh" loading={checking} disabled={disabled} onClick={onClick}>بررسی دوباره</Button>
);
