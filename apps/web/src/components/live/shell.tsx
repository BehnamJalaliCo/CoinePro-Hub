'use client';

// ⟨1.24⟩ The live views of the shell (design/LIVE_VIEWS.md §4 A and P, contract §42): the seed of the live store, GL-1 «چراغ زنده» in the
// header and in the corner of every live panel, GL-2 «نوار کلید توقف» across the top of every screen, NO-1 the urgent banner and the toast
// of a card for the seal, and the chip «n رویداد در نبودت» after the tab was hidden or the stream was away.

import Link from 'next/link';
import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { useCompanies, useControl, usePresence } from '@/lib/api/hooks';
import { call } from '@/lib/api/v13';
import { useLiveSummary } from '@/lib/api/v42';
import { useSessions } from '@/lib/api/v34';
import { byFa } from '@/lib/control';
import { companyOf } from '@/lib/company';
import { attention, useAttention } from '@/lib/live/attention';
import { beaconOf, liveStore, useStreamMeta, type Beacon } from '@/lib/live/store';
import { Facts, Ltr } from '@/components/look/text';
import { cx, jTime } from '@/lib/format';
import { Arc, useReducedMotion, useTick } from './motion';

// ----------------------------------------------------------------------------------------------------- the seed --
/** Mounted once in the shell: seeds the live store from `GET /live/summary` (and the sessions' badges), and reads the summary again when
 *  the stream comes back after a drop. */
export function LiveSeed() {
  const qc = useQueryClient();
  const q = useLiveSummary();
  const sessions = useSessions('open');
  const meta = useStreamMeta();
  const was = useRef(meta.state);
  useEffect(() => {
    if (q.data) liveStore.seed(q.data);
    else if (q.data === null || q.isError) liveStore.noSeed();
  }, [q.data, q.isError]);
  useEffect(() => { if (sessions.data) liveStore.seedSessions(sessions.data); }, [sessions.data]);
  useEffect(() => {
    const before = was.current;
    was.current = meta.state;
    if (meta.state === 'live' && before !== 'live' && before !== 'connecting') void qc.invalidateQueries({ queryKey: ['live', 'summary'] });
  }, [meta.state, qc]);
  return null;
}

// ------------------------------------------------------------------------------------------------------- GL-1 --
const secsFa = (ms: number) => { const s = Math.max(1, Math.round(ms / 1000)); return s < 60 ? `${s} ثانیه` : `${Math.round(s / 60)} دقیقه`; };
const BEACON_FA: Record<Beacon, string> = { live: 'زنده', reconnecting: 'در حال وصل', stale: 'قدیمی', offline: 'بی‌اتصال' };

/** What the beacon says now, and since when it has been so. */
export function useBeacon(): { state: Beacon; label: string; since: number | null; beat: number } {
  const meta = useStreamMeta();
  const now = useTick(5000);
  const b = beaconOf(meta, now);
  const label = b.state === 'stale' && b.since ? `${BEACON_FA.stale} · ${secsFa(now - b.since)}` : BEACON_FA[b.state];
  return { ...b, label, beat: meta.beat };
}

/**
 * GL-1 in the header: «زنده» (one breath per byte from the hub, at most every 2 s), «در حال وصل» (an arc turns while it retries), «قدیمی ·
 * n دقیقه» (amber, still: no byte for 45 s, so every figure is frozen), «بی‌اتصال» (the browser has no network). The word always says it.
 */
export function LiveBeacon({ compact = false }: { compact?: boolean }) {
  const b = useBeacon();
  const tone = b.state === 'live' ? 'bg-pos-soft text-pos' : b.state === 'offline' ? 'bg-tile text-muted' : 'bg-warn-soft text-warn';
  return (
    <span role="status" aria-live="polite" title={b.label} data-beacon={b.state} className={cx('inline-flex h-7 flex-none items-center gap-1.5 rounded-full px-2.5 text-[12px] font-semibold', tone)}>
      {b.state === 'reconnecting' ? <Arc size={12} color="var(--hq-warning)" word="" />
        : b.state === 'offline' ? <svg width={10} height={10} viewBox="0 0 10 10" aria-hidden><path d="M2 2l6 6M8 2l-6 6" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" /></svg>
        : <span key={b.state === 'live' ? b.beat : 'still'} aria-hidden className={cx('size-1.5 rounded-full bg-current', b.state === 'live' && b.beat > 0 && 'hq-m6-once')} />}
      <span className={cx(compact && 'hidden sm:inline')}>{b.label}</span>
    </span>
  );
}

/** GL-1 in the corner of a live panel: nothing while live; «قدیمی · since» or «در حال وصل» otherwise, so a frozen view never looks calm. */
export function LiveCorner({ className }: { className?: string }) {
  const b = useBeacon();
  const away = useAwayChip();
  if (b.state === 'live' && !away) return null;
  return (
    <span className={cx('inline-flex flex-wrap items-center gap-1.5', className)}>
      {b.state !== 'live' ? (
        <span data-corner={b.state} className={cx('inline-flex h-6 items-center gap-1 rounded-full border px-2 text-[11px] font-semibold', b.state === 'offline' ? 'border-strong text-muted' : 'border-warn bg-warn-soft text-warn')}>
          {b.state === 'reconnecting' ? <Arc size={10} color="var(--hq-warning)" word="" /> : null}
          {b.state === 'stale' && b.since ? `داده‌ها از ${jTime(new Date(b.since).toISOString())} تازه نشده‌اند` : b.label}
        </span>
      ) : null}
      {away ? <AwayChip n={away} /> : null}
    </span>
  );
}

