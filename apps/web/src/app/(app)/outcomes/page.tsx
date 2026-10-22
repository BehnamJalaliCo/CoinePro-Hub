'use client';

import { useMemo, useState } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { Md } from '@/components/ui/md';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, SectionTitle, Skeleton, StatTile } from '@/components/ui/primitives';
import { ActorAvatar, OUTCOME_STATUS, RefChip, ScopeChips, VERDICT, kpiFig, pct01 } from '@/components/v17/bits';
import { useCompanies } from '@/lib/api/hooks';
import { accuracy, useOutcomes, type OutcomeReview, type Verdict } from '@/lib/api/v17';
import { ACTOR_FA } from '@/lib/labels';
import { useScope } from '@/lib/scope';
import { useNow } from '@/lib/store';
import { cx, jDate } from '@/lib/format';

const VERDICTS: Verdict[] = ['pending', 'met', 'partly', 'missed', 'unmeasurable'];
const unit = (metric: string) => (/٪|%/.test(metric) ? '%' : '');

function Review({ r }: { r: OutcomeReview }) {
  const v = VERDICT[r.verdict] ?? { fa: r.verdict, tone: 'neutral' as const };
  const now = useNow();
  const due = !!now && r.status === 'due' && r.verdict === 'pending' && Date.parse(r.due_at) <= now;
  return (
    <div className={cx('flex min-w-0 flex-col gap-1.5 rounded-[12px] bg-tile p-3', due && 'ring-1 ring-[var(--hq-gold-ink)]')}>
      <span className="flex items-center gap-2 text-[12px] text-muted"><span className="font-semibold text-sec">روز {r.day}</span><span className="fig">{r.ref}</span></span>
      <Pill tone={v.tone} dot className="self-start">{v.fa}</Pill>
      <span className="text-[12px] text-sec">{r.measured ? <>اندازه <span className="fig font-semibold text-ink">{kpiFig(r.measured.value, unit(r.expected.metric_fa))}</span> · {jDate(r.measured.at)}</> : <>موعد {jDate(r.due_at)}</>}</span>
      <span className="text-[11px] text-muted">{OUTCOME_STATUS[r.status] ?? r.status}</span>
      {r.proposer_note_md ? <div className="rounded-[8px] bg-card p-2"><span className="text-[11px] text-muted">یادداشت پیشنهاددهنده</span><Md text={r.proposer_note_md} className="text-[12px] leading-6 text-sec" /></div> : null}
      {r.overseer_note_md ? <div className="rounded-[8px] bg-card p-2"><span className="text-[11px] text-muted">حکم ناظر</span><Md text={r.overseer_note_md} className="text-[12px] leading-6 text-sec" /></div> : null}
      {!r.expected.kpi && r.status === 'answered' && r.verdict === 'pending' ? <span className="text-[11px] text-warn">منتظر حکم ناظر (PR-006)</span> : null}
    </div>
  );
}

