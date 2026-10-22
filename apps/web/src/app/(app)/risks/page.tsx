'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense, useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ActorAvatar, CoMark, RISK_CATEGORY, RISK_STATUS, RefChip, ScopeChips, daysFrom, scoreTone } from '@/components/v17/bits';
import { useCompanies } from '@/lib/api/hooks';
import { faError, reviewDays, useRiskAction, useRiskMatrix, useRisks, type Risk, type RiskCategory, type RiskStatus } from '@/lib/api/v17';
import { ACTOR_FA } from '@/lib/labels';
import { useScope } from '@/lib/scope';
import { useNow } from '@/lib/store';
import { cx, jDate } from '@/lib/format';

const CATEGORIES = Object.keys(RISK_CATEGORY) as RiskCategory[];
const STATUSES: RiskStatus[] = ['open', 'mitigating', 'accepted', 'closed'];
const field = 'w-full rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink';
const LEVEL = ['خیلی کم', 'کم', 'متوسط', 'زیاد', 'خیلی زیاد'];
const cellTone = (s: number) => (s >= 15 ? 'bg-neg-soft text-neg' : s >= 8 ? 'bg-warn-soft text-warn' : 'bg-tile text-sec');
const cn = (s: number) => `border-transparent ${cellTone(s)}`;

function ScoreBadge({ r }: { r: Pick<Risk, 'score' | 'likelihood' | 'impact'> }) {
  const t = scoreTone(r.score);
  return (
    <span className={cx('flex size-12 flex-none flex-col items-center justify-center rounded-[12px]', t === 'neg' ? 'bg-neg-soft text-neg' : t === 'warn' ? 'bg-warn-soft text-warn' : 'bg-tile text-sec')} aria-label={`امتیاز ${r.score}`}>
      <span className="fig text-[18px] font-bold leading-6">{r.score}</span>
      <span className="fig text-[10px] opacity-80">{r.likelihood}×{r.impact}</span>
    </span>
  );
}

/** The 5 × 5 counts: likelihood up the side, impact along the bottom (left to right, like every data chart). */
function Matrix({ company, cell, onCell }: { company: string | null; cell: [number, number] | null; onCell: (c: [number, number] | null) => void }) {
  const q = useRiskMatrix(company);
  const counts = q.data?.counts;
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="ماتریس ریسک" note="ریسک‌های باز، در حال کاهش و پذیرفته" action={cell ? <Button size="sm" variant="ghost" onClick={() => onCell(null)}>همه</Button> : null} />
      {!counts ? <Skeleton className="h-64" /> : (
        <div className="flex gap-2">
          <span className="flex w-4 items-center justify-center text-[11px] text-muted [writing-mode:vertical-rl]">احتمال</span>
          <div className="flex flex-1 flex-col gap-1.5">
            <div className="grid grid-cols-5 gap-1.5" dir="ltr">
              {[5, 4, 3, 2, 1].flatMap((l) => [1, 2, 3, 4, 5].map((i) => {
                const n = counts[l - 1]?.[i - 1] ?? 0;
                const on = cell?.[0] === l && cell?.[1] === i;
                return (
                  <button key={`${l}-${i}`} type="button" onClick={() => onCell(on ? null : [l, i])} aria-label={`احتمال ${l}، اثر ${i}: ${n} ریسک`} aria-pressed={on}
                    className={cx('flex aspect-square items-center justify-center rounded-[8px] border text-[15px] font-semibold transition-colors', n ? cn(l * i) : 'border-div bg-transparent text-muted', on && 'ring-2 ring-[var(--hq-gold-ink)]')}>
                    <span className="fig">{n || ''}</span>
                  </button>
                );
              }))}
            </div>
            <div className="grid grid-cols-5 gap-1.5 text-center text-[10px] text-muted" dir="ltr">{[1, 2, 3, 4, 5].map((i) => <span key={i} className="fig">{i}</span>)}</div>
            <span className="text-center text-[11px] text-muted">اثر</span>
          </div>
        </div>
      )}
      <p className="text-[11px] leading-5 text-muted">امتیاز = احتمال × اثر. از ۱۵ به بالا بازبینی هر ۱۴ روز و راه کاهش یا پذیرش تو لازم است؛ از ۸ به بالا هر ۳۰ روز؛ بقیه ۹۰ روز.</p>
    </Card>
  );
}

