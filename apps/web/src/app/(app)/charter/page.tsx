'use client';

import { useState } from 'react';
import { CompanyMark, Monogram } from '@/components/brand/marks';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Skeleton } from '@/components/ui/primitives';
import { CharterEditor, CharterScopeView, scopeName } from '@/components/v17/charter';
import { useCompanies } from '@/lib/api/hooks';
import { useCharter, type Charter } from '@/lib/api/v17';

/** اساسنامه (contract §20.2): one holding charter and a company addendum each, versioned; agents read the sealed versions, only the owner seals. */
export default function CharterPage() {
  const q = useCharter();
  const { data: companies } = useCompanies();
  const name = (c: string) => companies?.find((x) => x.code === c)?.name_fa ?? c;
  const scopes = q.data ?? [];
  const [pick, setPick] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ scope: string; from: Charter | null } | null>(null);
  const s = scopes.find((x) => x.scope === (pick ?? scopes[0]?.scope)) ?? null;
  // A company without an addendum can get one: companies are data, so every one of them is offered.
  const missing = (companies ?? []).filter((c) => c.kind !== 'holding' && !scopes.some((x) => x.scope === c.code));
  return (
    <>
      <PageHeader eyebrow="ایجنت‌ها میخوانند، هرگز نمینویسند؛ فقط تو مُهر میکنی" title="اساسنامه">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">یک سند هلدینگ و برای هر شرکت یک الحاقیه که با آن تعارض ندارد. هر تغییر نسخه‌ی تازه است و تا مُهر تو، هیچ ایجنتی آن را نمیخواند. ایجنت‌ها فقط اصلاحیه پیشنهاد میدهند (کارت «اصلاحیه‌ی اساسنامه» در کارتابل).</p>
      </PageHeader>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-96" /> : !scopes.length ? <Card><Empty icon="report" title="هنوز اساسنامه‌ای نیست" /></Card> : (
        <>
          <div className="flex flex-wrap gap-2">
            {scopes.map((x) => (
              <FilterChip key={x.scope} selected={s?.scope === x.scope} onClick={() => setPick(x.scope)}>
                <span className="flex items-center gap-1.5">{x.scope === 'holding' ? <Monogram size={12} /> : <CompanyMark code={x.scope} height={12} mono />}{scopeName(x.scope, name)}{x.proposed ? <span className="size-1.5 rounded-full bg-gold-ink" aria-label="منتظر مُهر" /> : null}</span>
              </FilterChip>
            ))}
            {missing.map((c) => <FilterChip key={c.code} onClick={() => setEdit({ scope: c.code, from: null })}><span className="flex items-center gap-1.5 text-muted">+ الحاقیه‌ی {c.name_fa}</span></FilterChip>)}
          </div>
          {s ? <CharterScopeView key={s.scope} s={s} name={name} onEdit={() => setEdit({ scope: s.scope, from: s.proposed ?? s.sealed })} /> : null}
        </>
      )}
      {edit ? <CharterEditor scope={edit.scope} from={edit.from} name={name} onClose={() => setEdit(null)} /> : null}
    </>
  );
}
