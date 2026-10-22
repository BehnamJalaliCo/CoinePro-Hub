'use client';

import Link from 'next/link';
import { Suspense } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, PageHeader, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { RefChip } from '@/components/v17/bits';
import { CHANNEL_FA, ClassTag, JDay, ScopeTag, daysLeftFa, reminderToFa, useArchive } from '@/components/v20/bits';
import { faError, useDueReminders, useReminderDone, type DueReminder } from '@/lib/api/v20';
import { cx } from '@/lib/format';

function Row({ x }: { x: DueReminder }) {
  const m = useArchive();
  const done = useReminderDone();
  const toast = useToast();
  const f = m.cls(x.class)?.fields.find((y) => y.key === x.field);
  const closed = x.state === 'done';
  const tone = closed ? 'text-muted' : x.days_left <= 7 ? 'text-neg' : x.days_left <= 30 ? 'text-warn' : 'text-sec';
  const mark = async () => {
    try { await done.mutateAsync(x.id); toast({ tone: 'ok', text: 'یادآور بسته شد.' }); } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <li className={cx('flex min-w-0 flex-wrap items-center gap-3 rounded-[14px] p-3', closed ? 'bg-page' : 'bg-tile')}>
      <span className={cx('flex w-[5.5rem] flex-none flex-col items-center gap-0.5 text-center', tone)}>
        <Icon name="time" size={18} />
        <span className="text-[13px] font-semibold">{closed ? 'انجام شد' : daysLeftFa(x.days_left)}</span>
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <Link href={`/archive/${x.record}`} title={x.title_fa} className="truncate text-[14px] font-semibold text-ink hover:underline">{x.title_fa}</Link>
        <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-muted">
          <span className="fig text-sec">{x.record}</span>
          <ScopeTag scope={x.scope} />
          <ClassTag cls={x.class} />
          <span>{f?.title_fa ?? x.field}: <JDay d={x.at} className="text-sec" /></span>
        </span>
        <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-muted">
          <span>{x.lead_days} روز پیش از موعد</span>
          <span>برای {reminderToFa(x.to)}، در {CHANNEL_FA[x.channel] ?? x.channel}</span>
          {x.rule ? <RefChip r={x.rule} tone="neutral" /> : null}
        </span>
      </span>
      {closed ? <Pill tone="pos" icon="seal">بسته</Pill> : <Button size="sm" variant="secondary" icon="seal" loading={done.isPending} onClick={mark}>انجام شد</Button>}
    </li>
  );
}

function RemindersInner() {
  const q = useDueReminders();
  const xs = [...(q.data ?? [])].sort((a, b) => Number(a.state === 'done') - Number(b.state === 'done') || a.days_left - b.days_left);
  return (
    <>
      <PageHeader eyebrow="بایگانی · قراردادها، مجوزها و دامنه‌ها پیش از سررسید" title="یادآورها">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">هر یادآور از قاعده‌ی نوع سند میآید (مثلاً پایان قرارداد ۶۰، ۳۰ و ۷ روز قبل). وقتی کار اصلی انجام شد (تمدید، بازبینی، فسخ) اینجا ببندش؛ تا بسته نشود در کارتابل یا خلاصه‌ی روزانه میماند.</p>
      </PageHeader>
      <Card className="flex min-w-0 flex-col gap-2 p-2 md:p-3">
        {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-20" />)
          : !xs.length ? <Empty icon="time" title="یادآوری سر نرسیده" body="هر سررسیدی که به روزهای قاعده‌اش برسد اینجا می‌آید." />
            : <ul className="flex flex-col gap-2">{xs.map((x) => <Row key={x.id} x={x} />)}</ul>}
      </Card>
      <p className="text-[12px] text-muted">قاعده‌ها در <Link href="/archive/settings?tab=reminders" className="font-semibold text-gold-ink hover:underline">طرح بایگانی، یادآورها</Link>.</p>
    </>
  );
}

/** یادآورها (contract §23.6): due reminders, nearest first, with the days left; closing one closes it everywhere. */
export default function RemindersPage() {
  return <Suspense><RemindersInner /></Suspense>;
}
