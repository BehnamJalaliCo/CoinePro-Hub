'use client';

// ⟨1.0.1⟩ Part C, the working group (C3.4), the pieces its pages are built from: a member company as a tile (its state as a shape and
// a word, its last run, its next run, a silver work line only while something of it runs, and when it stands still its one-line reason
// with a quiet «راه بینداز»), a routine's last seven runs as dots (done, failed, skipped, in the queue: each its own shape), when a
// routine runs next (worked out from its own schedule, on the owner's clock), and the one-line summary of a draft for its seal.

import Link from 'next/link';
import type { ReactNode } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { WorkBand } from '@/components/live/motion';
import { Button } from '@/components/ui/button';
import { FaText } from '@/components/v29/text';
import type { RoutineRun } from '@/lib/api/v29';
import { deskDayFa } from '@/lib/api/v55';
import { ago, cx } from '@/lib/format';
import { plain } from '@/lib/plain';
import { STICKY_TOP, useStuck } from './collapse';
import { Facts, Ltr, clock, faCount } from './text';

// ================================================================================================== the header ==
/** A state as a shape and a word, never a colour alone: `on` a filled dot, `wait` a ring, `off` a short bar. */
export function StateWord({ kind, children }: { kind: 'on' | 'wait' | 'off'; children: ReactNode }) {
  return (
    <span className={cx('inline-flex flex-none items-center gap-1.5 text-[12px] font-semibold', kind === 'on' ? 'text-silver-ink' : kind === 'wait' ? 'text-ink' : 'text-muted')} data-state-word={kind}>
      {kind === 'on' ? <span aria-hidden className="size-2 rounded-full bg-current" />
        : kind === 'wait' ? <span aria-hidden className="size-2.5 rounded-full border-[1.5px] border-current" />
        : <span aria-hidden className="h-[2px] w-2.5 rounded-full bg-current" />}
      <span>{children}</span>
    </span>
  );
}

/**
 * The head of a working group's page: where it came from, its title and state, a line of facts and its quiet actions. Once the page
 * has scrolled under it, it folds to the title and the state on one line (M18). The page's own flex gap is taken back by [gap].
 */
export function GroupHeader({ eyebrow, title, state, facts, actions, children, gap = '-mb-4' }: {
  eyebrow?: ReactNode; title: ReactNode; state?: ReactNode; facts?: ReactNode; actions?: ReactNode; children?: ReactNode; gap?: string;
}) {
  const { sentinel, stuck } = useStuck();
  return (
    <>
      <div ref={sentinel} aria-hidden className={gap} />
      <header data-stuck={stuck ? '' : undefined} data-testid="group-header"
        className={cx(STICKY_TOP, 'hq-m18 sticky z-10 -mx-2 flex flex-col gap-1.5 rounded-[12px] px-2 py-1.5', stuck && 'bg-page/95 shadow-[0_8px_20px_rgba(0,0,0,.18)] backdrop-blur-md')}>
        {eyebrow ? <span className="hq-m18-fold text-caption text-muted">{eyebrow}</span> : null}
        <div className="flex items-center gap-3">
          <h1 className={cx('min-w-0 flex-1 font-semibold text-ink', stuck ? 'truncate text-[15px] leading-7' : 'text-h1')}>{title}</h1>
          {state}
        </div>
        {facts ? <p className="hq-m18-fold text-[12px] leading-6 text-muted">{facts}</p> : null}
        {children ? <div className="hq-m18-fold">{children}</div> : null}
        {actions ? <div className="hq-m18-fold flex flex-wrap items-center gap-2 pt-1">{actions}</div> : null}
      </header>
    </>
  );
}

// =============================================================================================== the next run ==
const ZONE_MIN = 210; // the owner's clock (Tehran, +03:30 all year), which the hub's schedules are written in
const DAYS = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];

