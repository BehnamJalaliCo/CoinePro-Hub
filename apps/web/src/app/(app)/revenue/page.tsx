'use client';

import { useMemo, useState } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { LinesChart } from '@/components/charts/charts';
import { Card, ErrorState, PageHeader, SectionTitle, Segmented, Skeleton, StatTile } from '@/components/ui/primitives';
import { AccountsCard, AlertsCard, FunnelCard, RescueCard } from '@/components/v16/revenue';
import { compact, money } from '@/components/v16/bits';
import { useCompanies } from '@/lib/api/hooks';
import { useRevenueDays, useRevenueSummary, type RevenuePeriod } from '@/lib/api/v16';
import { companyColor } from '@/lib/company';
import { useScope } from '@/lib/scope';
import { cx, usd } from '@/lib/format';

const PERIOD_FA: Record<RevenuePeriod, string> = { day: 'دیروز', week: '۷ روز', month: '۳۰ روز' };
const dayLabel = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { day: 'numeric', month: 'short', timeZone: 'Asia/Tehran' });
const shift = (day: string, n: number) => new Date(Date.parse(`${day}T12:00:00Z`) + n * 86_400_000).toISOString().slice(0, 10);

/** درآمد (contract §19.1–§19.2): referral commission every day after the exchange settles, against what the tokens cost; the funnel and
 *  referral rescue. USDT is read as dollars (≈), which the page says. */
