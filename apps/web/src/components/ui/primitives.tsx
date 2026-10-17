'use client';

import { type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import type { IconName } from '@/generated/icons';
import { cx } from '@/lib/format';
import { Button } from './button';

const OCT = 'polygon(30% 0, 70% 0, 100% 30%, 100% 70%, 70% 100%, 30% 100%, 0 70%, 0 30%)';

export function Card({ children, className, as: As = 'div', ...rest }: { children: ReactNode; className?: string; as?: 'div' | 'section' | 'article' } & React.HTMLAttributes<HTMLElement>) {
  return <As className={cx('rounded-[16px] bg-card', className)} {...rest}>{children}</As>;
}

export function SectionTitle({ title, note, action, className }: { title: ReactNode; note?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cx('flex items-end gap-3', className)}>
      <div className="flex min-w-0 flex-1 flex-col">
        <h2 className="text-h3 font-semibold text-ink">{title}</h2>
        {note ? <p className="text-caption text-muted">{note}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({ eyebrow, title, actions, children }: { eyebrow?: ReactNode; title: ReactNode; actions?: ReactNode; children?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end gap-x-4 gap-y-3">
      <div className="flex min-w-0 flex-1 flex-col">
        {eyebrow ? <span className="text-caption text-muted">{eyebrow}</span> : null}
        <h1 className="text-h1 font-semibold text-ink">{title}</h1>
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      {children ? <div className="w-full">{children}</div> : null}
    </header>
  );
}

type Tone = 'neutral' | 'gold' | 'pos' | 'neg' | 'warn' | 'lapis' | 'learn' | 'silver';
const TONE: Record<Tone, string> = {
  neutral: 'bg-tile text-sec',
  gold: 'bg-gold-soft text-gold-ink',
  pos: 'bg-pos-soft text-pos',
  neg: 'bg-neg-soft text-neg',
  warn: 'bg-warn-soft text-warn',
  lapis: 'bg-lapis-soft text-lapis',
  learn: 'bg-learn-soft text-learn',
  silver: 'bg-[var(--hq-silver-soft)] text-silver-ink',
};

/** Status pill: colour is never alone — always a dot or icon plus words. */
export function Pill({ tone = 'neutral', icon, dot, live, children, className }: { tone?: Tone; icon?: IconName; dot?: boolean; live?: boolean; children: ReactNode; className?: string }) {
  return (
    <span className={cx('inline-flex h-6 flex-none items-center gap-1.5 rounded-full px-2.5 text-[12px] font-semibold', TONE[tone], className)}>
      {icon ? <Icon name={icon} size={14} /> : null}
      {dot || live ? <span className="size-1.5 rounded-full bg-current" style={live ? { animation: 'hq-live 1.4s infinite' } : undefined} /> : null}
      {children}
    </span>
  );
}

export function FilterChip({ selected, onClick, children, count }: { selected?: boolean; onClick?: () => void; children: ReactNode; count?: number }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cx(
        'inline-flex h-8 flex-none items-center gap-1.5 rounded-full px-3 text-[13px] transition-colors duration-[120ms]',
        selected ? 'tahrir bg-gold-soft font-semibold text-gold-ink' : 'border border-strong text-sec hover:bg-hover hover:text-ink',
      )}
    >
      {children}
      {count != null ? <span className="text-[12px] opacity-80">{count}</span> : null}
    </button>
  );
}

export function Segmented<T extends string>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: Array<{ value: T; label: ReactNode; icon?: IconName }>; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex rounded-[10px] bg-tile p-1">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={cx('flex h-8 flex-1 items-center justify-center gap-1.5 rounded-[8px] px-3 text-[13px] transition-colors', on ? 'bg-raised font-semibold text-ink shadow-[inset_0_-2px_0_var(--hq-gold-ink)]' : 'text-sec hover:text-ink')}
          >
            {o.icon ? <Icon name={o.icon} size={16} /> : null}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        'flex h-[26px] w-11 flex-none items-center rounded-full px-[3px] transition-colors duration-200',
        disabled ? 'border border-div bg-disabled-fill' : checked ? 'justify-end bg-gold' : 'justify-start border-[1.5px] border-[var(--hq-switch-off)] bg-tile',
      )}
    >
      <span className={cx('rounded-full transition-all duration-200', disabled ? 'size-[18px] bg-disabled' : checked ? 'size-5 bg-on-gold' : 'size-4 bg-sec')} />
    </button>
  );
}

