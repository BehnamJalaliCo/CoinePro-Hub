'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { use, useEffect } from 'react';
import { Avatar } from '@/components/brand/avatar';
import { CompanyMark } from '@/components/brand/marks';
import { Bar, Card, ErrorState, PageHeader, Pill, SectionTitle, Skeleton, budgetTone } from '@/components/ui/primitives';
import { RunList } from '@/components/v15/runs';
import { WorkActions } from '@/components/v15/work-actions';
import { OrderTrackerCard, TimelineCard, useTrack } from '@/components/v21/orders';
import { PriorityTag } from '@/components/v21/priority';
import { CouncilCard } from '@/components/v28/council';
import { WorkSplitCard } from '@/components/v33/parallel';
import { PlayerLine } from '@/components/work/player';
import { useWorkRuns } from '@/lib/api/v15';
import { isOwnerOrder } from '@/lib/api/v21';
import { ACTOR_FA, WORK_KIND, WORK_STATUS } from '@/lib/labels';
import { isWorkRef, refPrefix, refRoute } from '@/lib/refs';
import { ago, cx, jDateTime, tokens, usd } from '@/lib/format';
import { plain } from '@/lib/plain';

/**
 * One work item and its delegation path (D2·2): owner → CEO → manager → employee, depth ≤ 2. ⟨0.4.0⟩ An order the owner gave opens with
 * its tracker (the stage on a stepper, an honest estimate, who holds it now, its outputs) and its live timeline from `/tree-events`. The
 * page takes the work's id or its ref (`W-000104`); ⟨0.5.0⟩ any other ref (`MT-0077`) goes to its own page, never to the hub as a work.
 */
