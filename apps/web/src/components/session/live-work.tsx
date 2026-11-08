'use client';

// ⟨1.23⟩ Contract §41 «the session shows its work live and never stalls»: the owner sees the session work the way Claude Code shows its steps.
// `LiveWork` sits just above the composer: who is working and at which step, the last few lines as they stream in, the elapsed time, and
// the whole list on a tap; when nothing runs it says why in plain words (waiting for him, stuck with «ادامه بده», or quiet). `PaceChip` is
// the «با من | خودکار» switch of the header; `PlanProgress` is «کار n از m» with its thin bar.

import { useEffect, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { errText } from '@/components/v31/kit';
import { FaText } from '@/components/v29/text';
import { PACE_FA, type Pace, type SessionTask } from '@/lib/api/v34';
import { useNudge, useSessionActivity, type ActivityLine, type SessionActivity } from '@/lib/api/v41';
import { ago, cx, jTime } from '@/lib/format';

/** How many lines show before the owner opens the list. */
const SHOWN = 4;

/** A clock that moves once a second while [on]. */
function useNow(on: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!on) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [on]);
  return now;
}

/** «۰۲:۰۵» for the time a work has been going on. */
export function elapsed(from: string, now: number): string {
  const s = Math.max(0, Math.floor((now - Date.parse(from)) / 1000));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
}

function Lines({ lines, all }: { lines: ActivityLine[]; all: boolean }) {
  const shown = all ? lines : lines.slice(-SHOWN);
  if (!shown.length) return null;
  return (
    <ul className={cx('flex flex-col gap-0.5', all && 'max-h-64 overflow-y-auto overscroll-contain')} aria-label="آخرین قدم‌ها" aria-live="polite" data-lines={shown.length}>
      {shown.map((l, i) => (
        <li key={`${l.at}-${i}`} data-line className={cx('flex items-baseline gap-2 text-[12px] leading-6', i === shown.length - 1 ? 'text-ink' : 'text-sec')}>
          <span className="fig flex-none text-muted">{jTime(l.at)}</span>
          <span className="min-w-0 flex-1"><span className="text-muted">{l.who_fa}: </span><FaText text={l.text_fa} /></span>
        </li>
      ))}
    </ul>
  );
}

