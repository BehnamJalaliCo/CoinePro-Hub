'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { Avatar } from '@/components/brand/avatar';
import { CompanyMark } from '@/components/brand/marks';
import { Button, IconButton } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, Rating, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { RefChip, ScopeChips } from '@/components/v17/bits';
import { RANGES, UndoBar, dayFa, inputCls, ownerDay, span, type Undo } from '@/components/v21/bits';
import { DeleteDialog, DeleteOne, RowCheck, SelectAll, SelectionBar, useCleanup, useSelection } from '@/components/v28/outputs';
import { ApiError } from '@/lib/api/client';
import { handled } from '@/lib/api/observe';
import { useCompanies, useInbox, useRate } from '@/lib/api/hooks';
import { activeFilters, categoryOf, useLocalSeen, useOutput, useOutputActions, useOutputs, type Category, type Inbox21, type Output, type OutputQuery } from '@/lib/api/v21';
import { useScope } from '@/lib/scope';
import { cx, jDateTime, jTime, modelLabel, tokens, usd } from '@/lib/format';

// Outputs (0.3.0, contract §5.2 ⟨1.7.3⟩): what the agents and the hub's own reporting delivered. The owner reads one and marks it seen (the
// button on the row or on its page, or all at once): it leaves «تازه» for «خوانده‌شده» and stays, so agents and the digital chief keep
// learning from it, search and the archive still find it, and it can be filed in the archive to be cited later. Rating stays separate.
// ⟨1.10⟩ §28.1: outputs must not pile up — the owner chooses several (a box on each row, shift for a range, «همه») and files them, marks
// them seen, or deletes them for good (the passkey on exactly that set; one Audit line each stays). Only the owner ever deletes one.

const CATEGORY_FA: Record<Category, string> = { report: 'گزارش', work: 'کار' };
type Tab = 'new' | 'seen' | 'all';

/** `usage` as the hub writes it (§5.2: input, output and cache tokens, cost and equivalent cost), or the older `{tokens, usd}`. */
function usageOf(d: Output): { used: number | null; cost: string | null } {
  const u = (d.usage ?? {}) as Record<string, unknown>;
  const n = (k: string) => (typeof u[k] === 'number' ? (u[k] as number) : null);
  const s = (k: string) => (u[k] == null ? null : String(u[k]));
  const parts = ['input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens'].map(n).filter((x): x is number => x != null);
  const used = n('tokens') ?? (parts.length ? parts.reduce((a, b) => a + b, 0) : null);
  const cost = s('usd') ?? (Number(s('cost_usd') ?? 0) > 0 ? s('cost_usd') : s('equiv_cost_usd'));
  return { used: used && used > 0 ? used : null, cost };
}

function RatePanel({ d }: { d: Output }) {
  const rate = useRate();
  const toast = useToast();
  const [score, setScore] = useState(d.rating?.score ?? 0);
  const [hover, setHover] = useState<number | null>(null);
  const [comment, setComment] = useState(d.rating?.comment ?? '');
  const dirty = score !== (d.rating?.score ?? 0) || comment !== (d.rating?.comment ?? '');
  return (
    <section className="flex flex-col gap-3 rounded-[16px] bg-tile/60 p-4">
      <div className="flex flex-col gap-0.5">
        <h3 className="text-[15px] font-semibold">{d.rating ? 'امتیاز تو (قابل تغییر)' : 'امتیاز تو'}</h3>
        <span className="text-[12px] text-muted">امتیاز تو ۴۰٪ نمره‌ی کارمند است و در یادگیری او اثر دارد؛ جدا از «خوانده‌شده».</span>
      </div>
      <div className="no-scrollbar overflow-x-auto"><Rating value={score} hover={hover} onHover={setHover} onChange={setScore} label="امتیاز خروجی" /></div>
      <textarea value={comment ?? ''} onChange={(e) => setComment(e.target.value)} rows={2} maxLength={5000} placeholder="نکته برای کارمند (اختیاری)" className="rounded-[10px] border border-strong bg-tile p-3 text-[14px] text-ink outline-none focus:border-gold-ink" />
      <div className="flex items-center gap-3">
        {d.rating ? <span className="flex-1 text-[12px] text-gold-ink">{d.rating.score} از ۱۰، {jDateTime(d.rating.rated_at)}</span> : <span className="flex-1" />}
        <Button variant="primary" icon="rate" disabled={!score || !dirty} loading={rate.isPending} onClick={async () => {
          try { await rate.mutateAsync({ ref: d.ref, score, comment: comment || undefined }); toast({ tone: 'ok', text: `امتیاز ${score} ثبت شد.` }); }
          catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' }); }
        }}>ثبت امتیاز</Button>
      </div>
    </section>
  );
}

