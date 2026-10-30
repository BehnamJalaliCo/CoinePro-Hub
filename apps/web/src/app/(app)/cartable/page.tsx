'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useMemo, useState } from 'react';
import { DecisionRow } from '@/components/cartable/decision-row';
import { DecisionDetail } from '@/components/cartable/decision-detail';
import { BatchSeal } from '@/components/v17/cartable';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Segmented, Skeleton } from '@/components/ui/primitives';
import { Sheet } from '@/components/ui/overlay';
import { useDecision, useDecisions } from '@/lib/api/hooks';
import { useScope } from '@/lib/scope';
import { SealCards, useServerSeals } from '@/components/v26/bits';
import { SERVER_DESTRUCTIVE } from '@/lib/api/v26';

type Tab = 'pending' | 'approved' | 'rejected' | 'returned';

function useWide() {
  const [w, setW] = useState(true);
  useEffect(() => {
    const m = window.matchMedia('(min-width: 1024px)');
    const f = () => setW(m.matches);
    f();
    m.addEventListener('change', f);
    return () => m.removeEventListener('change', f);
  }, []);
  return w;
}

function CartableInner() {
  const router = useRouter();
  const params = useSearchParams();
  // 0.3.0: a company's own cartable (its control actions open `?company=`); otherwise the scope switch.
  const { company: scoped } = useScope();
  const only = params.get('company');
  const company = only ?? scoped;
  const wide = useWide();
  const [tab, setTab] = useState<Tab>('pending');
  const [risk, setRisk] = useState<string | null>(null);
  const q = useDecisions({ status: tab, company: company ? [company] : undefined, risk: (risk ?? undefined) as never });
  // Cartable age (M8): what expires first, what has waited longest, or the newest.
  const [sort, setSort] = useState<'expiry' | 'oldest' | 'newest'>('expiry');
  const items = useMemo(() => {
    // ⟨1.8⟩ §26.3: a server's destructive command stands above as its own card, with its command and its seal.
    const xs = (q.data?.items ?? []).filter((d) => tab !== 'pending' || d.kind !== SERVER_DESTRUCTIVE);
    const t = (s: string | null | undefined, empty: number) => (s ? new Date(s).getTime() : empty);
    if (sort === 'expiry') xs.sort((a, b) => t(a.expires_at, Infinity) - t(b.expires_at, Infinity) || t(a.created_at, 0) - t(b.created_at, 0));
    else xs.sort((a, b) => (sort === 'oldest' ? 1 : -1) * (t(a.created_at, 0) - t(b.created_at, 0)));
    return xs;
  }, [q.data, sort, tab]);
  const serverSeals = useServerSeals(company);
  const selected = params.get('ref') ?? (wide ? items[0]?.ref ?? null : null);
  const detail = useDecision(selected);
  const select = (ref: string | null) => {
    const q = new URLSearchParams();
    if (ref) q.set('ref', ref);
    if (only) q.set('company', only);
    router.replace(q.size ? `/cartable?${q}` : '/cartable', { scroll: false });
  };

  const next = () => {
    const i = items.findIndex((d) => d.ref === selected);
    const n = items[i + 1] ?? items[i - 1];
    select(n?.ref ?? null);
  };

  const list = (
    <Card className="flex flex-col gap-1 p-2">
      {q.isLoading ? Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="m-1 h-[70px]" />)
        : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : !items.length ? <Empty icon="seal" title={tab === 'pending' ? 'چیزی منتظر مُهر تو نیست' : 'موردی نیست'} body={tab === 'pending' ? 'وقتی مدیرعامل‌ها یا مدیرها چیزی پیشنهاد کنند، این‌جا میاید.' : undefined} />
        : items.map((d) => <DecisionRow key={d.ref} d={d} selected={d.ref === selected} onSelect={() => select(d.ref)} />)}
    </Card>
  );

  return (
    <>
      <PageHeader eyebrow="کارتابل تصمیم" title="کارتابل">
        <div className="flex flex-wrap items-center gap-3">
          <div className="w-full max-w-md">
            <Segmented<Tab> label="وضعیت" value={tab} onChange={(v) => { setTab(v); select(null); }} options={[
              { value: 'pending', label: 'منتظر مُهر' }, { value: 'approved', label: 'مُهرشده' }, { value: 'returned', label: 'برگشتی' }, { value: 'rejected', label: 'ردشده' },
            ]} />
          </div>
          <div className="flex flex-wrap gap-2">
            {[['high', 'ریسک بالا'], ['medium', 'متوسط'], ['low', 'کم']].map(([v, l]) => <FilterChip key={v} selected={risk === v} onClick={() => setRisk(risk === v ? null : v!)}>{l}</FilterChip>)}
          </div>
          {/* ⟨1.5⟩ §20.10: low-risk A1 cards sealed together with one passkey. */}
          {tab === 'pending' ? <BatchSeal /> : null}
          {tab === 'pending' ? (
            <label className="flex items-center gap-2 text-[12px] text-sec">ترتیب
              <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} className="h-9 rounded-[10px] border border-strong bg-tile px-2 text-[13px] text-ink outline-none focus:border-gold-ink">
                <option value="expiry">زودتر منقضی</option><option value="oldest">بیشترین انتظار</option><option value="newest">تازه‌ترین</option>
              </select>
            </label>
          ) : null}
        </div>
      </PageHeader>
      {tab === 'pending' && serverSeals.length ? <SealCards cards={serverSeals} /> : null}
      {wide ? (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(320px,420px)_minmax(0,1fr)]">
          <div className="lg:sticky lg:top-20">{list}</div>
          <Card className="p-5 lg:p-7">
            {!selected ? <Empty icon="cartable" title="یک مورد را انتخاب کن" />
              : detail.isLoading ? <div className="flex flex-col gap-3"><Skeleton className="h-16" /><Skeleton className="h-32" /><Skeleton className="h-48" /></div>
              : detail.error ? <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
              : detail.data ? <DecisionDetail key={detail.data.ref} d={detail.data} onDone={next} /> : null}
          </Card>
        </div>
      ) : (
        <>
          {list}
          <Sheet open={!!selected} onOpenChange={(v) => !v && select(null)} title={detail.data?.title ?? 'تصمیم'} width={560}>
            {detail.data ? <DecisionDetail key={detail.data.ref} d={detail.data} onDone={() => select(null)} /> : <Skeleton className="h-64" />}
          </Sheet>
        </>
      )}
    </>
  );
}

export default function CartablePage() {
  return <Suspense><CartableInner /></Suspense>;
}