/** بازبینی نتیجه (contract §20.6): what each sealed decision promised, measured at 30, 60 and 90 days; prediction accuracy comes from the verdicts. */
export default function OutcomesPage() {
  const { company: scope } = useScope();
  const { data: companies } = useCompanies();
  const [picked, setPicked] = useState<string | null | undefined>(undefined);
  const raw = picked !== undefined ? picked : scope;
  const company = companies?.find((c) => c.code === raw)?.kind === 'holding' ? null : raw;
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [due, setDue] = useState(false);
  const q = useOutcomes({ company, verdict, due });
  const all = useOutcomes({ company });
  const rows = useMemo(() => q.data?.pages.flatMap((p) => p.items) ?? [], [q.data]);
  const every = useMemo(() => all.data?.pages.flatMap((p) => p.items) ?? [], [all.data]);
  const groups = useMemo(() => {
    const m = new Map<string, OutcomeReview[]>();
    for (const r of rows) m.set(r.decision, [...(m.get(r.decision) ?? []), r]);
    return [...m.entries()].map(([decision, rs]) => ({ decision, rs: rs.sort((a, b) => a.day - b.day) }));
  }, [rows]);
  const by = (v: Verdict) => every.filter((r) => r.verdict === v).length;
  const people = useMemo(() => {
    const m = new Map<string, OutcomeReview[]>();
    for (const r of every) m.set(r.proposer.code, [...(m.get(r.proposer.code) ?? []), r]);
    return [...m.values()].map((rs) => ({ a: rs[0]!.proposer, acc: accuracy(rs), n: rs.filter((r) => r.verdict === 'met' || r.verdict === 'partly' || r.verdict === 'missed').length })).sort((a, b) => (b.acc ?? -1) - (a.acc ?? -1));
  }, [every]);
  return (
    <>
      <PageHeader eyebrow="قول هر تصمیم در ۳۰، ۶۰ و ۹۰ روز با عدد سنجیده میشود" title="بازبینی نتیجه">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">با KPI حکم را کد میدهد: «رسید» در هدف، «نیمه‌راه» از نیمه‌ی فاصله به بعد، وگرنه «نرسید». بی‌KPI، پیشنهاددهنده یادداشت و شاهد میدهد و ناظر حکم میکند. دقت پیش‌بینی مدیرها و مدیرعامل‌ها از همین حکم‌هاست.</p>
      </PageHeader>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="رسید" value={<span className="fig">{by('met')}</span>} tone="pos" />
        <StatTile label="نیمه‌راه" value={<span className="fig">{by('partly')}</span>} tone="warn" />
        <StatTile label="نرسید" value={<span className="fig">{by('missed')}</span>} tone="neg" />
        <StatTile label="منتظر سنجش یا حکم" value={<span className="fig">{by('pending') + by('unmeasurable')}</span>} />
      </div>
      <div className="flex flex-col gap-2">
        <ScopeChips value={company} onChange={setPicked} allLabel="همه‌ی شرکت‌ها" holding={false} />
        <div className="flex flex-wrap gap-2">
          <FilterChip selected={!verdict} onClick={() => setVerdict(null)}>همه‌ی حکم‌ها</FilterChip>
          {VERDICTS.map((v) => <FilterChip key={v} selected={verdict === v} onClick={() => setVerdict(v)}>{VERDICT[v]!.fa}</FilterChip>)}
          <FilterChip selected={due} onClick={() => setDue(!due)}>فقط موعدرسیده</FilterChip>
        </div>
      </div>
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex min-w-0 flex-col gap-3">
          {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-64" /> : !groups.length ? <Card><Empty icon="refresh" title="بازبینی‌ای نیست" /></Card> : groups.map(({ decision, rs }) => {
            const e = rs[0]!.expected;
            return (
              <Card key={decision} as="article" className="flex min-w-0 flex-col gap-3 p-4">
                <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
                  <CompanyMark code={rs[0]!.company} height={13} mono /><RefChip r={decision} /><span className="flex items-center gap-1.5"><ActorAvatar a={rs[0]!.proposer} size={18} />{ACTOR_FA(rs[0]!.proposer)}</span>
                </div>
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <h2 className="text-[15px] font-semibold text-ink">{e.metric_fa}</h2>
                  <span className="fig text-[13px] text-sec">{kpiFig(e.baseline, unit(e.metric_fa))} → {kpiFig(e.target, unit(e.metric_fa))}</span>
                  <span className="text-[12px] text-muted">تا {e.by_days} روز{e.kpi ? <> · <span className="fig">KPI {e.kpi}</span></> : ' · بی‌KPI'}</span>
                </div>
                <div className="grid gap-2 sm:grid-cols-3">{rs.map((r) => <Review key={r.ref} r={r} />)}</div>
              </Card>
            );
          })}
        </div>
        <Card className="flex flex-col gap-3 p-4">
          <SectionTitle title="دقت پیش‌بینی" note="رسید ۱، نیمه‌راه نیم، نرسید صفر" />
          {!people.length ? <p className="text-[12px] text-muted">هنوز حکمی نیست.</p> : (
            <ul className="flex flex-col gap-2.5">
              {people.map((p) => (
                <li key={p.a.code} className="flex items-center gap-2.5">
                  <ActorAvatar a={p.a} size={28} />
                  <span className="flex min-w-0 flex-1 flex-col"><span className="truncate text-[13px] font-semibold">{ACTOR_FA(p.a)}</span><span className="text-[11px] text-muted">{p.n} حکم سنجیده</span></span>
                  <span className={cx('fig text-[15px] font-semibold', p.acc == null ? 'text-muted' : p.acc >= 0.7 ? 'text-pos' : p.acc >= 0.4 ? 'text-warn' : 'text-neg')}>{pct01(p.acc)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
