'use client';

// ⟨1.15⟩ Contract §33.2–§33.3 «پول»: the revenue board (MRR with its forecast band, KPIs, cohorts, ROI, cost per output), the payments the
// company's own ledger and the public chain agree or disagree on, the day-by-day reconcile, and the payment sources (read, add, change
// behind the passkey). Money is only read here: no button moves, approves or refunds anything.

import { useMemo, useState } from 'react';
import { axisOf } from '@/components/charts/charts';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, FilterChip, Pill, SectionTitle, StatTile } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaText, fig } from '@/components/v29/text';
import { errText, field, notYet } from '@/components/v31/kit';
import {
  NETWORK_FA, OUTPUT_COST_FA, PAY_STATUS, SOURCE_STATE, usePayments, useReconcile, useRevenueBoard, useSourceActions, useSources,
  type PayStatus, type PaymentSource, type RevenueBoard, type SourceBody,
} from '@/lib/api/v33';
import { cx, jDateTime } from '@/lib/format';
import { Loading, Txt, dayShort, dollars, monthLabel, pctOf, usdt } from './bits';

const rate = (v: number | null | undefined) => (v == null ? null : v <= 1 ? v * 100 : v);

// ============================================================================================== the MRR chart ==
/** MRR by month with the forecast as a dashed line inside its band; identity never by colour alone (legend words, dashes, a band). */
function MrrChart({ b }: { b: RevenueBoard }) {
  const [hi, setHi] = useState<number | null>(null);
  const W = 720, H = 240, P = { l: 52, r: 16, t: 14, b: 28 };
  const hist = b.months.map((m) => ({ month: m.month, v: m.mrr_usdt }));
  const fc = b.forecast;
  const all = [...hist.map((h) => h.month), ...fc.map((f) => f.month)];
  const n = all.length;
  const [yMax, yStep] = axisOf([...hist.map((h) => h.v), ...fc.map((f) => f.high)]);
  const x = (i: number) => (n <= 1 ? W / 2 : P.l + (i / (n - 1)) * (W - P.l - P.r));
  const y = (v: number) => H - P.b - (v / yMax) * (H - P.t - P.b);
  const histPath = hist.map((h, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(h.v).toFixed(1)}`).join('');
  const last = hist.length - 1;
  const fcPts = fc.map((f, i) => ({ i: last + 1 + i, ...f }));
  const fcPath = fc.length && last >= 0 ? `M${x(last).toFixed(1)},${y(hist[last]!.v).toFixed(1)}${fcPts.map((f) => `L${x(f.i).toFixed(1)},${y(f.mrr_usdt).toFixed(1)}`).join('')}` : '';
  const band = fc.length && last >= 0
    ? `M${x(last).toFixed(1)},${y(hist[last]!.v).toFixed(1)}${fcPts.map((f) => `L${x(f.i).toFixed(1)},${y(f.high).toFixed(1)}`).join('')}${[...fcPts].reverse().map((f) => `L${x(f.i).toFixed(1)},${y(f.low).toFixed(1)}`).join('')}Z`
    : '';
  const ticks = [0, 1, 2, 3, 4].map((k) => yStep * k);
  const every = Math.ceil(n / 8);
  const at = (i: number) => (i <= last ? { label: hist[i]!.month, text: usdt(hist[i]!.v) } : { label: fcPts[i - last - 1]!.month, text: `${usdt(fcPts[i - last - 1]!.mrr_usdt)} (بازه ${fig(fcPts[i - last - 1]!.low)} تا ${fig(fcPts[i - last - 1]!.high)})` });
  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-[12px] text-sec" aria-label="راهنما">
        <li className="flex items-center gap-2"><span className="h-[2px] w-4 rounded-full bg-[var(--hq-gold-bright)]" />درآمد ماهانه (MRR)</li>
        {fc.length ? <li className="flex items-center gap-2"><span className="h-0 w-4 border-t-2 border-dashed border-[var(--hq-lapis,#5B8DEF)]" />پیش‌بینی</li> : null}
        {fc.length ? <li className="flex items-center gap-2"><span className="h-3 w-4 rounded-sm bg-[var(--hq-lapis,#5B8DEF)] opacity-20" />بازه‌ی پیش‌بینی</li> : null}
      </ul>
      <div className="relative" style={{ direction: 'ltr' }}>
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full touch-pan-y" role="img" aria-label="نمودار درآمد ماهانه و پیش‌بینی" onPointerLeave={() => setHi(null)}
          onPointerMove={(e) => { const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const px = ((e.clientX - r.left) / r.width) * W; const i = Math.round(((px - P.l) / (W - P.l - P.r)) * (n - 1)); setHi(i >= 0 && i < n ? i : null); }}>
          {ticks.map((t) => <g key={t}><line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="var(--hq-line-divider)" /><text x={P.l - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--hq-text-muted)" fontFamily="IRANYekanX">{fig(t)}</text></g>)}
          {all.map((m, i) => (i % every === 0 || i === n - 1 ? <text key={m} x={x(i)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--hq-text-muted)" fontFamily="IRANYekanX">{m.slice(2, 7)}</text> : null))}
          {band ? <path d={band} fill="var(--hq-lapis, #5B8DEF)" opacity={0.2} /> : null}
          {fcPath ? <path d={fcPath} fill="none" stroke="var(--hq-lapis, #5B8DEF)" strokeWidth={2} strokeDasharray="6 5" strokeLinecap="round" /> : null}
          {histPath ? <path d={histPath} fill="none" stroke="var(--hq-gold-bright)" strokeWidth={2.2} strokeLinejoin="round" strokeLinecap="round" /> : null}
          {hist.map((h, i) => <circle key={h.month} cx={x(i)} cy={y(h.v)} r={i === last || hi === i ? 4 : 2.2} fill="var(--hq-gold-bright)" stroke="var(--hq-surface-card)" strokeWidth={1.5} />)}
          {hi != null ? <line x1={x(hi)} x2={x(hi)} y1={P.t} y2={H - P.b} stroke="var(--hq-line-strong)" /> : null}
        </svg>
        {hi != null ? (
          <div className="pointer-events-none absolute top-1 rounded-[10px] bg-raised px-3 py-2 text-[12px] shadow-[0_8px_24px_rgba(0,0,0,.35)]" style={{ left: `clamp(8px, ${(x(hi) / W) * 100}% - 80px, calc(100% - 200px))`, direction: 'rtl' }}>
            <div className="text-muted">{at(hi).label}{hi > last ? ' · پیش‌بینی' : ''}</div><div className="fig font-semibold">{at(hi).text}</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ================================================================================================ revenue board ==
function Cohorts({ b }: { b: RevenueBoard }) {
  if (!b.cohorts.length) return <p className="text-[13px] text-muted">هنوز گروه ماهانه‌ای نیست.</p>;
  const cols = Math.max(...b.cohorts.map((c) => c.retained.length));
  return (
    <div className="no-scrollbar overflow-x-auto">
      <table className="w-full min-w-[420px] border-separate border-spacing-1 text-[12px]" aria-label="گروه‌های ماهانه و ماندگاری">
        <thead><tr className="text-muted"><th className="px-2 text-start font-normal">ماه شروع</th><th className="px-2 font-normal">اندازه</th>{Array.from({ length: cols }, (_, i) => <th key={i} className="fig px-1 font-normal">{i === 0 ? 'ماه ۰' : `ماه ${i}`}</th>)}</tr></thead>
        <tbody>
          {b.cohorts.map((c) => (
            <tr key={c.start_month}>
              <th scope="row" className="fig px-2 text-start font-semibold" dir="ltr">{monthLabel(c.start_month)}</th>
              <td className="fig px-2 text-center text-sec">{fig(c.size)}</td>
              {Array.from({ length: cols }, (_, i) => {
                const v = c.retained[i];
                return v == null ? <td key={i} /> : (
                  <td key={i} className="fig rounded-[6px] px-1 py-1.5 text-center font-semibold" style={{ background: `color-mix(in srgb, var(--hq-gold-bright) ${Math.round(Math.min(100, Math.max(0, v)) * 0.8)}%, transparent)` }}>{fig(v)}%</td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The revenue board of one company, or of the whole holding (`company` null). */
export function RevenueBoardView({ company }: { company: string | null }) {
  const q = useRevenueBoard(company);
  if (q.isLoading) return <Loading h="h-72" />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const b = q.data;
  if (!b) return notYet('chart', 'تابلوی درآمد بعد از به‌روزرسانی ستاد میاید', 'درآمد ماهانه، ریزش، ارزش هر مشتری، گروه‌های ماهانه و پیش‌بینی این‌جا میاید.');
  if (!b.months.length) return <Card><Empty icon="chart" title="هنوز پرداختی خوانده نشده" body="بعد از وصل شدن دفتر شرکت یا آدرس عمومی، درآمد ماهانه این‌جا میاید." /></Card>;
  const cur = b.months.at(-1)!;
  const prev = b.months.at(-2);
  const mrrChange = prev?.mrr_usdt ? ((cur.mrr_usdt - prev.mrr_usdt) / prev.mrr_usdt) * 100 : null;
  const cost = b.roi.cost_usd;
  const costTotal = cost.tokens + cost.voice + cost.ads + (cost.servers ?? 0);
  return (
    <div className="flex flex-col gap-4" aria-label="تابلوی درآمد">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatTile label="درآمد ماهانه (MRR)" value={<span className="fig">{usdt(cur.mrr_usdt)}</span>}
          sub={mrrChange == null ? 'ماه قبل داده ندارد' : <span><span className={cx('fig font-semibold', mrrChange >= 0 ? 'text-pos' : 'text-neg')}>{mrrChange >= 0 ? '+' : '−'}{Math.abs(mrrChange).toFixed(1)}%</span> نسبت به ماه قبل</span>} />
        <StatTile label="مشتری فعال" value={<span className="fig">{fig(cur.active)}</span>} sub={<span>تازه <span className="fig">{fig(cur.new_customers)}</span>، رفته <span className="fig">{fig(cur.churned)}</span></span>} />
        <StatTile label="نرخ ریزش" value={<span className="fig">{pctOf(rate(b.churn_rate), 1)}</span>} sub="ماهانه" />
        <StatTile label="ارزش هر مشتری (LTV)" value={<span className="fig">{b.ltv_usdt == null ? '—' : usdt(b.ltv_usdt)}</span>} sub={b.ltv_usdt == null ? 'با ریزش صفر یا کم‌تر از ۳ ماه داده حساب نمیشود' : `میانگین هر مشتری ${usdt(cur.arpu_usdt, 1)}`} />
        <StatTile label="هزینه‌ی جذب (CAC)" value={<span className="fig">{b.cac_usdt == null ? '—' : usdt(b.cac_usdt, 1)}</span>} sub={b.payback_months == null ? 'بازگشت سرمایه نامعلوم' : <span>برگشت در <span className="fig">{fig(b.payback_months, 1)}</span> ماه</span>} />
      </div>
      <Card as="section" className="flex flex-col gap-3 p-5" aria-label="درآمد ماهانه و پیش‌بینی">
        <SectionTitle title="درآمد ماهانه و پیش‌بینی" note="عددها از ردیف‌های ذخیره‌شده با کد حساب میشوند" />
        <MrrChart b={b} />
        <p className="text-[13px] leading-6 text-sec" aria-label="پایه‌ی پیش‌بینی">
          {b.forecast.length ? <><Pill tone="warn" className="me-2">تخمین</Pill><FaText text={b.forecast_basis_fa} /></> : <FaText text={b.forecast_basis_fa ?? 'پیش‌بینی با دست‌کم ۴ ماه داده ممکن است.'} />}
        </p>
      </Card>
      <div className="grid items-start gap-4 xl:grid-cols-2">
        <Card as="section" className="flex flex-col gap-3 p-5" aria-label="گروه‌های ماهانه">
          <SectionTitle title="گروه‌های ماهانه" note="هر ردیف مشتریان یک ماه؛ درصدِ هنوز پرداخت‌کننده بعد از هر ماه" />
          <Cohorts b={b} />
        </Card>
        <div className="flex min-w-0 flex-col gap-4">
          <Card as="section" className="flex flex-col gap-3 p-5" aria-label="بازده سرمایه">
            <SectionTitle title="بازده (ROI)" note="درآمد در برابر هزینه‌ی همین دوره" />
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-[12px] bg-tile p-3"><div className="text-[11px] text-muted">درآمد</div><div className="fig pt-1 text-[15px] font-semibold">{usdt(b.roi.revenue_usdt)}</div></div>
              <div className="rounded-[12px] bg-tile p-3"><div className="text-[11px] text-muted">هزینه</div><div className="fig pt-1 text-[15px] font-semibold">{dollars(costTotal, 0)}</div></div>
            </div>
            <ul className="flex flex-col text-[13px]" aria-label="هزینه به تفکیک">
              {([['توکن', cost.tokens], ['صدا', cost.voice], ['تبلیغات', cost.ads], ['سرورها', cost.servers]] as const).map(([k, v]) => (
                <li key={k} className="flex items-center justify-between border-t border-div py-1.5 first:border-0"><span className="text-sec">{k}</span><span className="fig">{v == null ? 'هنوز حساب نمیشود' : dollars(v, 0)}</span></li>
              ))}
            </ul>
            <p className="text-[13px]">هر دلار هزینه <span className="fig font-semibold">{b.roi.ratio == null ? '—' : fig(b.roi.ratio, 1)}</span> دلار درآمد آورده.</p>
          </Card>
          <Card as="section" className="flex flex-col gap-2 p-5" aria-label="هزینه‌ی هر خروجی">
            <SectionTitle title="هزینه‌ی هر خروجی" note="میانگین هزینه‌ی توکن، با شمار" />
            {b.cost_per_output.length ? (
              <ul className="flex flex-col">{b.cost_per_output.map((c) => (
                <li key={c.kind} className="flex items-center justify-between gap-3 border-t border-div py-2 text-[13px] first:border-0"><span>{OUTPUT_COST_FA[c.kind] ?? c.kind}<span className="text-muted"> · <span className="fig">{fig(c.count)}</span> بار</span></span><span className="fig font-semibold">{dollars(c.usd_each, 2)}</span></li>
              ))}</ul>
            ) : <p className="text-[13px] text-muted">هنوز خروجی‌ای شمرده نشده.</p>}
          </Card>
        </div>
      </div>
    </div>
  );
}

// ================================================================================================== payments ==
const isoDay = (d: Date) => d.toISOString().slice(0, 10);
const short = (h: string | null) => (h ? `${h.slice(0, 8)}…${h.slice(-6)}` : null);
const ORDER: PayStatus[] = ['matched', 'ledger_only', 'chain_only', 'amount_mismatch', 'pending_chain'];

export function PaymentsCard({ code }: { code: string }) {
  const [status, setStatus] = useState<PayStatus | null>(null);
  const [from, setFrom] = useState(() => isoDay(new Date(Date.now() - 30 * 86_400_000)));
  const [to, setTo] = useState(() => isoDay(new Date()));
  const q = usePayments(code, { status, from, to });
  const rec = useReconcile(code, from, to);
  const sums = useMemo(() => {
    const s = { matched: 0, ledger_only: 0, chain_only: 0, amount_mismatch: 0 };
    for (const d of rec.data ?? []) { s.matched += d.matched; s.ledger_only += d.ledger_only; s.chain_only += d.chain_only; s.amount_mismatch += d.amount_mismatch; }
    return s;
  }, [rec.data]);
  const rows = q.data ?? [];
  const sum = rows.reduce((a, p) => a + (p.amount_usdt ?? 0), 0);
  const noAmount = rows.filter((p) => p.amount_usdt == null).length;
  return (
    <Card as="section" className="flex flex-col gap-3 p-5" aria-label="پرداخت‌ها">
      <SectionTitle title="پرداخت‌ها" note="هر پرداخت دفتر شرکت با پول روی زنجیره تطبیق داده میشود؛ این‌جا فقط خوانده میشود" />
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-wrap gap-2" role="group" aria-label="وضعیت پرداخت">
          <FilterChip selected={status === null} onClick={() => setStatus(null)}>همه</FilterChip>
          {ORDER.map((s) => {
            const n = s === 'pending_chain' ? undefined : sums[s];
            return <FilterChip key={s} selected={status === s} onClick={() => setStatus(status === s ? null : s)} count={n}>{PAY_STATUS[s].fa}</FilterChip>;
          })}
        </div>
        <label className="flex flex-col gap-1 text-[12px] text-sec">از<input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} dir="ltr" aria-label="از روز" className={cx(field, 'h-9 w-auto text-[12px]')} /></label>
        <label className="flex flex-col gap-1 text-[12px] text-sec">تا<input type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} dir="ltr" aria-label="تا روز" className={cx(field, 'h-9 w-auto text-[12px]')} /></label>
      </div>
      {q.isLoading ? <Loading h="h-40" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : !q.data ? notYet('budget', 'پرداخت‌ها بعد از به‌روزرسانی ستاد میاید', 'پرداخت‌های دفتر شرکت و زنجیره با هم تطبیق داده میشوند.')
        : !rows.length ? <Empty icon="budget" title="پرداختی با این فیلتر نیست" body="بازه یا وضعیت را عوض کن، یا یک منبع پرداخت را «بخوان»." />
        : (
          <>
            <p className="text-[12px] text-sec" aria-live="polite"><span className="fig">{fig(rows.length)}</span> پرداخت، جمع <span className="fig font-semibold text-ink">{usdt(sum, 2)}</span>{noAmount ? <> ، <span className="fig">{fig(noAmount)}</span> مورد درون‌برنامه (شمرده میشود، جمع نمیشود)</> : null}</p>
            <ul className="flex flex-col">
              {rows.map((p) => {
                const s = PAY_STATUS[p.status];
                return (
                  <li key={p.id} aria-label={`پرداخت ${p.ext_id}`} className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-div py-3 first:border-0">
                    <span className="flex min-w-0 flex-[1_1_13rem] flex-col">
                      <span className="text-[14px] font-semibold"><span className="fig" dir="ltr">{p.customer}</span>{p.plan ? <span className="text-sec"> · {p.plan}</span> : null}</span>
                      <span className="text-[11px] text-muted">{jDateTime(p.paid_at)}{p.network ? ` · ${NETWORK_FA[p.network] ?? p.network}` : ''}</span>
                      {p.tx_hash ? <span className="fig truncate text-[11px] text-muted" dir="ltr" title={p.tx_hash}>{short(p.tx_hash)}</span> : null}
                    </span>
                    <span className="fig text-[14px] font-semibold">{p.amount_usdt == null ? <span className="text-[12px] font-normal text-muted">درون‌برنامه</span> : usdt(p.amount_usdt, 2)}</span>
                    <span title={s.hint}><Pill tone={s.tone} dot>{s.fa}</Pill></span>
                  </li>
                );
              })}
            </ul>
          </>
        )}
    </Card>
  );
}

export function ReconcileCard({ code }: { code: string }) {
  const [from] = useState(() => isoDay(new Date(Date.now() - 14 * 86_400_000)));
  const [to] = useState(() => isoDay(new Date()));
  const q = useReconcile(code, from, to);
  if (q.isLoading) return <Loading h="h-40" />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return null;
  const days = [...q.data].sort((a, b) => b.day.localeCompare(a.day));
  return (
    <Card as="section" className="flex flex-col gap-3 p-5" aria-label="تطبیق روزانه">
      <SectionTitle title="تطبیق روزانه" note="۱۴ روز اخیر؛ هر روز دفتر شرکت در برابر زنجیره" />
      {!days.length ? <p className="text-[13px] text-muted">هنوز روزی تطبیق داده نشده.</p> : (
        <div className="no-scrollbar overflow-x-auto">
          <table className="w-full min-w-[520px] text-[13px]" aria-label="تطبیق روزانه‌ی پرداخت‌ها">
            <thead><tr className="text-[11px] text-muted"><th className="py-1.5 text-start font-normal">روز</th><th className="font-normal">دفتر</th><th className="font-normal">زنجیره</th><th className="font-normal">تطبیق</th><th className="font-normal">فقط دفتر</th><th className="font-normal">فقط زنجیره</th><th className="font-normal">مبلغ کم</th></tr></thead>
            <tbody>
              {days.map((d) => (
                <tr key={d.day} className="border-t border-div text-center">
                  <th scope="row" className="fig py-2 text-start font-semibold" dir="ltr">{dayShort(d.day)}</th>
                  <td className="fig">{fig(d.ledger_count)}</td><td className="fig">{fig(d.chain_count)}</td>
                  <td className="fig text-pos">{fig(d.matched)}</td>
                  <td className={cx('fig', d.ledger_only ? 'font-semibold text-neg' : 'text-muted')}>{fig(d.ledger_only)}</td>
                  <td className={cx('fig', d.chain_only ? 'font-semibold text-warn' : 'text-muted')}>{fig(d.chain_only)}</td>
                  <td className={cx('fig', d.amount_mismatch ? 'font-semibold text-warn' : 'text-muted')}>{fig(d.amount_mismatch)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {days.filter((d) => d.note_fa).map((d) => <p key={d.day} className="pt-1 text-[12px] text-sec"><span className="fig" dir="ltr">{dayShort(d.day)}</span>: <FaText text={d.note_fa} /></p>)}
        </div>
      )}
    </Card>
  );
}

// =========================================================================================== payment sources ==
type Form = { id?: string; kind: 'ledger' | 'chain'; adapter: string; network: '' | 'bsc_usdt' | 'trc20_usdt'; address: string };
const blank: Form = { kind: 'chain', adapter: '', network: 'bsc_usdt', address: '' };

export function SourcesCard({ code }: { code: string }) {
  const q = useSources(code);
  const act = useSourceActions(code);
  const toast = useToast();
  const [form, setForm] = useState<Form | null>(null);
  if (q.isLoading) return <Loading h="h-40" />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return notYet('globe', 'منبع‌های پرداخت بعد از به‌روزرسانی ستاد میاید', 'دفتر شرکت و آدرس عمومی کیف پول این‌جا وصل میشود.');
  const valid = !!form && form.adapter.trim() && (form.kind === 'ledger' || (form.network && form.address.trim()));
  const save = () => {
    if (!form) return;
    const body: SourceBody = { id: form.id, kind: form.kind, adapter: form.adapter.trim(), network: form.kind === 'chain' && form.network ? form.network : null, address: form.kind === 'chain' ? form.address.trim() : null };
    act.save.mutate(body, { onSuccess: () => { toast({ tone: 'ok', text: 'منبع ذخیره شد.' }); setForm(null); }, onError: (e) => toast({ tone: 'error', text: errText(e, 'ذخیره نشد.') }) });
  };
  return (
    <Card as="section" className="flex flex-col gap-3 p-5" aria-label="منبع‌های پرداخت">
      <SectionTitle title="منبع‌های پرداخت" note="دفتر خود شرکت (از راه runner) و آدرس عمومی روی زنجیره؛ کلید خصوصی هرگز این‌جا نیست" action={<Button size="sm" variant="primary" icon="add" onClick={() => setForm(blank)}>منبع تازه</Button>} />
      {form ? (
        <div className="hq-rise flex flex-col gap-3 rounded-[12px] bg-tile p-4" aria-label="مشخصات منبع">
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="نوع منبع">
            {([['chain', 'زنجیره (آدرس عمومی)'], ['ledger', 'دفتر شرکت (runner)']] as const).map(([k, l]) => (
              <button key={k} type="button" role="radio" aria-checked={form.kind === k} disabled={!!form.id} onClick={() => setForm({ ...form, kind: k })} className={cx('h-9 rounded-full px-3.5 text-[13px] font-semibold', form.kind === k ? 'bg-gold text-on-gold' : 'bg-card text-sec')}>{l}</button>
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Txt label="نام آداپتور" value={form.adapter} set={(v) => setForm({ ...form, adapter: v })} ltr />
            {form.kind === 'chain' ? (
              <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">شبکه</span>
                <select value={form.network} onChange={(e) => setForm({ ...form, network: e.target.value as Form['network'] })} aria-label="شبکه" className={cx(field, 'h-10')}>
                  <option value="bsc_usdt">{NETWORK_FA.bsc_usdt}</option><option value="trc20_usdt">{NETWORK_FA.trc20_usdt}</option>
                </select></label>
            ) : null}
          </div>
          {form.kind === 'chain' ? <Txt label="آدرس عمومی کیف پول" value={form.address} set={(v) => setForm({ ...form, address: v })} ltr /> : (
            <p className="text-[12px] leading-6 text-sec">برای دفتر شرکت، runner آن سرور باید جفت شده و نسخه‌اش ۰٫۳٫۰ یا بالاتر باشد. پرسش دفتر روی خود آن سرور می‌ماند.</p>
          )}
          <div className="flex gap-2">
            <Button variant="primary" loading={act.save.isPending} disabled={!valid} onClick={save}>ذخیره</Button>
            <Button onClick={() => setForm(null)}>بی‌خیال</Button>
          </div>
          <p className="text-[11px] text-muted">ذخیره با اثر انگشت یا چهره تأیید میشود.</p>
        </div>
      ) : null}
      {!q.data.length ? <p className="text-[13px] text-muted">هنوز منبعی وصل نشده.</p> : (
        <ul className="flex flex-col">{q.data.map((s) => <SourceRow key={s.id} s={s} busy={act.read.isPending && act.read.variables === s.id}
          onRead={() => act.read.mutate(s.id, { onSuccess: () => toast({ tone: 'ok', text: 'خوانده شد.' }), onError: (e) => toast({ tone: 'error', text: errText(e, 'خواندن نشد.') }) })}
          onEdit={() => setForm({ id: s.id, kind: s.kind, adapter: s.adapter, network: s.network ?? '', address: s.address ?? '' })} />)}</ul>
      )}
    </Card>
  );
}

function SourceRow({ s, busy, onRead, onEdit }: { s: PaymentSource; busy: boolean; onRead: () => void; onEdit: () => void }) {
  const st = SOURCE_STATE[s.state];
  const title = s.kind === 'ledger' ? 'دفتر شرکت' : `زنجیره${s.network ? ` · ${NETWORK_FA[s.network] ?? s.network}` : ''}`;
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-div py-3 first:border-0" aria-label={`منبع ${title}`}>
      <span className="flex min-w-0 flex-[1_1_14rem] flex-col">
        <span className="text-[14px] font-semibold">{title}</span>
        <span className="fig text-[11px] text-muted" dir="ltr">{s.adapter}{s.address ? ` · ${s.address.length > 20 ? `${s.address.slice(0, 8)}…${s.address.slice(-6)}` : s.address}` : ''}</span>
        <span className="text-[11px] text-muted">{s.last_read_at ? `آخرین خواندن ${jDateTime(s.last_read_at)}` : 'هنوز خوانده نشده'}</span>
        {s.state === 'error' && s.last_error_fa ? <span className="text-[12px] leading-6 text-neg" role="alert"><FaText text={s.last_error_fa} /></span> : null}
      </span>
      <Pill tone={st.tone} dot>{st.fa}</Pill>
      <span className="flex gap-2">
        <Button size="sm" icon="refresh" loading={busy} disabled={s.state === 'not_configured'} onClick={onRead} aria-label={`بخوان ${s.adapter}`}>بخوان</Button>
        <Button size="sm" icon="edit" onClick={onEdit} aria-label={`ویرایش ${s.adapter}`}>ویرایش</Button>
      </span>
    </li>
  );
}

/** The whole «پول» page body of one company. */
export function CompanyMoney({ code }: { code: string }) {
  return (
    <>
      <RevenueBoardView company={code} />
      <PaymentsCard code={code} />
      <ReconcileCard code={code} />
      <SourcesCard code={code} />
    </>
  );
}

