'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Empty, FilterChip, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { ActorAvatar, RefChip } from '@/components/v17/bits';
import { useCases } from '@/lib/api/v19';
import { faError, useHoldAction, useHolds, useRecords, type ArchiveRecord, type HoldScope, type LegalHold } from '@/lib/api/v20';
import { ACTOR_FA } from '@/lib/labels';
import { cx } from '@/lib/format';
import { ErrorLine, JDay, JStamp, bad, fieldErrors, useArchive, type ArchiveMaps, field, fieldArea } from './bits';

/** Does a hold cover a record (§23.12): an explicit record always; otherwise every facet it names must match. */
export function covers(m: ArchiveMaps, s: HoldScope, r: Pick<ArchiveRecord, 'ref' | 'folder' | 'class' | 'parties' | 'doc_date'>): boolean {
  if (s.records?.includes(r.ref)) return true;
  const facets = [s.folders?.length, s.classes?.length, s.parties?.length, s.from || s.to].filter(Boolean).length;
  if (!facets) return false;
  if (s.folders?.length && !s.folders.some((f) => m.folderPath(r.folder).some((x) => x.ref === f))) return false;
  if (s.classes?.length && !s.classes.includes(r.class ?? '')) return false;
  if (s.parties?.length && !r.parties.some((p) => s.parties!.includes(p.party))) return false;
  if (s.from && (!r.doc_date || r.doc_date < s.from)) return false;
  if (s.to && (!r.doc_date || r.doc_date > s.to)) return false;
  return true;
}

/** The facets of a hold in words: explicit records, then folders, classes, parties and dates that must all match. */
export function HoldScopeLine({ s }: { s: HoldScope }) {
  const m = useArchive();
  const facets: React.ReactNode[] = [];
  if (s.folders?.length) facets.push(<span key="f">پوشه‌ی {s.folders.map((f) => m.folder(f)?.title_fa ?? f).join(' یا ')}</span>);
  if (s.classes?.length) facets.push(<span key="c">نوع {s.classes.map((c) => m.cls(c)?.title_fa ?? c).join(' یا ')}</span>);
  if (s.parties?.length) facets.push(<span key="p">با {s.parties.map((p) => m.party(p)?.name_fa ?? p).join(' یا ')}</span>);
  if (s.from || s.to) facets.push(<span key="d" className="inline-flex flex-wrap items-center gap-1">تاریخ سند {s.from ? <>از <JDay d={s.from} /></> : null} {s.to ? <>تا <JDay d={s.to} /></> : null}</span>);
  return (
    <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[12px] text-sec">
      {s.records?.length ? <span className="inline-flex flex-wrap items-center gap-1">این سندها: {s.records.map((r) => <RefChip key={r} r={r} tone="neutral" />)}</span> : null}
      {s.records?.length && facets.length ? <span className="text-muted">و</span> : null}
      {facets.length ? <>هر سند {facets.reduce<React.ReactNode[]>((a, x, i) => (i ? [...a, <span key={`and${i}`} className="text-muted">و</span>, x] : [x]), [])}</> : null}
    </span>
  );
}