function RiskCard({ r, hi, onEdit }: { r: Risk; hi: boolean; onEdit: () => void }) {
  const now = useNow();
  const st = RISK_STATUS[r.status] ?? { fa: r.status, tone: 'neutral' as const };
  const review = now ? daysFrom(r.review_at, now) : null;
  const bare = r.score >= 15 && !r.mitigation_md && !r.accepted && r.status !== 'closed';
  return (
    <Card as="article" id={r.ref} className={cx('flex min-w-0 flex-col gap-3 p-4', hi && 'ring-2 ring-[var(--hq-gold-ink)]', r.status === 'closed' && 'opacity-70')}>
      <div className="flex items-start gap-3">
        <ScoreBadge r={r} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex flex-wrap items-center gap-2 text-[12px] text-muted"><CoMark code={r.company} /><span>{RISK_CATEGORY[r.category] ?? r.category}</span><span className="fig">{r.ref}</span><span className="flex-1" /><Pill tone={st.tone} dot className="h-5 text-[11px]">{st.fa}</Pill></span>
          <h2 className="text-[15px] font-semibold leading-7 text-ink">{r.title_fa}</h2>
          <Md text={r.body_md} className="text-[13px] leading-6 text-sec" />
        </div>
      </div>
      {bare ? <p className="flex items-start gap-2 rounded-[10px] bg-neg-soft p-2.5 text-[12px] leading-6 text-ink"><span className="text-neg"><Icon name="urgent" size={14} /></span>امتیاز بالای ۱۵ بی‌راه کاهش و بی‌پذیرش: یا راه کاهش، یا کارت «پذیرش ریسک» (با اثر انگشت، حداکثر ۹۰ روز).</p> : null}
      {r.mitigation_md ? <div className="rounded-[10px] bg-tile p-2.5"><span className="text-[11px] font-semibold text-gold-ink">راه کاهش</span><Md text={r.mitigation_md} className="text-[13px] leading-6 text-sec" /></div> : null}
      {r.accepted ? <p className="flex flex-wrap items-center gap-2 text-[12px] text-sec">پذیرفته تا {jDate(r.accepted.until, true)}<RefChip r={r.accepted.decision} /></p> : null}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[12px] text-muted">
        <span className="flex items-center gap-1.5"><ActorAvatar a={r.owner} size={20} />{ACTOR_FA(r.owner)}</span>
        {r.status !== 'closed' && review != null ? <span className={cx(review < 0 && 'font-semibold text-neg')}>{review < 0 ? `بازبینی ${-review} روز گذشته` : `بازبینی ${jDate(r.review_at)}`}</span> : null}
        {Object.entries(r.links).filter(([, v]) => v).map(([k, v]) => <RefChip key={k} r={String(v)} tone="neutral" />)}
        <span className="flex-1" />
        {r.status !== 'closed' ? <Button size="sm" variant="ghost" icon="edit" onClick={onEdit}>ویرایش</Button> : null}
      </div>
      {r.history.length > 1 ? (
        <details className="text-[12px]"><summary className="cursor-pointer text-sec">تاریخچه ({r.history.length})</summary>
          <ul className="mt-2 flex flex-col gap-1">{r.history.map((h, i) => <li key={i} className="flex flex-wrap gap-2 text-muted"><span>{jDate(h.at)}</span><span className="text-sec">{ACTOR_FA(h.by)}</span><span className="text-ink">{h.change}</span>{h.note ? <span>{h.note}</span> : null}</li>)}</ul>
        </details>
      ) : null}
    </Card>
  );
}

