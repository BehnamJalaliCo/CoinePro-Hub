'use client';

// ⟨1.0.1⟩ Part C, the session redesigned (C2.2; features 13, 14, 15, 28 and 75), the pieces the session page is built from:
// - the mood light: a small shape and one word, never colour alone («فکر میکند», «کار میکند», «منتظر تو», «گیر کرده», «آرام», «تمام»);
// - the segmented line under the header: what is done is silver, what waits for the owner is gold, the rest is empty;
// - the «الان» bar above the composer while something works: who, for which company, the whole sentence of what it does, the time,
//   and «نگه دار» always at the same edge (one tap stops the live work; it then reads «ادامه بده»). A workshop turn or the holder's own
//   direct turn shows the build ring: real elapsed time out of the turn's cap, amber from 90 percent;
// - the «منتظر تو» card: the ONE place of the holder's question, with its ready answers (one tap answers);
// - the «گره» card: one sentence of why the session stands still, and one action;
// - the cards of the session that wait for his word, answered in place; the live steps as thin lines; the end leaf of a closed session;
// - ⟨2026-11-11⟩ the still card: an open session nobody works on and nothing above explains is «ایستاده» after twenty minutes, with the
//   last thing done and «ادامه بده» (the owner's 12-hour stall that read «آرام» and offered nothing to press); an outside call (ChatGPT
//   drafting the text, the AI narrator) is one of those at work in the «الان» bar, with its model's mark.

import Link from 'next/link';
import { useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Avatar } from '@/components/brand/avatar';
import { ModelMark } from '@/components/brand/model-mark';
import { Icon } from '@/components/icon';
import { Arc, TickMark, WorkBand, useReducedMotion, useTick } from '@/components/live/motion';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import { FixButton, PlainText } from '@/components/v29/bits';
import { FaText } from '@/components/v29/text';
import { ApiError } from '@/lib/api/client';
import { useCompanies, useDecide } from '@/lib/api/hooks';
import type { Fix } from '@/lib/api/v29';
import { WORKSPACE_LIVE, useStopWorkspace, type OrderParallel } from '@/lib/api/v33';
import type { Badge, OrderCard, SessionReport, SessionTask } from '@/lib/api/v34';
import { useNudge, type ActivityLine, type Mood, type SessionActivity, type Worker } from '@/lib/api/v41';
import { DECIDE_YOURSELF_FA, MOOD_FA, deskDayFa, readyAnswers, type MoodKey } from '@/lib/api/v55';
import { ago, cx, jTime, tokens } from '@/lib/format';
import { plain } from '@/lib/plain';
import { haptic } from './haptics';
import { waitedFa } from './home';
import { DrawnTick, Ring, ringColor } from './ring';
import { SpringSheet } from './spring-sheet';
import { Facts, Ltr, faCount } from './text';

// ====================================================================================================== the mood ==
const KNOWN: readonly Mood[] = ['thinking', 'working', 'waiting', 'stuck', 'idle'];

/**
 * The session's mood: the hub's own word when it sends one (§55.1); on an older hub it is read from what the activity says; with no
 * activity at all, from the session's badge. A closed session is «تمام». ⟨2026-11-11⟩ A session ready for his OK waits for him: never
 * «آرام», whatever an older hub says. The page puts «ایستاده» over an «آرام» that has stood too long (`stillOf`).
 */
export function moodOf(a: SessionActivity | null | undefined, hint: { closed: boolean; badge?: Badge | null; asked?: boolean }): MoodKey {
  if (hint.closed) return 'done';
  let mood: MoodKey;
  if (a) {
    if (a.mood && KNOWN.includes(a.mood)) mood = a.mood;
    else if (a.stuck_fa) mood = 'stuck';
    else if (a.waiting_fa) mood = 'waiting';
    else if (a.working.length) mood = 'working';
    else mood = hint.asked ? 'waiting' : 'idle';
  } else if (hint.asked || hint.badge === 'your_turn') mood = 'waiting';
  else mood = hint.badge === 'stuck' ? 'stuck' : hint.badge === 'moving' ? 'working' : 'idle';
  return mood === 'idle' && hint.badge === 'ready' ? 'waiting' : mood;
}

const MOOD_TONE: Record<MoodKey, string> = {
  thinking: 'text-silver-ink', working: 'text-silver-ink', waiting: 'text-gold-ink', stuck: 'text-neg', idle: 'text-muted', still: 'text-muted', done: 'text-muted',
};

/** «چراغ حال»: a shape and a word. The arc of «کار میکند» turns only while this is shown, which is only while work is live. */
export function MoodLight({ mood, word, size = 14, className }: { mood: MoodKey; word?: string | null; size?: number; className?: string }) {
  const rm = useReducedMotion();
  return (
    <span className={cx('hq-m2 inline-flex flex-none items-center gap-1.5 whitespace-nowrap text-[12px] font-semibold', MOOD_TONE[mood], className)} data-testid="mood-light" data-mood={mood}>
      <svg width={size} height={size} viewBox="0 0 14 14" aria-hidden className="flex-none">
        {mood === 'thinking' || mood === 'still' ? <circle cx={7} cy={7} r={5} fill="none" stroke="currentColor" strokeWidth={1.6} />
          : mood === 'working' ? (
            <>
              <circle cx={7} cy={7} r={5} fill="none" stroke="var(--hq-line-strong)" strokeWidth={1.6} />
              <circle cx={7} cy={7} r={5} fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeDasharray="9 23" className={rm ? undefined : 'hq-m7'} />
            </>
          )
          : mood === 'waiting' ? <circle cx={7} cy={7} r={3.6} fill="currentColor" />
          : mood === 'stuck' ? <circle cx={7} cy={7} r={5} fill="none" stroke="currentColor" strokeWidth={1.8} strokeDasharray="5.2 2.65" />
          : mood === 'done' ? <path d="M2.8 7.4l2.7 2.7L11.2 4.4" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
          : <circle cx={7} cy={7} r={3} fill="currentColor" opacity={0.7} />}
      </svg>
      <span>{mood === 'done' ? MOOD_FA.done : word || MOOD_FA[mood]}</span>
    </span>
  );
}

