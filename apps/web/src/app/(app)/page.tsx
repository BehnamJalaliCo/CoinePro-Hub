'use client';

import { useRouter } from 'next/navigation';
import { useVoiceOrder } from '@/components/work/voice-order';
import { DecisionRow } from '@/components/cartable/decision-row';
import { CommandBar, OfficeBody, OfficeHeader, OfficeSkeleton } from '@/components/office/office';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { StoriesBar } from '@/components/v14/stories';
import { HomeOrdersCard } from '@/components/v21/orders';
import { CriticalCard, HomeNotServed, HomeOrders, HomeSkeleton, MorningCard, ProgressCard, SuggestionCard } from '@/components/v29/home';
import { useDecisions } from '@/lib/api/hooks';
import { useHome } from '@/lib/api/v29';
import { useOffice } from '@/lib/api/v34';
import { UsageHomeCard } from '@/components/v33/usage';
import { useScope } from '@/lib/scope';

// ⟨1.17⟩ Contract §35.5, the owner's office: the command bar, the sessions (his turn first), the canvas of the companies and their links, the
// cards waiting for his seal, the money in one line, what is critical and suggestions on any subject. It is not a dashboard of one subject: the
// per-group KPI block is gone. A hub from before §35 answers `/office` with 404 and the page shows the older home (§29.13) instead.
// Servers, the watch, the workshop and the technical findings live under «فنی»; nothing technical is added here.

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

/** The home of a hub that has no office yet (§29.13): what it had, without the per-group KPI block. */
function OlderHome() {
  const voice = useVoiceOrder();
  const home = useHome();
  const h = home.data;
  return (
    <>
      <CommandBar />
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

export default function OwnerOffice() {
  const office = useOffice();
  return (
    <>
      <OfficeHeader />
      {office.isLoading ? <OfficeSkeleton /> : office.error ? <ErrorState error={office.error} onRetry={() => office.refetch()} /> : office.data ? <OfficeBody o={office.data} /> : <OlderHome />}
    </>
  );
}