export function HoldCard({ h, highlight }: { h: LegalHold; highlight?: boolean }) {
  const act = useHoldAction();
  const toast = useToast();
  const [asking, setAsking] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const active = h.state === 'active';
  const release = async () => {
    setFailure(null);
    try { await act.release.mutateAsync(h.ref); setAsking(false); toast({ tone: 'ok', text: <>توقیف <span className="fig">{h.ref}</span> آزاد شد.</> }); } catch (e) { setAsking(false); setFailure(e); }
  };
  return (
    <article id={h.ref} className={cx('flex min-w-0 scroll-mt-24 flex-col gap-2.5 rounded-[16px] bg-card p-4', highlight && 'ring-2 ring-[var(--hq-gold-ink)]', !active && 'opacity-80')}>
      <header className="flex min-w-0 flex-wrap items-center gap-2">
        <span className={active ? 'text-neg' : 'text-muted'}><Icon name="lock" size={18} /></span>
        <span className="min-w-0 flex-1 text-[15px] font-semibold text-ink">{h.title_fa}</span>
        <span className="fig text-[12px] text-muted">{h.ref}</span>
        {active ? <Pill tone="neg" dot>فعال</Pill> : <Pill>آزادشده</Pill>}
      </header>
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
        {h.case ? <RefChip r={h.case} note="پرونده" /> : <span>بی‌پرونده</span>}
        <span className="inline-flex items-center gap-1"><ActorAvatar a={h.placed_by} size={18} />{ACTOR_FA(h.placed_by)}، <JStamp at={h.placed_at} year /></span>
        {h.released_at ? <span>آزاد: <JStamp at={h.released_at} year /></span> : null}
      </div>
      <Md text={h.reason_md} className="text-[13px] leading-6 text-sec" />
      <HoldScopeLine s={h.scope} />
      {active ? (
        <div className="flex min-w-0 flex-col gap-1.5 rounded-[12px] bg-tile p-3">
          <span className="text-[12px] text-sec">{!h.records ? 'فعلاً سندی زیر آن نیست؛ سند تازه‌ای که بخورد، از همان لحظه توقیف است.' : h.records === 1 ? 'یک سند زیر این توقیف است؛ جز نسخه‌ی تازه تغییری نمیپذیرد و امحا نمیشود.' : `${h.records} سند زیر این توقیف‌اند؛ جز نسخه‌ی تازه تغییری نمیپذیرند و امحا نمیشوند.`}</span>
          {h.record_refs?.length ? <span className="flex flex-wrap gap-1">{h.record_refs.map((r) => <RefChip key={r} r={r} />)}</span> : null}
        </div>
      ) : null}
      <ErrorLine error={failure} />
      {active ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" icon="lock" onClick={() => setAsking(true)}>آزاد کن</Button>
          <span className="text-[11px] text-muted">آزاد کردن فقط با passkey توست.</span>
        </div>
      ) : null}
      <Dialog open={asking} onOpenChange={setAsking} title={<>آزاد کردن <span className="fig">{h.ref}</span></>} actions={<>
        <Button variant="primary" icon="lock" loading={act.release.isPending} onClick={release}>با passkey آزاد کن</Button>
        <Button variant="secondary" onClick={() => setAsking(false)}>نه</Button>
      </>}>
        <p>{h.records === 1 ? 'یک سند زیر آن دوباره تغییرپذیر میشود و اگر نگهداری‌اش تمام شده باشد، در کارت امحای بعدی میآید.' : `${h.records ? `${h.records} سند زیر آن` : 'سندهای زیر آن'} دوباره تغییرپذیر میشوند و اگر نگهداری‌شان تمام شده باشد، در کارت امحای بعدی میآیند.`} passkey بسته به <span className="fig">{h.ref}</span> است.</p>
      </Dialog>
    </article>
  );
}