// ============================================================================================ the plan, in a line ==
const openTasks = (tasks: SessionTask[]) => tasks.filter((t) => t.state !== 'dropped').sort((a, b) => a.n - b.n);
/** «کار ۳ از ۴»: the task the session is on (the last one once all are done); null with no plan. */
export function taskOf(tasks: SessionTask[] | undefined): { n: number; total: number } | null {
  const live = openTasks(tasks ?? []);
  if (!live.length) return null;
  const done = live.filter((t) => t.state === 'done').length;
  return { n: Math.min(live.length, done + 1), total: live.length };
}
export const taskFa = (t: { n: number; total: number }) => `کار ${t.n} از ${t.total}`;

/**
 * The plan as a line of parts: done is silver, what waits for the owner is gold, the rest is empty. A line of the plan he
 * dictated himself (`by` = owner) is not a part that waits for him: only the first open part of a session that waits is his.
 */
export function SegmentLine({ tasks, waiting, className }: { tasks: SessionTask[] | undefined; waiting: boolean; className?: string }) {
  const live = openTasks(tasks ?? []);
  if (!live.length) return null;
  const first = live.findIndex((t) => t.state !== 'done');
  const kinds = live.map((t, i) => (t.state === 'done' ? 'done' : waiting && i === first ? 'waiting' : 'todo'));
  const done = kinds.filter((k) => k === 'done').length;
  return (
    <span role="img" aria-label={`${done} کار از ${live.length} انجام شده${kinds.includes('waiting') ? '؛ یک بخش منتظر تو است' : ''}`} data-testid="segment-line" className={cx('flex gap-1', className)}>
      {kinds.map((k, i) => <span key={live[i]!.id} data-seg={k} className={cx('hq-m2 h-[3px] min-w-2 flex-1 rounded-full', k === 'done' ? 'bg-silver-ink' : k === 'waiting' ? 'bg-gold-ink' : 'bg-tile')} />)}
    </span>
  );
}

// =================================================================================================== time, in words ==
/** «۲ ساعت و ۱۰ دقیقه», «۴۰ دقیقه», «۳ روز»: how long something took (a count in a sentence). */
export function tookFa(from: string | null | undefined, to: string | null | undefined): string | null {
  if (!from || !to) return null;
  const m = Math.round((Date.parse(to) - Date.parse(from)) / 60_000);
  if (!Number.isFinite(m) || m < 0) return null;
  if (m < 1) return 'کمتر از یک دقیقه';
  if (m < 60) return `${m} دقیقه`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (h >= 48) return `${Math.round(h / 24)} روز`;
  return r ? `${h} ساعت و ${r} دقیقه` : `${h} ساعت`;
}
/** «0:42», «23:05», «1:02:10»: a running timer, for an isolated Latin run. */
export function timer(from: string, now: number): string {
  const s = Math.max(0, Math.floor((now - Date.parse(from)) / 1000));
  const h = Math.floor(s / 3600);
  const two = (n: number) => String(n).padStart(2, '0');
  return h ? `${h}:${two(Math.floor((s % 3600) / 60))}:${two(s % 60)}` : `${Math.floor(s / 60)}:${two(s % 60)}`;
}

// ============================================================================================= the live steps ==
const lineKey = (l: ActivityLine, i: number) => l.id ?? `${l.at}-${i}`;

function useCompanyName() {
  const { data } = useCompanies();
  return (code: string | null | undefined) => (code ? data?.find((c) => c.code === code)?.name_fa ?? null : null);
}

/** One step of live work: its real clock time, who and for which company, what; a running one turns, a finished one is ticked. */
function LiveLine({ l, now, draw, name, centred }: { l: ActivityLine; now: number; draw: boolean; name: (c: string | null | undefined) => string | null; centred?: boolean }) {
  const co = name(l.company);
  return (
    <li data-line data-state={l.state ?? undefined} className={cx('flex items-baseline gap-2 text-[12px] leading-6', draw && 'hq-m1-row', l.state === 'failed' ? 'text-neg' : 'text-sec', centred && 'justify-center')}>
      <Ltr className="flex-none text-[11px] text-muted">{jTime(l.at)}</Ltr>
      <span className={cx('min-w-0', !centred && 'flex-1')}>
        <span className="text-silver-ink">{l.who_fa}{co && !l.who_fa.includes(co) ? `، ${co}` : ''}: </span><FaText text={plain(l.text_fa)} />
      </span>
      <span className="flex-none self-center">
        {l.state === 'running' ? <span className="inline-flex items-center gap-1" data-mark="running"><Arc size={13} /><span data-line-secs><Ltr className="text-[11px] text-muted">{Math.max(0, Math.round((now - Date.parse(l.at)) / 1000))}s</Ltr></span></span>
          : l.state === 'done' || l.state === 'failed' ? <TickMark size={13} failed={l.state === 'failed'} draw={draw} /> : null}
      </span>
    </li>
  );
}

