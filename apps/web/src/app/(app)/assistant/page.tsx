'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Icon } from '@/components/icon';
import { Avatar } from '@/components/brand/avatar';
import { Chat } from '@/components/chat/chat';
import { Button } from '@/components/ui/button';
import { Md, MdInline } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useErrandAction, useErrands, type Errand } from '@/lib/api/v14';
import { ago, cx, jTime, usd } from '@/lib/format';

const STATUS: Record<Errand['status'], { fa: string; tone: 'neutral' | 'lapis' | 'gold' | 'pos' | 'neg' | 'warn'; live?: boolean }> = {
  queued: { fa: 'در صف', tone: 'neutral' }, working: { fa: 'در حال انجام', tone: 'lapis', live: true }, waiting_owner: { fa: 'منتظر مُهر تو', tone: 'gold' },
  done: { fa: 'انجام شد', tone: 'pos' }, failed: { fa: 'نشد', tone: 'neg' }, cancelled: { fa: 'لغو شد', tone: 'warn' },
};
const STEP_ICON = { search: 'search', read: 'report', browse: 'globe', request: 'server', draft: 'edit', note: 'info', proposal: 'seal' } as const;

function ErrandSheet({ e, onClose }: { e: Errand; onClose: () => void }) {
  const act = useErrandAction();
  const live = e.status === 'working' || e.status === 'queued';
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} title={<span className="flex items-center gap-2"><span className="fig text-[13px] text-muted">{e.ref}</span>{e.title_fa}</span>} width={560}
      footer={live ? <Button variant="danger" loading={act.cancel.isPending} onClick={() => act.cancel.mutateAsync(e.ref).then(onClose)}>لغو کن</Button> : e.decision_ref ? <Link href={`/cartable?ref=${e.decision_ref}`} className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-[10px] bg-gold font-bold text-on-gold"><Icon name="seal" size={18} />کارت تصمیم <span className="fig">{e.decision_ref}</span></Link> : undefined}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
          <Pill tone={STATUS[e.status].tone} live={STATUS[e.status].live} dot={!STATUS[e.status].live}>{STATUS[e.status].fa}</Pill>
          {e.source === 'voice' ? <span className="flex items-center gap-1"><Icon name="mic" size={12} />از ویس</span> : null}
          <span className="fig">{usd(e.usage.usd)}</span>
        </div>
        <p className="text-[14px] leading-7 text-ink">{e.brief_md}</p>
        {e.result_md ? <Card className="bg-tile p-4"><Md text={e.result_md} className="flex flex-col gap-2 text-[14px] leading-7 text-ink" /></Card> : null}
        <div className="flex flex-col gap-1.5">
          <span className="text-[12px] font-semibold text-sec">مسیر کار</span>
          <ol className="relative flex flex-col gap-3 ps-6">
            <span className="absolute bottom-2 start-[9px] top-2 w-px bg-div" aria-hidden />
            {e.steps.map((s, i) => (
              <li key={i} className="relative flex items-start gap-2 text-[13px]">
                <span className="absolute -start-6 flex size-5 items-center justify-center rounded-full bg-tile text-sec"><Icon name={STEP_ICON[s.kind]} size={12} /></span>
                <span className="min-w-0 flex-1 text-ink"><MdInline text={s.summary_fa} /></span>
                <span className="text-[11px] text-muted">{jTime(s.at)}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </Sheet>
  );
}

/** دستیار شخصی (contract §18.3): the owner's errands, done with the internet; any outside commitment waits for the owner's seal. */
export default function AssistantPage() {
  const q = useErrands();
  const [open, setOpen] = useState<Errand | null>(null);
  const items = q.data?.items ?? [];
  const current = open ? items.find((e) => e.ref === open.ref) ?? open : null;
  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
      <div className="flex min-w-0 h-[calc(100dvh-64px-48px)] min-h-[520px] flex-col lg:h-[calc(100dvh-64px-36px)]">
        <header className="flex items-center gap-4 border-b border-div pb-4">
          <Avatar kind="assistant" size={52} state="working" />
          <div className="flex flex-1 flex-col">
            <h1 className="text-h2 font-semibold">دستیار شخصی</h1>
            <p className="text-caption text-muted">کارهای دم‌دستی‌ات را با اینترنت انجام میدهد؛ هر خرید، ارسال یا ثبت‌نام فقط با مُهر تو.</p>
          </div>
        </header>
        <Chat code="P" agentKind="assistant" placeholder="بگو چه کار کنم… (ویس، عکس یا فایل هم میشود)" suggestions={['سه پیشنهاد هتل در استانبول زیر ۱۵۰ یورو پیدا کن', 'خبرهای امروز بازار طلا را با منبع خلاصه کن', 'یک ایمیل مؤدبانه برای عقب انداختن جلسه بنویس']} />
      </div>
      <Card className="flex h-fit flex-col gap-3 p-4">
        <SectionTitle title="کارها" note="هر درخواست یک کار با مسیر قابل دیدن" />
        {q.isLoading ? <Skeleton className="h-40" /> : !items.length ? <Empty icon="assistant" title="هنوز کاری نخواسته‌ای" body="در گفت‌وگو بگو؛ دستیار کار را میسازد و جلو میبرد." /> : (
          <ul className="flex flex-col gap-2">
            {items.map((e) => (
              <li key={e.ref}>
                <button type="button" onClick={() => setOpen(e)} className={cx('flex w-full flex-col gap-1.5 rounded-[12px] p-3 text-start hover:bg-hover', e.status === 'waiting_owner' ? 'bg-gold-soft' : 'bg-tile')}>
                  <span className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{e.title_fa}</span>
                    <Pill tone={STATUS[e.status].tone} live={STATUS[e.status].live} dot={!STATUS[e.status].live}>{STATUS[e.status].fa}</Pill>
                  </span>
                  <span className="flex items-center gap-2 text-[11px] text-muted"><span className="fig">{e.ref}</span><span>{e.steps.length} گام</span><span className="flex-1" /><span>{ago(e.updated_at)}</span></span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {current ? <ErrandSheet e={current} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}
