'use client';

import { useState } from 'react';
import { PageHeader, Segmented, Skeleton, StatTile } from '@/components/ui/primitives';
import { ChannelsTab, ConversationsTab, KbTab, QueueTab, ShadowTab } from '@/components/v16/support';
import { useCompanies } from '@/lib/api/hooks';
import { useChannels, useKb, useQueue, useShadow } from '@/lib/api/v16';
import { useScope } from '@/lib/scope';

type Tab = 'queue' | 'conversations' | 'channels' | 'kb' | 'shadow';

/** پشتیبانی (contract §19.3–§19.6): a desk the owner teaches. Rules answer first, verbatim from approved knowledge; a model drafts only
 *  from approved articles; the outbound guard checks every word; what is left waits in the teaching queue. */
export default function SupportPage() {
  const { company: scope } = useScope();
  const { data: companies } = useCompanies();
  const company = companies?.find((c) => c.code === scope)?.kind === 'holding' ? null : scope;
  const [tab, setTab] = useState<Tab>('queue');
  const queue = useQueue();
  const channels = useChannels();
  const proposed = useKb({ status: 'proposed' });
  const shadow = useShadow();
  const ready = queue.data && channels.data && proposed.data && shadow.data;
  const live = (channels.data ?? []).filter((c) => c.state === 'live' && c.kind !== 'mystery');
  return (
    <>
      <PageHeader eyebrow="میزی که تو آموزشش میدهی؛ هیچ کلمه‌ای بی‌نگهبان به مشتری نمیرسد" title="پشتیبانی">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">اول قاعده: پرسشی که عین یک مقاله‌ی تأییدشده است بی‌مدل جواب میگیرد. بعد ایجنت فقط از مقاله‌های تأییدشده پیش‌نویس میدهد و کد هر لینک، کد و عدد را میسنجد. پشتیبانی هرگز رمز، کلید، کد تأیید یا عبارت بازیابی نمیخواهد و هرگز وعده‌ی سود نمیدهد.</p>
      </PageHeader>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {!ready ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[104px] rounded-[14px]" />) : (
          <>
            <StatTile label="منتظر تو" value={queue.data.length} tone={queue.data.length ? 'warn' : undefined} sub="صف آموزش" />
            <StatTile label="کانال روشن" value={live.length} sub={`از ${channels.data.filter((c) => c.kind !== 'mystery').length} کانال`} />
            <StatTile label="مقاله‌ی منتظر تأیید" value={proposed.data.length} sub="تأیید با passkey" />
            <StatTile label="آزمون سایه‌ی قبول" value={shadow.data.filter((r) => r.pass).length} sub={`از ${shadow.data.length} شرکت آزموده`} />
          </>
        )}
      </div>
      <div className="overflow-x-auto pb-1">
        <Segmented<Tab> label="بخش‌های پشتیبانی" value={tab} onChange={setTab} options={[
          { value: 'queue', label: 'صف آموزش' }, { value: 'conversations', label: 'گفت‌وگوها' }, { value: 'channels', label: 'کانال‌ها' }, { value: 'kb', label: 'دانش' }, { value: 'shadow', label: 'آزمون سایه' },
        ]} />
      </div>
      {tab === 'queue' ? <QueueTab /> : tab === 'conversations' ? <ConversationsTab initialCompany={company} /> : tab === 'channels' ? <ChannelsTab /> : tab === 'kb' ? <KbTab initialCompany={company} /> : <ShadowTab />}
    </>
  );
}
