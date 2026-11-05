'use client';

// ⟨1.15⟩ Contract §33: the small pieces the money, sales, journey and persona pages share — a company's page header with its section
// links, form fields, a figure in plain Latin digits, and the impact chip of a decision (measured, or «تخمین» with its basis).

import Link from 'next/link';
import type { ReactNode } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { Pill, Skeleton } from '@/components/ui/primitives';
import { FaText, fig } from '@/components/v29/text';
import { field } from '@/components/v31/kit';
import { useCompanies } from '@/lib/api/hooks';
import { dec, impactOf, type Dec, type Impact } from '@/lib/api/v33';
import { cx } from '@/lib/format';

export const Loading = ({ h = 'h-48' }: { h?: string }) => <Skeleton className={cx(h, 'rounded-[16px]')} />;

/** «1,200 USDT»; a Decimal string of the hub is read as a number first. */
export const usdt = (v: Dec | number | null | undefined, digits = 0) => { const n = dec(v); return n == null ? '—' : `${fig(n, digits)} USDT`; };
export const dollars = (v: Dec | number | null | undefined, digits = 2) => { const n = dec(v); return n == null ? '—' : `$${fig(n, digits)}`; };
export const pctOf = (n: number | null | undefined, digits = 0) => (n == null ? '—' : `${fig(n, digits)}%`);
/** «2026-11»: the month as the hub writes it, in Latin digits. */
export const monthLabel = (m: string) => m.slice(0, 7);
export const dayShort = (d: string) => d.slice(5, 10).replace('-', '/');

export function useCompanyName(code: string) {
  const { data } = useCompanies();
  const c = data?.find((x) => x.code === code);
  return { name: c?.name_fa ?? code, holding: c?.kind === 'holding', known: !!c };
}

const SECTIONS = [
  { seg: 'money', fa: 'پول' }, { seg: 'sales', fa: 'فروش' }, { seg: 'journey', fa: 'سفر شرکت' }, { seg: 'personas', fa: 'مخاطب‌ها' },
] as const;
/** Header of a company's new sections: the company, and links among «پول، فروش، سفر، مخاطب‌ها». */
export function CompanyHead({ code, here, title, note, actions }: { code: string; here: (typeof SECTIONS)[number]['seg']; title: string; note?: ReactNode; actions?: ReactNode }) {
  const { name } = useCompanyName(code);
  return (
    <header className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-x-4 gap-y-3">
        <div className="flex min-w-0 flex-[1_1_16rem] flex-col">
          <span className="flex items-center gap-1.5 text-caption text-muted"><Link href={`/companies/${code}`} className="inline-flex items-center gap-1.5 hover:text-ink"><CompanyMark code={code} height={12} mono />{name}</Link></span>
          <h1 className="text-h1 font-semibold text-ink">{title}</h1>
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      <nav aria-label="بخش‌های شرکت" className="no-scrollbar flex gap-2 overflow-x-auto">
        {SECTIONS.map((s) => (
          <Link key={s.seg} href={`/companies/${code}/${s.seg}`} aria-current={s.seg === here ? 'page' : undefined}
            className={cx('inline-flex h-9 flex-none items-center rounded-full px-4 text-[13px] font-semibold', s.seg === here ? 'bg-gold text-on-gold' : 'bg-tile text-sec hover:bg-hover')}>{s.fa}</Link>
        ))}
      </nav>
      {note ? <p className="max-w-3xl text-[13px] leading-6 text-sec">{note}</p> : null}
    </header>
  );
}

export const Txt = ({ label, value, set, ltr, w, placeholder, type }: { label: string; value: string; set: (v: string) => void; ltr?: boolean; w?: string; placeholder?: string; type?: string }) => (
  <label className={cx('flex min-w-0 flex-col gap-1.5', w)}><span className="text-[12px] text-sec">{label}</span>
    <input type={type} value={value} placeholder={placeholder} onChange={(e) => set(e.target.value)} dir={ltr ? 'ltr' : 'auto'} aria-label={label} className={cx(field, 'h-10', ltr && 'text-left')} /></label>
);
export const Area = ({ label, value, set, rows = 3 }: { label: string; value: string; set: (v: string) => void; rows?: number }) => (
  <label className="flex min-w-0 flex-col gap-1.5"><span className="text-[12px] text-sec">{label}</span>
    <textarea value={value} rows={rows} onChange={(e) => set(e.target.value)} dir="auto" aria-label={label} className={cx(field, 'py-2.5 leading-7')} /></label>
);

/** The money of an impact in words: «+1,200 USDT درآمد، +40 دلار هزینه». */
export function impactParts(i: Impact) {
  const parts: string[] = [];
  if (i.revenue_usdt != null) parts.push(`${i.revenue_usdt >= 0 ? '+' : '−'}${fig(Math.abs(i.revenue_usdt))} USDT درآمد`);
  if (i.cost_usd != null) parts.push(`${i.cost_usd > 0 ? '+' : i.cost_usd < 0 ? '−' : ''}${fig(Math.abs(i.cost_usd))} دلار هزینه`);
  return parts.join('، ') || 'اثر پولی ندارد';
}
/** Money impact of a decision: measured by code, or an estimate (always labelled «تخمین»), with its basis in the title. */
export function ImpactChip({ d }: { d: unknown }) {
  const i = impactOf(d);
  if (!i) return null;
  const est = i.kind === 'estimate';
  return (
    <span title={`${i.basis_fa} (در ${fig(i.horizon_days)} روز)`} aria-label={`اثر پولی ${est ? 'تخمینی' : 'اندازه‌گیری‌شده'}: ${impactParts(i)}`}>
      <Pill tone={est ? 'warn' : 'pos'} icon={est ? 'time' : 'chart'} className="max-w-full">{est ? <span>تخمین</span> : null}<span className="fig truncate">{impactParts(i)}</span></Pill>
    </span>
  );
}
/** The block under a decision: the chip, the horizon and its basis in words. */
export function ImpactBlock({ d }: { d: unknown }) {
  const i = impactOf(d);
  if (!i) return null;
  return (
    <section className="flex flex-col gap-1.5" aria-label="اثر پولی">
      <h3 className="text-[12px] font-semibold text-gold-ink">اثر پولی</h3>
      <div className="flex flex-wrap items-center gap-2"><ImpactChip d={d} /><span className="text-[12px] text-muted">در <span className="fig">{fig(i.horizon_days)}</span> روز</span></div>
      <p className="text-[13px] leading-6 text-sec"><FaText text={i.basis_fa} />{i.kind === 'estimate' ? ' این عدد حدس است، نه اندازه‌گیری.' : ''}</p>
    </section>
  );
}
