'use client';

/**
 * ⟨1.0.1⟩ §47.4 «دفتر موضوع‌ها»: what a company already said in a working group, so no day repeats another.
 *
 * The owner's order was «هیچ روزی تکراری نباشد». The hub keeps each day's topic and each outside sample in a ledger and refuses one that
 * is said again. Under each member of a working group one row says how much is in it and opens it: he looks for a line, adds one
 * himself («این را قبلاً گفته‌ایم»), or frees one so it may be made again. Nothing is shown on a hub before §47.
 */
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaText } from '@/components/v29/text';
import { ApiError } from '@/lib/api/client';
import { SOURCE_FA, ledgerCountsFa, useLedger, useLedgerActions, useLedgerCounts, type TopicEntry, type TopicKind } from '@/lib/api/v47';
import { cx, jDate, safeHref } from '@/lib/format';

const FIELD = 'w-full rounded-[10px] border border-strong bg-tile px-3 text-[14px] text-ink outline-none transition-colors placeholder:text-muted focus:border-gold-ink';
const QUIET = 'h-8 flex-none rounded-[8px] px-2 text-[12px] font-semibold';

/** One member's row: the counts, and the way into the ledger. */
export function LedgerRow({ group, company, nameFa }: { group: string; company: string; nameFa: string }) {
  const q = useLedgerCounts(group, company);
  const [open, setOpen] = useState(false);
  if (!q.data) return null;
  return (
    <div className="flex items-center gap-3 ps-7" data-ledger={company}>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-[12px] text-sec">دفتر موضوع‌ها</span>
        <span className="truncate text-[11px] text-muted" data-ledger-counts>{ledgerCountsFa(q.data)}</span>
      </span>
      <button type="button" aria-haspopup="dialog" aria-label={`دفتر موضوع‌های ${nameFa}`} onClick={() => setOpen(true)} className={cx(QUIET, 'text-gold-ink hover:bg-gold-soft')}>باز کن</button>
      {open ? <LedgerSheet group={group} company={company} nameFa={nameFa} onClose={() => setOpen(false)} /> : null}
    </div>
  );
}

function Line({ t, freeing, busy, onAsk, onFree, onKeep }: { t: TopicEntry; freeing: boolean; busy: boolean; onAsk: () => void; onFree: () => void; onKeep: () => void }) {
  const href = t.kind === 'reference' ? safeHref(t.url) : null;
  // a sample with no words of its own is its address: said once, as the link
  const titled = !!t.title_fa && t.title_fa !== t.url;
  return (
    <li className="flex flex-col gap-1 py-2.5" data-topic={t.kind}>
      <div className="flex items-start gap-2">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          {titled ? <span className="text-[13px] leading-6 text-ink [overflow-wrap:anywhere]"><FaText text={t.title_fa} /></span> : null}
          {href ? <a href={href} target="_blank" rel="noreferrer" dir="ltr" className="fig truncate text-right text-[12px] text-gold-ink hover:underline">{href.replace(/^https?:\/\/(www\.)?/, '')}</a>
            : t.kind === 'reference' && t.url ? <span dir="ltr" className="fig truncate text-right text-[12px] text-sec">{t.url}</span> : null}
          <span className="text-[11px] text-muted">{jDate(t.at, true)} · {SOURCE_FA[t.source] ?? 'ثبت‌شده'}</span>
        </div>
        {freeing ? null : <button type="button" onClick={onAsk} className={cx(QUIET, 'text-sec hover:bg-hover hover:text-ink')}>آزاد کن</button>}
      </div>
      {freeing ? (
        <div role="group" aria-label="آزاد کردن این خط" className="flex flex-wrap items-center gap-2">
          <span className="min-w-0 flex-1 text-[12px] text-sec">دوباره قابل ساخت میشود.</span>
          <Button size="sm" variant="secondary" loading={busy} onClick={onFree}>آزاد کن</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={onKeep}>نه</Button>
        </div>
      ) : null}
    </li>
  );
}