/** One deliverable: summary, body, evidence, what produced it, seen and filing, and the owner's rating. */
function Detail({ refId, onSeen, onGone }: { refId: string; onSeen: (refs: string[], seen: boolean, text: string) => Promise<boolean>; onGone: () => void }) {
  const q = useOutput(refId);
  const act = useOutputActions();
  const toast = useToast();
  const local = useLocalSeen();
  const { data: companies } = useCompanies();
  const [busy, setBusy] = useState(false);
  if (q.isLoading) return <div className="flex flex-col gap-3"><Skeleton className="h-16" /><Skeleton className="h-64" /></div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  if (!d?.ref) return <Empty icon="deliverable" title="این خروجی پیدا نشد" />;
  const seenAt = d.seen_at ?? local[d.ref] ?? null;
  const cat = categoryOf(d);
  const pw = (d.produced_with ?? {}) as Record<string, string>;
  const model = pw.label_fa ?? (pw.model ? `${modelLabel(pw.model)}${pw.effort ? ` · ${pw.effort}` : ''}` : null);
  const { used, cost } = usageOf(d);
  const file = async () => {
    try {
      const out = await act.file.mutateAsync(d.ref);
      toast({ tone: 'ok', text: <>در بایگانی ثبت شد: <span className="fig">{out.record}</span>؛ پیش‌نویس است تا بایگان کاملش کند.</> });
      void q.refetch();
    } catch (e) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 405)) { handled(e); toast({ tone: 'info', text: 'بایگانی خروجی با به‌روزرسانی هاب فعال میشود.' }); }
      else toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'بایگانی نشد.' });
    }
  };
  return (
    <article className="flex flex-col gap-5">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
          <Pill tone={cat === 'report' ? 'lapis' : 'silver'}>{CATEGORY_FA[cat]}</Pill>
          <span className="text-sec"><CompanyMark code={d.company} height={13} mono /></span>
          <span>{companies?.find((c) => c.code === d.company)?.name_fa ?? d.company}</span>
          <span className="fig">{d.ref}</span>
        </div>
        <h2 className="text-h2 font-semibold leading-9">{d.title}</h2>
      </header>
      {/* Seen, and filed in the archive (⟨1.7.3⟩): the two things done with an output once read. */}
      <div className="flex flex-wrap items-center gap-2">
        {!seenAt ? (
          <Button variant="primary" size="sm" icon="seal" loading={busy} onClick={async () => { setBusy(true); try { if (await onSeen([d.ref], true, `${d.ref} به «خوانده‌شده» رفت`)) void q.refetch(); } finally { setBusy(false); } }}>خوانده شد</Button>
        ) : (
          <>
            <Pill tone="pos" icon="seal">خوانده شد، {jDateTime(seenAt)}</Pill>
            <Button variant="text" size="sm" loading={busy} onClick={async () => { setBusy(true); try { if (await onSeen([d.ref], false, `${d.ref} دوباره تازه شد`)) void q.refetch(); } finally { setBusy(false); } }}>دوباره تازه کن</Button>
          </>
        )}
        {d.filed_as ? <RefChip r={d.filed_as} note="در بایگانی" /> : <Button variant="secondary" size="sm" icon="deliverable" loading={act.file.isPending} onClick={file}>بایگانی کن</Button>}
        <span className="flex-1" />
        <DeleteOne refId={d.ref} filed={!!d.filed_as} onGone={onGone} />
      </div>
      <div className="flex items-center gap-3 rounded-[14px] bg-tile/60 p-3">
        <Link href={`/employees/${d.producer.code}`} className="flex min-w-0 flex-1 items-center gap-3 rounded-[10px] hover:text-gold-ink">
          <Avatar kind={d.producer.kind} dept={d.producer.department} size={40} />
          <span className="flex min-w-0 flex-1 flex-col">
            <span className="text-[13px] font-semibold">{d.producer.title_fa}</span>
            <span className="text-[11px] text-muted"><span className="fig">{d.producer.code}</span>، {jDateTime(d.created_at)}</span>
          </span>
        </Link>
        {d.work_ref ? <Link href={`/work/${d.work_ref}`} className="inline-flex h-8 flex-none items-center gap-1.5 rounded-full bg-tile px-3 text-[12px] text-sec hover:text-ink"><Icon name="task" size={14} />کار مربوط <span className="fig">{d.work_ref}</span></Link> : null}
      </div>
      <div className="rounded-[14px] bg-gold-soft p-4">
        <span className="text-[12px] font-semibold text-gold-ink">خلاصه</span>
        <Md text={d.summary} className="mt-1 flex flex-col gap-2 text-[14px] leading-7 text-ink" />
      </div>
      <Md text={d.body} />
      {model || used ? (
        <div className="flex flex-wrap gap-6 rounded-[12px] bg-tile p-3">
          {model ? <div className="flex flex-col"><span className="text-[11px] text-muted">ساخته‌شده با</span><span className={cx('text-[13px] font-semibold', !/[؀-ۿ]/.test(model) && 'fig')}>{model}</span></div> : null}
          {used ? <div className="flex flex-col"><span className="text-[11px] text-muted">مصرف</span><span className="fig text-[13px] font-semibold">{tokens(used)} tok · {usd(cost)}</span></div> : null}
        </div>
      ) : null}
      {d.attachments?.length ? (
        <section className="flex flex-col gap-1.5">
          <h3 className="text-[12px] font-semibold text-gold-ink">پیوست‌ها</h3>
          {d.attachments.map((f) => <span key={f.id} className="fig text-[12px] text-sec">{f.name} · {Math.round(f.size / 1024)} KB</span>)}
        </section>
      ) : null}
      {Array.isArray(d.evidence) && d.evidence.length ? (
        <section className="flex flex-col gap-2">
          <h3 className="text-[12px] font-semibold text-gold-ink">شاهد</h3>
          <ul className="flex flex-col gap-1">{(d.evidence as Array<Record<string, string>>).map((e, i) => <li key={i} className="flex items-center gap-2 text-[13px] text-sec"><Icon name="seal" size={14} /><span className="fig">{e.kind}</span><span className="fig text-muted">{e.ref}</span>{e.note ? <span className={/[A-Za-z]/.test(e.note) ? 'fig' : undefined}>{e.note}</span> : null}</li>)}</ul>
        </section>
      ) : null}
      <RatePanel key={`${d.ref}-${d.rating?.rated_at ?? ''}`} d={d} />
    </article>
  );
}