/** When a schedule (an RRULE of the hub's: hourly, daily, weekly on its days, monthly on its day) runs next; null when it cannot be read. */
export function nextRun(schedule: string | null | undefined, nowMs = Date.now()): string | null {
  if (!schedule) return null;
  const k = Object.fromEntries(schedule.replace(/^RRULE:/, '').split(';').map((x) => x.split('=') as [string, string]));
  const h = Number(k.BYHOUR ?? 0);
  const m = Number(k.BYMINUTE ?? 0);
  if (!Number.isFinite(h) || !Number.isFinite(m)) return null;
  const off = ZONE_MIN * 60_000;
  const local = new Date(nowMs + off);
  const at = (day: number, hour = h) => Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate() + day, hour, m) - off;
  const iso = (t: number) => new Date(t).toISOString();
  if (k.FREQ === 'HOURLY') {
    for (let i = 0; i < 2; i++) { const t = at(0, local.getUTCHours() + i); if (t > nowMs) return iso(t); }
    return null;
  }
  if (k.FREQ === 'DAILY') {
    for (let d = 0; d < 2; d++) { const t = at(d); if (t > nowMs) return iso(t); }
    return null;
  }
  if (k.FREQ === 'WEEKLY') {
    const days = (k.BYDAY ?? '').split(',').map((d) => DAYS.indexOf(d)).filter((d) => d >= 0);
    for (let d = 0; d < 8; d++) {
      const t = at(d);
      if (t > nowMs && (!days.length ? d === 0 || d === 7 : days.includes(new Date(t + off).getUTCDay()))) return iso(t);
    }
    return null;
  }
  if (k.FREQ === 'MONTHLY') {
    const day = Number(k.BYMONTHDAY ?? 1);
    for (let mo = 0; mo < 2; mo++) {
      const t = Date.UTC(local.getUTCFullYear(), local.getUTCMonth() + mo, day, h, m) - off;
      if (t > nowMs) return iso(t);
    }
  }
  return null;
}

/** «امروز 18:30», «فردا 07:00», «۲۵ آبان 09:00»: a moment to come, its hour in Latin tabular digits. */
export function WhenAt({ iso }: { iso: string }) {
  return <span data-when-at>{deskDayFa(iso)} <Ltr>{clock(iso)}</Ltr></span>;
}

// ============================================================================================ the last seven runs ==
const RUN_FA: Record<RoutineRun['state'], string> = { done: 'انجام شد', failed: 'ناموفق', skipped: 'رد شد', queued: 'در صف' };

/** The last seven runs of a routine, oldest first: done is a filled dot, failed a red square, skipped a hollow dot, queued a ring. */
export function RunDots({ runs, label }: { runs: RoutineRun[]; label: string }) {
  const last = runs.slice().sort((a, b) => a.at.localeCompare(b.at)).slice(-7);
  const pad = Array.from({ length: Math.max(0, 7 - last.length) });
  const failed = last.filter((r) => r.state === 'failed').length;
  return (
    <span role="img" data-testid="run-dots" data-runs={last.length}
      aria-label={`${label}: ${last.length ? `${faCount(last.length)} نوبت آخر${failed ? `، ${faCount(failed)} ناموفق` : '، همه بی‌خطا'}` : 'هنوز نوبتی نداشته'}`}
      className="inline-flex flex-none items-center gap-1" dir="ltr">
      {pad.map((_, i) => <span key={`p${i}`} data-dot="none" className="size-2 rounded-full border border-div" />)}
      {last.map((r) => (
        <span key={r.id} data-dot={r.state} title={`${RUN_FA[r.state]}، ${ago(r.at)}`}
          className={cx('size-2', r.state === 'done' ? 'rounded-full bg-pos' : r.state === 'failed' ? 'rounded-[2px] bg-neg' : r.state === 'queued' ? 'rounded-full border-[1.5px] border-silver-ink' : 'rounded-full border-[1.5px] border-strong')} />
      ))}
    </span>
  );
}

// =================================================================================================== a member ==
export type MemberLook = { company: string; name_fa: string; state: 'on' | 'paused' };