export default function RevenuePage() {
  const { company: scope } = useScope();
  const { data: companies } = useCompanies();
  // The holding earns nothing itself: its scope reads as the whole holding.
  const company = companies?.find((c) => c.code === scope)?.kind === 'holding' ? null : scope;
  const [period, setPeriod] = useState<RevenuePeriod>('month');
  const sum = useRevenueSummary(period, company);
  const s = sum.data;
  const to = s?.to ?? new Date(new Date().getTime() - 86_400_000).toISOString().slice(0, 10);
  const from = shift(to, -29);
  const days = useRevenueDays({ from, to, company });

  const keys = useMemo(() => Array.from({ length: 30 }, (_, i) => shift(from, i)), [from]);
  const lines = useMemo(() => {
    const cos = [...new Set([...(s?.by_company ?? []).map((c) => c.company), ...(days.data ?? []).map((d) => d.company)])];
    return cos.map((c) => {
      const mine = (days.data ?? []).filter((d) => d.company === c);
      return {
        key: c, color: companyColor(companies, c),
        label: <span className="flex items-center gap-1.5"><CompanyMark code={c} height={11} mono />{companies?.find((x) => x.code === c)?.name_fa ?? c}</span>,
        values: keys.map((k) => { const xs = mine.filter((d) => d.day === k); return xs.length ? xs.reduce((a, d) => a + Number(d.commission_usdt), 0) : null; }),
      };
    });
  }, [s, days.data, keys, companies]);

  const total = s ? Number(s.total_usdt) : null;
  const prev = s?.prev_total_usdt != null ? Number(s.prev_total_usdt) : null;
  const change = total != null && prev ? ((total - prev) / prev) * 100 : null;
  const cost = s ? s.by_company.reduce((a, c) => a + Number(c.token_cost_usd), 0) : null;
  const net = s ? s.by_company.reduce((a, c) => a + Number(c.net_usd), 0) : null;
  const invitees = s && days.data ? days.data.filter((d) => d.day >= s.from && d.day <= s.to).reduce((a, d) => a + d.new_invitees, 0) : null;
  const incomplete = (days.data ?? []).filter((d) => !d.complete).length;

  return (
    <>
      <PageHeader eyebrow="کمیسیون رفرال صرافی‌ها، هر روز بعد از تسویه" title="درآمد"
        actions={<div className="w-56"><Segmented label="دوره" value={period} onChange={setPeriod} options={[{ value: 'day', label: 'روز' }, { value: 'week', label: 'هفته' }, { value: 'month', label: 'ماه' }]} /></div>}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">درآمد به USDT است و این‌جا هم‌ارز دلار خوانده میشود (USDT ≈ USD). هزینه‌ی توکن از خزانه میاید، نه از گزارش ایجنت. pull کار کد است و کلید صرافی هرگز از egress بیرون نمیرود.</p>
      </PageHeader>
      {sum.error ? <ErrorState error={sum.error} onRetry={() => sum.refetch()} /> : null}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {!s ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[104px] rounded-[14px]" />) : (
          <>
            <StatTile label={`درآمد ${PERIOD_FA[period]}`} value={<span className="fig">{money(s.total_usdt)}<span className="text-[13px] font-normal text-sec"> USDT</span></span>}
              sub={change == null ? 'دوره‌ی قبل داده ندارد' : <span><span className={cx('fig font-semibold', change >= 0 ? 'text-pos' : 'text-neg')}>{change >= 0 ? '+' : '−'}{Math.abs(change).toFixed(1)}%</span> نسبت به دوره‌ی قبل</span>} />
            <StatTile label="هزینه‌ی توکن" value={<span className="fig">{usd(cost)}</span>} sub="از خزانه‌ی توکن" />
            <StatTile label="خالص" value={<span className="fig">{usd(net)}</span>} tone={net != null && net < 0 ? 'neg' : undefined} sub="درآمد منهای توکن" />
            <StatTile label="دعوت‌شده‌ی تازه" value={invitees == null ? '—' : <span className="fig">{invitees}</span>} sub="از داده‌ی افیلیت" />
          </>
        )}
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="flex flex-col gap-3 p-5">
            <SectionTitle title="روند ۳۰ روز" note={`کمیسیون روزانه‌ی هر شرکت به USDT؛ روز بی‌داده خالی میماند${incomplete ? `، ${incomplete} روز هنوز ناقص` : ''}`} />
            {days.error ? <ErrorState error={days.error} onRetry={() => days.refetch()} /> : !days.data ? <Skeleton className="h-60" /> : (
              <>
                <LinesChart label="کمیسیون روزانه‌ی هر شرکت" days={keys.map((k) => ({ key: k, label: dayLabel.format(new Date(`${k}T12:00:00Z`)) }))} lines={lines} fmt={(v) => money(v)} tick={compact} />
                <details className="text-[12px]">
                  <summary className="cursor-pointer text-sec">جدول روزها</summary>
                  <div className="mt-2 max-h-72 overflow-auto">
                    <table className="w-full border-collapse">
                      <thead><tr className="text-right text-[11px] text-muted"><th className="px-2 py-1 font-semibold">روز</th>{lines.map((l) => <th key={l.key} className="px-2 py-1 font-semibold">{l.label}</th>)}</tr></thead>
                      <tbody>{[...keys].reverse().map((k) => { const i = keys.indexOf(k); return <tr key={k} className="border-t border-div"><td className="px-2 py-1 text-sec">{dayLabel.format(new Date(`${k}T12:00:00Z`))}</td>{lines.map((l) => <td key={l.key} className="fig px-2 py-1 text-ink">{l.values[i] != null ? money(l.values[i]) : '—'}</td>)}</tr>; })}</tbody>
                    </table>
                  </div>
                </details>
              </>
            )}
          </Card>
          <Card className="flex flex-col gap-2 p-5">
            <SectionTitle title="شرکت‌ها" note={`${PERIOD_FA[period]}؛ رنگ هر شرکت ثابت است، نه بر اساس رتبه`} />
            <div className="hidden grid-cols-[minmax(0,1.3fr)_repeat(3,minmax(0,1fr))_minmax(0,1.1fr)] gap-3 px-1 text-[11px] text-muted sm:grid"><span>شرکت</span><span>درآمد (USDT)</span><span>هزینه‌ی توکن</span><span>خالص</span><span>سهم</span></div>
            {!s ? <Skeleton className="h-32" /> : (
              <ul className="flex flex-col">
                {s.by_company.map((c) => (
                  <li key={c.company} className="grid grid-cols-3 gap-x-3 gap-y-1.5 border-t border-div px-1 py-3 sm:grid-cols-[minmax(0,1.3fr)_repeat(3,minmax(0,1fr))_minmax(0,1.1fr)] sm:items-center">
                    <span className="col-span-3 flex items-center gap-2 text-[13px] font-semibold sm:col-span-1"><CompanyMark code={c.company} height={14} mono />{companies?.find((x) => x.code === c.company)?.name_fa ?? c.company}</span>
                    <span className="flex flex-col"><span className="text-[10px] text-muted sm:hidden">درآمد (USDT)</span><span className="fig text-[13px] font-semibold">{money(c.usdt)}</span></span>
                    <span className="flex flex-col"><span className="text-[10px] text-muted sm:hidden">هزینه‌ی توکن</span><span className="fig text-[13px] text-sec">{usd(c.token_cost_usd)}</span></span>
                    <span className="flex flex-col"><span className="text-[10px] text-muted sm:hidden">خالص</span><span className={cx('fig text-[13px] font-semibold', Number(c.net_usd) < 0 ? 'text-neg' : 'text-ink')}>{usd(c.net_usd)}</span></span>
                    <span className="col-span-3 flex items-center gap-2 sm:col-span-1">
                      <span className="h-2 flex-1 rounded-full bg-tile"><span className="block h-full rounded-l-[4px] rounded-r-full" style={{ width: `${Math.max(1.5, c.share * 100)}%`, background: companyColor(companies, c.company) }} /></span>
                      <span className="fig w-10 text-[12px] text-sec">{Math.round(c.share * 100)}%</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <FunnelCard initial={company} />
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <AlertsCard alerts={s?.alerts} />
          <AccountsCard />
          <RescueCard company={company} />
        </div>
      </div>
    </>
  );
}