const REF_RE = /^AR-\d{6}$/;
/** «توقیف تازه»: a title, the case, the reason, and a scope of explicit records or facets that must all match (§23.12). */
export function NewHoldSheet({ onClose, onMade, caseRef }: { onClose: () => void; onMade: (ref: string) => void; caseRef?: string | null }) {
  const m = useArchive();
  const act = useHoldAction();
  const toast = useToast();
  const cases = useCases({});
  const all = useRecords({});
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [title, setTitle] = useState('');
  const [kase, setKase] = useState<string>(caseRef ?? '');
  const [reason, setReason] = useState('');
  const [s, setS] = useState<HoldScope>({});
  const [refText, setRefText] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<unknown>(null);
  const toggle = (k: 'folders' | 'classes' | 'parties', v: string) => setS((x) => { const xs = x[k] ?? []; const n = xs.includes(v) ? xs.filter((y) => y !== v) : [...xs, v]; return { ...x, [k]: n.length ? n : undefined }; });
  const addRef = () => {
    const r = refText.trim().toUpperCase();
    if (!REF_RE.test(r)) return;
    setS((x) => ({ ...x, records: [...new Set([...(x.records ?? []), r])] }));
    setRefText('');
  };
  const records = all.data?.pages.flatMap((p) => p.items) ?? [];
  const hit = records.filter((r) => covers(m, s, r));
  const empty = !s.records?.length && !s.folders?.length && !s.classes?.length && !s.parties?.length && !s.from && !s.to;
  const ok = title.trim().length >= 3 && reason.trim().length >= 10 && !empty;
  const make = async () => {
    setErrors({}); setFailure(null);
    try {
      const h = await act.place.mutateAsync({ key, body: { title_fa: title.trim(), case: kase || null, reason_md: reason.trim(), scope: Object.fromEntries(Object.entries(s).filter(([, v]) => v != null && v !== '')) } });
      toast({ tone: 'ok', text: <>توقیف <span className="fig">{h.ref}</span> گذاشته شد؛ {h.records ?? 0} سند زیر آن است.</> });
      onMade(h.ref);
    } catch (e) { if (e instanceof ApiError && e.status) setKey(crypto.randomUUID()); setErrors(fieldErrors(e)); setFailure(e); }
  };
  const caseList = cases.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={600} title="توقیف تازه" description="سندهای زیر توقیف جز نسخه‌ی تازه تغییری نمیپذیرند و تا آزاد شدن امحا نمیشوند. آزاد کردن فقط با passkey توست."
      footer={<div className="flex flex-wrap items-center gap-2"><Button variant="primary" icon="lock" disabled={!ok} loading={act.place.isPending} onClick={make}>توقیف کن</Button><Button variant="ghost" onClick={onClose}>انصراف</Button>{!empty ? <span className="text-[12px] text-muted">اکنون {hit.length} سند را میگیرد.</span> : null}</div>}>
      <div className="flex flex-col gap-4 text-[13px]">
        <label className="flex flex-col gap-1.5 font-semibold text-sec">عنوان
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={160} placeholder="مثلاً: اختلاف با صرافی بر سر کمیسیون" className={field(errors.title_fa && bad)} />
        </label>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">پرونده‌ی حقوقی
          {/* Refs in an <option> cannot carry the figure class: the whole list takes the figure face (Latin digits), in its own direction. */}
          <select aria-label="پرونده‌ی حقوقی" value={kase} onChange={(e) => setKase(e.target.value)} className={field(errors.case && bad)} style={{ fontFamily: 'var(--font-fig)' }}>
            <option value="">— بدون پرونده —</option>
            {caseList.map((c) => <option key={c.ref} value={c.ref}>{c.ref} · {c.title_fa}</option>)}
            {kase && !caseList.some((c) => c.ref === kase) ? <option value={kase}>{kase}</option> : null}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">دلیل
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} maxLength={5000} placeholder="چه چیزی باید دست‌نخورده بماند و تا کی" className={fieldArea('font-normal', errors.reason_md && bad)} />
        </label>
        <fieldset className="flex flex-col gap-3 rounded-[14px] bg-tile p-3">
          <legend className="sr-only">دامنه‌ی توقیف</legend>
          <span className="text-[12px] leading-5 text-sec">سندهایی که نام میبری همیشه زیر توقیف‌اند؛ بقیه‌ی سندها فقط وقتی که <b className="font-semibold text-ink">همه‌ی</b> قیدهای پایین را داشته باشند.</span>
          <div className="flex flex-col gap-1.5">
            <span className="font-semibold text-sec">سند به سند</span>
            <div className="flex gap-1.5">
              <input aria-label="شناسه‌ی سند برای توقیف" dir="ltr" value={refText} onChange={(e) => setRefText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addRef(); } }} placeholder="AR-000000" className={field('fig h-9 text-left')} />
              <Button size="sm" variant="secondary" disabled={!REF_RE.test(refText.trim().toUpperCase())} onClick={addRef}>افزودن</Button>
            </div>
            {s.records?.length ? <span className="flex flex-wrap gap-1.5">{s.records.map((r) => <FilterChip key={r} selected onClick={() => setS((x) => ({ ...x, records: x.records?.filter((y) => y !== r).length ? x.records!.filter((y) => y !== r) : undefined }))}><span className="fig">{r}</span><Icon name="close" size={12} /></FilterChip>)}</span> : null}
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="font-semibold text-sec">پوشه (با زیرپوشه‌ها)</span>
            <span className="flex flex-wrap gap-1.5">{m.folders.filter((f) => f.status === 'active' && !f.parent).flatMap((f) => [f, ...m.folders.filter((x) => x.parent === f.ref)]).map((f) => <FilterChip key={f.ref} selected={!!s.folders?.includes(f.ref)} onClick={() => toggle('folders', f.ref)}>{f.title_fa} <span className="fig text-[11px] opacity-70">{f.scope}</span></FilterChip>)}</span>
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="font-semibold text-sec">نوع سند</span>
            <span className="flex flex-wrap gap-1.5">{m.classes.filter((c) => c.status === 'active').map((c) => <FilterChip key={c.key} selected={!!s.classes?.includes(c.key)} onClick={() => toggle('classes', c.key)}>{c.title_fa}</FilterChip>)}</span>
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="font-semibold text-sec">طرف</span>
            <span className="flex flex-wrap gap-1.5">{m.parties.filter((p) => p.status === 'active').map((p) => <FilterChip key={p.ref} selected={!!s.parties?.includes(p.ref)} onClick={() => toggle('parties', p.ref)}>{p.name_fa}</FilterChip>)}</span>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {(['from', 'to'] as const).map((k) => (
              <label key={k} className="flex flex-col gap-1 font-semibold text-sec">
                <span className="flex items-center gap-1.5">{k === 'from' ? 'تاریخ سند از' : 'تا'}{s[k] ? <JDay d={s[k]} className="font-normal text-muted" /> : null}</span>
                <input type="date" dir="ltr" aria-label={k === 'from' ? 'توقیف: تاریخ سند از' : 'توقیف: تاریخ سند تا'} value={s[k] ?? ''} onChange={(e) => setS((x) => ({ ...x, [k]: e.target.value || undefined }))} className={field('fig h-9')} />
              </label>
            ))}
          </div>
          {errors.scope ? <span className="text-[12px] text-neg">دامنه‌ی توقیف خالی است.</span> : null}
          {!empty ? (
            <div className="flex flex-col gap-1">
              <span className="text-[12px] text-sec">{all.isLoading ? 'در حال شمردن…' : hit.length ? `${hit.length} سند فعلی را میگیرد:` : 'فعلاً سندی را نمیگیرد؛ سندهای آینده‌ای که بخورند را میگیرد.'}</span>
              {hit.length ? <span className="flex flex-wrap gap-1">{hit.slice(0, 24).map((r) => <RefChip key={r.ref} r={r.ref} tone="neutral" note={r.title_fa} className="max-w-[16rem]" />)}</span> : null}
            </div>
          ) : null}
        </fieldset>
        <ErrorLine error={failure} />
      </div>
    </Sheet>
  );
}