/** The head of a member's tile: its mark and name, its state as a shape and a word, its last and next run, and its work line. */
export function MemberHead({ m, runs, next, onStart, starting, action }: {
  m: MemberLook;
  /** This company's runs in the group (any order); undefined while they are not known (an older hub). */
  runs: RoutineRun[] | null | undefined;
  /** When its next routine runs; null when none does. */
  next: string | null;
  onStart?: () => void; starting?: boolean; action?: ReactNode;
}) {
  const mine = (runs ?? []).filter((r) => r.company === m.company).sort((a, b) => b.at.localeCompare(a.at));
  const last = mine.find((r) => r.state !== 'queued') ?? null;
  const running = mine.some((r) => r.state === 'queued');
  const on = m.state === 'on';
  // Why it stands still: what its last run said, when it failed; else that it was stopped.
  const why = !on ? (last?.state === 'failed' && last.note_fa ? plain(last.note_fa) : 'این شرکت در کارگروه ایستاده است؛ روال‌هایش اجرا نمیشوند.') : null;
  return (
    <div className="flex flex-col gap-1.5" data-member-head data-state={m.state} data-running={running ? '' : undefined}>
      <div className="flex items-center gap-2.5">
        <CompanyMark code={m.company} height={18} mono />
        <span className="min-w-0 flex-1 text-[15px] font-semibold leading-6 text-ink">{m.name_fa}</span>
        <span className={cx('inline-flex flex-none items-center gap-1.5 text-[12px] font-semibold', on ? 'text-silver-ink' : 'text-muted')} data-member-state={m.state}>
          {on ? <span aria-hidden className="size-2 rounded-full bg-current" /> : <span aria-hidden className="size-2.5 rounded-full border-[1.5px] border-current" />}
          {on ? (running ? 'در کار' : 'فعال') : 'ایستاده'}
        </span>
        {action}
      </div>
      {runs !== undefined && runs !== null || next ? (
        <span className="text-[12px] leading-5 text-sec" data-member-runs>
          <Facts>
            {last ? <>آخرین نوبت {ago(last.at)}، {RUN_FA[last.state]}</> : runs ? 'هنوز نوبتی نداشته' : null}
            {on && next ? <>نوبت بعد <WhenAt iso={next} /></> : null}
          </Facts>
        </span>
      ) : null}
      {why ? (
        <div className="flex flex-wrap items-center gap-2" data-member-still>
          <span className="min-w-0 flex-1 text-[12px] leading-5 text-sec"><FaText text={why} /></span>
          {onStart ? <Button variant="secondary" size="sm" loading={starting} onClick={onStart}>راه بینداز</Button> : null}
        </div>
      ) : null}
      {/* The silver work line shows only while something of this company runs. */}
      <WorkBand on={on && running} height={3} label="در کار" />
    </div>
  );
}

/** A quiet link at the end of a member's head («جلسه‌اش», «آمادگی»). */
export function QuietLink({ href, children }: { href: string; children: ReactNode }) {
  return <Link href={href} className="inline-flex h-8 flex-none items-center rounded-[8px] px-2 text-[12px] font-semibold text-silver-ink hover:bg-[var(--hq-silver-soft)] hover:text-ink">{children}</Link>;
}

/** A row of a member's settings group: what it is, where it stands, and its quiet action. */
export const SETTING_ROW = 'flex flex-col gap-1.5 py-2.5';
export const QUIET_ACTION = 'h-8 flex-none rounded-[8px] px-2 text-[12px] font-semibold text-silver-ink hover:bg-[var(--hq-silver-soft)] hover:text-ink';

// ============================================================================================ the draft's summary ==
/** «۳ جایگاه | ۲ روال | ۱ اتصال»: what a seal starts, in one line. */
export function SealSummary({ seats, routines, connections }: { seats: number; routines: number; connections: number }) {
  return <Facts>{`${faCount(seats)} جایگاه`}{`${faCount(routines)} روال`}{connections ? `${faCount(connections)} اتصال` : null}</Facts>;
}
