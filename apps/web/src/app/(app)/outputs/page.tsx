'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ScopeChips } from '@/components/v17/bits';
import { RANGES, UndoBar, dayFa, inputCls, ownerDay, span, type Undo } from '@/components/v21/bits';
import { DeleteDialog, SelectAll, SelectionBar, useCleanup, useSelection } from '@/components/v28/outputs';
import { STICKY_TOP, useStuck } from '@/components/look/collapse';
import { useWide } from '@/components/look/fill';
import { DecisionBar } from '@/components/look/decision-bar';
import { OutputsTabs } from '@/components/look/desk';
import { OutputDetail, OutputRow } from '@/components/look/output';
import { SpringSheet } from '@/components/look/spring-sheet';
import { STAGGER, staggerStyle } from '@/components/look/stagger';
import { viewTransition } from '@/components/look/transition';
import { ApiError } from '@/lib/api/client';
import { useCompanies, useInbox } from '@/lib/api/hooks';
import { activeFilters, categoryOf, useLocalSeen, useOutputActions, useOutputs, type Inbox21, type Output, type OutputQuery } from '@/lib/api/v21';
import { useScope } from '@/lib/scope';
import { cx } from '@/lib/format';

// Outputs (0.3.0, contract §5.2 ⟨1.7.3⟩): what the agents and the hub's own reporting delivered. The owner reads one and marks it seen (the
// button on the row or on its page, or all at once): it leaves «تازه» for «خوانده‌شده» and stays, so agents and the digital chief keep
// learning from it, search and the archive still find it, and it can be filed in the archive to be cited later. Rating stays separate.
// ⟨1.10⟩ §28.1: outputs must not pile up: the owner chooses several (a box on each row, shift for a range, «همه») and files them, marks
// them seen, or deletes them for good (the passkey on exactly that set; one Audit line each stays). Only the owner ever deletes one.
// ⟨1.0.1⟩ Part C (C3.3): the list is media cards with their posters and its search folds away once the list has scrolled under its
// bar; a card opens out of itself (M14) into the output's page (components/look/output.tsx), which on a phone takes the list's place;
// «میز انتشار» is the other half of this place (components/look/desk.tsx).

type Tab = 'new' | 'seen' | 'all';

function Filters({ open, onOpenChange, query, set, producers, range, setRange, onClear, count }: {
  open: boolean; onOpenChange: (v: boolean) => void; query: OutputQuery; set: (p: Partial<OutputQuery>) => void;
  producers: Array<Output['producer'] & { label: string }>; range: string; setRange: (r: string) => void; onClear: () => void; count: number | null;
}) {
  const label = 'text-[12px] font-semibold text-sec';
  return (
    <SpringSheet open={open} onOpenChange={onOpenChange} title="فیلترها" description="روی هر سه زبانه اعمال میشوند" width={480}
      bar={<DecisionBar label="نمایش" primary={{ label: count == null ? 'نمایش' : `نمایش ${count.toLocaleString('fa-IR')} خروجی`, onClick: () => onOpenChange(false) }} quiet={[{ label: 'پاک کردن فیلترها', onClick: onClear }]} />}>
      <div className="flex flex-col gap-5 pb-1">
        <div className="flex flex-col gap-2">
          <span className={label}>دسته</span>
          <div className="flex flex-wrap gap-2">
            <FilterChip selected={!query.category} onClick={() => set({ category: null })}>همه</FilterChip>
            <FilterChip selected={query.category === 'report'} onClick={() => set({ category: 'report' })}>گزارش</FilterChip>
            <FilterChip selected={query.category === 'work'} onClick={() => set({ category: 'work' })}>کار</FilterChip>
          </div>
          <span className="text-[11px] text-muted">گزارش: آنچه خود هاب مینویسد (گزارش صبحگاهی، نامه‌ها)؛ کار: خروجی ایجنت برای یک کار.</span>
        </div>
        <div className="flex flex-col gap-2"><span className={label}>شرکت</span><ScopeChips value={query.company ?? null} onChange={(c) => set({ company: c })} /></div>
        {producers.length || query.producer ? (
          <div className="flex flex-col gap-2">
            <span className={label}>سازنده</span>
            <div className="flex flex-wrap gap-2">
              <FilterChip selected={!query.producer} onClick={() => set({ producer: null })}>همه</FilterChip>
              {producers.map((p) => <FilterChip key={p.code} selected={query.producer === p.code} onClick={() => set({ producer: p.code })}>{p.label}</FilterChip>)}
            </div>
          </div>
        ) : null}
        <div className="flex flex-col gap-2">
          <span className={label}>بازه‌ی زمانی</span>
          <div className="flex flex-wrap gap-2">{RANGES.map(([k, fa]) => <FilterChip key={k} selected={range === k} onClick={() => setRange(k)}>{fa}</FilterChip>)}</div>
        </div>
      </div>
    </SpringSheet>
  );
}

