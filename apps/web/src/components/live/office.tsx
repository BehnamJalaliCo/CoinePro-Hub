'use client';

// ⟨1.24⟩ The office's live views (design/LIVE_VIEWS.md §4 B, D, I; contract §42): OF-1 «نبض دفتر» (four figures on top of the office),
// MO-1 «کنتور توکن» (today's spend against the daily budget, four kinds, the burn rate) and CO-1 «کارت زنده‌ی شرکت» (one card per company,
// for any number of companies). They read the live store (seeded from `GET /live/summary`, moved by the stream). A figure changes by
// crossfade and its tahrir glints once; nothing counts up; what is missing is «—». On the owner's pages the meter speaks of spend, not of
// «توکن» (§34: plain words); the treasury's own page names it.

import Link from 'next/link';
import { useEffect, useMemo } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { Card, SectionTitle } from '@/components/ui/primitives';
import { useCompanies, useEmployees, useTreasury } from '@/lib/api/hooks';
import { BADGE, type Badge } from '@/lib/api/v34';
import { companyColor, companyOf } from '@/lib/company';
import { activityScore, inFlight, lockedOf, peopleBusy, peopleDots, perMin, waitingForOwner, type LiveState } from '@/lib/live/model';
import { liveStore, useLiveState } from '@/lib/live/store';
import { ago, cx, tokens as tokFig, usd } from '@/lib/format';
import { LiveFigure, WorkBand, useFlip, useTick } from './motion';
import { PERSON_FA, StateGlyph } from './person';
import { LiveCorner } from './shell';

const dash = (v: number | null | undefined) => (v == null ? '—' : String(v));

// ------------------------------------------------------------------------------------------------------- OF-1 --
function PulseTile({ label, sub, sig, glint, href, children }: { label: string; sub: string; sig: string; glint: 'gold' | 'silver'; href?: string; children: React.ReactNode }) {
  const body = (
    <>
      <span className="text-[12px] text-sec">{label}</span>
      <LiveFigure sig={sig} glint={glint} className="mt-0.5"><span className="text-[26px] font-bold leading-[34px] text-ink">{children}</span></LiveFigure>
      <span className="mt-1 line-clamp-2 text-[11px] leading-4 text-muted">{sub}</span>
    </>
  );
  const cls = 'flex min-w-0 flex-col rounded-[14px] border border-div bg-card px-3.5 py-3';
  return href ? <Link href={href} className={cx(cls, 'transition-colors hover:bg-hover')} data-pulse={label}>{body}</Link> : <div className={cls} data-pulse={label}>{body}</div>;
}