// --------------------------------------------------------------------------------------------- rule 7, the chip --
/** «n رویداد در نبودت» while it is shown (8 s after the owner came back). */
export function useAwayChip(): number | null {
  useStreamMeta();
  const now = useTick(2000);
  return liveStore.awayChip(now);
}
export function AwayChip({ n }: { n: number }) {
  return (
    <button type="button" onClick={() => liveStore.dismissAway()} data-away={n} className="hq-m1 inline-flex h-6 items-center gap-1 rounded-full border border-strong bg-raised px-2.5 text-[11px] text-ink">
      {n} رویداد در نبودت؛ بی‌حرکت اعمال شد
    </button>
  );
}

// ------------------------------------------------------------------------------------------------------- GL-2 --
/**
 * GL-2: while the holding or a company is locked, a negative band across the top of every screen with who, since when and by whose word
 * (it settles from the top on engage and goes on release). The stillness everywhere has a reason the owner can see.
 */
export function KillBand() {
  const { data: control } = useControl();
  const { data: companies } = useCompanies();
  const h = control?.holding;
  const locked = (control?.companies ?? []).filter((k) => k.state === 'engaged');
  if (!control || (h?.state !== 'engaged' && !locked.length)) return null;
  const name = (code: string) => companyOf(companies, code).nameFa;
  const since = (at: string) => <>از <Ltr>{jTime(at)}</Ltr></>;
  const facts = h?.state === 'engaged'
    ? <Facts>هلدینگ قفل است{since(h.changed_at)}{byFa(h.changed_by)}</Facts>
    : locked.length === 1
      ? <Facts>{`${name(locked[0]!.company)} قفل است`}{since(locked[0]!.changed_at)}{byFa(locked[0]!.changed_by)}</Facts>
      : `${locked.length} شرکت قفل‌اند: ${locked.map((k) => name(k.company)).join('، ')}`;
  return (
    <div role="status" aria-live="polite" data-testid="kill-band" data-scope={h?.state === 'engaged' ? 'holding' : 'company'} className="hq-m1 bg-page">
      <div className="h-1 bg-neg" aria-hidden />
      <div className="flex items-center gap-2 bg-neg-soft px-4 py-1 text-[12px] font-semibold text-ink md:px-6">
        <span className="text-neg"><Icon name="lock" size={14} /></span>
        {/* ⟨1.0.1⟩ the facts are parted by the hairline: «·» beside a Persian digit reads as a zero; the clock is a Latin figure. */}
        <span className="min-w-0 flex-1 truncate">{facts}</span>
        <Link href={h?.state === 'engaged' ? '/control' : '/companies'} className="flex-none text-[12px] text-neg hover:underline">کلیدها</Link>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------- NO-1 --
/** 🔴 the banner under the header: it stays until «دیدم» (which reads the notification), and «باز کن» goes to what it is about. */
export function UrgentBanner() {
  const { urgent } = useAttention();
  if (!urgent) return null;
  const ack = () => {
    attention.ack();
    if (urgent.notificationId) void call('POST', '/notifications/read', { ids: [urgent.notificationId] }).catch(() => undefined);
  };
  return (
    <div role="alert" aria-live="assertive" data-testid="urgent-banner" className="hq-m1 mx-4 mt-3 flex flex-wrap items-center gap-3 rounded-[14px] border border-neg bg-neg-soft px-4 py-2.5 md:mx-6">
      <span aria-hidden className="size-2.5 flex-none rounded-full bg-neg" />
      <span className="min-w-0 flex-1 text-[14px] text-ink"><span className="font-semibold">فوری · </span>{urgent.title}{urgent.text ? <span className="text-sec">؛ {urgent.text}</span> : null}</span>
      {urgent.route ? <Link href={urgent.route} onClick={ack} className="text-[13px] font-semibold text-neg hover:underline">{urgent.action}</Link> : null}
      <Button size="sm" variant="secondary" onClick={ack}>دیدم</Button>
    </div>
  );
}

/** 🟡 a card for the seal: a toast with a gold hairline at the start edge, six seconds; quiet in khalvat (only 🔴 interrupts there). */
export function DecisionToasts() {
  const { decisions } = useAttention();
  const { data: presence } = usePresence();
  const rm = useReducedMotion();
  if (!decisions.length || presence?.khalvat) return null;
  return (
    <div aria-live="polite" className="pointer-events-none fixed bottom-24 start-4 z-[61] flex w-[min(380px,calc(100vw-32px))] flex-col gap-2 md:bottom-6">
      {decisions.map((d) => (
        <div key={d.id} data-testid="decision-toast" className={cx('pointer-events-auto flex items-center gap-3 rounded-[12px] border border-strong bg-raised px-4 py-2.5 shadow-[0_8px_24px_rgba(0,0,0,.35)]', !rm && 'hq-m1')} style={{ borderInlineStartWidth: 3, borderInlineStartColor: 'var(--hq-gold-fill)' }}>
          <span className="min-w-0 flex-1 text-[13px] leading-5 text-ink"><span className="font-semibold">تصمیم تازه · </span>{d.title}</span>
          {d.route ? <Link href={d.route} onClick={() => attention.dropDecision(d.id)} className="flex-none text-[13px] font-semibold text-gold-ink hover:underline">کارتابل</Link> : null}
        </div>
      ))}
    </div>
  );
}
