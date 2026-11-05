'use client';

import { useRouter } from 'next/navigation';
import { useVoiceOrder } from '@/components/work/voice-order';
import { DecisionRow } from '@/components/cartable/decision-row';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { StoriesBar } from '@/components/v14/stories';
import { HomeOrdersCard } from '@/components/v21/orders';
import { CriticalCard, GroupKpiCard, HomeNotServed, HomeOrders, HomeSkeleton, MorningCard, ProgressCard, SuggestionCard } from '@/components/v29/home';
import { useDecisions, usePresence } from '@/lib/api/hooks';
import { useHome } from '@/lib/api/v29';
import { UsageHomeCard } from '@/components/v33/usage';
import { useScope } from '@/lib/scope';
import { jWeekday } from '@/lib/format';

// ⟨1.11⟩ Contract §29.13, the owner's home: the business, not the servers (the owner, 2026-11-02: «کل اپ شده مسائل فنی سرورها … میخوام به
// سئو، محصولات، پیشرفت و درآمد فکر کنم»). Three cards on top, the morning's five lines, each working group's KPI per company, the orders
// with their state, the cards waiting for the seal, and only critical items. Servers, the watch, the workshop, the live orbit and the
// technical findings moved to «شرکت ← فنی» and their own pages; nothing technical is re-added here.

function Greeting() {
  const { data: presence } = usePresence();
  const voice = useVoiceOrder();
  const today = new Date();
  const g = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(today);
  const h = Number(new Intl.DateTimeFormat('en-US', { hour: 'numeric', hourCycle: 'h23', timeZone: 'Asia/Tehran' }).format(today));
  const hello = h < 12 ? 'صبح بخیر' : h < 17 ? 'روز بخیر' : 'عصر بخیر';
  return (
    <header className="flex flex-wrap items-end gap-x-4 gap-y-2">
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-caption text-muted">{jWeekday(today.toISOString())} · <span className="fig">{g}</span></span>
        <h1 className="text-display font-semibold">{hello}، مدیر کل</h1>
      </div>
      {presence?.khalvat ? <Pill tone="learn" icon="khalvat">خلوت روشن؛ فقط فوری میرسد</Pill> : null}
      {/* The golden button and, beside it, a new rule for the holding (§29.3), by voice or in words. */}
      <div className="flex flex-wrap gap-2 max-sm:w-full">
        <Button variant="primary" icon="mic" onClick={() => voice()} className="max-sm:flex-1">فرمان صوتی</Button>
        <Button variant="secondary" icon="seal" onClick={() => voice({ mode: 'rule' })} className="max-sm:flex-1">قانون تازه برای هلدینگ</Button>
      </div>
    </header>
  );
}

/** The cards that wait for the owner's seal (the hub lists only what is the owner's, §29.1). */
function Cartable() {
  const router = useRouter();
  const { company } = useScope();
  const q = useDecisions({ status: 'pending', company: company ? [company] : undefined });
  return (
    <Card className="flex flex-col gap-2 p-4">
      <SectionTitle title="منتظر مُهر تو" note="فقط تصمیم‌هایی که با توست" action={<Button variant="text" size="sm" iconEnd="next" onClick={() => router.push('/cartable')}>کارتابل</Button>} />
      {q.isLoading ? <div className="flex flex-col gap-2">{Array.from({ length: 2 }, (_, i) => <Skeleton key={i} className="h-[72px]" />)}</div>
        : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : !q.data?.items.length ? <Empty icon="seal" title="چیزی منتظر مُهر تو نیست" />
        : <div className="flex flex-col gap-0.5">{q.data.items.slice(0, 4).map((d) => <DecisionRow key={d.ref} d={d} href={`/cartable?ref=${d.ref}`} />)}</div>}
    </Card>
  );
}

export default function OwnerHome() {
  const voice = useVoiceOrder();
  const home = useHome();
  const h = home.data;
  return (
    <>
      <Greeting />
      {home.isLoading ? <HomeSkeleton /> : home.error ? <ErrorState error={home.error} onRetry={() => home.refetch()} /> : !h ? (
        <>
          <HomeNotServed />
          <div className="grid gap-4 xl:grid-cols-2"><HomeOrdersCard onNewOrder={() => voice()} /><Cartable /></div>
        </>
      ) : (
        <>
          <CriticalCard items={h.critical} />
          <div className="grid items-stretch gap-4 lg:grid-cols-3">
            <SuggestionCard kind="effective" s={h.cards.effective} />
            <SuggestionCard kind="good" s={h.cards.good} />
            <ProgressCard p={h.cards.progress} />
          </div>
          <StoriesBar />
          <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
            <div className="flex min-w-0 flex-col gap-4">
              <MorningCard lines={h.morning} />
              <UsageHomeCard />
              {h.groups.map((g) => <GroupKpiCard key={g.key} g={g} />)}
            </div>
            <div className="flex min-w-0 flex-col gap-4">
              <HomeOrders orders={h.orders} onNewOrder={() => voice()} />
              <Cartable />
            </div>
          </div>
        </>
      )}
    </>
  );
}
