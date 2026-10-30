'use client';

import { Icon } from '@/components/icon';
import { PRIORITIES, priority, type PriorityTone } from '@/lib/priority';
import { cx } from '@/lib/format';

// Priorities in words (0.4.0; the Android app's ui/work/Priority.kt): the Persian name large, the code small and Latin beside it, and the
// chosen one's meaning in one line, so the owner never has to know what "P2" is.

const SOFT: Record<PriorityTone, string> = { neg: 'bg-neg-soft', warn: 'bg-warn-soft', lapis: 'bg-lapis-soft', neutral: 'bg-tile', silver: 'bg-[var(--hq-silver-soft)]' };
const INK: Record<PriorityTone, string> = { neg: 'text-neg', warn: 'text-warn', lapis: 'text-lapis', neutral: 'text-sec', silver: 'text-silver-ink' };
const LINE: Record<PriorityTone, string> = { neg: 'border-[var(--hq-negative)]/55', warn: 'border-[var(--hq-warning)]/55', lapis: 'border-[var(--hq-lapis)]/55', neutral: 'border-strong', silver: 'border-[var(--hq-silver-ink)]/55' };

/** Choosing a priority: five labelled choices and the chosen one's meaning in one line beneath. */
export function PriorityPicker({ value, onChange }: { value: string; onChange: (code: string) => void }) {
  const chosen = priority(value);
  return (
    <div className="flex flex-col gap-2">
      <div role="radiogroup" aria-label="اولویت" className="flex gap-1 rounded-[10px] bg-tile p-1">
        {PRIORITIES.map((p) => {
          const on = p.code === value;
          return (
            <button key={p.code} type="button" role="radio" aria-checked={on} aria-label={`${p.fa}، ${p.code}: ${p.line}`} onClick={() => onChange(p.code)}
              className={cx('flex min-h-[52px] flex-1 flex-col items-center justify-center gap-0.5 rounded-[8px] border px-1 transition-colors duration-200',
                on ? cx(p.tone === 'neutral' ? 'bg-raised' : SOFT[p.tone], LINE[p.tone]) : 'border-transparent hover:bg-hover')}>
              <span className={cx('truncate text-[12.5px] leading-[18px]', on ? cx('font-bold', p.tone === 'neutral' ? 'text-ink' : INK[p.tone]) : 'font-medium text-sec')}>{p.fa}</span>
              <span className={cx('fig text-[10px] leading-[13px]', on ? INK[p.tone] : 'text-muted')}>{p.code}</span>
            </button>
          );
        })}
      </div>
      {/* The meaning of the chosen one, under the control; it changes with a quick cross-fade. */}
      <div key={chosen.code} className={cx('hq-rise flex items-start gap-2 rounded-[8px] px-2.5 py-2', SOFT[chosen.tone])}>
        <span className={cx('mt-0.5', chosen.tone === 'neutral' ? 'text-ink' : INK[chosen.tone])}><Icon name={chosen.icon} size={16} /></span>
        <span className="text-[12px] leading-5 text-ink"><b className="font-bold">{chosen.fa}</b> (<span className="fig">{chosen.code}</span>): {chosen.line}</span>
      </div>
    </div>
  );
}

/** A priority shown: the name, and the code small and Latin; a quiet pill for «عادی», the tone for the others. Its meaning on hover. */
export function PriorityTag({ code, compact }: { code: string | null | undefined; compact?: boolean }) {
  const p = priority(code);
  return (
    <span title={p.line} aria-label={`اولویت ${p.fa}`} className={cx('inline-flex flex-none items-center gap-1.5 rounded-full font-semibold', SOFT[p.tone], INK[p.tone], compact ? 'h-5 px-2 text-[11px]' : 'h-6 px-2.5 text-[12px]')}>
      {!compact ? <Icon name={p.icon} size={13} /> : null}
      {p.fa}{p.fa !== p.code ? <span className="fig opacity-70">{p.code}</span> : null}
    </span>
  );
}

/** A list row's small priority mark: the tone's dot for the urgent ones, nothing for the rest. */
export function PriorityDot({ code }: { code: string | null | undefined }) {
  const p = priority(code);
  if (p.tone === 'neutral' || p.tone === 'silver') return null;
  return <span title={p.fa} className={cx('size-1.5 flex-none rounded-full', p.tone === 'neg' ? 'bg-neg' : p.tone === 'warn' ? 'bg-warn' : 'bg-lapis')} />;
}
