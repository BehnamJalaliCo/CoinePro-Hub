'use client';

import Link from 'next/link';
import { use } from 'react';
import { Icon } from '@/components/icon';
import { Avatar } from '@/components/brand/avatar';
import { CompanyMark } from '@/components/brand/marks';
import { Card, Empty, ErrorState, PageHeader, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { EMPLOYEE_STATUS, EmployeeActions } from '@/components/v15/employee-actions';
import { RunList } from '@/components/v15/runs';
import { useEmployee } from '@/lib/api/hooks';
import { useRuns } from '@/lib/api/v15';
import { ACTIVITY, EMPLOYEE_KIND, WORK_STATUS } from '@/lib/labels';
import { ago, jDate, modelLabel } from '@/lib/format';

function Trend({ values }: { values: Array<number | null> }) {
  const v = values.map((x) => x ?? NaN);
  const ok = v.filter((x) => !Number.isNaN(x));
  if (ok.length < 2) return <span className="text-[12px] text-muted">روند هنوز کافی نیست</span>;
  const min = Math.min(...ok, 0);
  const max = Math.max(...ok, 10);
  const w = 160, h = 40;
  // Time runs left→right (market convention for data charts).
  const pts = v.map((x, i) => (Number.isNaN(x) ? null : `${(i / (v.length - 1)) * w},${h - ((x - min) / (max - min)) * h}`)).filter(Boolean).join(' ');
  return <svg style={{ direction: "ltr" }} width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-label="روند ماهانه‌ی نمره"><polyline points={pts} fill="none" stroke="var(--hq-silver-ink)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export default function EmployeePage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  const q = useEmployee(code);
  const runs = useRuns({ employee: code, limit: 20 });
  if (q.isLoading) return <div className="flex flex-col gap-4"><Skeleton className="h-28" /><Skeleton className="h-64" /></div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const e = q.data!;
  return (
    <>
      <div className="flex flex-wrap items-center gap-5">
        <Avatar kind={e.kind} dept={e.department} state={e.activity} size={88} number={e.code.split('-').at(-1)} />
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <PageHeader eyebrow={<Link href={`/companies/${e.company}`} className="inline-flex items-center gap-1.5 hover:text-ink"><CompanyMark code={e.company} height={12} mono />{e.department ?? EMPLOYEE_KIND[e.kind]}</Link>} title={e.display_name ?? e.title_fa} actions={<EmployeeActions e={e} />} />
          <div className="flex flex-wrap items-center gap-2">
            <span className="fig text-[13px] text-sec">{e.code}</span>
            <Pill tone={e.activity === 'working' ? 'pos' : e.activity === 'error' ? 'neg' : 'neutral'} dot live={e.activity === 'working'}>{ACTIVITY[e.activity] ?? e.activity}</Pill>
            {e.model ? <Pill tone="silver"><span className="fig">{modelLabel(String(e.model.model ?? ''))} · {e.model.effort}</span></Pill> : null}
            {e.status !== 'active' ? <Pill tone={e.status === 'dismissed' ? 'neg' : 'warn'}>{EMPLOYEE_STATUS[e.status] ?? e.status}</Pill> : null}
          </div>
          {e.activity_note ? <span className="text-[13px] text-muted">«{e.activity_note}»، {ago(e.activity_at)}</span> : null}
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="flex flex-col gap-3 p-5">
          <h2 className="text-[14px] font-semibold">نمره</h2>
          <div className="flex items-end gap-3"><span className="text-[36px] font-semibold leading-none">{e.score.value != null ? e.score.value.toFixed(1).replace('.', '٫') : '—'}</span><span className="pb-1 text-[12px] text-muted">از ۱۰</span></div>
          <Trend values={e.score.trend} />
          <p className="text-[12px] leading-5 text-muted">۴۰٪ امتیاز تو + ۲۵٪ انجام با شاهد + ۲۰٪ هزینه‌ی هر خروجی + ۱۵٪ به‌موقع بودن. {e.score.rank_in_department ? `رتبه‌ی ${e.score.rank_in_department} در دپارتمان.` : ''}</p>
        </Card>
        <Card className="flex flex-col gap-2 p-5">
          <h2 className="text-[14px] font-semibold">شرح کار</h2>
          {(e.duties as string[]).length ? <ul className="flex list-disc flex-col gap-1 pr-5 text-[13px] leading-6 text-sec marker:text-muted">{(e.duties as string[]).map((d) => <li key={d}>{d}</li>)}</ul> : <p className="text-[13px] text-muted">از منشور نقش.</p>}
          <div className="flex flex-wrap gap-1.5 pt-2">{(e.permissions as string[]).map((p) => <span key={p} className="fig rounded-[6px] bg-tile px-2 py-0.5 text-[11px] text-sec">{p}</span>)}</div>
          <p className="pt-2 text-[12px] text-muted">از {jDate(e.hired_at, true)}{e.hired_by_decision ? <>، با <Link href={`/cartable?ref=${e.hired_by_decision}`} className="fig text-gold-ink">{e.hired_by_decision}</Link></> : null}</p>
        </Card>
        <Card className="flex flex-col gap-2 p-5">
          <h2 className="text-[14px] font-semibold">آخرین امتیازها</h2>
          {e.recent_ratings.length ? e.recent_ratings.map((r) => (
            <Link key={r.deliverable} href={`/outputs?ref=${r.deliverable}`} className="flex items-center gap-3 rounded-[10px] p-2 hover:bg-hover">
              <span className="flex size-8 items-center justify-center bg-gold text-[12px] font-bold text-on-gold" style={{ clipPath: 'polygon(30% 0,70% 0,100% 30%,100% 70%,70% 100%,30% 100%,0 70%,0 30%)' }}>{r.score}</span>
              <span className="fig flex-1 text-[12px] text-sec">{r.deliverable}</span><span className="text-[11px] text-muted">{jDate(r.rated_at)}</span>
            </Link>
          )) : <Empty icon="rate" title="هنوز امتیازی نگرفته" />}
        </Card>
      </div>
      <Card className="flex flex-col gap-3 p-5">
        <SectionTitle title="اجراهای اخیر" note="قدم‌ها، ابزارها و مصرف هر اجرا؛ اجرای در جریان خودش تازه میشود" />
        {runs.isLoading ? <Skeleton className="h-24" /> : runs.error ? <ErrorState error={runs.error} onRetry={() => runs.refetch()} />
          : <RunList runs={runs.data?.items ?? []} showEmployee={false} empty="هنوز اجرایی ثبت نشده." />}
      </Card>
      <Card className="flex flex-col gap-1 p-2">
        <h2 className="px-3 pt-2 text-[14px] font-semibold">کارهای اخیر</h2>
        {e.recent_work.length ? e.recent_work.map((w) => (
          <Link key={w.ref} href={`/work/${w.ref}`} className="flex items-center gap-3 rounded-[12px] p-3 hover:bg-hover">
            <Icon name="task" size={18} /><span className="flex-1 truncate text-[14px]">{w.title}</span><span className="fig text-[12px] text-muted">{w.ref}</span><span className="text-[12px] text-sec">{WORK_STATUS[w.status] ?? w.status}</span>
          </Link>
        )) : <p className="px-3 pb-3 text-[13px] text-muted">کاری ثبت نشده.</p>}
      </Card>
    </>
  );
}
