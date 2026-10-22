'use client';

import Link from 'next/link';
import { useState } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, PageHeader, Pill, Skeleton } from '@/components/ui/primitives';
import { downloadCsv, useResolutionList, type Resolution } from '@/lib/api/v15';
import { ACTOR_FA } from '@/lib/labels';
import { jDate, jDateTime } from '@/lib/format';
import { useScope } from '@/lib/scope';

/** Where a resolution came from: the sealed decision or the owner's message it was recorded from (§5.4). */
function Source({ r }: { r: Resolution }) {
  const d = r.source?.decision; const m = r.source?.message;
  if (d) return <Link href={`/cartable?ref=${d}`} className="fig text-gold-ink hover:underline">{d}</Link>;
  if (m) return <span className="text-sec">از پیام <span className="fig">{m}</span></span>;
  return null;
}

/** The resolutions book (دفتر مصوبات): every sealed decision and every resolution the owner recorded, one numbered, append-only ledger. */
export default function ResolutionsPage() {
  const { company } = useScope();
  const [q, setQ] = useState('');
  const list = useResolutionList({ q: q.trim().length >= 2 ? q.trim() : undefined, company });
  const [open, setOpen] = useState<Resolution | null>(null);
  const items = list.data?.items ?? [];
  const exportCsv = () => downloadCsv('resolutions.csv', ['ref', 'company', 'title', 'body', 'source', 'sealed_at', 'sent_to'],
    items.map((r) => [r.ref, r.company ?? 'HQ', r.title, r.body, r.source?.decision ?? r.source?.message ?? '', r.sealed_at, r.sent_to.join(' ')]));
  return (
    <>
      <PageHeader eyebrow="هر تصمیم مُهرشده و هر مصوبه‌ای که تو ثبت کردی؛ شماره‌دار و تغییرناپذیر" title="دفتر مصوبات"
        actions={items.length ? <Button variant="secondary" size="sm" icon="download" onClick={exportCsv}>Excel</Button> : null}>
        <label className="flex h-11 max-w-md items-center gap-2 rounded-[12px] border border-strong bg-tile px-3 text-sec focus-within:border-gold-ink">
          <Icon name="search" size={18} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="جستجو در عنوان و متن" className="h-full min-w-0 flex-1 bg-transparent text-[14px] text-ink outline-none" aria-label="جستجو در مصوبات" />
        </label>
      </PageHeader>
      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} />
        : list.isLoading ? <div className="flex flex-col gap-2">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-24 rounded-[14px]" />)}</div>
        : !items.length ? <Empty icon="seal" title={q ? 'مصوبه‌ای با این عبارت نیست' : 'هنوز مصوبه‌ای نیست'} body="با مُهر هر تصمیم، مصوبه‌اش اینجا ثبت میشود. از هر پیام هم میتوانی مصوبه ثبت کنی." />
        : (
          <ul className="flex flex-col gap-2">
            {items.map((r) => (
              <li key={r.ref}>
                <Card as="article" className="p-0">
                  <button type="button" onClick={() => setOpen(r)} className="flex w-full flex-col gap-2 rounded-[16px] p-4 text-start hover:bg-hover">
                    <span className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
                      <span className="fig font-semibold text-gold-ink">{r.ref}</span>
                      {r.company ? <span className="text-sec"><CompanyMark code={r.company} height={12} mono /></span> : <Pill tone="neutral">هلدینگ</Pill>}
                      <span>{jDate(r.sealed_at, true)}</span>
                      <span className="flex-1" />
                      <Source r={r} />
                    </span>
                    <span className="text-[15px] font-semibold text-ink">{r.title}</span>
                    <span className="line-clamp-2 text-[13px] leading-6 text-sec">{r.body}</span>
                  </button>
                </Card>
              </li>
            ))}
          </ul>
        )}
      {open ? (
        <Sheet open onOpenChange={(v) => !v && setOpen(null)} title={<span className="flex items-center gap-2"><span className="fig text-[13px] text-gold-ink">{open.ref}</span>{open.title}</span>} width={560}>
          <div className="flex flex-col gap-4 text-[13px]">
            <Md text={open.body} className="text-[14px] leading-7" />
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sec">
              <dt className="text-muted">مُهر</dt><dd>{ACTOR_FA(open.sealed_by)} · {jDateTime(open.sealed_at)}</dd>
              <dt className="text-muted">منبع</dt><dd><Source r={open} /></dd>
              {open.sent_to.length ? <><dt className="text-muted">ابلاغ به</dt><dd className="flex flex-wrap gap-1">{open.sent_to.map((c) => <Link key={c} href={`/employees/${c}`} className="fig rounded-full bg-tile px-2 py-0.5 text-[12px] hover:bg-hover">{c}</Link>)}</dd></> : null}
              {open.follow_up_work_id ? <><dt className="text-muted">کار پیگیری</dt><dd><Link href={`/work/${open.follow_up_work_id}`} className="text-gold-ink hover:underline">باز کردن کار</Link></dd></> : null}
            </dl>
          </div>
        </Sheet>
      ) : null}
    </>
  );
}