/** The newest steps of the work that is live, as thin lines at the end of the thread. Nothing while nothing works. */
export function LiveTail({ a, shown = 3 }: { a: SessionActivity | null | undefined; shown?: number }) {
  const name = useCompanyName();
  const lines = a?.working.length ? a.last.slice(-shown) : [];
  const now = useTick(1000, lines.some((l) => l.state === 'running'));
  if (!lines.length) return null;
  return (
    <ul aria-label="قدم‌های کار زنده" aria-live="polite" data-testid="live-tail" className="mx-auto flex w-full max-w-[40rem] flex-col">
      {lines.map((l, i) => <LiveLine key={lineKey(l, i)} l={l} now={now} draw name={name} />)}
    </ul>
  );
}

// ================================================================================================ the «الان» bar ==
type W = Worker;
const isTurn = (w: W) => (w.kind === 'workshop' || w.kind === 'direct') && !!w.cap_s;
/** ⟨2026-11-11⟩ An outside model or voice working for the session: shown like a run, never as a ring, never stopped from the bar. */
export const isCall = (w: W) => w.kind === 'call';
const KIND_FA: Partial<Record<NonNullable<W['kind']>, string>> = { workshop: 'کارگاه', server: 'سرور شرکت' };
const sentenceOf = (w: W) => plain(w.last_fa || w.doing_fa || w.work_title_fa);
/** The worker the bar speaks of: a turn first (its ring is the bar's mark), else the hub's own run before an outside call it waits on. */
export const leadWorker = (working: W[]): W | null => working.find(isTurn) ?? working.find((w) => !isCall(w)) ?? working[0] ?? null;
/** The model a call's mark is drawn from: its name as the hub says it, a Persian name read as its key. */
const CALL_MODEL: Record<string, string> = { 'جی‌پی‌تی': 'gpt', 'چت‌جی‌پی‌تی': 'gpt', 'جمنای': 'gemini', 'جمینای': 'gemini', 'دیپ‌سیک': 'deepseek' };
export const callModel = (w: W) => CALL_MODEL[w.who_fa.trim()] ?? w.who_fa.trim();

/** One worker's mark: the holder's own turn wears the manager's ring, an outside call its model's logo on a tile, the rest a colleague. */
function WorkerMark({ w, size }: { w: W; size: number }) {
  if (isCall(w)) {
    return (
      <span role="img" aria-label={w.who_fa} data-call-mark className="flex flex-none items-center justify-center rounded-full bg-tile shadow-[inset_0_0_0_1px_var(--hq-line-divider)]" style={{ width: size, height: size }}>
        <ModelMark model={callModel(w)} size={Math.round(size * 0.52)} />
      </span>
    );
  }
  return <Avatar kind={w.kind === 'direct' ? 'manager' : 'employee'} size={size} state="working" label={w.who_fa} />;
}

/** The work a «نگه دار» stops: the task in hand, else the live workspace, else the first open task that names its work, else the last one that does. */
export function liveWorkRef(r: SessionReport): string | null {
  const tasks = r.tasks ?? [];
  const p = r as OrderParallel;
  return tasks.find((t) => t.state === 'doing' && t.work_ref)?.work_ref
    ?? (p.workspaces ?? []).find((w) => WORKSPACE_LIVE.has(w.state))?.work_ref
    ?? tasks.find((t) => t.state === 'todo' && t.work_ref)?.work_ref
    ?? (p.parts ?? [])[0]?.work_ref
    ?? tasks.filter((t) => t.work_ref).sort((a, b) => b.n - a.n)[0]?.work_ref
    ?? null;
}

/** How far a turn is into its time cap: its share (0..1), the minute it is in, the cap in minutes, and whether it is past 90 percent. */
export function turnTime(w: W, now: number): { share: number; min: number; capMin: number; late: boolean } {
  const cap = Math.max(60, w.cap_s ?? 3600);
  const spent = Math.max(0, (now - Date.parse(w.started_at)) / 1000);
  const share = Math.min(1, spent / cap);
  const capMin = Math.round(cap / 60);
  return { share, min: Math.min(capMin, Math.floor(spent / 60)), capMin, late: share >= 0.9 };
}
/** Past 90 percent: amber leaning to red, so that beside the page's gold (and in the day theme) it never reads as gold. */
const LATE_INK = { color: ringColor('near') };

/** The build ring of a workshop or direct turn: real elapsed time out of its cap, the minute in its middle; amber from 90 percent. */
export function BuildRing({ w, now, size = 76 }: { w: W; now: number; size?: number }) {
  const { share, min, capMin, late } = turnTime(w, now);
  return (
    <Ring value={share} size={size} stroke={5} tone={late ? 'near' : 'silver'} label={`${min} دقیقه از ${capMin} دقیقه گذشته${late ? '؛ نزدیک سقف زمان' : ''}`} className="flex-none">
      <span data-testid="build-ring" data-late={late ? '' : undefined} className="flex flex-col items-center gap-0.5">
        <span className="text-[20px] font-bold leading-6 text-ink" style={late ? LATE_INK : undefined} data-ring-minute>{faCount(min)}</span>{' '}
        <span className="text-[9.5px] leading-3 text-muted">از {faCount(capMin)} دقیقه</span>
      </span>
    </Ring>
  );
}

const HOLD = 'inline-flex min-h-12 flex-none items-center justify-center rounded-[12px] border px-3.5 text-[13px] font-semibold disabled:opacity-60';