export default function WorkPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: raw } = use(params);
  const id = decodeURIComponent(raw);
  const router = useRouter();
  const other = refPrefix(id) && !isWorkRef(id) ? refRoute(id) : null;
  useEffect(() => { if (other) router.replace(other); }, [other, router]);
  const { track, loading, error } = useTrack(other ? null : id, true);
  const w = track?.root;
  const runs = useWorkRuns(w?.id ?? id);
  if (other) return <Skeleton className="h-20" />;
  if (loading || (!w && !error)) return <div className="flex flex-col gap-4"><Skeleton className="h-20" /><Skeleton className="h-64" /></div>;
  if (error || !w) return <ErrorState error={error} onRetry={() => router.refresh()} />;
  const pct = w.budget.tokens ? (w.budget.tokens_used / w.budget.tokens) * 100 : null;
  const order = isOwnerOrder(w);
  return (
    <>
      <PageHeader eyebrow={<span className="inline-flex items-center gap-2"><CompanyMark code={w.company} height={12} mono />{order ? 'فرمان تو' : WORK_KIND[w.kind] ?? w.kind}</span>} title={plain(w.title)} actions={<WorkActions key={w.version} w={w} />} />
      <div className="flex flex-wrap gap-2">
        <Pill tone={w.status === 'done' ? 'pos' : w.status === 'failed' ? 'neg' : 'neutral'} dot>{WORK_STATUS[w.status] ?? w.status}</Pill>
        <PriorityTag code={w.priority} />
        {w.overdue ? <Pill tone="neg" icon="urgent">عقب‌افتاده، پله‌ی {w.escalation_level}</Pill> : null}
        {w.due_at ? <Pill tone="neutral" icon="time">موعد {jDateTime(w.due_at)}</Pill> : null}
      </div>
      {/* ⟨1.9⟩ §27.1: who plays this order, and a named player that never came. */}
      {order ? (() => { const x = w as { player?: string | null; mode?: string | null; media?: string | null; player_fallback?: boolean }; return <PlayerLine player={x.player} mode={x.mode} media={x.media} fallback={!!x.player_fallback} />; })() : null}
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          {order && track ? <OrderTrackerCard t={track} /> : null}
          {/* ⟨1.9⟩ §27.2 an order given to the council: each player, and Claude's synthesis (⟨1.10⟩ §28.4: failures in plain Persian). */}
          <CouncilCard work={w.ref} mode={(w as { mode?: string | null }).mode} title={w.title} />
          {/* ⟨1.15⟩ §33.7: a work split into parallel parts shows them side by side with the merge. */}
          <WorkSplitCard id={w.id} />
          {track ? <TimelineCard t={track} /> : null}
          <Card className="flex flex-col gap-4 p-5">
            <h2 className="text-[14px] font-semibold">مسیر ارجاع</h2>
            <ol className="relative flex flex-col gap-4 pe-4">
              <span className="absolute bottom-3 start-[19px] top-3 w-px bg-div" aria-hidden />
              <li className="relative flex items-center gap-3"><Avatar kind="owner" size={40} /><div className="flex flex-col"><span className="text-[13px] font-semibold">{ACTOR_FA(w.created_by)}</span><span className="text-[11px] text-muted">فرمان، {ago(w.created_at)}</span></div></li>
              {w.chain.map((s) => (
                <li key={s.id} className="relative flex items-center gap-3">
                  <Avatar kind={s.assignee?.kind ?? 'employee'} dept={s.assignee?.department} size={40} state={s.status === 'in_progress' ? 'working' : 'idle'} />
                  <div className="flex min-w-0 flex-1 flex-col">
                    <span className="text-[13px] font-semibold">{s.assignee?.title_fa ?? '—'}</span>
                    <span className="text-[11px] text-muted">{WORK_STATUS[s.status] ?? s.status}، {ago(s.created_at)}</span>
                  </div>
                  <span className="fig text-[12px] text-sec">{usd(s.usd_used)}</span>
                </li>
              ))}
            </ol>
            {w.children.length ? (
              <div className="flex flex-col gap-1 border-t border-div pt-3">
                <span className="text-[12px] font-semibold text-sec">کارهای زیرمجموعه</span>
                {w.children.flatMap((k) => [k, ...(k.children ?? [])]).map((k) => (
                  <Link key={k.id} href={`/work/${k.id}`} className={cx('flex items-center gap-2 rounded-[8px] px-1 py-1.5 text-[13px] hover:bg-hover', k.depth > w.depth + 1 && 'ps-6')}>
                    <span className="min-w-0 flex-1 truncate">{plain(k.title ?? '')}</span>
                    <span className="text-[11px] text-muted">{k.assignee?.title_fa}، {WORK_STATUS[k.status] ?? k.status}{k.progress != null ? `، ${Math.round(k.progress * 100)}٪` : ''}</span>
                  </Link>
                ))}
              </div>
            ) : null}
          </Card>
          {/* ⟨1.17⟩ Nothing technical to the owner: the runs are folded away, for the engineer who asks. */}
          <details className="rounded-[16px] bg-card p-5">
            <summary className="cursor-pointer text-[13px] font-semibold text-sec">جزئیات فنی اجراها</summary>
            <div className="flex flex-col gap-3 pt-3">
              {runs.isLoading ? <Skeleton className="h-24" /> : runs.error ? <ErrorState error={runs.error} onRetry={() => runs.refetch()} />
                : <RunList runs={runs.data ?? []} details={runs.data} empty="هنوز ایجنتی روی این کار اجرا نشده." />}
            </div>
          </details>
        </div>
        <div className="flex flex-col gap-4">
          <Card className="flex flex-col gap-2 p-5">
            <h2 className="text-[14px] font-semibold">بودجه</h2>
            <div className="flex items-center text-[12px] text-sec"><span className="flex-1">واحد مصرف</span><span className="fig">{tokens(w.budget.tokens_used)} / {tokens(w.budget.tokens)}</span></div>
            {pct != null ? <Bar pct={pct} tone={budgetTone(pct)} /> : null}
            <div className="flex items-center text-[12px] text-sec"><span className="flex-1">هزینه‌ی معادل</span><span className="fig">{usd(w.budget.usd_used)}{w.budget.usd ? ` / ${usd(w.budget.usd)}` : ''}</span></div>
          </Card>
          <Card className="flex flex-col gap-2 p-5">
            <h2 className="text-[14px] font-semibold">شرح</h2>
            <p className="whitespace-pre-wrap text-[14px] leading-7 text-sec">{plain(w.brief) || '—'}</p>
            {w.progress_note ? <p className="rounded-[10px] bg-tile p-3 text-[13px]">{w.progress_note}{w.progress_pct != null ? ` (${w.progress_pct}٪)` : ''}</p> : null}
            {(w.deliverable_refs ?? []).length ? (
              <div className="flex flex-wrap gap-2">{w.deliverable_refs!.map((r, i) => <Link key={r} href={`/outputs?ref=${r}`} className="rounded-full bg-gold-soft px-2.5 py-0.5 text-[12px] text-gold-ink hover:underline">خروجی <span className="fig">{i + 1}</span></Link>)}</div>
            ) : w.deliverable_ids.length ? <Link href="/outputs" className="text-[13px] text-gold-ink">{w.deliverable_ids.length} خروجی</Link> : null}
          </Card>
        </div>
      </div>
    </>
  );
}
