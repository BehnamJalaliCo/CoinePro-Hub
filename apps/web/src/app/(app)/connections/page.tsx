'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { FilterChip, PageHeader, Skeleton } from '@/components/ui/primitives';
import { CompanyConnections } from '@/components/v29/connections';
import { useCompanies } from '@/lib/api/hooks';
import { useScope } from '@/lib/scope';

function Inner() {
  const router = useRouter();
  const search = useSearchParams();
  const { company: scope } = useScope();
  const { data: companies } = useCompanies();
  const list = (companies ?? []).filter((c) => c.kind !== 'holding' && c.status !== 'archived');
  const asked = search.get('company') ?? scope;
  const code = list.find((c) => c.code === asked)?.code ?? list[0]?.code ?? null;
  return (
    <>
      <PageHeader eyebrow="آنچه هر شرکت میتواند بسنجد و مدیریت کند؛ رمزها فقط در گاوصندوق ستاد" title="اتصال‌ها" />
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1" role="group" aria-label="شرکت">
        {list.map((c) => (
          <FilterChip key={c.code} selected={code === c.code} onClick={() => router.replace(`/connections?company=${c.code}`, { scroll: false })}>
            <span className="flex items-center gap-1.5"><CompanyMark code={c.code} height={12} mono />{c.name_fa}</span>
          </FilterChip>
        ))}
      </div>
      {code ? <CompanyConnections code={code} /> : <Skeleton className="h-72 rounded-[16px]" />}
    </>
  );
}

/** ⟨1.11⟩ §29.12: each company's connections, with their guides and the write-only secret. */
export default function ConnectionsPage() {
  return <Suspense><Inner /></Suspense>;
}
