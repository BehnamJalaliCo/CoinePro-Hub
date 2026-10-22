'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Empty, ErrorState, FilterChip, PageHeader, Skeleton, Switch } from '@/components/ui/primitives';
import { KNOWLEDGE_KIND, KNOWLEDGE_STATUS, LAYER_FA, ScopeChips, daysFrom } from '@/components/v17/bits';
import { EntryCard, EntryEditor, EntrySheet, ExpiringCard } from '@/components/v17/knowledge';
import { useKnowledge, type KnowledgeEntry, type KnowledgeKind, type KnowledgeStatus, type Layer } from '@/lib/api/v17';
import { useScope } from '@/lib/scope';
import { useNow } from '@/lib/store';

const LAYERS: Layer[] = ['holding', 'company', 'department', 'employee'];
const KINDS: KnowledgeKind[] = ['principle', 'policy', 'fact', 'faq', 'playbook', 'support'];
const STATUSES: KnowledgeStatus[] = ['draft', 'in_review', 'approved', 'expired', 'retired'];

function KnowledgeInner() {
  const router = useRouter();
  const params = useSearchParams();
  const open = params.get('ref');
  const setOpen = (ref: string | null) => router.replace(ref ? `/knowledge?ref=${ref}` : '/knowledge', { scroll: false });
  const { company: scope } = useScope();
  const [picked, setPicked] = useState<string | null | undefined>(undefined);
  const company = picked !== undefined ? picked : scope;
  const [layer, setLayer] = useState<Layer | null>(null);
  const [kind, setKind] = useState<KnowledgeKind | null>(null);
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [text, setText] = useState('');
  const [expired, setExpired] = useState(false);
  const [edit, setEdit] = useState<KnowledgeEntry | 'new' | null>(null);
  const q = useKnowledge({ layer, company, kind, status, q: text, include_expired: expired });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  const now = useNow();
  const expiring = now ? items.filter((e) => e.status === 'approved' && e.kind !== 'support' && daysFrom(`${e.valid_until}T20:29:00Z`, now) <= 14 && daysFrom(`${e.valid_until}T20:29:00Z`, now) >= 0) : [];
  return (
    <>
      <PageHeader eyebrow="چهار لایه؛ هر ورودی با منبع و تاریخ انقضا" title="دانشنامه" actions={<Button variant="primary" icon="add" onClick={() => setEdit('new')}>ورودی تازه</Button>}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">هلدینگ برای همه، شرکت برای همان شرکت و هلدینگ، دپارتمان برای همان دپارتمان و مدیرعاملش. لایه‌ی کارمند همان حافظه‌ی خود اوست و فقط دیده میشود؛ مقاله‌های پشتیبانی هم این‌جا فقط دیده میشوند و ویرایششان از <Link href="/support" className="text-gold-ink">پشتیبانی</Link> است. ورودی منقضی به ایجنت‌ها نمیرسد و منبع پذیرفته نمیشود.</p>
      </PageHeader>
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="جستجو در عنوان و متن…" aria-label="جستجو در دانشنامه" className="h-9 w-full max-w-xs rounded-[10px] border border-strong bg-tile px-3 text-[13px] text-ink outline-none focus:border-gold-ink" />
          <label className="flex items-center gap-2 text-[12px] text-sec"><Switch checked={expired} onChange={setExpired} label="نشان دادن منقضی‌ها" />منقضی‌ها هم</label>
        </div>
        <ScopeChips value={company} onChange={setPicked} allLabel="همه‌ی شرکت‌ها" />
        <div className="flex flex-wrap gap-2"><FilterChip selected={!layer} onClick={() => setLayer(null)}>همه‌ی لایه‌ها</FilterChip>{LAYERS.map((l) => <FilterChip key={l} selected={layer === l} onClick={() => setLayer(l)}>{LAYER_FA[l]!.fa}</FilterChip>)}</div>
        <div className="flex flex-wrap gap-2"><FilterChip selected={!kind} onClick={() => setKind(null)}>همه‌ی نوع‌ها</FilterChip>{KINDS.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{KNOWLEDGE_KIND[k]}</FilterChip>)}</div>
        <div className="flex flex-wrap gap-2"><FilterChip selected={!status} onClick={() => setStatus(null)}>همه‌ی وضعیت‌ها</FilterChip>{STATUSES.map((s) => <FilterChip key={s} selected={status === s} onClick={() => setStatus(s)}>{KNOWLEDGE_STATUS[s]!.fa}</FilterChip>)}</div>
      </div>
      <ExpiringCard items={expiring} onOpen={setOpen} />
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-64" /> : !items.length ? <Empty icon="knowledge" title="ورودی‌ای پیدا نشد" /> : (
        <div className="grid items-start gap-3 md:grid-cols-2 xl:grid-cols-3">{items.map((e) => <EntryCard key={e.ref} e={e} onOpen={() => setOpen(e.ref)} />)}</div>
      )}
      {q.hasNextPage ? <Button variant="secondary" size="sm" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>بیشتر</Button> : null}
      {open ? <EntrySheet refId={open} onClose={() => setOpen(null)} onEdit={(e) => { setOpen(null); setEdit(e); }} /> : null}
      {edit ? <EntryEditor from={edit === 'new' ? null : edit} onClose={() => setEdit(null)} /> : null}
    </>
  );
}

/** دانشنامه (contract §20.3): one store in four layers, every entry sourced and dated. */
export default function KnowledgePage() {
  return <Suspense><KnowledgeInner /></Suspense>;
}
