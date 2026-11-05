'use client';

// ⟨1.15⟩ Contract §33.1 «مصرف»: the usage report in the advisor's words. The figures are the pack (code, from the Token Treasury, the voice
// meter, lines and ads); the words are one mid-model call. The pack sits under «جزئیات»; older reports stay in the history.

import Link from 'next/link';
import { useState } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { HBars } from '@/components/charts/charts';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, Pill, SectionTitle, Segmented } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaPara, FaText, fig } from '@/components/v29/text';
import { errText, notYet } from '@/components/v31/kit';
import { useCompanies } from '@/lib/api/hooks';
import { ROLE_FA } from '@/lib/labels';
import { useMakeUsageReport, useUsageReports, type UsagePack, type UsageReport } from '@/lib/api/v33';
import { cx, jDate, jDateTime, tokens } from '@/lib/format';
import { Loading, dollars } from './bits';

const PERIOD_FA = { day: 'روزانه', week: 'هفتگی' } as const;
/** The Token Treasury's domains (`apps/api/src/hq_api/domain/spend.py` DOMAINS), in the owner's words. */
const DOMAIN_FA: Record<string, string> = {
  work: 'کار فرمان‌ها و شرکت‌ها', media: 'رسانه', council: 'شورا', meetings: 'جلسه‌ها', advisor: 'مشاور', oversight: 'نظارت',
  catalogue: 'فهرست سرورها', server: 'کار روی سرورهای شرکت‌ها', talk: 'گفتگوی تو',
};
const delta = (v: number | null | undefined) => (v == null ? null : <span className={cx('fig font-semibold', v <= 0 ? 'text-pos' : 'text-warn')}>{v >= 0 ? '+' : '−'}{Math.abs(v).toFixed(1)}%</span>);

function Pack({ pack }: { pack: UsagePack }) {
  const { data: companies } = useCompanies();
  const name = (c: string) => companies?.find((x) => x.code === c)?.name_fa ?? c;
  return (
    <div className="flex flex-col gap-4" aria-label="جزئیات عددها">
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {([
          ['در برابر دوره‌ی قبل', <>{delta(pack.vs_prev.usd_pct) ?? '—'} هزینه</>],
          ['صدا', dollars(pack.voice_usd)], ['تبلیغات', dollars(pack.ads_spend_usd, 0)],
          ['خط تولید', <><span className="fig">{fig(pack.lines.runs)}</span> اجرا، <span className="fig">{tokens(pack.lines.tokens)}</span> توکن</>],
        ] as const).map(([k, v]) => <div key={k} className="rounded-[12px] bg-tile p-3"><dt className="text-[11px] text-muted">{k}</dt><dd className="fig pt-1 text-[14px] font-semibold">{v}</dd></div>)}
      </dl>
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="flex flex-col gap-2"><h3 className="text-[13px] font-semibold text-sec">به تفکیک کار</h3>
          <HBars rows={pack.by_domain.map((d) => ({ key: d.domain, label: DOMAIN_FA[d.domain] ?? d.domain, value: d.usd_equiv, fmt: `${dollars(d.usd_equiv)} · ${fig(d.share * 100)}%` }))} /></section>
        <section className="flex flex-col gap-2"><h3 className="text-[13px] font-semibold text-sec">به تفکیک شرکت</h3>
          <HBars rows={pack.by_company.map((c) => ({ key: c.company, label: <span className="flex items-center gap-1.5"><CompanyMark code={c.company} height={11} mono />{name(c.company)}</span>, value: c.usd_equiv, fmt: `${dollars(c.usd_equiv)} · ${fig(c.share * 100)}%` }))} /></section>
      </div>
      {pack.top_runs.length ? (
        <section className="flex flex-col gap-1.5"><h3 className="text-[13px] font-semibold text-sec">گران‌ترین اجراها</h3>
          <ul className="flex flex-col">{pack.top_runs.map((r) => <li key={r.ref} className="flex items-center justify-between gap-3 border-t border-div py-1.5 text-[13px] first:border-0"><span><span className="fig">{r.ref}</span>{r.role ? <span className="text-muted"> · {ROLE_FA[r.role] ?? r.role}</span> : null}</span><span className="fig">{tokens(r.tokens)} توکن</span></li>)}</ul></section>
      ) : null}
      {pack.anomalies.length ? (
        <section className="flex flex-col gap-1.5"><h3 className="text-[13px] font-semibold text-warn">چیزهای غیرعادی</h3>
          <ul className="flex flex-col gap-1">{pack.anomalies.map((a, i) => <li key={i} className="rounded-[10px] bg-warn-soft px-3 py-2 text-[13px] leading-6"><FaText text={a.note} /></li>)}</ul></section>
      ) : null}
    </div>
  );
}