/**
 * «الان»: stuck above the composer while something works. A tap on it opens the live-work sheet; «نگه دار» stops the live work with
 * the hub's own stop of that work, and the same place then reads «ادامه بده». [held]: the owner stopped it (kept by the page, which
 * then shows no still card: this bar's «ادامه بده» is the one way back).
 */
export function NowBar({ refId, a, r, onOpen, held, onHeld }: {
  refId: string; a: SessionActivity | null | undefined; r: SessionReport; onOpen: () => void; held: boolean; onHeld: (held: boolean) => void;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const stop = useStopWorkspace();
  const nudge = useNudge(refId);
  const setHeld = onHeld;
  const working = a?.working ?? [];
  const live = working.length > 0;
  const now = useTick(1000, live);
  if (!live && !held) return null;
  const w = leadWorker(working);
  const direct = w?.kind === 'direct';
  // An outside call that is all that works is not the hub's to stop.
  const workRef = working.length && working.every(isCall) ? null : liveWorkRef(r);
  const hold = () => {
    if (!workRef || stop.isPending) return;
    stop.mutate(workRef, {
      onSuccess: () => { haptic('tick'); setHeld(true); void qc.invalidateQueries({ queryKey: ['orders', 'activity', refId] }); },
      onError: (e) => { haptic('error'); toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'نگه داشته نشد؛ دوباره بزن.' }); },
    });
  };
  const go = () => nudge.mutate(undefined, {
    onSuccess: () => { haptic('tick'); setHeld(false); },
    onError: (e) => { haptic('error'); toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'نشد؛ دوباره بزن.' }); },
  });
  const stopped = held && !live;
  return (
    <section aria-label="الان" data-testid="now-bar" data-state={stopped ? 'held' : 'working'} data-kind={w?.kind ?? 'run'} className="hq-m1 flex flex-none flex-col overflow-hidden rounded-[14px] bg-card">
      <div className="flex items-center gap-2.5 p-2.5 ps-3">
        <button type="button" onClick={onOpen} aria-haspopup="dialog" aria-label="کار زنده را باز کن" className="flex min-w-0 flex-1 items-center gap-3 rounded-[10px] text-start">
          {stopped || !w ? <span aria-hidden className="flex size-8 flex-none items-center justify-center rounded-full bg-tile text-muted"><span className="size-2.5 rounded-[2px] bg-current" /></span>
            : isTurn(w) ? <BuildRing w={w} now={now} />
            : (
              <span className="flex flex-none items-center" data-workers={working.length}>
                {working.slice(0, 3).map((x, i) => <span key={`${x.who_fa}-${i}`} className={cx('rounded-full bg-card', i > 0 && '-ms-2.5')}><WorkerMark w={x} size={32} /></span>)}
              </span>
            )}
          <span className="flex min-w-0 flex-1 flex-col gap-0.5">
            {stopped || !w ? (
              <>
                <span className="text-[13px] font-semibold text-ink" role="status">کار نگه داشته شد</span>
                <span className="text-[12px] leading-5 text-sec">هر وقت خواستی «ادامه بده» را بزن؛ از همان‌جا ادامه پیدا میکند.</span>
              </>
            ) : (
              <>
                <span className="text-[11px] leading-5 text-muted" data-now-who>
                  <Facts>
                    {w.who_fa}
                    {direct ? 'دارد روی فرمان تو کار میکند' : w.company_fa && !w.who_fa.includes(w.company_fa) ? w.company_fa : null}
                    {direct ? null : KIND_FA[w.kind ?? 'run'] ?? null}
                    {working.length > 1 ? `و ${faCount(working.length - 1)} نفر دیگر` : null}
                  </Facts>
                </span>
                {/* The whole sentence: it wraps, it is never cut. */}
                <span className="text-[13px] font-semibold leading-6 text-ink [overflow-wrap:anywhere]" role="status" data-now-sentence><FaText text={sentenceOf(w)} /></span>
                {isTurn(w) && turnTime(w, now).late ? <span className="inline-flex items-center gap-1 text-[11px] font-semibold" style={LATE_INK} data-now-late><Icon name="time" size={12} />نزدیک سقف زمان</span> : null}
              </>
            )}
          </span>
          {!stopped && w && !isTurn(w) ? <span className="flex-none" data-now-timer><Ltr className="text-[13px] text-sec">{timer(working.reduce((m, x) => (Date.parse(x.started_at) < Date.parse(m) ? x.started_at : m), w.started_at), now)}</Ltr></span> : null}
        </button>
        {stopped
          ? <button type="button" onClick={go} disabled={nudge.isPending} className={cx(HOLD, 'border-strong text-ink hover:bg-hover')}>ادامه بده</button>
          : workRef ? <button type="button" onClick={hold} disabled={stop.isPending} aria-busy={stop.isPending || undefined} className={cx(HOLD, 'border-[var(--hq-neg-line)] text-neg hover:bg-neg-soft')}>نگه دار</button>
          : null}
      </div>
      {/* The silver work line moves only while the work is live. */}
      <WorkBand on={live && !stopped} height={4} label="کار در جریان است" />
    </section>
  );
}

/**
 * A quiet session, in its details and the live sheet: when it last worked, and one tap that tells its holder to take the work up again
 * (the hub's nudge). Nothing while someone works. [button] false: the page's still card already carries «ادامه بده»; the line stays.
 */
