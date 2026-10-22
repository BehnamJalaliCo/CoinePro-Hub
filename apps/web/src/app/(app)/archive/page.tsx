'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card, ErrorState, PageHeader, Skeleton } from '@/components/ui/primitives';
import { ScopeChips } from '@/components/v17/bits';
import { JDay, useArchive, field } from '@/components/v20/bits';
import { DraftsBlock, ExpiringStrip, FixityLine, IntakeSheet, PartyCard, RecordRow, RecordsEmpty } from '@/components/v20/records';
import { useArchiveSearch, useHolds, useRecords, type RecordFilters } from '@/lib/api/v20';
import { useScope } from '@/lib/scope';
import { cx } from '@/lib/format';

const KEYS = ['scope', 'class', 'folder', 'level', 'party', 'from', 'to'] as const;
type Key = (typeof KEYS)[number];
type F = Record<Key, string | null>;

function Filters({ f, set, open }: { f: F; set: (k: Key, v: string | null) => void; open: boolean }) {
  const m = useArchive();
  const folders = m.folders.filter((x) => !f.scope || x.scope === f.scope);
  const sel = (k: Key, label: string, options: Array<{ v: string; t: string }>) => (
    <label className="flex min-w-0 flex-col gap-1 text-[11px] text-muted">{label}
      <select aria-label={label} value={f[k] ?? ''} onChange={(e) => set(k, e.target.value || null)} className={field('h-9 text-[13px]', f[k] && 'border-gold-ink')}>
        <option value="">همه</option>
        {options.map((o) => <option key={o.v} value={o.v}>{o.t}</option>)}
      </select>
    </label>
  );
  return (
    <div className={cx('grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6', !open && 'hidden md:grid')}>
      {sel('class', 'نوع سند', m.classes.map((c) => ({ v: c.key, t: `${c.title_fa}${c.status === 'retired' ? ' (بازنشسته)' : ''}` })))}
      {sel('folder', 'پوشه', folders.map((x) => ({ v: x.ref, t: `${'— '.repeat(Math.max(0, m.folderPath(x.ref).length - 1))}${x.title_fa}${f.scope ? '' : ` · ${x.scope}`}` })))}
      {sel('level', 'سطح', m.levels.map((l) => ({ v: l.key, t: l.title_fa })))}
      {sel('party', 'طرف', m.parties.map((p) => ({ v: p.ref, t: p.name_fa })))}
      {(['from', 'to'] as const).map((k) => (
        <label key={k} className="flex min-w-0 flex-col gap-1 text-[11px] text-muted">
          <span className="flex items-center gap-1">{k === 'from' ? 'تاریخ سند از' : 'تا'}{f[k] ? <JDay d={f[k]} className="text-sec" /> : null}</span>
          <input aria-label={k === 'from' ? 'تاریخ سند از' : 'تاریخ سند تا'} type="date" dir="ltr" value={f[k] ?? ''} onChange={(e) => set(k, e.target.value || null)} className={field('fig h-9 text-[13px]', f[k] && 'border-gold-ink')} />
        </label>
      ))}
    </div>
  );
}

function ArchiveInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { company } = useScope();
  const m = useArchive();
  const holds = useHolds({ state: 'active' });
  const f = Object.fromEntries(KEYS.map((k) => [k, params.get(k)])) as F;
  const [text, setText] = useState(() => params.get('q') ?? '');
  const [making, setMaking] = useState(params.get('new') === '1');
  const [open, setOpen] = useState(false);
  const q = params.get('q') ?? '';
  // A link that changes the query (the sidebar, a chip) brings the box along; typing leads the URL, not the other way.
  const [seenQ, setSeenQ] = useState(q);
  if (q !== seenQ) { setSeenQ(q); if (q !== text.trim()) setText(q); }
  const go = (next: F & { q: string }) => {
    const s = new URLSearchParams();
    for (const [k, v] of Object.entries(next)) if (v) s.set(k, v);
    router.replace(s.size ? `/archive?${s}` : '/archive', { scroll: false });
  };
  const set = (k: Key, v: string | null) => go({ ...f, ...(k === 'scope' ? { folder: null } : {}), [k]: v, q });
  // The search box writes the URL a moment after typing stops, so a refresh or a shared link keeps the query.
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const type = (v: string) => {
    setText(v);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => go({ ...f, q: v.trim() }), 350);
  };
  useEffect(() => () => clearTimeout(timer.current), []);
  const filters: RecordFilters = { ...f, class: f.class, q: q.length >= 2 ? q : null };
  const list = useRecords(filters);
  const hits = useArchiveSearch(q, { scope: f.scope, class: f.class, level: f.level, from: f.from, to: f.to });
  const snippet = new Map((hits.data ?? []).map((h) => [h.ref, h.snippet_fa]));
  const rows = (list.data?.pages.flatMap((p) => p.items) ?? []).filter((r) => q.length >= 2 || r.state !== 'draft');
  const active = KEYS.filter((k) => k !== 'scope' && f[k]).length;
  const filtered = active > 0 || !!f.scope || q.length >= 2;
  return (
    <>
      <PageHeader eyebrow="هر سند یک بار ثبت میشود، نسخه دارد و بعد از مُهر دست نمیخورد" title="بایگانی"
        actions={<Button variant="primary" icon="add" onClick={() => setMaking(true)}>سند تازه</Button>}>
        <div className="flex flex-col gap-2">
          <FixityLine />
          <nav aria-label="بخش‌های بایگانی" className="flex flex-wrap gap-2 text-[12px]">
            <Link href="/archive/holds" className="inline-flex h-8 items-center gap-1.5 rounded-full border border-strong px-3 text-sec hover:bg-hover hover:text-ink"><Icon name="lock" size={14} />توقیف‌ها{holds.data?.length ? <span className="text-muted">{holds.data.length} فعال</span> : null}</Link>
            <Link href="/archive/reminders" className="inline-flex h-8 items-center gap-1.5 rounded-full border border-strong px-3 text-sec hover:bg-hover hover:text-ink"><Icon name="time" size={14} />یادآورها</Link>
            <Link href="/archive/retention" className="inline-flex h-8 items-center gap-1.5 rounded-full border border-strong px-3 text-sec hover:bg-hover hover:text-ink"><Icon name="memory" size={14} />پایان نگهداری</Link>
            <Link href="/archive/settings" className="inline-flex h-8 items-center gap-1.5 rounded-full border border-strong px-3 text-sec hover:bg-hover hover:text-ink"><Icon name="settings" size={14} />طرح بایگانی</Link>
          </nav>
        </div>
      </PageHeader>
      <ExpiringStrip />
      <div className="grid min-w-0 grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-3">
          <Card className="flex min-w-0 flex-col gap-3 p-3 md:p-4">
            <div className="flex min-w-0 gap-2">
              <label className="flex h-11 min-w-0 flex-1 items-center gap-2 rounded-[12px] border border-strong bg-tile px-3 text-sec focus-within:border-gold-ink">
                <Icon name="search" size={18} />
                <input value={text} onChange={(e) => type(e.target.value)} placeholder="جستجو در عنوان، مشخصات و متن فایل‌ها" aria-label="جستجو در بایگانی" className="h-full min-w-0 flex-1 bg-transparent text-[14px] text-ink outline-none" />
                {text ? <button type="button" onClick={() => { clearTimeout(timer.current); setText(''); go({ ...f, q: '' }); }} aria-label="پاک کردن جستجو" className="text-muted hover:text-ink"><Icon name="close" size={14} /></button> : null}
              </label>
              <Button variant={active ? 'silver' : 'secondary'} icon="filter" className="md:hidden" aria-label={active ? `فیلترها (${active})` : 'فیلترها'} aria-expanded={open} onClick={() => setOpen((v) => !v)}>{active ? `${active}` : ''}</Button>
            </div>
            <ScopeChips value={f.scope} onChange={(v) => set('scope', v)} allLabel="همه" />
            <Filters f={f} set={set} open={open} />
          </Card>
          {f.party ? <PartyCard refId={f.party} onClear={() => set('party', null)} /> : null}
          <Card className="flex min-w-0 flex-col gap-1 p-2">
            {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : list.isLoading || m.q.isLoading ? Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="m-1 h-16" />) : !rows.length ? <RecordsEmpty filtered={filtered} /> : (
              <>
                <p className="px-3 pb-1 pt-2 text-[12px] text-muted" aria-live="polite">{q.length >= 2 ? `${rows.length} نتیجه برای «${q}»` : `${rows.length} سند`}{filtered && !q ? ' با این فیلترها' : ''}</p>
                <ul className="flex flex-col">{rows.map((r) => <li key={r.ref}><RecordRow r={r} q={q.length >= 2 ? q : undefined} snippet={q.length >= 2 ? snippet.get(r.ref) ?? null : null} /></li>)}</ul>
                {list.hasNextPage ? <Button variant="ghost" className="m-2" loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>بیشتر</Button> : null}
              </>
            )}
          </Card>
        </div>
        <aside className="order-first flex min-w-0 flex-col gap-3 lg:order-none">
          <DraftsBlock scope={f.scope} />
        </aside>
      </div>
      {making ? <IntakeSheet scope={f.scope ?? company} onClose={() => setMaking(false)} /> : null}
    </>
  );
}

/** بایگانی (contract §23): search, filters, drafts waiting to be filed, what expires soonest, and intake. */
export default function ArchivePage() {
  return <Suspense><ArchiveInner /></Suspense>;
}
