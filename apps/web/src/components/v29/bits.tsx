'use client';

// ⟨1.11⟩ Shared pieces of §29's screens: the hub's plain Persian as the owner reads it (Latin runs isolated, every number a Latin figure,
// paragraphs justified), the order's and the employee's state, and the one-tap fix that knows where each fix is done.

import { useRouter } from 'next/navigation';
import { useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Pill } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { EMPLOYEE_STATE, ORDER_STATE, localFix, stateOf, type EmployeeState, type Fix, type OrderState, type Stuck } from '@/lib/api/v29';
import { cx } from '@/lib/format';
import { ConnectionSheet } from './connections';
import { FaText } from './text';

export { FaPara, FaText, fig } from './text';

export function OrderStatePill({ state }: { state: OrderState | string }) {
  const s = ORDER_STATE[state as OrderState] ?? { fa: state, tone: 'neutral' as const };
  return <Pill tone={s.tone} dot={!s.live} live={s.live}>{s.fa}</Pill>;
}

/** §29.14 on every employee chip: idle, thinking, working, waiting, stuck, done. */
export function EmployeeStateChip({ e, className }: { e: { state?: string | null; activity?: string | null }; className?: string }) {
  const st: EmployeeState = stateOf(e);
  const s = EMPLOYEE_STATE[st];
  return <Pill tone={s.tone} dot={!s.live} live={s.live} className={cx('h-5 text-[11px]', className)}>{s.fa}</Pill>;
}
/** The avatar ring that matches the state. */
export const ringOf = (e: { state?: string | null; activity?: string | null }) => EMPLOYEE_STATE[stateOf(e)].ring;

/**
 * A fix in one tap. A guide opens here (the write-only secret with it), a card or a switch opens its own page, and anything else is the
 * hub's: [run] does it (the order's or the readiness route) and says how it went.
 */
export function FixButton({ fix, company, run, size = 'sm', variant = 'primary', className }: {
  fix: Fix; company?: string | null; run?: (f: Fix) => Promise<unknown>; size?: 'sm' | 'md'; variant?: 'primary' | 'secondary' | 'silver'; className?: string;
}) {
  const router = useRouter();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [guide, setGuide] = useState<{ company: string; kind: string } | null>(null);
  const local = localFix(fix, company);
  const onClick = async () => {
    if (local?.kind === 'guide') { if (local.company) setGuide({ company: local.company, kind: local.connection }); return; }
    if (local?.kind === 'go') {
      if (local.href.startsWith('#')) document.getElementById(local.href.slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      else router.push(local.href);
      return;
    }
    if (!run) return;
    setBusy(true);
    try {
      const out = await run(fix);
      toast(out === null ? { tone: 'info', text: 'ستاد هنوز این کار را انجام نمیدهد؛ بعد از به‌روزرسانی ستاد کار میکند.' } : { tone: 'ok', text: 'انجام شد.' });
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد؛ دوباره بزن.' });
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button size={size} variant={variant} icon={local?.kind === 'guide' ? 'globe' : local?.kind === 'go' ? 'next' : 'seal'} loading={busy} onClick={onClick} className={className}>{fix.label_fa}</Button>
      {guide ? <ConnectionSheet company={guide.company} kind={guide.kind} onClose={() => setGuide(null)} /> : null}
    </>
  );
}

/** An employee's stuck reason and its fix (§29.14), under its chip. */
export function StuckLine({ stuck, company, run }: { stuck: Stuck; company: string; run?: (f: Fix) => Promise<unknown> }) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-[10px] bg-neg-soft px-3 py-2 text-[12px] leading-5 text-ink">
      <span className="min-w-0 flex-[1_1_12rem]"><FaText text={stuck.reason_fa} /></span>
      {stuck.fix ? <FixButton fix={stuck.fix} company={company} run={run} variant="secondary" /> : null}
    </div>
  );
}

/** A small titled block inside a card. */
export function Block({ title, children, action, className }: { title: ReactNode; children: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <section className={cx('flex flex-col gap-2', className)}>
      <div className="flex items-center gap-2"><h3 className="flex-1 text-[13px] font-semibold text-sec">{title}</h3>{action}</div>
      {children}
    </section>
  );
}