export function IdleNudge({ refId, a, button = true }: { refId: string; a: SessionActivity | null | undefined; button?: boolean }) {
  const toast = useToast();
  const nudge = useNudge(refId);
  if (!a || a.working.length) return null;
  // The answer changes what the session shows at once, and this piece may be gone by then: the promise says it either way.
  const go = () => void nudge.mutateAsync().then(
    () => { haptic('tick'); toast({ tone: 'ok', text: 'گفتم ادامه بدهد.' }); },
    (e: unknown) => { haptic('error'); toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'نشد؛ دوباره بزن.' }); },
  );
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="idle-nudge">
      <span className="min-w-0 flex-1 text-[12px] leading-5 text-sec">{a.idle_since ? `آخرین کار ${ago(a.idle_since)}` : `${STILL_FA}.`}</span>
      {button ? <Button variant="secondary" size="sm" loading={nudge.isPending} onClick={go}>ادامه بده</Button> : null}
    </div>
  );
}

/**
 * The live-work sheet: who works on what, each with its own line and time, then every step so far; ⟨2026-11-11⟩ and, when nobody
 * works, what the session waits on (as Android's): the owner is asked, it is stuck (with «ادامه بده»), or it is quiet since a time
 * (with «ادامه بده», unless it waits for his OK, [ready]).
 */
export function LiveSheet({ open, onOpenChange, a, refId, ready = false }: { open: boolean; onOpenChange: (v: boolean) => void; a: SessionActivity | null | undefined; refId?: string; ready?: boolean }) {
  const name = useCompanyName();
  const working = a?.working ?? [];
  const lines = a?.last ?? [];
  const now = useTick(1000, open && (working.length > 0 || lines.some((l) => l.state === 'running')));
  return (
    <SpringSheet open={open} onOpenChange={onOpenChange} title="کار زنده" testid="live-sheet" description={working.length ? undefined : 'الان کسی روی این جلسه کار نمیکند.'}>
      <div className="flex flex-col gap-4 pb-1">
        {working.length ? (
          <ul aria-label="چه کسی کار میکند" className="flex flex-col gap-2">
            {working.map((w, i) => (
              <li key={`${w.who_fa}-${i}`} data-worker={w.kind ?? 'run'} className="flex items-center gap-3 rounded-[12px] bg-card p-3">
                {isTurn(w) ? <BuildRing w={w} now={now} size={64} /> : <WorkerMark w={w} size={36} />}
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="text-[11px] leading-5 text-muted"><Facts>{w.who_fa}{w.company_fa && !w.who_fa.includes(w.company_fa) ? w.company_fa : null}{KIND_FA[w.kind ?? 'run'] ?? null}</Facts></span>
                  <span className="text-[13px] font-semibold leading-6 text-ink [overflow-wrap:anywhere]"><FaText text={sentenceOf(w)} /></span>
                  <span className="text-[11px] text-muted"><PlainText text={w.work_title_fa} /></span>
                </span>
                <Ltr className="flex-none text-[12px] text-sec">{timer(w.started_at, now)}</Ltr>
              </li>
            ))}
          </ul>
        ) : null}
        {lines.length ? (
          <section className="flex flex-col gap-1" aria-label="همه‌ی قدم‌ها">
            <h3 className="text-[12px] font-semibold text-muted">قدم‌ها</h3>
            <ul className="flex flex-col" data-lines={lines.length}>{lines.map((l, i) => <LiveLine key={lineKey(l, i)} l={l} now={now} draw={false} name={name} />)}</ul>
          </section>
        ) : <p className="text-[13px] text-muted">هنوز قدمی ثبت نشده.</p>}
        {a && !working.length && refId ? <LiveWhy refId={refId} a={a} ready={ready} /> : null}
      </div>
    </SpringSheet>
  );
}

/** The end of the live sheet while nobody works: why, and «ادامه بده» where it helps. */
function LiveWhy({ refId, a, ready }: { refId: string; a: SessionActivity; ready: boolean }) {
  const toast = useToast();
  const nudge = useNudge(refId);
  const go = () => void nudge.mutateAsync().then(
    () => { haptic('tick'); toast({ tone: 'ok', text: 'گفتم ادامه بدهد.' }); },
    (e: unknown) => { haptic('error'); toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'نشد؛ دوباره بزن.' }); },
  );
  if (a.waiting_fa) {
    return <p className="flex items-start gap-2.5 border-t border-div pt-3 text-[13px] leading-6 text-ink" data-testid="live-why"><MoodLight mood="waiting" className="mt-1" /><span className="min-w-0 flex-1"><PlainText text={a.waiting_fa} /></span></p>;
  }
  if (a.stuck_fa) {
    return (
      <div className="flex flex-col items-start gap-2.5 border-t border-div pt-3" data-testid="live-why">
        <p className="flex items-start gap-2.5 text-[13px] leading-6 text-ink"><MoodLight mood="stuck" className="mt-1" /><span className="min-w-0 flex-1"><PlainText text={a.stuck_fa} /></span></p>
        <Button variant="secondary" size="sm" loading={nudge.isPending} onClick={go}>ادامه بده</Button>
      </div>
    );
  }
  return ready ? null : <div className="border-t border-div pt-3"><IdleNudge refId={refId} a={a} /></div>;
}

// ============================================================================================ the «منتظر تو» card ==
const CARD = 'hq-edge hq-m1 flex flex-none flex-col gap-2 rounded-[14px] bg-card p-3';
const answerCls = 'inline-flex min-h-10 items-center rounded-[12px] border border-strong px-3.5 py-1.5 text-start text-[13px] font-semibold leading-5 text-ink hover:bg-hover disabled:text-disabled';

