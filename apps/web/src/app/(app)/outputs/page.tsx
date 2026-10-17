'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';
import { Icon } from '@/components/icon';
import { Avatar } from '@/components/brand/avatar';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Card, Empty, ErrorState, PageHeader, Pill, Rating, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError, type Schemas } from '@/lib/api/client';
import { useDeliverable, useDeliverables, useRate } from '@/lib/api/hooks';
import { useScope } from '@/lib/scope';
import { ago, cx, jDate, tokens, usd } from '@/lib/format';

type D = Schemas['Deliverable'];

function RatePanel({ d }: { d: D }) {
  const rate = useRate();
  const toast = useToast();
  const [score, setScore] = useState(d.rating?.score ?? 0);
  const [hover, setHover] = useState<number | null>(null);
  const [comment, setComment] = useState(d.rating?.comment ?? '');
  const dirty = score !== (d.rating?.score ?? 0) || comment !== (d.rating?.comment ?? '');
  return (
    <div className="flex flex-col gap-3 rounded-[16px] bg-card p-4">
      <div className="flex items-center gap-2">
        <span className="flex-1 text-[13px] font-semibold">امتیاز تو</span>
        <span className="text-[12px] text-muted">۴۰٪ نمره‌ی کارمند</span>
      </div>
      <div className="overflow-x-auto no-scrollbar"><Rating value={score} hover={hover} onHover={setHover} onChange={setScore} label="امتیاز خروجی" /></div>
      <textarea value={comment ?? ''} onChange={(e) => setComment(e.target.value)} rows={2} maxLength={5000} placeholder="نظر کوتاه (اختیاری)؛ مستقیم به حافظه‌ی کارمند میرود" className="rounded-[10px] border border-strong bg-tile p-3 text-[14px] text-ink outline-none focus:border-gold-ink" />
      <div className="flex items-center gap-3">
        {d.rating ? <span className="flex-1 text-[12px] text-gold-ink">{d.rating.score} از ۱۰، {jDate(d.rating.rated_at)}</span> : <span className="flex-1" />}
        <Button variant="primary" icon="rate" disabled={!score || !dirty} loading={rate.isPending} onClick={async () => {
          try { await rate.mutateAsync({ ref: d.ref, score, comment: comment || undefined }); toast({ tone: 'ok', text: `امتیاز ${score} ثبت شد.` }); }
          catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' }); }
        }}>{d.rating ? 'به‌روز کن' : 'ثبت امتیاز'}</Button>
      </div>
    </div>
  );
}

function Detail({ refId }: { refId: string }) {
  const q = useDeliverable(refId);
  if (q.isLoading) return <div className="flex flex-col gap-3"><Skeleton className="h-16" /><Skeleton className="h-64" /></div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  if (!d) return null;
  const pw = (d.produced_with ?? {}) as Record<string, string>;
  const usage = (d.usage ?? {}) as Record<string, number | string>;
  return (
    <article className="flex flex-col gap-5">
      <header className="flex items-start gap-3">
        <Avatar kind={d.producer.kind} dept={d.producer.department} size={44} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="text-[12px] text-muted">{d.producer.title_fa}، <span className="fig">{d.producer.code}</span>، {ago(d.created_at)}</span>
          <h2 className="text-h2 font-semibold">{d.title}</h2>
          <div className="flex flex-wrap gap-2 pt-1">
            <Pill tone="neutral"><CompanyMark code={d.company} height={12} mono /></Pill>
            {pw.model ? <Pill tone="silver"><span className="fig">{pw.label_fa ?? `${pw.model.replace('claude-', '')} · ${pw.effort ?? ''}`}</span></Pill> : null}
            {usage.tokens ? <Pill tone="neutral"><span className="fig">{tokens(Number(usage.tokens))} tok · {usd(String(usage.usd ?? ''))}</span></Pill> : null}
            <Link href={`/work/${d.work_ref}`} className="inline-flex h-6 items-center gap-1 rounded-full bg-tile px-2.5 text-[12px] text-sec hover:text-ink"><span className="fig">{d.work_ref}</span><Icon name="next" size={12} mirror /></Link>
          </div>
        </div>
      </header>
      <div className="rounded-[14px] bg-gold-soft p-4 text-[14px] leading-7 text-ink">{d.summary}</div>
      <Md text={d.body} />
      {Array.isArray(d.evidence) && d.evidence.length ? (
        <section className="flex flex-col gap-2">
          <h3 className="text-[12px] font-semibold text-gold-ink">شاهد</h3>
          <ul className="flex flex-col gap-1">{(d.evidence as Array<Record<string, string>>).map((e, i) => <li key={i} className="flex items-center gap-2 text-[13px] text-sec"><Icon name="seal" size={14} /><span className="fig">{e.kind}</span><span className="fig text-muted">{e.ref}</span>{e.note ? <span className={/[A-Za-z]/.test(e.note) ? 'fig' : undefined}>{e.note}</span> : null}</li>)}</ul>
        </section>
      ) : null}
      <RatePanel d={d} />
    </article>
  );
}

function OutputsInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { company } = useScope();
  const [tab, setTab] = useState<'unrated' | 'all'>('unrated');
  const q = useDeliverables({ company: company ? [company] : undefined, unrated: tab === 'unrated' ? true : undefined });
  const items = q.data?.items ?? [];
  const sel = params.get('ref') ?? items[0]?.ref ?? null;
  return (
    <>
      <PageHeader eyebrow="کارتابل خروجی" title="خروجی‌ها">
        <div className="max-w-xs"><Segmented label="نمایش" value={tab} onChange={setTab} options={[{ value: 'unrated', label: 'بی‌امتیاز' }, { value: 'all', label: 'همه' }]} /></div>
      </PageHeader>
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(300px,400px)_minmax(0,1fr)]">
        <Card className="flex flex-col gap-1 p-2 lg:sticky lg:top-20">
          {q.isLoading ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="m-1 h-16" />)
            : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
            : !items.length ? <Empty icon="deliverable" title={tab === 'unrated' ? 'همه‌ی خروجی‌ها امتیاز گرفته‌اند' : 'هنوز خروجی‌ای نیست'} />
            : items.map((d) => (
              <button key={d.ref} type="button" onClick={() => router.replace(`/outputs?ref=${d.ref}`, { scroll: false })} className={cx('flex items-start gap-3 rounded-[12px] p-3 text-right transition-colors', sel === d.ref ? 'tahrir bg-gold-soft' : 'hover:bg-hover')}>
                <Avatar kind={d.producer.kind} dept={d.producer.department} size={34} />
                <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="truncate text-[14px] font-semibold">{d.title}</span>
                  <span className="line-clamp-2 text-[12px] leading-5 text-muted">{d.summary}</span>
                  <span className="flex items-center gap-2 pt-0.5 text-[11px] text-muted"><CompanyMark code={d.company} height={11} mono />{ago(d.created_at)}</span>
                </div>
                {d.rating ? <span className="flex size-8 flex-none items-center justify-center bg-gold text-[12px] font-bold text-on-gold" style={{ clipPath: 'polygon(30% 0,70% 0,100% 30%,100% 70%,70% 100%,30% 100%,0 70%,0 30%)' }}>{d.rating.score}</span> : null}
              </button>
            ))}
        </Card>
        <Card className="p-5 lg:p-7">{sel ? <Detail key={sel} refId={sel} /> : <Empty icon="deliverable" title="یک خروجی را انتخاب کن" />}</Card>
      </div>
    </>
  );
}

export default function OutputsPage() {
  return <Suspense><OutputsInner /></Suspense>;
}