/** One output in the list: a new one carries a gold dot and full ink; a seen one is quieter. Its button marks it either way. */
function Row({ d, seen, selected, checked, companyFa, onOpen, onMark, onCheck }: {
  d: Output; seen: boolean; selected: boolean; checked: boolean; companyFa: string; onOpen: () => void; onMark: () => void; onCheck: (range: boolean) => void;
}) {
  const cat = categoryOf(d);
  return (
    <div className={cx('group relative flex gap-2 rounded-[14px] p-3 transition-colors', selected ? 'tahrir bg-gold-soft' : checked ? 'bg-gold-soft/60' : 'hover:bg-hover')}>
      <RowCheck on={checked} label={`انتخاب ${d.ref}: ${d.title}`} onToggle={onCheck} />
      <button type="button" onClick={onOpen} className="flex min-w-0 flex-1 flex-col gap-1.5 text-start" aria-current={selected || undefined}>
        <span className="flex items-center gap-2">
          {!seen ? <span className="size-2 flex-none rounded-full bg-gold" aria-label="تازه" /> : null}
          <Pill tone={cat === 'report' ? 'lapis' : 'silver'} className="h-5 px-2 text-[11px]">{CATEGORY_FA[cat]}</Pill>
          <span className="text-sec"><CompanyMark code={d.company} height={12} mono /></span>
          <span className="min-w-0 flex-1 truncate text-[11px] text-muted">{companyFa}</span>
          {d.rating ? <Pill tone="silver" className="h-5 px-2 text-[11px]">{d.rating.score} از ۱۰</Pill> : <Pill tone="gold" dot className="h-5 px-2 text-[11px]">بی‌امتیاز</Pill>}
        </span>
        <span className={cx('line-clamp-2 text-[14px] font-semibold leading-6', seen ? 'text-sec' : 'text-ink')}>{d.title}</span>
        <span className={cx('line-clamp-2 text-[12px] leading-5', seen ? 'text-muted' : 'text-sec')}>{d.summary}</span>
        <span className="flex items-center gap-1.5 text-[11px] text-muted">
          <span className="min-w-0 truncate">{d.producer.title_fa}، {jTime(d.created_at)}، <span className="fig">{d.ref}</span></span>
          {d.filed_as ? <span className="ms-auto inline-flex flex-none items-center gap-1"><Icon name="deliverable" size={12} /><span className="fig">{d.filed_as}</span></span> : null}
        </span>
      </button>
      <IconButton icon={seen ? 'refresh' : 'seal'} label={seen ? 'دوباره تازه' : 'خوانده شد'} size={34} onClick={onMark} className={cx('self-start', !seen && 'text-pos', 'opacity-70 group-hover:opacity-100 focus-visible:opacity-100')} />
    </div>
  );
}