/**
 * The holder's open question, in ONE place, right above the composer: the question, its ready answers as buttons (the hub's quick
 * replies, else the two or three options a question with «یا» names), always a last quiet «خودت تصمیم بگیر و ادامه بده», and how long
 * it has waited. One tap sends that answer through the session's own reply; typing in the composer still works.
 */
export function WaitingCard({ r, onReply, busy }: { r: SessionReport; onReply: (text: string) => Promise<boolean>; busy: boolean }) {
  const t = r.turn!;
  const [sent, setSent] = useState<string | null>(null);
  const [going, setGoing] = useState<string | null>(null);
  const answers = useMemo(() => readyAnswers(plain(t.question_fa), (r as { quick_replies?: string[] }).quick_replies), [t.question_fa, r]);
  const task = taskOf(r.tasks);
  const waited = waitedFa(t.at);
  const reply = async (text: string) => {
    if (busy || going) return;
    setGoing(text);
    const ok = await onReply(text);
    setGoing(null);
    if (ok) { haptic('seal'); setSent(text); } else haptic('error');
  };
  return (
    <section aria-label="منتظر تو" data-testid="waiting-card" className={CARD}>
      {sent ? (
        <span role="status" className="hq-m2-in flex items-center gap-1.5 text-[13px] text-sec"><span className="text-pos"><DrawnTick size={16} /></span>جوابت رفت: {sent}</span>
      ) : (
        <>
          <span className="text-[11px] leading-5 text-muted" data-waited><Facts>{`${t.who_fa} میپرسد`}{waited}{task && task.n <= task.total ? `${taskFa(task)} ایستاده` : null}</Facts></span>
          <p className="text-[14.5px] font-semibold leading-7 text-ink [overflow-wrap:anywhere]"><PlainText text={t.question_fa} /></p>
          <div role="group" aria-label="جواب‌های آماده" className="flex flex-col items-start gap-1.5">
            {answers.length ? <div className="flex flex-wrap gap-2">{answers.map((x) => <button key={x} type="button" disabled={busy || !!going} onClick={() => void reply(x)} className={answerCls}>{x}</button>)}</div> : null}
            <Button variant="text" size="sm" className="-ms-2" disabled={busy || !!going} loading={going === DECIDE_YOURSELF_FA} onClick={() => void reply(DECIDE_YOURSELF_FA)}>{DECIDE_YOURSELF_FA}</Button>
          </div>
        </>
      )}
    </section>
  );
}

// =================================================================================================== the «گره» card ==
type Blocker = { kind: string; title_fa: string; detail_fa?: string | null; fix?: Fix | null };

/**
 * A session that stands still: ONE card, one whole sentence of why, and one action: the fix the hub offers (its own words), else
 * «ادامه بده». Further knots fold under the first, each with its own quiet fix. [lead]: this card carries the page's full gold.
 */