function RiskSheet({ r, onClose }: { r: Risk | null; onClose: () => void }) {
  const act = useRiskAction();
  const toast = useToast();
  const now = useNow();
  const { data: companies } = useCompanies();
  const [company, setCompany] = useState<string | null>(r?.company ?? null);
  const [title, setTitle] = useState(r?.title_fa ?? '');
  const [body, setBody] = useState(r?.body_md ?? '');
  const [category, setCategory] = useState<RiskCategory>(r?.category ?? 'ops');
  const [l, setL] = useState(r?.likelihood ?? 3);
  const [i, setI] = useState(r?.impact ?? 3);
  const [status, setStatus] = useState<RiskStatus>(r?.status ?? 'open');
  const [mit, setMit] = useState(r?.mitigation_md ?? '');
  const [review, setReview] = useState(r ? r.review_at.slice(0, 10) : '');
  const score = l * i;
  const max = now ? new Date(now + reviewDays(score) * 86_400_000).toISOString().slice(0, 10) : '';
  const reviewBad = !!review && !!max && review > max;
  const valid = !!company && title.trim().length > 3 && !reviewBad;
  const save = () => (r
    ? act.patch.mutateAsync({ r, patch: { likelihood: l, impact: i, status, mitigation_md: mit.trim() || null, ...(review ? { review_at: `${review}T08:30:00Z` } : {}), title_fa: title.trim(), body_md: body.trim(), category } })
    : act.create.mutateAsync({ company: company!, title_fa: title.trim(), body_md: body.trim(), category, likelihood: l, impact: i, mitigation_md: mit.trim() || null, ...(review ? { review_at: `${review}T08:30:00Z` } : {}) }))
    .then((x) => { toast({ tone: 'ok', text: <>ریسک <span className="fig">{x.ref}</span> {r ? 'به‌روز شد' : 'ثبت شد؛ نگه‌دارش بازرس کل است'}.</> }); onClose(); })
    .catch((e) => toast({ tone: 'error', text: faError(e) }));
  const pick = (v: number, set: (n: number) => void, label: string) => (
    <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">{label}</span><div className="flex flex-wrap gap-1.5">{[1, 2, 3, 4, 5].map((n) => <FilterChip key={n} selected={v === n} onClick={() => set(n)}>{n} · {LEVEL[n - 1]}</FilterChip>)}</div></div>
  );
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={r ? <>ویرایش <span className="fig">{r.ref}</span></> : 'ریسک تازه'} description="بستن ریسک فقط با تأیید بازرس کل است." width={580}
      footer={<Button variant="primary" className="w-full" disabled={!valid} loading={act.patch.isPending || act.create.isPending} onClick={() => void save()}>ذخیره</Button>}>
      <div className="flex flex-col gap-4 text-[13px]">
        {!r ? <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">شرکت</span><div className="flex flex-wrap gap-2">{(companies ?? []).map((c) => <FilterChip key={c.code} selected={company === c.code} onClick={() => setCompany(c.code)}>{c.name_fa}</FilterChip>)}</div></div> : null}
        <label className="flex flex-col gap-1.5 font-semibold text-sec">عنوان<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} className={cx(field, 'h-10')} /></label>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">شرح<textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} className={cx(field, 'py-2 leading-7')} /></label>
        <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">دسته</span><div className="flex flex-wrap gap-1.5">{CATEGORIES.map((c) => <FilterChip key={c} selected={category === c} onClick={() => setCategory(c)}>{RISK_CATEGORY[c]}</FilterChip>)}</div></div>
        {pick(l, setL, 'احتمال')}
        {pick(i, setI, 'اثر')}
        <p className="flex items-center gap-2 text-sec">امتیاز <span className={cx('fig rounded-[8px] px-2 py-0.5 font-bold', cellTone(score))}>{score}</span> · بازبینی حداکثر هر {reviewDays(score)} روز</p>
        {r ? <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">وضعیت</span><div className="flex flex-wrap gap-2">{(['open', 'mitigating'] as const).map((s) => <FilterChip key={s} selected={status === s} onClick={() => setStatus(s)}>{RISK_STATUS[s]!.fa}</FilterChip>)}</div><span className="text-[11px] text-muted">پذیرش با کارت «پذیرش ریسک» در کارتابل است و بستن با بازرس کل.</span></div> : null}
        <label className="flex flex-col gap-1.5 font-semibold text-sec">راه کاهش<textarea value={mit} onChange={(e) => setMit(e.target.value)} rows={3} className={cx(field, 'py-2 leading-7')} /></label>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">بازبینی بعدی
          <input type="date" dir="ltr" value={review} max={max} onChange={(e) => setReview(e.target.value)} className={cx(field, 'fig h-10', reviewBad && 'border-[var(--hq-neg-line)]')} />
          {reviewBad ? <span className="text-[11px] font-normal text-neg">برای امتیاز {score} حداکثر {reviewDays(score)} روز بعد.</span> : null}
        </label>
      </div>
    </Sheet>
  );
}

