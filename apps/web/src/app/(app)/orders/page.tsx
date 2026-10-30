'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { ErrorState, FilterChip, PageHeader, Skeleton } from '@/components/ui/primitives';
import { NewOrder } from '@/components/work/new-order';
import { ACTIVE, DELIVERED, ENDED, OrderCard, OrdersEmpty } from '@/components/v21/orders';
import { BrowserNotifyCard } from '@/components/v21/push';
import { useOwnerOrders } from '@/lib/api/v21';

type Tab = 'active' | 'delivered' | 'ended' | 'all';
const TABS: Array<[Tab, string]> = [['active', 'در جریان'], ['delivered', 'تحویل‌شده'], ['ended', 'ناموفق یا لغو'], ['all', 'همه']];

/**
 * «فرمان‌های من» (0.4.0): every order the owner gave (`created_by=owner`), by state (on the way, delivered, ended), each with its company,
 * title, stage on a stepper, an estimate of how far along it is, who holds it now, when it last moved, and its output when it has one.
 * The stream keeps it live.
 */
export default function OrdersPage() {
  const router = useRouter();
  const q = useOwnerOrders();
  const [tab, setTab] = useState<Tab>('active');
  const [order, setOrder] = useState(false);
  const all = q.data ?? [];
  const groups: Record<Tab, typeof all> = {
    active: all.filter((w) => ACTIVE.has(w.status)), delivered: all.filter((w) => DELIVERED.has(w.status)), ended: all.filter((w) => ENDED.has(w.status)), all,
  };
  const list = groups[tab];
  return (
    <>
      <PageHeader eyebrow="هر فرمانی که دادی، از ثبت تا تحویل؛ زنده" title="فرمان‌های من" actions={<>
        <Button variant="primary" icon="command" onClick={() => setOrder(true)}>فرمان تازه</Button>
        <Button variant="text" icon="cartable" onClick={() => router.push('/cartable')}>کارتابل</Button>
      </>} />
      <BrowserNotifyCard />
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
        {TABS.map(([k, l]) => <FilterChip key={k} selected={tab === k} onClick={() => setTab(k)} count={q.data ? groups[k].length : undefined}>{l}</FilterChip>)}
      </div>
      {q.isLoading ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-[212px] rounded-[16px]" />)}</div>
        : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : !list.length ? <OrdersEmpty tab={tab} onNewOrder={() => setOrder(true)} />
        : <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">{list.map((w) => <OrderCard key={w.id} w={w} />)}</div>}
      <p className="text-[11px] text-muted">درصد پیشرفت تخمینی است: از مرحله‌ی فرمان و سهم کارهای زیرمجموعه‌ی تمام‌شده حساب میشود و فقط وقتی چیزی واقعاً اتفاق بیفتد جلو میرود.</p>
      <NewOrder open={order} onOpenChange={setOrder} />
    </>
  );
}