function LedgerSheet({ group, company, nameFa, onClose }: { group: string; company: string; nameFa: string; onClose: () => void }) {
  const toast = useToast();
  const [kind, setKind] = useState<TopicKind>('topic');
  const [search, setSearch] = useState('');
  const [applied, setApplied] = useState('');
  useEffect(() => { const t = setTimeout(() => setApplied(search.trim()), 350); return () => clearTimeout(t); }, [search]);
  const q = useLedger(group, company, kind, applied);
  const act = useLedgerActions(group, company);
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [refused, setRefused] = useState<string | null>(null);
  const [freeing, setFreeing] = useState<string | null>(null);

  const first = q.data?.pages[0] ?? null;
  const items = q.data?.pages.flatMap((p) => p?.items ?? []) ?? [];
  const reference = kind === 'reference';
  const ready = reference ? !!url.trim() : !!title.trim();
  const pick = (k: TopicKind) => { setKind(k); setRefused(null); setFreeing(null); };
  const add = () => act.add.mutate({ kind, title_fa: title.trim() || undefined, url: reference ? url.trim() : undefined }, {
    onSuccess: () => { setTitle(''); setUrl(''); setRefused(null); toast({ tone: 'ok', text: reference ? 'نمونه در دفتر ثبت شد.' : 'موضوع در دفتر ثبت شد.' }); },
    // said already (409), or not a line the ledger takes (422): the hub's own words, under the field
    onError: (e) => { if (e instanceof ApiError && (e.status === 409 || e.status === 422)) setRefused(e.messageFa); else toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد؛ دوباره بزن.' }); },
  });
  const free = (id: string) => act.free.mutate(id, {
    onSuccess: () => { setFreeing(null); toast({ tone: 'info', text: 'آزاد شد؛ دوباره میشود ساختش.' }); },
    onError: (e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'آزاد نشد؛ دوباره بزن.' }),
  });

  return (
    <Sheet
      open onOpenChange={(v) => { if (!v) onClose(); }} title="دفتر موضوع‌ها" description={`${nameFa} · هر چه این‌جاست دوباره ساخته نمیشود`} width={520}
      footer={(
        <form className="flex flex-col gap-2" aria-label="افزودن به دفتر" onSubmit={(e) => { e.preventDefault(); if (ready && !act.add.isPending) add(); }}>
          <div className="flex gap-2">
            <input value={title} onChange={(e) => { setTitle(e.target.value.slice(0, 300)); setRefused(null); }} dir="auto" placeholder="این را قبلاً گفته‌ایم…" aria-label={reference ? 'نام نمونه' : 'موضوعی که قبلاً گفته‌ایم'} className={cx(FIELD, 'h-11 min-w-0 flex-1')} />
            <Button type="submit" variant="primary" size="lg" icon="add" disabled={!ready} loading={act.add.isPending}>افزودن</Button>
          </div>
          {reference ? <input value={url} onChange={(e) => { setUrl(e.target.value.slice(0, 2000)); setRefused(null); }} dir="ltr" inputMode="url" placeholder="https://…" aria-label="لینک نمونه" className={cx(FIELD, 'fig h-11')} /> : null}
          {refused ? <p role="alert" className="text-[12px] leading-5 text-neg"><FaText text={refused} /></p>
            : <p className="text-[11px] leading-5 text-muted">{reference ? 'نمونه با لینکش ثبت میشود و دیگر از روی آن ساخته نمیشود.' : 'موضوعی که پیش از این گفته‌اید را بنویسید تا دوباره ساخته نشود.'}</p>}
        </form>
      )}
    >
      <div className="flex flex-col gap-3">
        <input value={search} onChange={(e) => setSearch(e.target.value.slice(0, 100))} dir="auto" placeholder="جستجو در دفتر" aria-label="جستجو در دفتر" className={cx(FIELD, 'h-11')} />
        <Segmented<TopicKind>
          label="موضوع یا نمونه" value={kind} onChange={pick}
          options={[
            { value: 'topic', label: <>موضوع‌ها{first ? <span className="text-[11px] text-muted">{first.topics}</span> : null}</> },
            { value: 'reference', label: <>نمونه‌ها{first ? <span className="text-[11px] text-muted">{first.references}</span> : null}</> },
          ]}
        />
        {q.isLoading ? <div className="flex flex-col gap-2">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-12 rounded-[10px]" />)}</div>
          : q.error ? <p role="alert" className="text-[13px] text-neg">{q.error instanceof ApiError ? q.error.messageFa : 'دفتر خوانده نشد.'}</p>
          : items.length ? (
            <>
              <ul className="flex flex-col divide-y divide-[var(--hq-div)]" aria-label={reference ? 'نمونه‌های ثبت‌شده' : 'موضوع‌های ثبت‌شده'}>
                {items.map((t) => <Line key={t.id} t={t} freeing={freeing === t.id} busy={act.free.isPending} onAsk={() => setFreeing(t.id)} onFree={() => free(t.id)} onKeep={() => setFreeing(null)} />)}
              </ul>
              {q.hasNextPage ? <Button variant="secondary" icon="next" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>بیشتر</Button> : null}
            </>
          ) : <p className="py-6 text-center text-[13px] text-muted">{applied ? 'چیزی با این جستجو پیدا نشد.' : reference ? 'هنوز نمونه‌ای ثبت نشده.' : 'هنوز موضوعی ثبت نشده.'}</p>}
      </div>
    </Sheet>
  );
}
