'use client';

import { type ComponentProps } from 'react';
import { Icon } from '@/components/icon';
import { Pill } from '@/components/ui/primitives';
import type { FoundingState, Severity } from '@/lib/api/v14';
import { cx } from '@/lib/format';

type Tone = ComponentProps<typeof Pill>['tone'];

export const SEVERITY: Record<Severity, { fa: string; tone: Tone }> = {
  critical: { fa: 'بحرانی', tone: 'neg' }, high: { fa: 'بالا', tone: 'neg' }, medium: { fa: 'متوسط', tone: 'warn' }, low: { fa: 'کم', tone: 'neutral' }, info: { fa: 'اطلاع', tone: 'lapis' },
};
export function SeverityPill({ s }: { s: Severity }) {
  const v = SEVERITY[s];
  return <Pill tone={v.tone} dot className={s === 'critical' ? 'ring-1 ring-[var(--hq-neg-line)]' : undefined}>{v.fa}</Pill>;
}

/** 0–5 stars, half steps; the value is also written out (stars are never read by colour or shape alone). */
export function Stars({ value, size = 16, label = true }: { value: number; size?: number; label?: boolean }) {
  const v = Math.max(0, Math.min(5, value));
  return (
    <span className="inline-flex items-center gap-1.5" aria-label={`${v} از ۵ ستاره`}>
      <span className="relative inline-flex" aria-hidden>
        <span className="inline-flex text-strong">{Array.from({ length: 5 }, (_, i) => <Icon key={i} name="star" size={size} />)}</span>
        <span className="absolute inset-y-0 start-0 inline-flex overflow-hidden text-gold-ink" style={{ width: `${(v / 5) * 100}%` }}>
          {Array.from({ length: 5 }, (_, i) => <Icon key={i} name="star" size={size} active />)}
        </span>
      </span>
      {label ? <span className="fig text-[12px] text-sec">{v.toFixed(1)}</span> : null}
    </span>
  );
}

/** A small trend line: one series, no axes, the last point marked. Recessive by design; the number beside it carries the value. */
export function Spark({ values, width = 72, height = 22, max, min }: { values: number[]; width?: number; height?: number; max?: number; min?: number }) {
  if (values.length < 2) return null;
  const hi = max ?? Math.max(...values);
  const lo = min ?? Math.min(...values);
  const span = hi - lo || 1;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * (width - 4) + 2, height - 2 - ((v - lo) / span) * (height - 4)] as const);
  const up = values.at(-1)! >= values[0]!;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden className="flex-none" style={{ direction: 'ltr' }}>
      <polyline points={pts.map((p) => p.join(',')).join(' ')} fill="none" stroke={up ? 'var(--hq-positive)' : 'var(--hq-negative)'} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={pts.at(-1)![0]} cy={pts.at(-1)![1]} r={3} fill={up ? 'var(--hq-positive)' : 'var(--hq-negative)'} stroke="var(--hq-surface-card)" strokeWidth={1.5} />
    </svg>
  );
}

/** A 0–100 score as a number and a thin bar; tone follows the bands used across the holding. */
export function Score({ value, className }: { value: number; className?: string }) {
  const tone = value >= 80 ? 'bg-pos' : value >= 65 ? 'bg-warn' : 'bg-neg';
  return (
    <span className={cx('inline-flex min-w-0 items-center gap-2', className)}>
      <span className="fig w-8 text-[13px] font-semibold text-ink">{Math.round(value)}</span>
      <span className="h-1.5 min-w-[48px] flex-1 overflow-hidden rounded-full bg-tile" dir="ltr"><span className={cx('block h-full rounded-full', tone)} style={{ width: `${value}%` }} /></span>
    </span>
  );
}

const NUMBER = /((?:[≥≤<>~±+−-]\s?)?\d[\d.,/:]*(?:\s?[%٪])?)/;

/** Mixed text such as a KPI target ("500 در 90 روز", "≥ 80%"): every number a Latin figure, the words in their right-to-left order. */
export function Figs({ text }: { text: string }) {
  return <>{text.split(NUMBER).map((p, i) => (i % 2 === 1 ? <span key={i} className="fig">{p}</span> : p))}</>;
}

export const AREA_FA: Record<string, string> = {
  truth: 'حقیقت', authority: 'اختیار', money: 'پول و توکن', safety: 'ایمنی', quality: 'کیفیت', delivery: 'تحویل', security: 'امنیت', data: 'داده', people: 'آدم‌ها', product: 'محصول', owner: 'دستور مالک',
};
export const METHOD_FA: Record<string, string> = { rule: 'قاعده', reconcile: 'تطبیق', sample: 'نمونه‌برداری', llm: 'تحلیل', blind_test: 'آزمون کور', mystery: 'مشتری ناشناس', drill: 'مانور' };

/** "FREQ=DAILY;BYHOUR=9" → "هر روز ۰۹:۰۰" (owner TZ), enough for a list. */
export function rruleFa(r: string): string {
  const k = Object.fromEntries(r.split(';').map((x) => x.split('=') as [string, string]));
  const hm = k.BYHOUR ? ` ${k.BYHOUR.padStart(2, '0')}:${(k.BYMINUTE ?? '0').padStart(2, '0')}` : '';
  const days: Record<string, string> = { SA: 'شنبه', SU: 'یکشنبه', MO: 'دوشنبه', TU: 'سه‌شنبه', WE: 'چهارشنبه', TH: 'پنجشنبه', FR: 'جمعه' };
  if (k.FREQ === 'HOURLY') return 'هر ساعت';
  if (k.FREQ === 'DAILY') return `هر روز${hm}`;
  if (k.FREQ === 'WEEKLY') return `${days[k.BYDAY ?? ''] ?? 'هر هفته'}ها${hm}`;
  if (k.FREQ === 'MONTHLY') return `ماهانه، روز ${k.BYMONTHDAY ?? '1'}${hm}`;
  return r;
}

export const FOUNDING_STATE: Record<FoundingState, { fa: string; tone: 'neutral' | 'lapis' | 'gold' | 'pos' | 'neg' | 'warn'; live?: boolean }> = {
  auditing: { fa: 'در حال ممیزی', tone: 'lapis', live: true }, proposed: { fa: 'پیشنهاد، منتظر مُهر', tone: 'gold' }, sealed: { fa: 'مُهر شد', tone: 'pos' },
  provisioning: { fa: 'ساخت سرور', tone: 'lapis', live: true }, ready_for_login: { fa: 'آماده‌ی ورود تو', tone: 'gold' }, active: { fa: 'فعال', tone: 'pos' }, cancelled: { fa: 'لغو شد', tone: 'warn' },
};
