'use client';

import Link from 'next/link';
import { use } from 'react';
import { Icon } from '@/components/icon';
import { ErrorState, Skeleton } from '@/components/ui/primitives';
import { LiveRoom, MinutesRoom, PrepRoom, WarRoom } from '@/components/v17/meetings';
import { useMeeting, useTurns } from '@/lib/api/v17';

/** One meeting (contract §20.1): before `live` the owner sees and edits the agenda and the budget; live, the round table; after, the minutes. */
export default function MeetingPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params);
  const q = useMeeting(ref);
  const m = q.data;
  const live = !!m && (m.state === 'live' || m.state === 'closing');
  const t = useTurns(ref, live);
  const turns = t.data?.items ?? [];
  return (
    <>
      <Link href="/meetings" className="flex items-center gap-1.5 self-start text-[13px] text-sec hover:text-ink"><Icon name="back" size={16} mirror />همه‌ی جلسه‌ها</Link>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : !m ? <div className="flex flex-col gap-4"><Skeleton className="h-24" /><Skeleton className="h-96" /></div>
        : m.type === 'war_room' ? <WarRoom m={m} turns={turns} />
        : live ? <LiveRoom m={m} turns={turns} whispers={t.data?.whispers ?? []} />
        : m.state === 'scheduled' || m.state === 'prep' ? <PrepRoom m={m} />
        : <MinutesRoom m={m} turns={turns} />}
    </>
  );
}