/** OF-1: is my holding working, and is anything waiting for me? */
export function OfficePulse() {
  const s = useLiveState((x) => x);
  const now = useTick(5000);
  const busy = peopleBusy(s);
  const total = s.people.total;
  const moving = s.sessions.moving;
  const waiting = waitingForOwner(s);
  const rate = perMin(s, now);
  return (
    <section aria-label="نبض دفتر" data-testid="office-pulse" className="flex flex-col gap-2">
      <div className="flex items-center justify-end empty:hidden"><LiveCorner /></div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <PulseTile label="الان کار میکنند" sub="کسانی که مدلی برایشان فکر میکند یا ابزاری کار میکند" sig={`${busy}/${total}`} glint="silver">
          {busy == null ? '—' : <>{busy}<span className="text-[13px] font-medium text-muted"> از {dash(total)}</span></>}
        </PulseTile>
        <PulseTile label="سشن در جریان" sub="کاری که الان قدمی دارد" sig={dash(moving)} glint="silver" href="/s">{dash(moving)}</PulseTile>
        <PulseTile label="منتظر تو" sub="تصمیم برای مُهر و سشن در نوبت تو" sig={dash(waiting)} glint="gold" href="/cartable">{dash(waiting)}</PulseTile>
        <PulseTile label="مصرف در دقیقه" sub="خزانه، زنده" sig={dash(rate)} glint="silver"><span className="fig">{rate == null ? '—' : tokFig(rate)}</span></PulseTile>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------- MO-1 --
const KINDS = [
  { key: 'input', fa: 'ورودی', color: 'var(--hq-chart-1)', weight: 1 },
  { key: 'output', fa: 'خروجی', color: 'var(--hq-chart-2)', weight: 5 },
  { key: 'cache', fa: 'کش', color: 'var(--hq-chart-3)', weight: 0.1 },
  { key: 'thinking', fa: 'فکر', color: 'var(--hq-chart-4)', weight: 5 },
] as const;

/** MO-1: today's spend against the daily budget, filled in four kinds; marks at 70, 90 and 100 %; the band rides the leading edge while
 *  calls are in flight. [named]: the treasury's page may call it «توکن»; the owner's pages say «مصرف». */
export function TokenMeter({ named = false, className }: { named?: boolean; className?: string }) {
  const s = useLiveState((x) => x);
  const t = s.tokens;
  const day = useTreasury({ period: 'day' });
  const totals = day.data?.totals;
  useEffect(() => { if (totals) liveStore.seedTokenKinds(totals); }, [totals]);
  const now = useTick(5000);
  const flying = inFlight(s, now);
  const rate = perMin(s, now);
  const spent = t.equiv_usd_today;
  const budget = t.budget_usd;
  const pct = spent != null && budget ? Math.min(100, (100 * spent) / budget) : null;
  const k = t.kinds;
  const weights = k ? KINDS.map((x) => k[x.key] * x.weight) : null;
  const wsum = weights?.reduce((a, b) => a + b, 0) ?? 0;
  const state = pct == null ? null : pct >= 100 ? { fa: 'سقف پر شد', cls: 'border-neg bg-neg-soft text-neg', icon: '🔴' } : pct >= 90 ? { fa: '۹۰٪ سقف', cls: 'border-warn bg-warn-soft text-warn' } : pct >= 70 ? { fa: '۷۰٪ سقف', cls: 'border-warn bg-warn-soft text-warn' } : { fa: 'در محدوده', cls: 'border-pos bg-pos-soft text-pos' };
  const fillTone = pct != null && pct >= 100 ? 'var(--hq-negative)' : pct != null && pct >= 90 ? 'var(--hq-warning)' : null;
  return (
    <Card as="section" className={cx('flex flex-col gap-2 p-4', className)} aria-label={named ? 'کنتور توکن' : 'مصرف امروز'} data-testid="token-meter">
      <SectionTitle title={named ? 'کنتور توکن · امروز' : 'مصرف امروز'} action={<span className="flex items-center gap-1.5"><LiveCorner />{state ? <span data-meter-state={state.fa} className={cx('inline-flex h-6 items-center rounded-full border px-2.5 text-[12px] font-semibold hq-m2', state.cls)}>{state.icon ? <span aria-hidden className="me-1">{state.icon}</span> : null}{state.fa}</span> : null}</span>} />
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <LiveFigure sig={spent == null ? '—' : spent.toFixed(2)} glint="gold" rule={false}><span className="fig text-[28px] font-bold leading-9 text-ink">{spent == null ? '—' : usd(spent)}</span></LiveFigure>
        <span className="text-[12px] text-sec">از سقف روزانه‌ی <span className="fig">{budget == null ? '—' : usd(budget)}</span></span>
        <span className="ms-auto text-[12px] text-muted"><span className="fig">{tokFig(t.today)}</span>{named ? ' توکن' : ' امروز'}</span>
      </div>
      <div className="relative mb-6 mt-3 h-3.5 rounded-[7px] bg-tile" role="meter" aria-label="مصرف امروز از سقف روزانه" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct == null ? undefined : Math.round(pct)} data-pct={pct == null ? undefined : Math.round(pct)}>
        <div className="hq-m12 absolute inset-y-0 start-0 flex gap-[2px] overflow-hidden rounded-[7px]" style={{ width: `${pct ?? 0}%` }}>
          {KINDS.map((x, i) => <span key={x.key} className="hq-m12 block h-full" style={{ flexGrow: weights && wsum ? weights[i]! / wsum : 0.25, background: fillTone ?? x.color }} />)}
        </div>
        {pct != null && flying > 0 && pct < 100 ? (
          <span className="absolute -bottom-2 w-11 translate-x-1/2" style={{ insetInlineStart: `${pct}%` }} data-lead><WorkBand on height={3} color="var(--hq-gold-ink)" label="مدل‌ها در حال کار" /></span>
        ) : null}
        {[70, 90, 100].map((m) => (
          <span key={m} className="absolute -bottom-1 -top-1 w-0 border-s-[1.5px]" style={{ insetInlineStart: m === 100 ? 'calc(100% - 1.5px)' : `${m}%`, borderColor: pct != null && pct >= m ? (m === 100 ? 'var(--hq-negative)' : 'var(--hq-warning)') : 'var(--hq-line-strong)' }} data-mark={m}>
            <span className={cx('absolute top-5 translate-x-1/2 whitespace-nowrap text-[10.5px]', pct != null && pct >= m ? 'text-warn' : 'text-muted')}>{m}٪</span>
          </span>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
        {KINDS.map((x) => (
          <span key={x.key} className="flex items-center gap-1.5" data-kind={x.key}>
            <i aria-hidden className="size-2.5 flex-none rounded-[3px]" style={{ background: x.color }} />{x.fa}
            <span className="fig ms-auto text-sec">{k ? tokFig(k[x.key]) : '—'}</span>
          </span>
        ))}
      </div>
      <span className="text-[11px] text-muted">{named ? 'توکن در دقیقه' : 'مصرف در دقیقه'}: <span className="fig">{rate == null ? '—' : tokFig(rate)}</span>{flying > 0 ? <span> · {flying} فراخوانی در جریان</span> : null}</span>
    </Card>
  );
}

// ------------------------------------------------------------------------------------------------------- CO-1 --
const ServerSquares = ({ online, total }: { online: number | null; total: number | null }) => {
  if (total == null) return <span className="text-[12px] text-muted">سرور —</span>;
  const on = online ?? 0;
  return (
    <span className="inline-flex items-center gap-[3px]" data-servers={`${on}/${total}`} aria-label={`${on} از ${total} سرور وصل`}>
      {Array.from({ length: Math.min(total, 6) }, (_, i) => (
        i < on ? <i key={i} aria-hidden className="size-[9px] rounded-[2px] border-[1.5px] border-pos" />
          : <svg key={i} width={9} height={9} viewBox="0 0 9 9" aria-hidden><rect x={0.75} y={0.75} width={7.5} height={7.5} rx={1.5} fill="var(--hq-soft-negative)" stroke="var(--hq-negative)" strokeWidth={1.5} /><path d="M2.8 2.8l3.4 3.4M6.2 2.8l-3.4 3.4" stroke="var(--hq-negative)" strokeWidth={1.2} /></svg>
      ))}
      <span className={cx('ms-1 text-[12px]', on < total ? 'font-semibold text-neg' : 'text-sec')}>{on} از {total} سرور{on < total ? ' · قطع' : ''}</span>
    </span>
  );
};

/** The sessions of a company by badge, from what the store knows (the open list and the stream); else the summary's count. */
function sessionsLine(s: LiveState, code: string): string {
  const mine = Object.values(s.sessions_by_ref).filter((x) => x.company === code && x.badge && x.badge !== 'closed');
  if (!mine.length) { const n = s.companies[code]?.sessions_open; return n == null ? 'سشن: —' : n ? `سشن: ${n} باز` : 'سشن: هیچ'; }
  const by = (['your_turn', 'moving', 'ready', 'stuck'] as Badge[]).map((b) => [b, mine.filter((x) => x.badge === b).length] as const).filter(([, n]) => n);
  return `سشن: ${by.map(([b, n]) => `${n} ${BADGE[b].fa}`).join(' · ')}`;
}

/** Every person's state from the employees list (§29.14): the dots start from it (one request, shared by every card). */
function useSeedPeople() {
  const emps = useEmployees({ limit: 200 });
  useEffect(() => { if (emps.data?.items) liveStore.seedPeople(emps.data.items as Parameters<typeof liveStore.seedPeople>[0]); }, [emps.data]);
}

/** The live part of a company card: people by state, servers, sessions by badge, today's spend against its cap, and its last event. */
export function CompanyLiveStrip({ code, className }: { code: string; className?: string }) {
  useSeedPeople();
  const s = useLiveState((x) => x);
  const c = s.companies[code];
  const now = useTick(30_000);
  const { dots, more } = useMemo(() => peopleDots(s, code), [s, code]);
  const line = useMemo(() => sessionsLine(s, code), [s, code]);
  const working = dots.filter((d) => d.state === 'working' || d.state === 'thinking').length;
  const spend = c?.spend_today_usd ?? null;
  const cap = c?.budget_usd ?? null;
  return (
    <div className={cx('flex min-w-0 flex-col gap-1', className)} data-company-live={code}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <ServerSquares online={c?.servers_online ?? null} total={c?.servers_total ?? null} />
        <span className="ms-auto text-[11px] text-muted" data-age>{c?.last_event_at ? ago(c.last_event_at, now) : '—'}</span>
      </div>
      <div className="flex flex-wrap items-center gap-[3px]" aria-label="حال کارمندها">
        {dots.map((d, i) => <span key={d.id ?? `x${i}`} role="img" aria-label={PERSON_FA[d.state]} title={PERSON_FA[d.state]} data-dot={d.state}><StateGlyph state={d.state} size={14} /></span>)}
        {more ? <span className="text-[11px] text-muted">+{more}</span> : null}
        <span className="ms-1.5 text-[11px] text-sec">{c?.working == null && !dots.length ? '— در کار' : `${Math.max(working, c?.working ?? 0)} در کار`}</span>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-sec">
        <span data-sessions>{line}</span>
        <span className="flex min-w-[120px] flex-1 items-center gap-2">
          {cap ? <span className="h-1 flex-1 overflow-hidden rounded-full bg-card" title="خرج امروز از سقف شرکت"><i className="hq-m12 block h-full rounded-full" style={{ width: `${Math.min(100, (100 * (spend ?? 0)) / cap)}%`, background: (spend ?? 0) >= cap ? 'var(--hq-negative)' : 'var(--hq-silver-ink)' }} /></span> : <span className="flex-1" />}
          <span className="fig text-[12px] text-sec">{usd(spend)}{cap ? ` / ${usd(cap)}` : ''}</span>
        </span>
      </div>
    </div>
  );
}

/** The company's mark in its octagon with the activity arc around it (share of people working, in its chart colour; M12 when it moves). */
export function ActivityMark({ code, size = 48 }: { code: string; size?: number }) {
  const { data: companies } = useCompanies();
  const c = useLiveState((s) => s.companies[code]);
  const share = c?.total ? Math.min(1, (c.working ?? 0) / c.total) : 0;
  const r = size / 2 - 3;
  const C = 2 * Math.PI * r;
  const oct = Array.from({ length: 8 }, (_, k) => { const a = Math.PI / 8 + (k * Math.PI) / 4; const R = size * 0.34; return `${(size / 2 + R * Math.cos(a)).toFixed(1)},${(size / 2 + R * Math.sin(a)).toFixed(1)}`; }).join(' ');
  return (
    <span className="relative flex flex-none items-center justify-center" style={{ width: size, height: size }} data-share={share.toFixed(2)}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className="absolute inset-0">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--hq-line-divider)" strokeWidth={3} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={companyColor(companies, code)} strokeWidth={3} strokeLinecap="round" transform={`rotate(-90 ${size / 2} ${size / 2})`} strokeDasharray={`${(share * C).toFixed(1)} ${C.toFixed(1)}`} className="hq-m12" />
        <polygon points={oct} fill="var(--hq-surface-tile)" stroke="var(--hq-line-strong)" />
      </svg>
      <span className="relative text-ink"><CompanyMark code={code} height={Math.round(size * 0.36)} /></span>
    </span>
  );
}

/** CO-1 for one company: is it alive, working, healthy, and what does it cost today. */
export function CompanyLiveCard({ code }: { code: string }) {
  const { data: companies } = useCompanies();
  const locked = useLiveState((s) => lockedOf(s, code));
  const c = useLiveState((s) => s.companies[code]);
  const runs = (c?.working ?? 0) > 0 && !locked;
  const name = c?.name_fa ?? companyOf(companies, code).nameFa;
  return (
    <Link href={`/companies/${code}`} data-flip={code} data-company-card={code} data-locked={locked || undefined}
      className={cx('flex flex-col gap-1 rounded-[14px] border border-transparent bg-tile px-3 py-2.5 transition-colors hover:border-strong', locked && 'hq-hatch')}>
      <span className="flex items-start gap-3">
        <ActivityMark code={code} />
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex items-center gap-2"><span className="truncate text-[14px] font-semibold text-ink">{name}</span>{locked ? <span className="inline-flex items-center gap-1 rounded-full border border-neg px-2 text-[11px] font-semibold text-neg">قفل</span> : null}</span>
          <CompanyLiveStrip code={code} />
        </span>
      </span>
      <WorkBand on={runs} height={2} label="کار در جریان" />
    </Link>
  );
}

/** CO-1 on the office: the busiest companies first (they slide to their place, M11), every company in the map's table. */
export function LiveCompanies({ max = 6 }: { max?: number }) {
  const order = useLiveState((s) => s.order);
  const companies = useLiveState((s) => s.companies);
  const servers = useLiveState((s) => s.servers_by_id);
  const now = useTick(60_000);
  const ranked = useMemo(() => {
    const off = (code: string) => Object.values(servers).filter((x) => x.company === code && x.state === 'offline').length;
    return order.map((code, i) => ({ code, i, score: activityScore(companies[code], off(code), now) })).sort((a, b) => b.score - a.score || a.i - b.i).map((x) => x.code);
  }, [order, companies, servers, now]);
  const shown = ranked.slice(0, max);
  const ref = useFlip<HTMLDivElement>(shown.join('|'));
  if (!order.length) return null;
  return (
    <Card as="section" className="flex flex-col gap-2.5 p-4" aria-label="شرکت‌ها، زنده" data-testid="live-companies">
      <SectionTitle title="شرکت‌ها · زنده" note={`${order.length} شرکت`} action={<LiveCorner />} />
      <div ref={ref} className="flex flex-col gap-2">{shown.map((code) => <CompanyLiveCard key={code} code={code} />)}</div>
      {ranked.length > shown.length ? <Link href="/network?view=table" className="self-start text-[12px] font-semibold text-gold-ink hover:underline">+{ranked.length - shown.length} شرکت دیگر · همه در نمای جدول</Link> : null}
      <PeopleLegend />
    </Card>
  );
}

/** What each shape means (rule 9: shape plus word). */
export function PeopleLegend() {
  return (
    <div className="flex flex-wrap gap-x-3.5 gap-y-1 border-t border-div pt-2 text-[11px] text-sec" aria-label="راهنمای چراغ هر نفر">
      {(['thinking', 'working', 'waiting', 'stuck', 'done', 'idle'] as const).map((s) => <span key={s} className="inline-flex items-center gap-1"><StateGlyph state={s} size={12} />{PERSON_FA[s]}</span>)}
    </div>
  );
}
