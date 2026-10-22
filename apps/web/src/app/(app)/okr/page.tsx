'use client';

import { useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Md } from '@/components/ui/md';
import { Bar, Card, Empty, ErrorState, FilterChip, PageHeader, Pill, Skeleton } from '@/components/ui/primitives';
import { ActorAvatar, OBJECTIVE_STATUS, RefChip, ScopeChips, pct01 } from '@/components/v17/bits';
import { useCompanies } from '@/lib/api/hooks';
import { okrProgress, useOkr, type KeyResult, type Objective } from '@/lib/api/v17';
import { ACTOR_FA } from '@/lib/labels';
import { useScope } from '@/lib/scope';
import { useNow } from '@/lib/store';
import { ago, cx, jDate } from '@/lib/format';

const CHECKIN_DAYS = 14;
const n = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1));
const quarterFa = (q: string) => { const m = /^(\d{4})-Q(\d)$/.exec(q); return m ? `فصل ${['', 'اول', 'دوم', 'سوم', 'چهارم'][Number(m[2])] ?? m[2]} ${m[1]}` : q; };

function KrRow({ k }: { k: KeyResult }) {
  const now = useNow();
  const last = [...k.checkins].sort((a, b) => b.at.localeCompare(a.at))[0];
  const late = !!now && (!last || now - Date.parse(last.at) > CHECKIN_DAYS * 86_400_000);
  return (
    <li className="flex flex-col gap-2 border-t border-div py-3 first:border-0">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
        <span className="fig pt-0.5 text-[11px] text-muted">{k.ref}</span>
        <span className="flex min-w-0 flex-[1_1_12rem] flex-col gap-0.5">
          <span className="text-[14px] font-semibold text-ink">{k.title_fa}</span>
          <span className="text-[12px] text-muted">{k.kpi ? <>از KPI <span className="fig text-sec">{k.kpi}</span></> : k.metric_fa}</span>
        </span>
        <span className="fig text-[13px] text-sec">{n(k.start)} → <span className="font-semibold text-ink">{k.current == null ? '—' : n(k.current)}</span> → {n(k.target)}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="flex-1"><Bar pct={k.progress * 100} tone={k.progress >= 0.7 ? 'pos' : k.progress >= 0.3 ? 'gold' : 'warn'} label={`پیشرفت ${k.title_fa}`} /></span>
        <span className="fig w-10 text-[12px] font-semibold text-ink">{pct01(k.progress)}</span>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted">
        <span>اطمینان <span className="fig text-sec">{pct01(k.confidence)}</span></span>
        <span>وزن <span className="fig text-sec">{k.weight}</span></span>
        <span className={cx('flex items-center gap-1', late && 'text-warn')}>{late ? <Icon name="time" size={12} /> : null}{last ? <>آخرین check-in {now ? ago(last.at, now) : jDate(last.at)}{late ? `؛ بیش از ${CHECKIN_DAYS} روز` : ''}</> : 'هنوز check-in ندارد'}</span>
      </div>
      {k.checkins.length ? (
        <details className="text-[12px]">
          <summary className="cursor-pointer text-sec">check-inها ({k.checkins.length})</summary>
          <ul className="mt-2 flex flex-col gap-2">
            {[...k.checkins].sort((a, b) => b.at.localeCompare(a.at)).map((c, i) => (
              <li key={i} className="flex gap-2 rounded-[10px] bg-tile p-2">
                <ActorAvatar a={c.by} size={22} />
                <span className="flex min-w-0 flex-1 flex-col gap-1">
                  <span className="text-muted">{ACTOR_FA(c.by)}، {jDate(c.at)} · اطمینان <span className="fig">{pct01(c.confidence)}</span></span>
                  <Md text={c.note_md} className="text-[12px] leading-6 text-sec" />
                  {c.evidence.length ? <span className="flex flex-wrap gap-1">{c.evidence.map((e, j) => <RefChip key={j} r={e.ref} tone="neutral" />)}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </li>
  );
}

function ObjectiveCard({ o }: { o: Objective }) {
  const { data: companies } = useCompanies();
  const st = OBJECTIVE_STATUS[o.status] ?? { fa: o.status, tone: 'neutral' as const };
  const p = okrProgress(o);
  return (
    <Card as="article" className={cx('flex min-w-0 flex-col gap-3 p-4 md:p-5', o.status === 'closed' && 'opacity-75')}>
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
        <CompanyMark code={o.company} height={13} mono /><span className="text-sec">{companies?.find((c) => c.code === o.company)?.name_fa ?? o.company}</span>
        <span>{quarterFa(o.quarter)}</span><span className="fig">{o.ref}</span>
        <span className="flex-1" />
        {o.decision ? <RefChip r={o.decision} note="مُهر" tone="neutral" /> : null}
        <Pill tone={st.tone} dot>{st.fa}</Pill>
      </div>
      <div className="flex items-start gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="text-h3 font-semibold text-ink">{o.title_fa}</h2>
          <Md text={o.why_md} className="text-[13px] leading-6 text-sec" />
          <span className="flex items-center gap-2 pt-1 text-[12px] text-muted"><ActorAvatar a={o.owner} size={20} />{ACTOR_FA(o.owner)}</span>
        </div>
        <div className="flex w-20 flex-none flex-col items-center gap-1 rounded-[14px] bg-tile py-3">
          <span className="fig text-[22px] font-semibold leading-7">{pct01(p)}</span>
          <span className="text-[10px] text-muted">پیشرفت وزنی</span>
        </div>
      </div>
      <ul className="flex flex-col">{o.key_results.map((k) => <KrRow key={k.ref} k={k} />)}</ul>
    </Card>
  );
}

/** OKR (contract §20.5): each company's objectives by Jalali quarter. A CEO drafts, only the owner's seal makes it active. */
export default function OkrPage() {
  const { company: scope } = useScope();
  const { data: companies } = useCompanies();
  const [picked, setPicked] = useState<string | null | undefined>(undefined);
  const raw = picked !== undefined ? picked : scope;
  const company = companies?.find((c) => c.code === raw)?.kind === 'holding' ? null : raw;
  const q = useOkr({ company });
  const all = useMemo(() => q.data ?? [], [q.data]);
  const quarters = useMemo(() => [...new Set(all.map((o) => o.quarter))].sort().reverse(), [all]);
  const current = quarters.find((x) => all.some((o) => o.quarter === x && o.status === 'active')) ?? quarters[0] ?? null;
  const [quarter, setQuarter] = useState<string | null>(null);
  const qtr = quarter ?? current;
  const list = all.filter((o) => !qtr || o.quarter === qtr).sort((a, b) => a.company.localeCompare(b.company));
  const without = (companies ?? []).filter((c) => c.kind !== 'holding' && (!company || c.code === company) && !list.some((o) => o.company === c.code && o.status === 'active'));
  return (
    <>
      <PageHeader eyebrow="هدف‌های فصل هر شرکت؛ فقط مُهر تو فعالشان میکند" title="OKR">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">مدیرعامل در ماه آخر هر فصل OKR فصل بعد را پیش‌نویس میکند و کارتش به کارتابل تو میاید؛ بی‌مُهر، فصل بی‌OKR میماند. نتیجه‌ی کلیدی وصل به KPI مقدارش را از همان KPI میگیرد و هر ۱۴ روز یک check-in میخواهد.</p>
      </PageHeader>
      <div className="flex flex-col gap-2">
        <ScopeChips value={company} onChange={setPicked} allLabel="همه‌ی شرکت‌ها" holding={false} />
        {quarters.length ? <div className="flex flex-wrap gap-2">{quarters.map((x) => <FilterChip key={x} selected={qtr === x} onClick={() => setQuarter(x)}>{quarterFa(x)}</FilterChip>)}</div> : null}
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-80" /> : !list.length && !without.length ? <Empty icon="planner" title="OKRی نیست" /> : (
        <div className="grid items-start gap-4 xl:grid-cols-2">
          {list.map((o) => <ObjectiveCard key={o.ref} o={o} />)}
          {qtr === current ? without.map((c) => (
            <Card key={c.code} className="flex items-start gap-3 p-4 text-[13px] text-sec">
              <span className="pt-0.5"><CompanyMark code={c.code} height={14} mono /></span>
              <span className="flex flex-col gap-1"><span className="font-semibold text-ink">{c.name_fa}: بدون OKR فعال در {qtr ? quarterFa(qtr) : 'این فصل'}</span><span>تحقق KPI در امتیاز شرکت از سهم KPIهای کارت امتیاز که به هدف رسیده‌اند حساب میشود.</span></span>
            </Card>
          )) : null}
        </div>
      )}
    </>
  );
}
