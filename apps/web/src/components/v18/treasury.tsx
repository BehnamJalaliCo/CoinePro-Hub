'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { Card, ErrorState, Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import { CoMark, Trend } from '@/components/v17/bits';
import { useWasteRange, useRoi, type RoiBy, type WasteDay } from '@/lib/api/v18';
import { cx, jDate, tokens, usd } from '@/lib/format';
import { DEPT_FA } from '@/lib/labels';
import { WASTE, pct01 } from './bits';

/** The owner's day (Asia/Tehran) n days ago, YYYY-MM-DD. */
const tehDay = (n: number) => new Date(Date.now() + 3.5 * 3_600_000 - n * 86_400_000).toISOString().slice(0, 10);
const dayFa = (d: string) => jDate(`${d}T08:00:00Z`);

// ------------------------------------------------------------------- waste (§21.7) --
/** The daily waste report: computed by code at 07:45 for the day before; never a prompt or a response, only the ledger and the runs. */
export function WasteCard({ company }: { company: string | null }) {
  const [from, to] = useMemo(() => [tehDay(14), tehDay(1)], []);
  const q = useWasteRange(from, to, company);
  const days = q.data ?? [];
  const [pick, setPick] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const d: WasteDay | undefined = days.find((x) => x.day === pick) ?? days.at(-1);
  const max = Math.max(0.2, ...days.map((x) => x.share));
  const items = [...(d?.items ?? [])].sort((a, b) => Number(b.usd) - Number(a.usd));
  const top = items[0] ? Number(items[0].usd) : 1;
  return (
    <Card className="flex flex-col gap-4 p-5">
      <SectionTitle title="هدررفت روزانه" note="با کد، از دفتر خزانه و اجراها؛ همان عددی که کارایی ستاره‌ها میخواند" action={d ? <Pill tone={d.share > 0.15 ? 'warn' : 'neutral'} dot>{d.share > 0.15 ? 'بالای ۱۵٪؛ اعلان گزارش رفت' : 'زیر آستانه'}</Pill> : null} />
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !d ? <Skeleton className="h-48" /> : (
        <>
          <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
            <div className="flex flex-col"><span className="text-[11px] text-muted">{dayFa(d.day)}</span><span className="fig text-[24px] font-semibold leading-8 text-ink">{usd(d.waste_usd)}</span></div>
            <div className="flex flex-col"><span className="text-[11px] text-muted">سهم از مصرف روز</span><span className={cx('fig text-[18px] font-semibold', d.share > 0.15 ? 'text-warn' : 'text-ink')}>{pct01(d.share, 1)}</span></div>
            <div className="flex flex-col"><span className="text-[11px] text-muted">در برابر میانگین ۷ روز</span><span className={cx('fig text-[18px] font-semibold', d.vs_7d > 0.1 ? 'text-warn' : d.vs_7d < -0.1 ? 'text-pos' : 'text-ink')}>{d.vs_7d >= 0 ? '+' : '−'}{pct01(Math.abs(d.vs_7d))}</span></div>
            <div className="flex flex-col"><span className="text-[11px] text-muted">کل روز</span><span className="fig text-[14px] text-sec">{tokens(d.waste_tokens)} / {tokens(d.total_tokens)} · {usd(d.total_usd)}</span></div>
          </div>
          {/* Fourteen days of share, oldest at the left (data charts read left to right); the line is the 15% notice. */}
          <div dir="ltr" className="relative flex h-16 items-end gap-1" role="group" aria-label="سهم هدررفت ۱۴ روز">
            <span aria-hidden className="absolute inset-x-0 border-t border-dashed border-[var(--hq-warning)] opacity-60" style={{ bottom: `${(0.15 / max) * 100}%` }} />
            {days.map((x) => (
              <button key={x.day} type="button" onClick={() => setPick(x.day)} aria-pressed={x.day === d.day} title={`${dayFa(x.day)} · ${pct01(x.share, 1)} · ${usd(x.waste_usd)}`} aria-label={`${dayFa(x.day)}: ${pct01(x.share, 1)}`}
                className={cx('flex-1 rounded-t-[4px] transition-colors', x.day === d.day ? 'bg-gold' : x.share > 0.15 ? 'bg-[var(--hq-warning)] opacity-70 hover:opacity-100' : 'bg-[var(--hq-silver-ink)] opacity-40 hover:opacity-70')}
                style={{ height: `${Math.max(6, (x.share / max) * 100)}%` }} />
            ))}
          </div>
          <ul className="flex flex-col gap-1">
            {items.map((it) => {
              const w = WASTE[it.category] ?? { fa: it.category, note: '' };
              const on = open === it.category;
              return (
                <li key={it.category} className="flex flex-col">
                  <button type="button" onClick={() => setOpen(on ? null : it.category)} aria-expanded={on} className="flex flex-col gap-1 rounded-[10px] px-2 py-1.5 text-start hover:bg-hover">
                    <span className="flex items-center gap-2 text-[12px]">
                      <span className="min-w-0 flex-1 text-ink" title={w.note}>{w.fa}</span>
                      <span className="text-muted">{it.count} مورد</span>
                      <span className="fig w-14 text-left text-muted">{tokens(it.tokens)}</span>
                      <span className="fig w-14 text-left font-semibold text-ink">{usd(it.usd)}</span>
                    </span>
                    <span className="h-1.5 overflow-hidden rounded-full bg-tile" aria-hidden><span className="block h-full rounded-full bg-[var(--hq-silver-ink)]" style={{ width: `${(Number(it.usd) / top) * 100}%` }} /></span>
                  </button>
                  {on ? (
                    <ul className="mb-1 flex flex-col gap-0.5 ps-4 pt-1 text-[12px]">
                      <li className="text-[11px] text-muted">{w.note}</li>
                      {it.top.map((t, i) => (
                        <li key={i} className="flex items-center gap-2">
                          {t.employee ? <Link href={`/employees/${t.employee}`} className="fig text-ink hover:underline">{t.employee}</Link> : null}
                          {t.work_ref ? <Link href={`/work/${t.work_ref}`} className="fig text-gold-ink hover:underline">{t.work_ref}</Link> : null}
                          {t.run_id ? <span className="fig text-muted">{t.run_id}</span> : null}
                          <span className="flex-1" /><span className="fig text-sec">{tokens(t.tokens)}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </Card>
  );
}

// --------------------------------------------------------------------- ROI (§21.7) --
const BY: Array<{ value: RoiBy; label: string }> = [{ value: 'company', label: 'شرکت' }, { value: 'department', label: 'دپارتمان' }, { value: 'employee', label: 'کارمند' }];
export function RoiCard({ company }: { company: string | null }) {
  const [by, setBy] = useState<RoiBy>('company');
  const [period, setPeriod] = useState<'week' | 'month'>('month');
  const q = useRoi({ by, period, company });
  const rows = [...(q.data ?? [])].sort((a, b) => (b.roi ?? -1) - (a.roi ?? -1) || Number(b.cost_usd) - Number(a.cost_usd));
  const label = (key: string, co: string) => {
    if (by === 'company') return <span className="flex items-center gap-1.5"><CoMark code={co} height={12} />{co}</span>;
    if (by === 'department') { const dept = key.split('-').slice(1).join('-'); return <span className="flex items-center gap-1.5"><CoMark code={co} height={11} />{DEPT_FA[dept] ?? dept}</span>; }
    return <Link href={`/employees/${key}`} className="fig hover:underline">{key}</Link>;
  };
  return (
    <Card className="flex flex-col gap-3 p-5">
      <SectionTitle title="ROI" note="هزینه، خروجی پذیرفته‌شده و امتیاز تو؛ درآمد فقط برای شرکت، چون کمیسیون به یک ایجنت نسبت داده نمیشود" />
      <div className="flex flex-wrap gap-2">
        <div className="w-full max-w-xs"><Segmented label="بر اساس" value={by} onChange={setBy} options={BY} /></div>
        <div className="w-44"><Segmented label="دوره" value={period} onChange={setPeriod} options={[{ value: 'week', label: 'هفته' }, { value: 'month', label: 'ماه' }]} /></div>
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-40" /> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-[12px]">
            <thead><tr className="text-right text-[11px] text-muted">{['', 'هزینه', 'پذیرفته', 'میانگین امتیاز', 'ارزش', 'هر خروجی', 'نسبت‌داده', 'درآمد', 'خالص', 'ROI', 'روند'].map((h, i) => <th key={i} className="px-2 py-1.5 font-semibold">{h}</th>)}</tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} className="h-10 border-t border-div">
                  <td className="px-2 text-ink">{label(r.key, r.company)}</td>
                  <td className="fig px-2 text-sec">{usd(r.cost_usd)}</td>
                  <td className="fig px-2 text-sec">{r.accepted}</td>
                  <td className="fig px-2 text-sec">{r.avg_rating ?? '—'}</td>
                  <td className="fig px-2 text-sec" title="Σ امتیاز تو ÷ ۱۰ روی خروجی‌های پذیرفته">{r.value_points}</td>
                  <td className="fig px-2 text-sec">{usd(r.cost_per_accepted_usd)}</td>
                  <td className="px-2 text-muted">{r.attributed.rescued ? <span>{r.attributed.rescued} نجات</span> : null}{r.attributed.resolved_conversations ? <span>{r.attributed.resolved_conversations} گفت‌وگو</span> : null}{!r.attributed.rescued && !r.attributed.resolved_conversations ? '—' : null}</td>
                  <td className="fig px-2 text-sec">{usd(r.revenue_usd)}</td>
                  <td className={cx('fig px-2', r.net_usd != null && Number(r.net_usd) < 0 ? 'text-neg' : 'text-sec')}>{usd(r.net_usd)}</td>
                  <td className="fig px-2 font-semibold text-ink">{r.roi != null ? `${r.roi}×` : '—'}</td>
                  <td className="px-2"><Trend values={r.trend} width={56} height={20} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="flex items-start gap-1.5 text-[11px] leading-5 text-muted"><Icon name="info" size={13} />روند: برای شرکت ROI، برای دپارتمان و کارمند هزینه‌ی هر خروجی پذیرفته‌شده در دوره‌های قبل. برای کارمند و دپارتمان عدد درآمد ساخته نمیشود.</p>
    </Card>
  );
}