export function LiveWork({ refId, closed }: { refId: string; closed: boolean }) {
  const q = useSessionActivity(refId, !closed);
  const nudge = useNudge(refId);
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const a: SessionActivity | null | undefined = q.data;
  const working = !!a?.working.length;
  const now = useNow(working);
  if (closed || !a) return null;

  const go = () => nudge.mutate(undefined, {
    onSuccess: () => toast({ tone: 'ok', text: 'گفتم ادامه بدهد.' }),
    onError: (e) => toast({ tone: 'error', text: errText(e, 'نشد؛ دوباره بزن.') }),
  });
  const more = a.last.length > SHOWN;
  const toggle = more ? (
    <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="self-start text-[12px] text-muted hover:text-ink">
      {open ? 'کمتر' : `همه‌ی قدم‌ها (${a.last.length})`}
    </button>
  ) : null;

  if (working) {
    const w = a.working[0]!;
    const first = a.working.reduce((m, x) => (Date.parse(x.started_at) < Date.parse(m) ? x.started_at : m), w.started_at);
    return (
      <Card as="section" className="flex flex-col gap-2 p-3 ring-1 ring-[var(--hq-lapis)]" aria-label="کار زنده" data-testid="live-work" data-state="working">
        <div className="flex items-center gap-2 text-[13px]">
          <span aria-hidden className="size-2 flex-none rounded-full bg-lapis" style={{ animation: 'hq-live 1.4s infinite' }} />
          <span className="min-w-0 flex-1 truncate font-semibold text-ink" role="status">
            {w.who_fa} دارد کار میکند · قدم {w.step}
            {a.working.length > 1 ? <span className="font-normal text-sec"> · و {a.working.length - 1} نفر دیگر</span> : null}
          </span>
          <span className="fig flex-none text-[12px] text-muted" aria-label="زمان گذشته" data-elapsed>{elapsed(first, now)}</span>
        </div>
        <p className="truncate text-[12px] text-sec">{w.work_title_fa}{w.company_fa ? ` · ${w.company_fa}` : ''}</p>
        <Lines lines={a.last} all={open} />
        {toggle}
      </Card>
    );
  }

  if (a.waiting_fa) {
    return (
      <Card as="section" className="flex flex-col gap-2 p-3 ring-1 ring-[var(--hq-gold-ink)]" aria-label="کار زنده" data-testid="live-work" data-state="waiting">
        <div className="flex items-center gap-2 text-[13px]"><Icon name="owner" size={16} className="flex-none text-gold-ink" /><span className="min-w-0 flex-1 font-semibold">منتظر شما: <FaText text={a.waiting_fa} /></span></div>
        {open ? <Lines lines={a.last} all /> : null}
        {toggle}
      </Card>
    );
  }

  if (a.stuck_fa) {
    return (
      <Card as="section" className="flex flex-col gap-2 bg-warn-soft p-3 ring-1 ring-[var(--hq-neg-line)]" aria-label="کار زنده" data-testid="live-work" data-state="stuck">
        <div className="flex flex-wrap items-center gap-2 text-[13px]" role="alert">
          <Icon name="bell" size={16} className="flex-none text-warn" />
          <span className="min-w-0 flex-1 font-semibold">گیر کرده: <FaText text={a.stuck_fa} /></span>
          <Button size="sm" variant="primary" icon="next" loading={nudge.isPending} onClick={go}>ادامه بده</Button>
        </div>
        {open ? <Lines lines={a.last} all /> : null}
        {toggle}
      </Card>
    );
  }

  const lastAt = a.last.at(-1)?.at ?? a.idle_since ?? null;
  return (
    <Card as="section" className="flex flex-col gap-2 p-3" aria-label="کار زنده" data-testid="live-work" data-state="idle">
      <div className="flex items-center gap-2 text-[13px] text-sec">
        <span aria-hidden className="size-2 flex-none rounded-full bg-[var(--hq-muted,currentColor)] opacity-50" />
        <span className="min-w-0 flex-1 truncate">آرام{lastAt ? ` · آخرین کار ${ago(lastAt)}` : ''}</span>
        <Button size="sm" variant="ghost" loading={nudge.isPending} onClick={go}>ادامه بده</Button>
      </div>
      {open ? <Lines lines={a.last} all /> : null}
      {toggle}
    </Card>
  );
}

/** «با من | خودکار» in the header: small, always at hand while the session is open. */
export function PaceChip({ pace, onChange, busy }: { pace: Pace; onChange: (p: Pace) => void; busy?: boolean }) {
  const opts: Pace[] = ['step', 'auto'];
  return (
    <div role="radiogroup" aria-label="روش کار" data-testid="pace-chip" className="flex flex-none rounded-full bg-tile p-0.5">
      {opts.map((p) => {
        const on = p === pace;
        return (
          <button key={p} type="button" role="radio" aria-checked={on} disabled={busy} onClick={() => { if (!on) onChange(p); }}
            className={cx('h-7 whitespace-nowrap rounded-full px-3 text-[12px] transition-colors disabled:opacity-60', on ? 'bg-raised font-semibold text-ink shadow-[inset_0_-2px_0_var(--hq-gold-ink)]' : 'text-sec hover:text-ink')}>
            {PACE_FA[p]}
          </button>
        );
      })}
    </div>
  );
}

/** «کار n از m» with a thin bar; a tap opens the plan. */
export function PlanProgress({ tasks, onOpen }: { tasks: SessionTask[]; onOpen: () => void }) {
  const live = tasks.filter((t) => t.state !== 'dropped');
  if (!live.length) return null;
  const done = live.filter((t) => t.state === 'done').length;
  const pct = Math.round((done / live.length) * 100);
  return (
    <button type="button" onClick={onOpen} aria-label={`کار ${done} از ${live.length}؛ برنامه را باز کن`} data-testid="plan-progress" className="flex min-w-0 flex-1 items-center gap-2 rounded-[8px] px-1 text-[12px] text-sec hover:text-ink">
      <span className="flex-none">کار <span className="fig">{done}</span> از <span className="fig">{live.length}</span></span>
      <span className="h-1 min-w-12 max-w-48 flex-1 overflow-hidden rounded-full bg-tile" aria-hidden><span className="block h-full rounded-full bg-gold" style={{ width: `${pct}%` }} /></span>
    </button>
  );
}
