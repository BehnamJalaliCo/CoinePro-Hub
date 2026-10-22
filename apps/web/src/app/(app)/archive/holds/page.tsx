'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { ErrorState, FilterChip, PageHeader, Skeleton } from '@/components/ui/primitives';
import { HoldCard, HoldsEmpty, NewHoldSheet } from '@/components/v20/holds';
import { useHolds } from '@/lib/api/v20';

type St = 'active' | 'released' | null;

function HoldsInner() {
  const params = useSearchParams();
  const router = useRouter();
  const sel = params.get('ref');
  const [state, setState] = useState<St>(null);
  const [making, setMaking] = useState(params.get('new') === '1');
  const q = useHolds({ state });
  const xs = [...(q.data ?? [])].sort((a, b) => Number(b.state === 'active') - Number(a.state === 'active') || b.placed_at.localeCompare(a.placed_at));
  const n = (q.data ?? []).filter((h) => h.state === 'active').length;
  // A hold named in the link (from a record, a case or a ref chip) is brought into view once it is on the page.
  const found = !!sel && xs.some((h) => h.ref === sel);
  useEffect(() => { if (found && sel) document.getElementById(sel)?.scrollIntoView({ block: 'center' }); }, [found, sel]);
  const close = () => { setMaking(false); if (params.get('new')) router.replace('/archive/holds', { scroll: false }); };
  return (
    <>
      <PageHeader eyebrow="بایگانی · سندهایی که تا آخر پرونده دست نمیخورند" title="توقیف‌های قانونی"
        actions={<Button variant="primary" icon="lock" onClick={() => setMaking(true)}>توقیف تازه</Button>}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">سند زیر توقیف جز نسخه‌ی تازه هیچ تغییری نمیپذیرد و حتی اگر نگهداری‌اش تمام شده باشد، از کارت امحا رد میشود. مشاور حقوقی با پرونده‌اش توقیف میگذارد؛ آزاد کردن فقط با passkey توست.</p>
      </PageHeader>
      <div className="flex flex-wrap gap-1.5">
        <FilterChip selected={state === null} onClick={() => setState(null)}>همه</FilterChip>
        <FilterChip selected={state === 'active'} onClick={() => setState('active')}>فعال{state === null && n ? <span className="text-[12px] opacity-80">{n}</span> : null}</FilterChip>
        <FilterChip selected={state === 'released'} onClick={() => setState('released')}>آزادشده</FilterChip>
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <div className="grid gap-3 lg:grid-cols-2"><Skeleton className="h-48" /><Skeleton className="h-48" /></div>
        : !xs.length ? <HoldsEmpty /> : <div className="grid min-w-0 grid-cols-1 items-start gap-3 lg:grid-cols-2">{xs.map((h) => <HoldCard key={h.ref} h={h} highlight={sel === h.ref} />)}</div>}
      {making ? <NewHoldSheet caseRef={params.get('case')} onClose={close} onMade={(ref) => { setMaking(false); router.replace(`/archive/holds?ref=${ref}`, { scroll: false }); }} /> : null}
    </>
  );
}

/** توقیف‌های قانونی (contract §23.5): what is frozen, for which case, and the owner's release with the passkey. */
export default function HoldsPage() {
  return <Suspense><HoldsInner /></Suspense>;
}
