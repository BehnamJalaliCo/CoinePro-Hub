'use client';

import Link from 'next/link';
import { useEffect, useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import type { IconName } from '@/generated/icons';
import { cx, jDate, jWeekday, OWNER_TZ } from '@/lib/format';

// Shared bits of the 0.3.0–0.6.0 pages: the undo bar, days in the owner's zone, the consequence list of a confirmation, a ref button.

/** The day of an instant in the owner's zone, as `YYYY-MM-DD`. */
export const ownerDay = (iso: string | Date) => new Intl.DateTimeFormat('en-CA', { timeZone: OWNER_TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(iso));
const addDays = (day: string, n: number) => { const d = new Date(`${day}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };

/** A day's header: «امروز، ۲۵ مهر», «دیروز، ۲۴ مهر», otherwise the weekday and date (the year when it is another year). */
export function dayFa(day: string): string {
  const today = ownerDay(new Date());
  const iso = `${day}T08:30:00Z`;
  if (day === today) return `امروز، ${jDate(iso)}`;
  if (day === addDays(today, -1)) return `دیروز، ${jDate(iso)}`;
  const year = (d: string) => new Intl.DateTimeFormat('en-u-ca-persian', { timeZone: OWNER_TZ, year: 'numeric' }).format(new Date(d));
  return year(iso) === year(new Date().toISOString()) ? jWeekday(iso) : `${jWeekday(iso)} ${jDate(iso, true).split(' ').pop()}`;
}

/** The date ranges of a filter, in the owner's zone; "this month" is the Jalali month. */
export const RANGES: Array<[string, string]> = [['all', 'همه‌ی زمان‌ها'], ['today', 'امروز'], ['yesterday', 'دیروز'], ['7d', '۷ روز اخیر'], ['30d', '۳۰ روز اخیر'], ['month', 'این ماه']];
export function span(range: string): { from: string | null; to: string | null } {
  const today = ownerDay(new Date());
  switch (range) {
    case 'today': return { from: today, to: today };
    case 'yesterday': return { from: addDays(today, -1), to: addDays(today, -1) };
    case '7d': return { from: addDays(today, -6), to: today };
    case '30d': return { from: addDays(today, -29), to: today };
    case 'month': {
      const dom = Number(new Intl.DateTimeFormat('en-u-ca-persian-nu-latn', { timeZone: OWNER_TZ, day: 'numeric' }).format(new Date()));
      return { from: addDays(today, -(dom - 1)), to: today };
    }
    default: return { from: null, to: null };
  }
}

/** An undo the owner has a few seconds for. */
export type Undo = { id: number; text: ReactNode; run: () => void };

/** "Marked · برگردان" for five seconds at the bottom of the page. */
export function UndoBar({ undo, onDone }: { undo: Undo | null; onDone: (id: number) => void }) {
  useEffect(() => {
    if (!undo) return;
    const t = setTimeout(() => onDone(undo.id), 5_000);
    return () => clearTimeout(t);
  }, [undo, onDone]);
  if (!undo) return null;
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-24 z-[55] flex justify-center px-4 md:bottom-8">
      <div key={undo.id} className="hq-rise pointer-events-auto flex min-h-12 w-full max-w-[520px] items-center gap-3 rounded-[14px] bg-raised py-1.5 pe-1.5 ps-4 shadow-[0_12px_32px_rgba(0,0,0,.35)]">
        <span className="text-pos"><Icon name="seal" size={18} active /></span>
        <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{undo.text}</span>
        <Button variant="text" size="sm" icon="back" onClick={() => { undo.run(); onDone(undo.id); }}>برگردان</Button>
      </div>
    </div>
  );
}

/** What will happen, line by line, with an icon each: a confirmation says exactly what the owner is about to do. */
export function Consequences({ lines, tone }: { lines: Array<[IconName, ReactNode]>; tone: 'neg' | 'pos' | 'warn' }) {
  return (
    <ul className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
      {lines.map(([icon, text], i) => (
        <li key={i} className="flex gap-2.5 text-[13px] leading-6 text-ink">
          <span className={cx('mt-1 flex-none', tone === 'neg' ? 'text-neg' : tone === 'pos' ? 'text-pos' : 'text-warn')}><Icon name={icon} size={16} /></span>
          <span>{text}</span>
        </li>
      ))}
    </ul>
  );
}

/** A gold-ink action that names a ref in Latin figures. */
export function RefButton({ label, refId, icon, href, className }: { label: string; refId: string; icon: IconName; href: string; className?: string }) {
  return (
    <Link href={href} className={cx('flex min-h-10 items-center gap-2 rounded-[10px] bg-gold-soft px-3 text-[13px] font-semibold text-gold-ink transition-colors hover:bg-[var(--hq-gold-hover-soft)]', className)}>
      <Icon name={icon} size={18} />
      <span>{label} <span className="fig font-bold">{refId}</span></span>
      <span className="flex-1" />
      <Icon name="next" size={14} mirror />
    </Link>
  );
}

/** A value that changes on its own clock (relative times on screen). */
export function useTick(ms = 30_000): number {
  const [n, setN] = useState(0);
  useEffect(() => { const t = setInterval(() => setN((x) => x + 1), ms); return () => clearInterval(t); }, [ms]);
  return n;
}

export const inputCls = 'h-11 w-full rounded-[10px] border border-strong bg-tile px-3 text-[14px] text-ink outline-none transition-colors focus:border-gold-ink';