/** Owner rating 1–10: numbered octagons (D1). A count, so Persian digits. */
export function Rating({ value, onChange, size = 36, label, hover, onHover }: { value: number; onChange?: (n: number) => void; size?: number; label: string; hover?: number | null; onHover?: (n: number | null) => void }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex gap-1.5" onMouseLeave={() => onHover?.(null)}>
      {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => {
        const on = n <= value;
        const hv = hover != null && n <= hover && !on;
        return (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={n === value}
            aria-label={`${n} از ۱۰`}
            disabled={!onChange}
            onClick={() => onChange?.(n)}
            onMouseEnter={() => onHover?.(n)}
            className={cx('flex items-center justify-center transition-colors disabled:cursor-default', on ? 'bg-gold font-bold text-on-gold' : hv ? 'bg-[var(--hq-gold-hover-soft)] font-semibold text-gold-ink' : 'bg-tile text-sec')}
            style={{ width: size, height: size, clipPath: OCT, fontSize: size > 30 ? 13 : 11 }}
          >
            {n}
          </button>
        );
      })}
    </div>
  );
}

export function Bar({ pct, tone = 'silver', height = 6, label }: { pct: number; tone?: 'silver' | 'gold' | 'warn' | 'neg' | 'pos'; height?: number; label?: string }) {
  const col = { silver: 'var(--hq-silver-ink)', gold: 'var(--hq-gold-fill)', warn: 'var(--hq-warning)', neg: 'var(--hq-negative)', pos: 'var(--hq-positive)' }[tone];
  const v = Math.max(0, Math.min(100, pct));
  return (
    <div role="progressbar" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100} aria-label={label} className="overflow-hidden rounded-full bg-tile" style={{ height }}>
      <span className="block h-full rounded-full transition-[width] duration-300" style={{ width: `${v}%`, background: col }} />
    </div>
  );
}

/** Budget meter tone (D2·2): neutral silver below 70%, warn to 90%, negative above. */
export const budgetTone = (pct: number | null | undefined): 'silver' | 'warn' | 'neg' => (pct == null || pct < 70 ? 'silver' : pct < 90 ? 'warn' : 'neg');

export function Skeleton({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return <span aria-hidden className={cx('hq-skeleton block rounded-[8px]', className)} style={style} />;
}

export function Empty({ icon = 'deliverable', title, body, action }: { icon?: IconName; title: ReactNode; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <span className="flex size-14 items-center justify-center rounded-full bg-tile text-muted"><Icon name={icon} size={26} /></span>
      <p className="text-body font-semibold text-ink">{title}</p>
      {body ? <p className="max-w-sm text-caption text-muted">{body}</p> : null}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const fa = (error as { messageFa?: string })?.messageFa ?? 'بارگذاری انجام نشد.';
  const code = (error as { code?: string })?.code;
  return (
    <div role="alert" className="flex flex-col items-center gap-3 px-6 py-10 text-center">
      <span className="flex size-14 items-center justify-center rounded-full bg-neg-soft text-neg"><Icon name="urgent" size={26} /></span>
      <p className="text-body font-semibold text-ink">{fa}</p>
      {code ? <p className="fig text-micro text-muted">{code}</p> : null}
      {onRetry ? <Button variant="secondary" icon="refresh" onClick={onRetry}>دوباره</Button> : null}
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="fig inline-flex h-5 items-center rounded-[5px] border border-strong px-1.5 text-[10px] text-sec">{children}</kbd>;
}

export function StatTile({ label, value, sub, tone }: { label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: 'neg' | 'warn' | 'pos' }) {
  return (
    <div className="flex flex-col gap-1 rounded-[14px] bg-card p-4">
      <span className="text-caption text-muted">{label}</span>
      <span className={cx('text-[24px] font-semibold leading-8', tone === 'neg' ? 'text-neg' : tone === 'warn' ? 'text-warn' : tone === 'pos' ? 'text-pos' : 'text-ink')}>{value}</span>
      {sub ? <span className="text-caption text-sec">{sub}</span> : null}
    </div>
  );
}