export function KnotCard({ refId, stuckFa, blockers, company, run, lead }: {
  refId: string; stuckFa: string | null | undefined; blockers: Blocker[]; company: string | null; run: (f: Fix) => Promise<unknown>; lead: boolean;
}) {
  const toast = useToast();
  const nudge = useNudge(refId);
  const [open, setOpen] = useState(false);
  const first = blockers.find((b) => b.fix) ?? blockers[0] ?? null;
  const rest = blockers.filter((b) => b !== first);
  const why = stuckFa || [first?.title_fa, first?.detail_fa].filter(Boolean).join('؛ ');
  if (!why) return null;
  // The answer changes what the session shows at once, and this piece may be gone by then: the promise says it either way.
  const go = () => void nudge.mutateAsync().then(
    () => { haptic('tick'); toast({ tone: 'ok', text: 'گفتم ادامه بدهد.' }); },
    (e: unknown) => { haptic('error'); toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'نشد؛ دوباره بزن.' }); },
  );
  return (
    <section aria-label="گره" data-testid="knot" data-count={Math.max(1, blockers.length)} className="hq-edge hq-m1 flex flex-none flex-col gap-2 rounded-[14px] bg-card p-3" data-edge="neg">
      <p role="alert" className="text-[13.5px] font-semibold leading-6 text-ink [overflow-wrap:anywhere]">
        <MoodLight mood="stuck" word="گره" className="me-2 align-[-1px]" /><PlainText text={why} />
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {first?.fix ? <FixButton fix={first.fix} company={company} run={run} size="sm" variant={lead ? 'primary' : 'secondary'} />
          : <Button size="sm" variant={lead ? 'primary' : 'secondary'} loading={nudge.isPending} onClick={go}>ادامه بده</Button>}
        {rest.length ? (
          <Button variant="text" size="sm" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'کمتر' : `و ${faCount(rest.length)} گره‌ی دیگر`}</Button>
        ) : null}
      </div>
      {open && rest.length ? (
        <ul className="flex flex-col gap-2 border-t border-div pt-2.5">
          {rest.map((b, i) => (
            <li key={`${b.kind}-${i}`} data-blocker className="flex flex-wrap items-center gap-2 text-[13px]">
              <span className="min-w-0 flex-[1_1_12rem] leading-6 [overflow-wrap:anywhere]"><PlainText text={b.title_fa} /></span>
              {b.fix ? <FixButton fix={b.fix} company={company} run={run} variant="secondary" /> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

// ================================================================================================= «ایستاده» ==
/** How long an open session may stand with nobody at work before the page says so itself. */
export const STILL_MINUTES = 20;
/** The still card's own words, when the hub gave no reason of its own. */
export const STILL_FA = 'الان کسی روی این جلسه کار نمیکند';
/** An open session that stands still: the last thing done (its last words when it is long) and when; the hub's own reason (a `stuck` badge's cause). */
export type Still = { line_fa: string | null; at: string | null; reason_fa: string | null };
/** The run's own envelope lines (it began, it ended, it was woken, someone joined): never «the last work». */
const ENVELOPE = new Set(['start', 'end', 'wake', 'join']);
const SYSTEM_FA = 'سامانه';
const oneLine = (t: string) => plain(t).replace(/\s*\n+\s*/g, ' ').trim();
const msOf = (iso: string | null | undefined) => { const t = Date.parse(iso ?? ''); return Number.isFinite(t) ? t : Number.NEGATIVE_INFINITY; };

/** The words of a long line that matter most, its end: the last sentences that fit in [max], after «… ». */
export function lastWordsFa(text: string, max = 140): string {
  const t = oneLine(text);
  if (t.length <= max) return t;
  let out = '';
  for (const p of t.split(/(?<=[.!؟?])\s+/).filter(Boolean).reverse()) {
    const next = out ? `${p} ${out}` : p;
    if (next.length > max) break;
    out = next;
  }
  if (!out) { const tail = t.slice(-max); const i = tail.indexOf(' '); out = i >= 0 ? tail.slice(i + 1) : tail; }
  return `… ${out}`;
}

/** The last thing done in the session: the newest of the activity's last step and the report's last step (the hub's own lines aside). */
export function lastWorkOf(r: SessionReport, a: SessionActivity | null | undefined): { text: string; at: string } | null {
  const line = [...(a?.last ?? [])].reverse().find((l) => l.text_fa.trim() && !ENVELOPE.has(l.kind ?? ''));
  const step = [...(r.steps ?? [])].reverse().find((x) => x.who_fa.trim() !== SYSTEM_FA && x.what_fa.trim() && x.what_fa.trim() !== '-');
  const pick = !line ? (step ? { text: step.what_fa, at: step.at } : null)
    : !step || msOf(line.at) >= msOf(step.at) ? { text: line.text_fa, at: line.at } : { text: step.what_fa, at: step.at };
  return pick ? { text: lastWordsFa(pick.text), at: pick.at } : null;
}

/**
 * The page's own safety net, when the hub has not said why a session stands (the owner's 12-hour stall read «آرام» and offered nothing
 * to press): null unless it is open, nothing waits for the owner (no question, no card, not ready), there is no knot, nobody works, the
 * activity says neither «waiting» nor «stuck», its plan is not done, and [STILL_MINUTES] have passed since the hub's idle time (else the
 * last line's, else the report's last move). A `stuck` badge's reason is the card's sentence; a `moving` badge's only echoes the last step.
 */
export function stillOf(r: SessionReport, a: SessionActivity | null | undefined, badge: Badge, now = Date.now()): Still | null {
  if (!a || r.session?.state === 'closed' || r.turn || (r.cards ?? []).length || (r.blockers ?? []).length) return null;
  if (badge === 'ready' || badge === 'your_turn' || badge === 'closed') return null;
  if (a.working.length || a.waiting_fa || a.stuck_fa) return null;
  const live = (r.tasks ?? []).filter((t) => t.state !== 'dropped');
  if (live.length && live.every((t) => t.state === 'done')) return null;
  const since = a.idle_since || a.last.at(-1)?.at || r.updated_at;
  if (now - msOf(since) < STILL_MINUTES * 60_000) return null;
  const last = lastWorkOf(r, a);
  const reason = badge === 'stuck' && r.session?.reason_fa?.trim() ? oneLine(r.session.reason_fa) : null;
  return { line_fa: last?.text ?? null, at: last?.at ?? null, reason_fa: reason };
}

/** «آخرین کار: … (دیشب 22:28)», the clock time a Latin figure; null when nothing was done yet. */
function StillLast({ still, now }: { still: Still; now: number }) {
  const line = still.line_fa?.trim().replace(/[.،؛]+$/, '');
  if (!line) return null;
  const day = deskDayFa(still.at, now);
  return <>آخرین کار: <FaText text={line} />{day ? <> ({day} <Ltr>{jTime(still.at)}</Ltr>)</> : null}</>;
}

/**
 * An open session nobody works on, and the hub has not said why: ONE calm card right above the composer, the shape of the knot's with
 * a silver edge: «ایستاده», one sentence (the hub's reason, else «الان کسی روی این جلسه کار نمیکند؛ آخرین کار: … (دیشب 22:28)»), and
 * «ادامه بده», the page's one full gold when nothing else holds it ([lead]). [canNudge] false: a hub that does not take the nudge; the
 * card only says it.
 */
export function StillCard({ refId, still, now, lead, canNudge = true }: { refId: string; still: Still; now: number; lead: boolean; canNudge?: boolean }) {
  const toast = useToast();
  const nudge = useNudge(refId);
  const go = () => void nudge.mutateAsync().then(
    () => { haptic('tick'); toast({ tone: 'ok', text: 'گفتم ادامه بدهد.' }); },
    (e: unknown) => { haptic('error'); toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'نشد؛ دوباره بزن.' }); },
  );
  const last = still.line_fa ? <StillLast still={still} now={now} /> : null;
  return (
    <section aria-label="ایستاده" data-testid="still-card" data-edge="silver" className="hq-edge hq-m1 flex flex-none flex-col gap-2 rounded-[14px] bg-card p-3">
      <p role="status" className="text-[13.5px] font-semibold leading-6 text-ink [overflow-wrap:anywhere]" data-still-sentence>
        <MoodLight mood="still" className="me-2 align-[-1px]" />
        {still.reason_fa ? <PlainText text={still.reason_fa} /> : last ? <>{STILL_FA}؛ {last}</> : `${STILL_FA}.`}
      </p>
      {still.reason_fa && last ? <p className="text-[12px] leading-5 text-muted [overflow-wrap:anywhere]" data-still-last>{last}</p> : null}
      {canNudge ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant={lead ? 'primary' : 'secondary'} loading={nudge.isPending} onClick={go}>ادامه بده</Button>
        </div>
      ) : null}
    </section>
  );
}

/** «جوابت رفت: …»: said for a moment where the question was, once the hub has taken the answer and asks no more. */
export function AnswerSent({ text }: { text: string }) {
  return (
    <section aria-label="جوابت رفت" data-testid="answer-sent" className={CARD}>
      <span role="status" className="hq-m2-in flex items-center gap-1.5 text-[13px] text-sec"><span className="flex-none text-pos"><DrawnTick size={16} /></span><span className="min-w-0 [overflow-wrap:anywhere]">جوابت رفت: {text}</span></span>
    </section>
  );
}

// ========================================================================== the session's cards that wait for his word ==
/**
 * The cards of this session that wait for a decision, answered where he sees them: one that takes a tap is approved here with one
 * tap; one the hub seals with the passkey (money, a permanent delete, keys and access, a destructive server command) opens that card.
 */
export function SessionCards({ cards }: { cards: OrderCard[] }) {
  const toast = useToast();
  const qc = useQueryClient();
  const decide = useDecide();
  const [done, setDone] = useState<string[]>([]);
  const list = cards.filter((c) => !done.includes(c.ref));
  if (!list.length) return null;
  const approve = (c: OrderCard) => decide.mutate({ ref: c.ref, verdict: 'approve' }, {
    onSuccess: () => { haptic('seal'); setDone((d) => [...d, c.ref]); toast({ tone: 'ok', text: 'تأیید شد.' }); for (const k of ['orders', 'office']) void qc.invalidateQueries({ queryKey: [k] }); },
    onError: (e) => { haptic('error'); toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد.' }); },
  });
  return (
    <section aria-label="کارت‌های منتظر تصمیم" data-testid="waiting-cards" data-count={list.length} className={CARD}>
      <ul className="flex flex-col gap-2.5">
        {list.map((c) => (
          <li key={c.ref} data-card={c.ref} className="flex flex-wrap items-center gap-2">
            <span className="flex min-w-0 flex-[1_1_12rem] flex-col">
              <span className="text-[14px] font-semibold leading-6 text-ink [overflow-wrap:anywhere]"><PlainText text={c.title_fa} /></span>
              <span className="text-[11px] leading-5 text-muted"><Facts>{c.by_fa ? plain(c.by_fa) : null}{plain(c.waits_fa)}</Facts></span>
            </span>
            {c.seal === 'tap'
              ? <Button variant="secondary" size="sm" data-seal="tap" loading={decide.isPending && decide.variables?.ref === c.ref} onClick={() => approve(c)}>تأیید</Button>
              : <Link href={`/cartable?ref=${encodeURIComponent(c.ref)}`} data-seal="passkey" className="inline-flex h-8 flex-none items-center rounded-[8px] border border-strong px-3 text-[12px] font-semibold text-ink hover:bg-hover">ببین و تأیید کن</Link>}
          </li>
        ))}
      </ul>
    </section>
  );
}

// =================================================================================================== the end leaf ==
/** A figure of the end leaf. */
function LeafFigure({ label, children }: { label: string; children: ReactNode }) {
  return <span className="flex min-w-0 flex-1 flex-col gap-0.5"><span className="text-[11px] text-muted">{label}</span><span className="text-[15px] font-semibold leading-6 text-ink">{children}</span></span>;
}

/**
 * The end of a closed session: what was made (its files, as [made]), how long it took, how many tokens; never half an empty screen.
 * [used]: the tokens of its outputs, null while they are not known.
 */
export function EndLeaf({ r, made, used, outputs, action }: { r: SessionReport; made?: ReactNode; used: number | null; outputs: number; action?: ReactNode }) {
  const took = tookFa(r.at, r.session?.closed_at ?? r.updated_at);
  const cancelled = r.state === 'cancelled';
  return (
    <section aria-label="پایان جلسه" data-testid="end-leaf" className="hq-m1 mx-auto mt-2 flex w-full max-w-[40rem] flex-col gap-3 rounded-[16px] bg-tile p-4 shadow-[inset_0_0_0_1px_var(--hq-line-divider)]">
      <div className="flex items-center gap-2">
        <MoodLight mood="done" />
        <span className="min-w-0 flex-1 text-[13px] text-sec">{cancelled ? 'این فرمان لغو و بایگانی شد.' : 'این جلسه تأیید و بایگانی شد.'}</span>
        {action}
      </div>
      <div className="flex items-start gap-3" data-leaf-figures>
        <LeafFigure label="ساخته شد">{outputs ? `${outputs} خروجی` : '—'}</LeafFigure>
        <LeafFigure label="طول کشید">{took ?? '—'}</LeafFigure>
        <LeafFigure label="مصرف">{used ? <><Ltr>{tokens(used)}</Ltr> واحد</> : '—'}</LeafFigure>
      </div>
      {made}
    </section>
  );
}
