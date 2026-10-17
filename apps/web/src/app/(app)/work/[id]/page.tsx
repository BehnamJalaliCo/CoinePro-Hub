'use client';

import Link from 'next/link';
import { use } from 'react';
import { Avatar } from '@/components/brand/avatar';
import { CompanyMark } from '@/components/brand/marks';
import { Bar, Card, ErrorState, PageHeader, Pill, Skeleton, budgetTone } from '@/components/ui/primitives';
import { useWork } from '@/lib/api/hooks';
import { ACTOR_FA, WORK_KIND, WORK_STATUS } from '@/lib/labels';
import { ago, cx, jDateTime, tokens, usd } from '@/lib/format';

/** One work item and its delegation path (D2·2): owner → CEO → manager → employee, depth ≤ 2. */
export default function WorkPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const q = useWork(id);
  if (q.isLoading) return <div className="flex flex-col gap-4"><Skeleton className="h-20" /><Skeleton className="h-64" /></div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const w = q.data!;
  const pct = w.budget.tokens ? (w.budget.tokens_used / w.budget.tokens) * 100 : null;
  return (
    <>
      <PageHeader eyebrow={<span className="inline-flex items-center gap-2"><CompanyMark code={w.company} height={12} mono /><span className="fig">{w.ref}</span>، {WORK_KIND[w.kind] ?? w.kind}</span>} title={w.title} />
      <div className="flex flex-wrap gap-2">
        <Pill tone={w.status === 'done' ? 'pos' : w.status === 'failed' ? 'neg' : 'neutral'} dot>{WORK_STATUS[w.status] ?? w.status}</Pill>
        <Pill tone={w.priority <= 'P1' ? 'neg' : 'neutral'}><span className="fig">{w.priority}</span></Pill>
        {w.overdue ? <Pill tone="neg" icon="urgent">عقب‌افتاده، پله‌ی {w.escalation_level}</Pill> : null}
        {w.due_at ? <Pill tone="neutral" icon="time">موعد {jDateTime(w.due_at)}</Pill> : null}
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <Card className="flex flex-col gap-4 p-5">
          <h2 className="text-[14px] font-semibold">مسیر ارجاع</h2>
          <ol className="relative flex flex-col gap-4 pr-4">
            <span className="absolute bottom-3 right-[19px] top-3 w-px bg-div" aria-hidden />
            <li className="relative flex items-center gap-3"><Avatar kind="owner" size={40} /><div className="flex flex-col"><span className="text-[13px] font-semibold">{ACTOR_FA(w.created_by)}</span><span className="text-[11px] text-muted">فرمان، {ago(w.created_at)}</span></div></li>
            {w.chain.map((s) => (
              <li key={s.id} className="relative flex items-center gap-3">
                <Avatar kind={s.assignee?.kind ?? 'employee'} dept={s.assignee?.department} size={40} state={s.status === 'in_progress' ? 'working' : 'idle'} />
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="text-[13px] font-semibold">{s.assignee?.title_fa ?? '—'} <span className="fig text-[11px] font-normal text-muted">{s.assignee?.code}</span></span>
                  <span className="text-[11px] text-muted">عمق {s.depth}، {WORK_STATUS[s.status] ?? s.status}، {ago(s.created_at)}</span>
                </div>
                <span className="fig text-[12px] text-sec">{tokens(s.tokens_used)} · {usd(s.usd_used)}</span>
              </li>
            ))}
          </ol>
          <p className="text-[12px] text-muted">ارجاع رکورد دیتابیس است، نه صحبت ایجنت با ایجنت؛ عمق بیشتر از ۲ رد میشود.</p>
        </Card>
        <div className="flex flex-col gap-4">
          <Card className="flex flex-col gap-2 p-5">
            <h2 className="text-[14px] font-semibold">بودجه</h2>
            <div className="flex items-center text-[12px] text-sec"><span className="flex-1">توکن</span><span className="fig">{tokens(w.budget.tokens_used)} / {tokens(w.budget.tokens)}</span></div>
            {pct != null ? <Bar pct={pct} tone={budgetTone(pct)} /> : null}
            <div className="flex items-center text-[12px] text-sec"><span className="flex-1">هزینه‌ی معادل</span><span className="fig">{usd(w.budget.usd_used)}{w.budget.usd ? ` / ${usd(w.budget.usd)}` : ''}</span></div>
          </Card>
          <Card className="flex flex-col gap-2 p-5">
            <h2 className="text-[14px] font-semibold">شرح</h2>
            <p className="whitespace-pre-wrap text-[14px] leading-7 text-sec">{w.brief || '—'}</p>
            {w.progress_note ? <p className={cx('rounded-[10px] bg-tile p-3 text-[13px]')}>{w.progress_note}{w.progress_pct != null ? ` (${w.progress_pct}٪)` : ''}</p> : null}
            {w.deliverable_ids.length ? <Link href="/outputs" className="text-[13px] text-gold-ink">{w.deliverable_ids.length} خروجی</Link> : null}
          </Card>
        </div>
      </div>
    </>
  );
}