function ReportCard({ r, head }: { r: UsageReport; head?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <Card as="article" className={cx('flex flex-col gap-4 p-5', head && 'tahrir')} aria-label={`گزارش مصرف ${r.ref}`}>
      <SectionTitle title={<>گزارش مصرف {PERIOD_FA[r.period]}</>} note={<><span className="fig">{r.ref}</span> · {jDate(r.from)} تا {jDate(r.to)} · نوشته شده {jDateTime(r.at)}</>} />
      {r.text ? (
        <>
          <ol className="flex flex-col gap-1.5" aria-label="خلاصه‌ی مشاور">
            {r.text.lines_fa.map((l, i) => <li key={i} className="flex items-start gap-2.5 text-[14px] leading-7"><span className="fig mt-1.5 flex size-5 flex-none items-center justify-center rounded-full bg-tile text-[11px] text-sec">{i + 1}</span><span className="min-w-0 flex-1"><FaPara text={l} /></span></li>)}
          </ol>
          <div className="rounded-[12px] bg-gold-soft p-3" aria-label="یک پیشنهاد برای صرفه‌جویی">
            <h3 className="text-[12px] font-semibold text-gold-ink">یک صرفه‌جویی</h3>
            <FaPara text={r.text.saving_fa} className="pt-1 text-[14px] leading-7" />
          </div>
          {r.words === 'code' ? <p className="text-[11px] text-muted">این بار مشاور متنی نداد؛ این خط‌ها را خود سامانه از روی عددها نوشته است.</p> : null}
        </>
      ) : <p className="text-[13px] text-muted">متن این گزارش هنوز نوشته نشده؛ عددها در «جزئیات» است.</p>}
      <div className="flex flex-col gap-3">
        <Button variant="text" size="sm" iconEnd="chevron" className="self-start" aria-expanded={open} onClick={() => setOpen(!open)}>جزئیات</Button>
        {open ? <Pack pack={r.pack} /> : null}
      </div>
    </Card>
  );
}

/** `/usage`: the latest report, a button for a fresh one, and the history. */
export function UsageView() {
  const [period, setPeriod] = useState<'day' | 'week'>('week');
  const q = useUsageReports(period);
  const make = useMakeUsageReport();
  const toast = useToast();
  const [pick, setPick] = useState<string | null>(null);
  const list = q.data ?? [];
  const shown = list.find((r) => r.ref === pick) ?? list[0];
  const rest = list.filter((r) => r.ref !== shown?.ref);
  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <div className="w-56"><Segmented label="دوره" value={period} onChange={(v) => { setPeriod(v); setPick(null); }} options={[{ value: 'week', label: 'هفتگی' }, { value: 'day', label: 'روزانه' }]} /></div>
        <Button variant="primary" icon="refresh" loading={make.isPending} onClick={() => make.mutate(period, { onSuccess: () => { setPick(null); toast({ tone: 'ok', text: 'گزارش تازه نوشته شد.' }); }, onError: (e) => toast({ tone: 'error', text: errText(e, 'گزارش ساخته نشد.') }) })}>گزارش تازه بساز</Button>
      </div>
      {q.isLoading ? <Loading h="h-72" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : !q.data ? notYet('chart', 'گزارش مصرف بعد از به‌روزرسانی ستاد میاید', 'مشاور هر روز و هر هفته مصرف را به زبان ساده می‌نویسد.')
        : !shown ? <Card><Empty icon="chart" title="هنوز گزارشی نیست" body="روزانه ساعت ۷:۵۵ و هفتگی شنبه ۹ صبح نوشته میشود؛ همین حالا هم می‌توانی یکی بسازی." /></Card>
        : (
          <>
            <ReportCard r={shown} head />
            {rest.length ? (
              <Card as="section" className="flex flex-col gap-1 p-4" aria-label="گزارش‌های قبلی">
                <SectionTitle title="گزارش‌های قبلی" />
                <ul className="flex flex-col">{rest.map((r) => (
                  <li key={r.ref} className="border-t border-div first:border-0">
                    <button type="button" onClick={() => { setPick(r.ref); window.scrollTo({ top: 0 }); }} className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 py-2.5 text-start hover:bg-hover/40">
                      <span className="fig w-20 text-[12px] text-muted">{r.ref}</span>
                      <span className="min-w-0 flex-[1_1_14rem] text-[13px]">{r.text?.lines_fa[0] ? <FaText text={r.text.lines_fa[0]} /> : <span className="text-muted">بدون متن</span>}</span>
                      <span className="text-[11px] text-muted">{jDate(r.to)}</span>
                    </button>
                  </li>
                ))}</ul>
              </Card>
            ) : null}
          </>
        )}
    </>
  );
}

/** A home card: the three lines of the latest daily report. Shows nothing until the hub serves it. */
export function UsageHomeCard() {
  const q = useUsageReports('day');
  const r = q.data?.[0];
  if (!r?.text) return null;
  return (
    <Card className="flex flex-col gap-2 p-4" aria-label="مصرف دیروز">
      <SectionTitle title="مصرف دیروز" note="به زبان مشاور" action={<Link href="/usage" className="text-[12px] font-semibold text-gold-ink hover:underline">گزارش کامل</Link>} />
      <ol className="flex flex-col gap-1.5">{r.text.lines_fa.slice(0, 3).map((l, i) => <li key={i} className="text-[13px] leading-6"><FaText text={l} /></li>)}</ol>
      <Pill tone="gold" icon="chart" className="self-start">{r.text.saving_fa.length > 60 ? `${r.text.saving_fa.slice(0, 58)}…` : r.text.saving_fa}</Pill>
    </Card>
  );
}