function Filters({ open, onOpenChange, query, set, producers, range, setRange, onClear }: {
  open: boolean; onOpenChange: (v: boolean) => void; query: OutputQuery; set: (p: Partial<OutputQuery>) => void;
  producers: Output['producer'][]; range: string; setRange: (r: string) => void; onClear: () => void;
}) {
  const label = 'text-[12px] font-semibold text-sec';
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="فیلترها" description="روی هر سه زبانه اعمال میشوند" width={460}
      footer={<div className="flex gap-2"><Button variant="primary" icon="filter" className="flex-1" onClick={() => onOpenChange(false)}>نمایش</Button><Button variant="ghost" onClick={onClear}>پاک کردن فیلترها</Button></div>}>
      <div className="flex flex-col gap-6">
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
              {producers.map((p) => <FilterChip key={p.code} selected={query.producer === p.code} onClick={() => set({ producer: p.code })}>{p.title_fa}</FilterChip>)}
            </div>
          </div>
        ) : null}
        <div className="flex flex-col gap-2">
          <span className={label}>بازه‌ی زمانی</span>
          <div className="flex flex-wrap gap-2">{RANGES.map(([k, fa]) => <FilterChip key={k} selected={range === k} onClick={() => setRange(k)}>{fa}</FilterChip>)}</div>
        </div>
      </div>
    </Sheet>
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
  const producers = useMemo(() => [...new Map(loaded.map((d) => [d.producer.code, d.producer])).values()].sort((a, b) => a.title_fa.localeCompare(b.title_fa, 'fa')), [loaded]);
  const days = useMemo(() => {
    const m = new Map<string, Output[]>();
    for (const d of list) { const k = ownerDay(d.created_at); m.set(k, [...(m.get(k) ?? []), d]); }
    return [...m];
  }, [list]);
  const nActive = activeFilters(query);
  const companyFa = (code: string) => companies?.find((c) => c.code === code)?.name_fa ?? code;
  const open = (ref: string) => router.replace(`/outputs?ref=${ref}${tab !== 'new' ? `&tab=${tab}` : ''}`, { scroll: false });

  return (
    <>
      <PageHeader eyebrow="آنچه ایجنت‌ها و گزارش‌های هاب تحویل داده‌اند" title="خروجی‌ها">
        <div className="max-w-md"><Segmented label="نمایش" value={tab} onChange={setTab} options={[
          { value: 'new', label: unseen ? `تازه (${unseen})` : 'تازه' }, { value: 'seen', label: 'خوانده‌شده' }, { value: 'all', label: 'همه' },
        ]} /></div>
      </PageHeader>
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(320px,440px)_minmax(0,1fr)] [&>*]:min-w-0">
        <Card className="flex flex-col gap-3 p-3 lg:sticky lg:top-20 lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto [&>*]:shrink-0">
          <div className="relative">
            <span className="pointer-events-none absolute inset-y-0 start-3 flex items-center text-muted"><Icon name="search" size={16} /></span>
            <input value={search} onChange={(e) => setSearch(e.target.value)} maxLength={100} placeholder="جستجو در عنوان و خلاصه" aria-label="جستجو در خروجی‌ها" className={cx(inputCls, 'ps-9')} />
          </div>
          <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
            <FilterChip selected={nActive > 0} onClick={() => setFilters(true)} count={nActive || undefined}><Icon name="filter" size={14} />فیلترها</FilterChip>
            <FilterChip selected={!!f.unrated} onClick={() => setF({ ...f, unrated: !f.unrated })}>بی‌امتیاز</FilterChip>
            <FilterChip selected={f.category === 'report'} onClick={() => setF({ ...f, category: f.category === 'report' ? null : 'report' })}>گزارش</FilterChip>
            <FilterChip selected={f.category === 'work'} onClick={() => setF({ ...f, category: f.category === 'work' ? null : 'work' })}>کار</FilterChip>
            {f.company ? <FilterChip selected onClick={() => setF({ ...f, company: null })}>× {companyFa(f.company)}</FilterChip> : null}
            {f.producer ? <FilterChip selected onClick={() => setF({ ...f, producer: null })}>× {producers.find((p) => p.code === f.producer)?.title_fa ?? f.producer}</FilterChip> : null}
            {range !== 'all' ? <FilterChip selected onClick={() => setRange('all')}>× {RANGES.find(([k]) => k === range)?.[1]}</FilterChip> : null}
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
                    {rows.map((d) => {
                      const seen = !!seenAt(d);
                      return <Row key={d.ref} d={d} seen={seen} selected={sel === d.ref} checked={pick.has(d.ref)} companyFa={companyFa(d.company)} onOpen={() => open(d.ref)}
                        onMark={() => void mark([d.ref], !seen, seen ? `${d.ref} دوباره تازه شد` : `${d.ref} خوانده شد`)} onCheck={(range) => pick.toggle(d.ref, range)} />;
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
        <Card className="p-5 lg:p-7">{sel ? <Detail key={sel} refId={sel} onSeen={mark} onGone={() => router.replace(`/outputs${tab !== 'new' ? `?tab=${tab}` : ''}`, { scroll: false })} />
          : <Empty icon="deliverable" title="یک خروجی را انتخاب کن" body="هر خروجی که بخوانی و «خوانده شد» بزنی به «خوانده‌شده» میرود. چند تا را با جعبه‌ی کنارشان انتخاب کن تا یک‌جا بایگانی، خوانده‌شده یا برای همیشه پاکشان کنی." />}</Card>
      </div>
      <Filters open={filters} onOpenChange={setFilters} query={query} set={(x) => setF({ ...f, ...x })} producers={producers} range={range} setRange={setRange}
        onClear={() => { setF({ category: null, unrated: false, company: null, producer: null }); setRange('all'); }} />
      <UndoBar undo={undo} onDone={(id) => setUndo((u) => (u?.id === id ? null : u))} />
      <DeleteDialog open={confirm} onOpenChange={setConfirm} count={pick.chosen.length} filed={filedCount(pick.chosen)} busy={clean.removing} onConfirm={async () => { if (await clean.remove(pick.chosen)) setConfirm(false); }} />
    </>
  );
}

export default function OutputsPage() {
  return <Suspense><OutputsInner /></Suspense>;
}
