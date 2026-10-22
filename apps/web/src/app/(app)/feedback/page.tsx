'use client';

import Link from 'next/link';
import { useState } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { CompanyChips, FEEDBACK_KIND, FEEDBACK_STATE, Masked } from '@/components/v16/bits';
import { useCompanies } from '@/lib/api/hooks';
import { faError, useFeedback, useFeedbackAction, type FeedbackItem, type FeedbackKind, type FeedbackState } from '@/lib/api/v16';
import { useScope } from '@/lib/scope';
import { ago, cx, jDate } from '@/lib/format';

const KINDS: FeedbackKind[] = ['bug', 'feature', 'confusion', 'complaint', 'praise'];
const STATES: FeedbackState[] = ['new', 'triaged', 'in_backlog', 'done', 'wont_do'];
const sourceHref = (s: string) => (s.startsWith('SC-') ? `/support/${s}` : s.startsWith('NP-') ? '/growth' : null);

function Item({ x }: { x: FeedbackItem }) {
  const act = useFeedbackAction();
  const toast = useToast();
  const [work, setWork] = useState('');
  const save = (patch: { state?: FeedbackState; work_ref?: string | null }, ok: string) =>
    act.mutateAsync({ item: x, patch }).then(() => { toast({ tone: 'ok', text: ok }); setWork(''); }).catch((e) => toast({ tone: 'error', text: faError(e) }));
  const k = FEEDBACK_KIND[x.kind] ?? { fa: x.kind, tone: 'neutral' as const };
  return (
    <Card as="article" className={cx('flex min-w-0 flex-col gap-3 p-4', (x.state === 'done' || x.state === 'wont_do') && 'opacity-75')}>
      <div className="flex items-start gap-3">
        <span className="flex w-14 flex-none flex-col items-center rounded-[12px] bg-tile py-2"><span className="fig text-[20px] font-semibold leading-7">{x.count}</span><span className="text-[10px] text-muted">بار</span></span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2"><Pill tone={k.tone} dot>{k.fa}</Pill><span className="fig rounded-[6px] bg-tile px-2 py-0.5 text-[11px] text-sec">{x.area}</span><CompanyMark code={x.company} height={12} mono /></div>
          <h2 className="text-[15px] font-semibold leading-7 text-ink">{x.title_fa}</h2>
          <span className="flex flex-wrap gap-x-2 text-[11px] text-muted"><span className="fig">{x.ref}</span><span>اولین بار {jDate(x.first_seen)}</span><span>آخرین بار {ago(x.last_seen)}</span></span>
        </div>
      </div>
      {x.quotes.length ? (
        <ul className="flex flex-col gap-1.5">
          {x.quotes.map((q, i) => <li key={i} className="border-s-2 border-strong ps-3"><Masked text={`«${q}»`} className="text-[13px] leading-6 text-sec" /></li>)}
        </ul>
      ) : null}
      {x.sources.length ? (
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="text-muted">منبع:</span>
          {x.sources.map((s) => { const h = sourceHref(s); return h ? <Link key={s} href={h} className="fig rounded-full bg-tile px-2 py-0.5 text-gold-ink hover:bg-hover">{s}</Link> : <span key={s} className="fig rounded-full bg-tile px-2 py-0.5 text-sec">{s}</span>; })}
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-2 border-t border-div pt-3">
        <select value={x.state} disabled={act.isPending} onChange={(e) => void save({ state: e.target.value as FeedbackState }, 'وضعیت به‌روز شد.')} aria-label={`وضعیت ${x.ref}`}
          className="h-9 rounded-[10px] border border-strong bg-tile px-2 text-[13px] text-ink outline-none focus:border-gold-ink">
          {STATES.map((s) => <option key={s} value={s}>{FEEDBACK_STATE[s]!.fa}</option>)}
        </select>
        {x.work_ref ? (
          <span className="flex items-center gap-2 text-[12px]">
            <Link href={`/work/${x.work_ref}`} className="fig rounded-full bg-gold-soft px-2.5 py-1 font-semibold text-gold-ink">{x.work_ref}</Link>
            <Button size="sm" variant="ghost" onClick={() => void save({ work_ref: null }, 'از کار جدا شد.')}>جدا کن</Button>
          </span>
        ) : (
          <span className="flex min-w-0 flex-1 items-center gap-2">
            <input value={work} onChange={(e) => setWork(e.target.value.toUpperCase().trim())} dir="ltr" placeholder="W-000123" aria-label={`کار مربوط به ${x.ref}`}
              className="fig h-9 w-32 min-w-0 rounded-[10px] border border-strong bg-tile px-3 text-[13px] text-ink outline-none focus:border-gold-ink" />
            <Button size="sm" variant="secondary" disabled={!/^W-\d{3,}$/.test(work)} onClick={() => void save({ work_ref: work, ...(x.state === 'new' || x.state === 'triaged' ? { state: 'in_backlog' as const } : {}) }, 'به کار وصل شد.')}>وصل به کار</Button>
          </span>
        )}
      </div>
    </Card>
  );
}

/** صندوق بازخورد (contract §19.7): from conversations and NPS comments, tagged by rules first; the most frequent first. */
export default function FeedbackPage() {
  const { company: scope } = useScope();
  const { data: companies } = useCompanies();
  const [picked, setPicked] = useState<string | null | undefined>(undefined);
  const company = picked !== undefined ? picked : companies?.find((c) => c.code === scope)?.kind === 'holding' ? null : scope;
  const [kind, setKind] = useState<FeedbackKind | null>(null);
  const [state, setState] = useState<FeedbackState | null>(null);
  const q = useFeedback({ company, kind, state });
  const items = [...(q.data?.pages.flatMap((p) => p.items) ?? [])].sort((a, b) => b.count - a.count);
  return (
    <>
      <PageHeader eyebrow="از گفت‌وگوهای پشتیبانی و توضیح‌های NPS؛ پرتکرارترین بالا" title="بازخورد">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">برچسب اول با کلیدواژه‌های هر شرکت (بی‌مدل) و بعد با مدل سبک در batch شبانه. موارد هم‌نوع و هم‌حوزه یکی میشوند؛ موردی که به آستانه‌ی شرکت برسد (پیش‌فرض ۵ بار در ۷ روز) یک کار برای مدیر محصول میشود. نقل‌قول‌ها ماسک‌شده‌اند.</p>
      </PageHeader>
      <div className="flex flex-col gap-2">
        <CompanyChips value={company} onChange={setPicked} />
        <div className="flex flex-wrap gap-2"><FilterChip selected={!kind} onClick={() => setKind(null)}>همه‌ی نوع‌ها</FilterChip>{KINDS.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{FEEDBACK_KIND[k]!.fa}</FilterChip>)}</div>
        <div className="flex flex-wrap gap-2"><FilterChip selected={!state} onClick={() => setState(null)}>همه‌ی وضعیت‌ها</FilterChip>{STATES.map((s) => <FilterChip key={s} selected={state === s} onClick={() => setState(s)}>{FEEDBACK_STATE[s]!.fa}</FilterChip>)}</div>
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-60" /> : !items.length ? <Empty icon="rate" title="بازخوردی نیست" /> : (
        <div className="grid items-start gap-3 lg:grid-cols-2">{items.map((x) => <Item key={x.ref} x={x} />)}</div>
      )}
      {q.hasNextPage ? <Button variant="secondary" size="sm" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>بیشتر</Button> : null}
    </>
  );
}