function OutputsInner() {
  const router = useRouter();
  const params = useSearchParams();
  const toast = useToast();
  const { company: scope } = useScope();
  const { data: companies } = useCompanies();
  const inbox = useInbox();
  const act = useOutputActions();
  const local = useLocalSeen();
  const [tab, setTab] = useState<Tab>((params.get('tab') as Tab | null) ?? 'new');
  const [f, setF] = useState<Omit<OutputQuery, 'seen' | 'from' | 'to' | 'q'>>({ category: null, unrated: false, company: scope, producer: null });
  const [range, setRange] = useState('all');
  const [search, setSearch] = useState('');
  const [applied, setApplied] = useState('');
  const [filters, setFilters] = useState(false);
  const [undo, setUndo] = useState<Undo | null>(null);
  // Marked a moment ago, before the next answer confirms it: ref → seen (for the list as it was; a fresh answer starts clean).
  const [opt, setOpt] = useState<{ data: unknown; m: Record<string, boolean> }>({ data: null, m: {} });
  useEffect(() => { const t = setTimeout(() => setApplied(search), 350); return () => clearTimeout(t); }, [search]);
  const { from, to } = span(range);
  const query: OutputQuery = { ...f, seen: tab === 'new' ? false : tab === 'seen' ? true : null, from, to, q: applied || null };
  const q = useOutputs(query);
  const loaded = useMemo(() => q.data?.pages.flatMap((p) => p.items) ?? [], [q.data]);
  const optimistic = useMemo(() => (opt.data === q.data ? opt.m : {}), [opt, q.data]);
  const setOptimistic = useCallback((f: (m: Record<string, boolean>) => Record<string, boolean>) => setOpt((o) => ({ data: q.data, m: f(o.data === q.data ? o.m : {}) })), [q.data]);

  // A hub that now keeps «seen» gets what this browser kept meanwhile, in one call.
  useEffect(() => {
    const refs = Object.keys(local);
    if (refs.length && loaded.some((d) => d.seen_at !== undefined)) act.seen.mutate({ refs, seen: true });
  }, [loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  const seenAt = useCallback((d: Output) => {
    const o = optimistic[d.ref];
    if (o === true) return d.seen_at ?? local[d.ref] ?? new Date().toISOString();
    if (o === false) return null;
    return d.seen_at ?? local[d.ref] ?? null;
  }, [optimistic, local]);
  const matches = (d: Output) => (query.seen == null || query.seen === !!seenAt(d)) && (!query.category || categoryOf(d) === query.category);
  const list = loaded.filter(matches);
  const sel = params.get('ref') ?? null;
  const order = useMemo(() => list.map((d) => d.ref), [list]);
  const pick = useSelection(order);
  const [confirm, setConfirm] = useState(false);
  const [seenBusy, setSeenBusy] = useState(false);
  const clean = useCleanup((refs) => { pick.clear(); setConfirm(false); if (sel && refs.includes(sel)) router.replace(`/outputs${tab !== 'new' ? `?tab=${tab}` : ''}`, { scroll: false }); });
  const filedCount = (refs: string[]) => refs.filter((r) => loaded.find((d) => d.ref === r)?.filed_as).length;
  const { clear: clearPick } = pick;
  // Another tab, filter or search is another list: nothing stays chosen from the last one.
  useEffect(() => { clearPick(); }, [tab, f, range, applied, clearPick]);

  const mark = useCallback(async (refs: string[], seen: boolean, text: string): Promise<boolean> => {
    if (!refs.length) return false;
    setOptimistic((o) => ({ ...o, ...Object.fromEntries(refs.map((r) => [r, seen])) }));
    const id = Date.now();
    setUndo({ id, text, run: () => {
      setOptimistic((o) => ({ ...o, ...Object.fromEntries(refs.map((r) => [r, !seen])) }));
      act.seen.mutate({ refs, seen: !seen });
    } });
    try {
      const out = await act.seen.mutateAsync({ refs, seen });
      if (out.local && !localStorage.getItem('hq.seen.told')) {
        localStorage.setItem('hq.seen.told', '1');
        toast({ tone: 'info', text: '«خوانده‌شده» فعلاً در همین مرورگر نگه داشته میشود؛ با به‌روزرسانی هاب همگام میشود.' });
      }
      return true;
    } catch (e) {
      setOptimistic((o) => { const n = { ...o }; for (const r of refs) delete n[r]; return n; });
      setUndo((u) => (u?.id === id ? null : u));
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' });
      return false;
    }
  }, [act.seen, toast, setOptimistic]);

  const unseen = (inbox.data as Inbox21 | undefined)?.deliverables_unseen ?? (tab === 'new' && q.data ? list.length : null);
  // Two makers with one title (each company's own) are told apart by their company's name.
  const producers = useMemo(() => {
    const all = [...new Map(loaded.map((d) => [d.producer.code, { ...d.producer, company: d.company }])).values()];
    const twice = (t: string) => all.filter((x) => x.title_fa === t).length > 1;
    return all.map((x) => ({ ...x, label: twice(x.title_fa) ? `${x.title_fa} ${companies?.find((c) => c.code === x.company)?.name_fa ?? x.company}` : x.title_fa }))
      .sort((a, b) => a.label.localeCompare(b.label, 'fa'));
  }, [loaded, companies]);
  const days = useMemo(() => {
    const m = new Map<string, Output[]>();
    for (const d of list) { const k = ownerDay(d.created_at); m.set(k, [...(m.get(k) ?? []), d]); }
    return [...m];
  }, [list]);
  const nActive = activeFilters(query);
  const companyFa = (code: string) => companies?.find((c) => c.code === code)?.name_fa ?? code;
  // M14: the card that was tapped grows into the output's page (its header takes the shared name once the output is there).
  const open = (ref: string, from?: HTMLElement) => viewTransition(() => router.replace(`/outputs?ref=${ref}${tab !== 'new' ? `&tab=${tab}` : ''}`, { scroll: false }), from, { route: true, wait: 500 });
  const back = () => router.replace(`/outputs${tab !== 'new' ? `?tab=${tab}` : ''}`, { scroll: false });
  // M18: once the list has scrolled under its bar, the search folds away and the chips stay as one bar.
  const { sentinel, stuck } = useStuck();
  const wide = useWide();

  return (
    <>
      {/* On a phone an open output is the whole page: the list's own header leaves (and the output's title is the page's heading). */}
      {sel && !wide ? null : (
      <div className={cx(sel && 'max-lg:hidden')}>
        <PageHeader eyebrow="آنچه ایجنت‌ها و گزارش‌های هاب تحویل داده‌اند" title="خروجی‌ها">
          <div className="flex flex-col gap-2">
            <OutputsTabs />
            <div className="max-w-md"><Segmented label="نمایش" value={tab} onChange={setTab} options={[
              { value: 'new', label: unseen ? `تازه (${unseen})` : 'تازه' }, { value: 'seen', label: 'خوانده‌شده' }, { value: 'all', label: 'همه' },
            ]} /></div>
          </div>
        </PageHeader>
      </div>
      )}
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(320px,440px)_minmax(0,1fr)] [&>*]:min-w-0">
        {/* On a phone an open output takes the list's place (its own «خروجی‌ها» leads back). */}
        <Card className={cx('flex flex-col gap-3 p-3 lg:sticky lg:top-20 lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto [&>*]:shrink-0', sel && 'max-lg:hidden')} data-testid="outputs-list">
          <div ref={sentinel} aria-hidden className="-mb-3" />
          <div data-stuck={stuck ? '' : undefined} data-testid="outputs-bar" className={cx(STICKY_TOP, 'hq-m18 sticky z-10 -mx-1 flex flex-col gap-2 rounded-[12px] px-1 py-1 lg:static', stuck && 'max-lg:bg-card/95 max-lg:shadow-[0_8px_20px_rgba(0,0,0,.18)] max-lg:backdrop-blur-md')}>
          <div className="hq-m18-fold relative lg:!block">
            <span className="pointer-events-none absolute inset-y-0 start-3 flex items-center text-muted"><Icon name="search" size={16} /></span>
            <input value={search} onChange={(e) => setSearch(e.target.value)} maxLength={100} placeholder="جستجو در عنوان و خلاصه" aria-label="جستجو در خروجی‌ها" className={cx(inputCls, 'ps-9')} />
          </div>
          <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
            <FilterChip selected={nActive > 0} onClick={() => setFilters(true)} count={nActive || undefined}><Icon name="filter" size={14} />فیلترها</FilterChip>
            <FilterChip selected={!!f.unrated} onClick={() => setF({ ...f, unrated: !f.unrated })}>بی‌امتیاز</FilterChip>
            <FilterChip selected={f.category === 'report'} onClick={() => setF({ ...f, category: f.category === 'report' ? null : 'report' })}>گزارش</FilterChip>
            <FilterChip selected={f.category === 'work'} onClick={() => setF({ ...f, category: f.category === 'work' ? null : 'work' })}>کار</FilterChip>
            {f.company ? <FilterChip selected onClick={() => setF({ ...f, company: null })}>× {companyFa(f.company)}</FilterChip> : null}
            {f.producer ? <FilterChip selected onClick={() => setF({ ...f, producer: null })}>× {producers.find((p) => p.code === f.producer)?.label ?? f.producer}</FilterChip> : null}
            {range !== 'all' ? <FilterChip selected onClick={() => setRange('all')}>× {RANGES.find(([k]) => k === range)?.[1]}</FilterChip> : null}
          </div>
          </div>
          {q.isLoading ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-28 rounded-[14px]" />)
            : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
            : !list.length ? (
              tab === 'new' && !nActive && !applied ? <Empty icon="seal" title="چیز تازه‌ای نمانده" body="هر خروجی تازه این‌جا میاید؛ خوانده‌شده‌ها در «خوانده‌شده» میمانند تا خودت بایگانی یا پاکشان کنی." />
                : tab === 'seen' && !nActive && !applied ? <Empty icon="deliverable" title="هنوز چیزی خوانده‌شده نیست" body="روی یک خروجی «خوانده شد» را بزن تا این‌جا بیاید." />
                : <Empty icon="filter" title="خروجی‌ای با این فیلترها نیست" />
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2 px-1">
                  <SelectAll all={pick.all} some={pick.some} count={list.length} onToggle={pick.toggleAll} />
                  <span className="flex-1" />
                  {tab === 'new' ? <Button variant="text" size="sm" icon="seal" onClick={() => void mark(list.map((d) => d.ref), true, `${list.length} خروجی خوانده شد`)}>همه را خوانده‌شده کن</Button> : null}
                </div>
                {days.map(([day, rows]) => (
                  <section key={day} className="flex flex-col gap-1" aria-label={dayFa(day)}>
                    <div className="flex items-center gap-2 px-1 pt-1">
                      <span className="text-[12px] font-semibold text-sec">{dayFa(day)}</span>
                      <span className="h-px flex-1 bg-div" />
                      <span className="text-[11px] text-muted">{rows.length} خروجی</span>
                    </div>
                    {rows.map((d, i) => {
                      const seen = !!seenAt(d);
                      return <div key={d.ref} className={STAGGER} style={staggerStyle(i)}><OutputRow d={d} seen={seen} selected={sel === d.ref} checked={pick.has(d.ref)} companyFa={companyFa(d.company)} onOpen={(from) => open(d.ref, from)}
                        onMark={() => void mark([d.ref], !seen, seen ? `${d.ref} دوباره تازه شد` : `${d.ref} خوانده شد`)} onCheck={(range) => pick.toggle(d.ref, range)} /></div>;
                    })}
                  </section>
                ))}
                {q.hasNextPage ? <Button variant="secondary" icon="next" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>بیشتر</Button> : null}
                <SelectionBar count={pick.chosen.length} filed={filedCount(pick.chosen)} busy={{ file: clean.filing, seen: seenBusy }} onClear={pick.clear}
                  onFile={async () => { if (await clean.file(pick.chosen.filter((r) => !loaded.find((d) => d.ref === r)?.filed_as))) pick.clear(); }}
                  onSeen={async () => { setSeenBusy(true); try { if (await mark(pick.chosen, true, `${pick.chosen.length.toLocaleString('fa-IR')} خروجی خوانده شد`)) pick.clear(); } finally { setSeenBusy(false); } }}
                  onDelete={() => setConfirm(true)} />
              </>
            )}
        </Card>
        <Card className={cx('p-4 lg:p-7', !sel && 'max-lg:hidden')}>{sel ? (
          <OutputDetail key={sel} refId={sel} onSeen={mark} onGone={back} heading={wide ? 'h2' : 'h1'}
            back={<button type="button" onClick={back} className="inline-flex h-8 items-center gap-1 rounded-[8px] text-[12px] text-muted hover:text-ink lg:hidden"><Icon name="back" size={14} mirror />خروجی‌ها</button>} />
        ) : <Empty icon="deliverable" title="یک خروجی را انتخاب کن" body="هر خروجی که بخوانی و «خوانده شد» بزنی به «خوانده‌شده» میرود. چند تا را با جعبه‌ی کنارشان انتخاب کن تا یک‌جا بایگانی، خوانده‌شده یا برای همیشه پاکشان کنی." />}</Card>
      </div>
      <Filters open={filters} onOpenChange={setFilters} query={query} set={(x) => setF({ ...f, ...x })} producers={producers} range={range} setRange={setRange} count={q.data ? list.length : null}
        onClear={() => { setF({ category: null, unrated: false, company: null, producer: null }); setRange('all'); }} />
      <UndoBar undo={undo} onDone={(id) => setUndo((u) => (u?.id === id ? null : u))} />
      <DeleteDialog open={confirm} onOpenChange={setConfirm} count={pick.chosen.length} filed={filedCount(pick.chosen)} busy={clean.removing} onConfirm={async () => { if (await clean.remove(pick.chosen)) setConfirm(false); }} />
    </>
  );
}

export default function OutputsPage() {
  return <Suspense><OutputsInner /></Suspense>;
}
