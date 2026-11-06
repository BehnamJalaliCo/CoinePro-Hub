'use client';

import { useState } from 'react';
import { useVoiceOrder } from '@/components/work/voice-order';
import { SessionRow } from '@/components/session/session-row';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Skeleton } from '@/components/ui/primitives';
import { OrderReportsCard } from '@/components/v29/report';
import { bySessionOrder, useSessions } from '@/lib/api/v34';

type Tab = 'open' | 'closed' | 'hidden';
const TABS: Array<[Tab, string]> = [['open', 'باز'], ['closed', 'بایگانی'], ['hidden', 'از فهرست برداشته‌شده']];

/** ⟨1.17⟩ §35.3 «جلسه‌ها»: every order is a session; the open ones with the owner's turn first, and the archive of the closed ones. */
export default function SessionsPage() {
  const voice = useVoiceOrder();
  const [tab, setTab] = useState<Tab>('open');
  const q = useSessions(tab === 'open' ? 'open' : tab === 'closed' ? 'closed' : 'all');
  const all = q.data ?? [];
  const list = (tab === 'hidden' ? all.filter((s) => s.hidden) : tab === 'closed' ? all.filter((s) => !s.hidden) : all).slice().sort(tab === 'open' ? bySessionOrder : (a, b) => Date.parse(b.last_at) - Date.parse(a.last_at));
  return (
    <>
      <PageHeader eyebrow="هر فرمان یک جلسه است؛ تا تأیید نکنی بسته نمیشود" title="جلسه‌ها" actions={<Button variant="primary" icon="command" onClick={() => voice()}>فرمان تازه</Button>} />
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
        {TABS.map(([k, l]) => <FilterChip key={k} selected={tab === k} onClick={() => setTab(k)} count={tab === k && q.data ? list.length : undefined}>{l}</FilterChip>)}
      </div>
      {q.isLoading ? <Skeleton className="h-64 rounded-[16px]" />
        : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : q.data === null ? <><Card><Empty icon="messages" title="جلسه‌ها بعد از به‌روزرسانی ستاد میآیند" body="تا آن موقع فرمان‌هایت همین‌جا با جواب‌شان دیده میشود." /></Card><OrderReportsCard /></>
        : !list.length ? <Card><Empty icon="messages" title={tab === 'open' ? 'جلسه‌ی بازی نیست' : tab === 'closed' ? 'هنوز جلسه‌ای بایگانی نشده' : 'جلسه‌ای از فهرست برداشته نشده'} body={tab === 'open' ? 'یک فرمان بده تا جلسه‌اش باز شود.' : undefined} action={tab === 'open' ? <Button icon="command" onClick={() => voice()}>فرمان تازه</Button> : undefined} /></Card>
        : <Card className="flex flex-col p-2"><ul className="flex flex-col divide-y divide-[var(--hq-divider,transparent)]">{list.map((s) => <li key={s.ref}><SessionRow s={s} /></li>)}</ul></Card>}
    </>
  );
}
