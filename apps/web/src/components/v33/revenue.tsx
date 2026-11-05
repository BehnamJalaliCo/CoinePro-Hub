'use client';

// ⟨1.15⟩ Contract §33.3: `by_source` on the revenue summary — per company, the referral commission (§19.1) and the customers' payments
// (§33.2) side by side, so the holding sees where its money comes from. In-app purchases carry no amount: they are counted, not summed.

import { HBars } from '@/components/charts/charts';
import { CompanyMark } from '@/components/brand/marks';
import { Card, SectionTitle } from '@/components/ui/primitives';
import { fig } from '@/components/v29/text';
import { useCompanies } from '@/lib/api/hooks';
import { dec0, useRevenueBySource } from '@/lib/api/v33';
import { usdt } from './bits';

export function BySourceCard({ period, company }: { period: string; company: string | null }) {
  const q = useRevenueBySource(period, company);
  const { data: companies } = useCompanies();
  const rows = q.data;
  if (!rows?.length) return null; // the hub has not added `by_source` yet: nothing new shows
  const affiliate = rows.reduce((a, r) => a + dec0(r.affiliate_usdt), 0);
  const payments = rows.reduce((a, r) => a + dec0(r.payments_usdt), 0);
  const store = rows.reduce((a, r) => a + (r.store_payments ?? 0), 0);
  const total = affiliate + payments;
  const share = (v: number) => (total ? (v / total) * 100 : 0);
  const name = (c: string) => companies?.find((x) => x.code === c)?.name_fa ?? c;
  return (
    <Card as="section" className="flex flex-col gap-3 p-5" aria-label="درآمد به تفکیک منبع">
      <SectionTitle title="از کجا میاید" note={<>جمع <span className="fig">{usdt(total)}</span></>} />
      <HBars rows={[
        { key: 'affiliate', label: 'کمیسیون رفرال', value: affiliate, fmt: `${usdt(affiliate)} · ${fig(share(affiliate))}%`, color: 'var(--hq-gold-bright)' },
        { key: 'payments', label: 'پرداخت مشتریان', value: payments, fmt: `${usdt(payments)} · ${fig(share(payments))}%`, color: 'var(--hq-lapis, #5B8DEF)' },
      ]} />
      {rows.length > 1 ? (
        <ul className="flex flex-col text-[13px]" aria-label="به تفکیک شرکت">
          {[...rows].sort((a, b) => dec0(b.total_usdt) - dec0(a.total_usdt)).map((r) => (
            <li key={r.company} className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-div py-2 first:border-0">
              <span className="flex min-w-0 flex-[1_1_9rem] items-center gap-1.5 font-semibold"><CompanyMark code={r.company} height={11} mono />{name(r.company)}</span>
              <span className="text-[12px] text-sec">رفرال <span className="fig text-ink">{usdt(r.affiliate_usdt)}</span></span>
              <span className="text-[12px] text-sec">مشتریان <span className="fig text-ink">{usdt(r.payments_usdt)}</span></span>
              <span className="fig font-semibold">{usdt(r.total_usdt)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {store ? <p className="text-[12px] text-muted"><span className="fig">{fig(store)}</span> خرید درون‌برنامه هم بود که مبلغش به ستاد نمیرسد؛ شمرده شده، جمع نشده.</p> : null}
    </Card>
  );
}