/** A case's holds on the legal page: what the counsel or the owner froze for it. */
export function CaseHolds({ caseRef }: { caseRef: string }) {
  const q = useHolds({ case: caseRef });
  const xs = q.data ?? [];
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <h3 className="min-w-0 flex-1 text-[12px] font-semibold text-gold-ink">توقیف‌های بایگانی</h3>
        <Link href={`/archive/holds?new=1&case=${caseRef}`} className="inline-flex items-center gap-1 text-[12px] font-semibold text-gold-ink hover:underline"><Icon name="add" size={14} />توقیف تازه</Link>
      </div>
      {q.isLoading ? <Skeleton className="h-12" /> : q.error ? <p className="text-[12px] text-neg">{faError(q.error)}</p> : !xs.length ? <p className="text-[12px] text-muted">برای این پرونده سندی توقیف نشده.</p> : (
        <ul className="flex flex-col gap-1.5">
          {xs.map((h) => (
            <li key={h.ref}>
              <Link href={`/archive/holds?ref=${h.ref}`} className="flex min-w-0 flex-wrap items-center gap-2 rounded-[10px] bg-tile px-3 py-2 text-[12px] hover:bg-hover">
                <span className={h.state === 'active' ? 'text-neg' : 'text-muted'}><Icon name="lock" size={14} /></span>
                <span className="fig text-muted">{h.ref}</span>
                <span className="min-w-0 flex-1 truncate text-ink">{h.title_fa}</span>
                {h.state === 'active' ? <span className="text-sec">{h.records ? `${h.records} سند` : 'بی‌سند'}</span> : <Pill className="h-5 text-[11px]">آزادشده</Pill>}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function HoldsEmpty() {
  return <Empty icon="lock" title="توقیفی نیست" body="مشاور حقوقی با پرونده‌اش توقیف میگذارد؛ تو هم از همین‌جا." />;
}