function RisksInner() {
  const params = useSearchParams();
  const hi = params.get('ref');
  const { company: scope } = useScope();
  const [picked, setPicked] = useState<string | null | undefined>(undefined);
  const company = picked !== undefined ? picked : scope;
  const [status, setStatus] = useState<RiskStatus | null>(null);
  const [category, setCategory] = useState<RiskCategory | null>(null);
  const [cell, setCell] = useState<[number, number] | null>(null);
  const [edit, setEdit] = useState<Risk | 'new' | null>(null);
  const q = useRisks({ company, status, category });
  const all = useMemo(() => q.data?.pages.flatMap((p) => p.items) ?? [], [q.data]);
  const list = all.filter((r) => !cell || (r.likelihood === cell[0] && r.impact === cell[1]));
  return (
    <>
      <PageHeader eyebrow="نگه‌دار دفتر: بازرس کل (QC)" title="دفتر ریسک" actions={<Button variant="primary" icon="add" onClick={() => setEdit('new')}>ریسک تازه</Button>}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">یافته‌ی بحرانی و هر کالبدشکافی خودشان پیش‌نویس ریسک میسازند. بازبینی دیرکرده اول کار پاسخ‌گو میشود و بعد یافته‌ی ناظر.</p>
      </PageHeader>
      <div className="flex flex-col gap-2">
        <ScopeChips value={company} onChange={setPicked} allLabel="همه" />
        <div className="flex flex-wrap gap-2"><FilterChip selected={!status} onClick={() => setStatus(null)}>همه‌ی وضعیت‌ها</FilterChip>{STATUSES.map((s) => <FilterChip key={s} selected={status === s} onClick={() => setStatus(s)}>{RISK_STATUS[s]!.fa}</FilterChip>)}</div>
        <div className="flex flex-wrap gap-2"><FilterChip selected={!category} onClick={() => setCategory(null)}>همه‌ی دسته‌ها</FilterChip>{CATEGORIES.map((c) => <FilterChip key={c} selected={category === c} onClick={() => setCategory(c)}>{RISK_CATEGORY[c]}</FilterChip>)}</div>
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-3">
          {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-64" /> : !list.length ? <Card><Empty icon="urgent" title="ریسکی پیدا نشد" /></Card> : list.map((r) => <RiskCard key={r.ref} r={r} hi={hi === r.ref} onEdit={() => setEdit(r)} />)}
        </div>
        <div className="order-first lg:order-none"><Matrix company={company} cell={cell} onCell={setCell} /></div>
      </div>
      {edit ? <RiskSheet r={edit === 'new' ? null : edit} onClose={() => setEdit(null)} /> : null}
    </>
  );
}

/** دفتر ریسک (contract §20.8). */
export default function RisksPage() {
  return <Suspense><RisksInner /></Suspense>;
}
