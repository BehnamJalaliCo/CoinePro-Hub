'use client';

import Link from 'next/link';
import { Suspense } from 'react';
import { Icon } from '@/components/icon';
import { Card, Empty, ErrorState, PageHeader, Pill, Skeleton } from '@/components/ui/primitives';
import { RefChip } from '@/components/v17/bits';
import { ClassTag, JDay, ScopeTag, THEN_FA, useArchive } from '@/components/v20/bits';
import { useRetentionDue, type RetentionDue } from '@/lib/api/v20';
import { cx } from '@/lib/format';

function Row({ x }: { x: RetentionDue }) {
  const m = useArchive();
  const rule = m.schema?.retention.find((r) => r.ref === x.rule);
  const held = x.holds.length > 0;
  return (
    <li className={cx('flex min-w-0 flex-col gap-2 rounded-[14px] p-3', held ? 'bg-neg-soft' : 'bg-tile')}>
      <span className="flex min-w-0 flex-wrap items-center gap-2">
        <Link href={`/archive/${x.ref}`} className="min-w-0 flex-1 truncate text-[14px] font-semibold text-ink hover:underline">{x.title_fa}</Link>
        {held ? <Pill tone="neg" icon="lock">توقیف؛ رد میشود و میماند</Pill>
          : x.then === 'dispose_card' ? (x.decision_ref ? <Pill tone="gold" icon="seal">در کارت امحا</Pill> : <Pill tone="warn" icon="time">در کارت هفته‌ی بعد</Pill>)
            : <Pill tone="lapis" icon="agent">بازبینی بایگان</Pill>}
      </span>
      <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-muted">
        <span className="fig text-sec">{x.ref}</span>
        <ScopeTag scope={x.scope} />
        <ClassTag cls={x.class} />
        <span>آغاز <JDay d={x.trigger_at} className="text-sec" /></span>
        <span>پایان <JDay d={x.due_at} className="text-sec" /></span>
      </span>
      <span className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
        <RefChip r={x.rule} tone="neutral" />{rule ? <span>{rule.title_fa}</span> : null}<span className="text-muted">· {THEN_FA[x.then] ?? x.then}</span>
        {held ? x.holds.map((h) => <Link key={h} href={`/archive/holds?ref=${h}`} className="fig text-neg hover:underline">{h}</Link>) : null}
        {x.decision_ref ? <Link href={`/cartable?ref=${x.decision_ref}`} className="inline-flex items-center gap-1 font-semibold text-gold-ink hover:underline"><Icon name="cartable" size={14} />کارت <span className="fig">{x.decision_ref}</span></Link> : null}
      </span>
    </li>
  );
}

function RetentionInner() {
  const q = useRetentionDue();
  const xs = [...(q.data ?? [])].sort((a, b) => a.due_at.localeCompare(b.due_at));
  const cards = [...new Set(xs.map((x) => x.decision_ref).filter((x): x is string => !!x))];
  return (
    <>
      <PageHeader eyebrow="بایگانی · سندهایی که نگهداری‌شان تمام شده" title="پایان نگهداری">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">هیچ سندی از اینجا پاک نمیشود. امحا فقط با مُهر تو روی کارت هفتگی «امحای سندهای بایگانی» است؛ بعد از آن فایل‌ها نابود میشوند و سنگ‌نشان (شناسه، نوع، عنوان، تاریخ‌ها، hash و همان تصمیم) میماند. سند زیر توقیف رد میشود.</p>
      </PageHeader>
      {cards.length ? (
        <div className="flex flex-wrap items-center gap-2 rounded-[14px] bg-gold-soft p-3 text-[13px] text-ink">
          <Icon name="seal" size={18} />کارت امحای منتظر مُهر تو:
          {cards.map((c) => <Link key={c} href={`/cartable?ref=${c}`} className="fig font-semibold text-gold-ink hover:underline">{c}</Link>)}
        </div>
      ) : null}
      <Card className="flex min-w-0 flex-col gap-2 p-2 md:p-3">
        {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-20" />)
          : !xs.length ? <Empty icon="memory" title="نگهداری هیچ سندی تمام نشده" body="وقتی قاعده‌ی نگهداری سندی به پایان برسد، اینجا با کارت امحایش میآید." />
            : <ul className="flex flex-col gap-2">{xs.map((x) => <Row key={x.ref} x={x} />)}</ul>}
      </Card>
      <p className="text-[12px] text-muted">قاعده‌ها در <Link href="/archive/settings?tab=retention" className="font-semibold text-gold-ink hover:underline">طرح بایگانی، نگهداری</Link>؛ پیش‌فرض‌اند، نه نظر حقوقی.</p>
    </>
  );
}

/** پایان نگهداری (contract §23.5): records whose retention ended; disposal happens only through the owner's `archive_disposal` card. */
export default function RetentionPage() {
  return <Suspense><RetentionInner /></Suspense>;
}
