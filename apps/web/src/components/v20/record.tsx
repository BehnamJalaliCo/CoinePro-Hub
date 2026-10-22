'use client';

import Link from 'next/link';
import { useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { Seal } from '@/components/brand/seal';
import { SealButton } from '@/components/cartable/seal-button';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Empty, ErrorState, PageHeader, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ActorAvatar, RefChip } from '@/components/v17/bits';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { uploadFile } from '@/lib/api/v13';
import {
  faError, useAccessLog, useHolds, useRecord, useRecordAction, useRecordFile,
  type ArchiveRecord, type Field, type RecordFile, type RecordLink, type RecordVersion,
} from '@/lib/api/v20';
import { companyOf } from '@/lib/company';
import { ACTOR_FA } from '@/lib/labels';
import { useNow } from '@/lib/store';
import { cx } from '@/lib/format';
import { ACCESS_FA, ClassTag, ErrorLine, FieldValue, FolderPath, JDay, JStamp, LevelPill, Panel, PartyChip, REF_KIND_FA, SOURCE_KIND, ScopeTag, Sha, StatePill, SuggestionLine, THEN_FA, daysLeftFa, daysTo, fieldErrors, useArchive, field, fieldArea } from './bits';
import { missingRequired } from './field-input';
import { FileFacts, RecordForm, metaFor, partiesFor, type RecordDraft } from './records';

const addKeep = (d: string, k: { years?: number; months?: number }) => {
  const x = new Date(`${d.slice(0, 10)}T12:00:00Z`);
  x.setUTCFullYear(x.getUTCFullYear() + (k.years ?? 0));
  x.setUTCMonth(x.getUTCMonth() + (k.months ?? 0));
  return x.toISOString().slice(0, 10);
};
/** Values that need a whole row even on a phone; the rest sit two to a row. */
const WIDE = new Set(['long_text', 'date_range', 'party', 'url', 'ref', 'multi_enum', 'email', 'text']);
const draftOf = (r: ArchiveRecord): RecordDraft => ({ class: r.class, title_fa: r.title_fa, metadata: { ...r.metadata }, level: r.level, folder: r.folder });
/** The name a secret refusal gave (its key in `fields`), never what the file held. */
const refusedName = (e: unknown) => (e instanceof ApiError && e.code === 'secret_in_document' ? Object.keys(e.fields ?? {})[0] ?? null : null);

// ------------------------------------------------------------------ a disposed record --
/** After the owner's disposal seal only the tombstone stays: ref, class, title, dates, hashes and the decision (§23.0). */
function Tombstone({ r }: { r: ArchiveRecord }) {
  const t = r.tombstone;
  return (
    <>
      <PageHeader eyebrow={<span className="flex flex-wrap items-center gap-2"><span className="fig">{r.ref}</span><ClassTag cls={r.class} /><ScopeTag scope={r.scope} /></span>} title={r.title_fa}
        actions={<Link href="/archive" className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-strong px-4 text-[13px] font-semibold text-ink hover:bg-hover"><Icon name="back" size={18} mirror />بایگانی</Link>} />
      <section aria-label="سنگ‌نشان" className="flex max-w-3xl flex-col gap-4 rounded-[18px] bg-card p-5">
        <div className="flex flex-wrap items-center gap-2"><StatePill state="disposed" /><span className="text-[13px] text-sec">فایل‌ها با کارت امحا نابود شدند؛ این سنگ‌نشان میماند.</span></div>
        <dl className="grid grid-cols-1 gap-3 text-[13px] sm:grid-cols-2">
          <div className="flex flex-col gap-1"><dt className="text-[11px] text-muted">تصمیم</dt><dd>{t?.decision ? <RefChip r={t.decision} /> : '—'}</dd></div>
          <div className="flex flex-col gap-1"><dt className="text-[11px] text-muted">امحا</dt><dd><JStamp at={t?.at} year /></dd></div>
          <div className="flex flex-col gap-1"><dt className="text-[11px] text-muted">ساخته</dt><dd><JStamp at={r.created_at} year /></dd></div>
          <div className="flex flex-col gap-1"><dt className="text-[11px] text-muted">ثبت</dt><dd><JStamp at={r.filed_at} year /></dd></div>
        </dl>
        {t?.hashes.length ? (
          <div className="flex flex-col gap-1.5">
            <h2 className="text-[12px] font-semibold text-gold-ink">hash فایل‌های نابودشده</h2>
            <ul className="flex flex-col gap-1">{t.hashes.map((h) => <li key={h.sha256 + h.name} dir="ltr" className="fig flex min-w-0 flex-wrap gap-x-3 rounded-[10px] bg-tile px-3 py-2 text-start text-[12px]"><span className="text-ink">{h.name}</span><span className="break-all text-muted">{h.sha256}</span></li>)}</ul>
          </div>
        ) : null}
      </section>
    </>
  );
}

// ------------------------------------------------------------------ a draft: complete it, then file it --
function DraftPanel({ r }: { r: ArchiveRecord }) {
  const m = useArchive();
  const act = useRecordAction();
  const toast = useToast();
  const [d, setD] = useState<RecordDraft>(() => draftOf(r));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<unknown>(null);
  const c = m.cls(d.class);
  const lacking = c ? missingRequired(c.fields, d.metadata) : [];
  const s = r.suggestion;
  const apply = () => {
    if (!s) return;
    const cls = d.class ?? s.class;
    const nc = m.cls(cls);
    const md = { ...d.metadata };
    for (const [k, v] of Object.entries(s.metadata ?? {})) if (md[k] == null || md[k] === '') md[k] = v;
    setD({ ...d, class: cls, title_fa: s.title_fa ?? d.title_fa, metadata: md, level: m.rank(nc?.default_level) > m.rank(d.level) ? nc!.default_level : d.level, folder: d.folder ?? (nc ? m.folders.find((f) => f.scope === r.scope && f.classes.includes(nc.key))?.ref ?? null : null) });
  };
  const patch = async (): Promise<ArchiveRecord> => act.patch.mutateAsync({
    r, body: { ...(d.class !== r.class ? { class: d.class } : {}), title_fa: d.title_fa.trim(), metadata: metaFor(m, d), folder: d.folder, parties: partiesFor(m, d, s?.parties ?? []), ...(d.level && d.level !== r.level ? { level: d.level } : {}) },
  });
  const save = async () => {
    setErrors({}); setFailure(null);
    try { await patch(); toast({ tone: 'info', text: 'پیش‌نویس ذخیره شد.' }); } catch (e) { setErrors(fieldErrors(e)); setFailure(e); }
  };
  const file = async () => {
    setErrors({}); setFailure(null);
    try {
      const saved = await patch();
      await act.file.mutateAsync(saved);
      toast({ tone: 'ok', text: <>سند <span className="fig">{r.ref}</span> ثبت شد.</> });
    } catch (e) { setErrors(fieldErrors(e)); setFailure(e); }
  };
  return (
    <Panel title="پیش‌نویس، منتظر ثبت" note="بایگان طبقه‌بندی میکند و مشخصات را کامل؛ ثبت با توست. پیشنهاد هیچ‌وقت خودش ثبت نمیشود." className="tahrir ring-1 ring-[var(--hq-gold-ink)]">
      {s ? (
        <div className="flex flex-wrap items-start gap-2 rounded-[12px] bg-learn-soft p-3">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <SuggestionLine r={r} />
            {s.note_fa ? <span className="text-[12px] leading-5 text-ink">{s.note_fa}</span> : null}
          </div>
          <Button size="sm" variant="secondary" icon="edit" onClick={apply}>پیشنهاد را بگذار</Button>
        </div>
      ) : null}
      <RecordForm scope={r.scope} value={d} onChange={setD} errors={errors} />
      <ErrorLine error={failure} />
      {c && lacking.length ? <p className="text-[12px] text-muted">برای ثبت کم است: {lacking.map((f) => `«${f.title_fa}»`).join('، ')}.</p> : null}
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" icon="seal" disabled={!c || lacking.length > 0 || !d.title_fa.trim()} loading={act.file.isPending || (act.patch.isPending && act.file.isIdle)} onClick={file}>ثبت کن</Button>
        <Button variant="secondary" disabled={!d.title_fa.trim()} loading={act.patch.isPending && !act.file.isPending} onClick={save}>ذخیره‌ی پیش‌نویس</Button>
      </div>
    </Panel>
  );
}

// ------------------------------------------------------------------ metadata, by the class's fields --
function MetadataPanel({ r }: { r: ArchiveRecord }) {
  const m = useArchive();
  const act = useRecordAction();
  const toast = useToast();
  const [editing, setEditing] = useState<RecordDraft | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<unknown>(null);
  const c = m.cls(r.class);
  const fields: Field[] = c?.fields ?? [];
  const known = new Set(fields.map((f) => f.key));
  const extra = Object.keys(r.metadata).filter((k) => !known.has(k));
  const held = r.holds.length > 0;
  const sealed = r.state === 'sealed';
  const save = async () => {
    if (!editing) return;
    setErrors({}); setFailure(null);
    try {
      await act.patch.mutateAsync({ r, body: { title_fa: editing.title_fa.trim(), metadata: metaFor(m, editing), folder: editing.folder, parties: partiesFor(m, editing) } });
      setEditing(null);
      toast({ tone: 'info', text: 'مشخصات ذخیره شد.' });
    } catch (e) { setErrors(fieldErrors(e)); setFailure(e); }
  };
  const row = (f: Field) => (
    <div key={f.key} className={cx('flex min-w-0 flex-col gap-1 rounded-[12px] bg-tile p-3', WIDE.has(f.type) && 'col-span-2', f.status === 'retired' && 'opacity-70')}>
      <dt className="flex items-center gap-1.5 text-[11px] text-muted">{f.title_fa}{f.status === 'retired' ? <span>(بازنشسته)</span> : null}{f.sensitive ? <Icon name="lock" size={11} /> : null}</dt>
      <dd className="min-w-0 text-[14px] font-semibold text-ink"><FieldValue f={f} v={r.metadata[f.key]} masked={r.masked?.includes(f.key)} /></dd>
    </div>
  );
  if (r.state === 'draft') return null;
  return (
    <Panel title="مشخصات" note={c ? <>طبق نوع «{c.title_fa}»، نسخه‌ی <span className="fig">{r.class_version ?? c.version}</span></> : null}
      action={editing ? null : sealed ? <span className="flex items-center gap-1 text-[12px] text-muted"><Icon name="lock" size={13} />مُهرشده؛ اصلاح یعنی نسخه‌ی تازه</span>
        : <Button size="sm" variant="ghost" icon="edit" disabled={held} title={held ? 'توقیف: جز نسخه‌ی تازه هیچ تغییری' : undefined} onClick={() => { setEditing(draftOf(r)); setErrors({}); setFailure(null); }}>ویرایش</Button>}>
      {editing ? (
        <div className="flex flex-col gap-3">
          <RecordForm scope={r.scope} value={editing} onChange={setEditing} errors={errors} lockClass hideLevel />
          <ErrorLine error={failure} />
          <div className="flex gap-2"><Button variant="primary" loading={act.patch.isPending} onClick={save}>ذخیره</Button><Button variant="ghost" onClick={() => setEditing(null)}>انصراف</Button></div>
        </div>
      ) : (
        <>
          <dl className="grid min-w-0 grid-flow-row-dense grid-cols-2 gap-2">
            {fields.filter((f) => f.status === 'active' || r.metadata[f.key] != null).map(row)}
            {extra.map((k) => row({ key: k, title_fa: k, type: 'text', required: false, searchable: false, sensitive: false, status: 'retired' }))}
          </dl>
          <dl className="grid min-w-0 grid-cols-1 gap-x-4 gap-y-2 text-[13px] sm:grid-cols-[auto_minmax(0,1fr)]">
            <dt className="text-muted">پوشه</dt><dd className="min-w-0 text-ink"><FolderPath refId={r.folder} /></dd>
            <dt className="text-muted">طرف‌ها</dt><dd className="flex min-w-0 flex-wrap gap-1.5">{r.parties.length ? r.parties.map((p) => <PartyChip key={p.party} refId={p.party} role={p.role_fa} />) : <span className="text-muted">—</span>}</dd>
            <dt className="text-muted">منبع</dt><dd className="text-ink">{SOURCE_KIND[r.source.kind] ?? r.source.kind}{r.source.ref ? <span className="fig mr-1.5 text-[12px] text-muted">{r.source.ref}</span> : null}</dd>
            <dt className="text-muted">ثبت</dt><dd className="flex flex-wrap items-center gap-1.5 text-ink"><ActorAvatar a={r.created_by} size={18} />{ACTOR_FA(r.created_by)}، <JStamp at={r.filed_at ?? r.created_at} year /></dd>
          </dl>
        </>
      )}
    </Panel>
  );
}

// ------------------------------------------------------------------ files and versions --
function FileViewer({ r, f, onClose }: { r: ArchiveRecord; f: RecordFile; onClose: () => void }) {
  const m = useArchive();
  const lvl = m.level(r.level);
  const needs = !!lvl?.step_up_to_view;
  const file = useRecordFile(r.ref, f, needs);
  const image = f.mime.startsWith('image/');
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={720} title={<span dir="ltr" className="fig">{f.name}</span>} description={<FileFacts f={f} />}>
      <div className="flex flex-col gap-3">
        {lvl?.watermark ? <p className="flex items-start gap-2 rounded-[12px] bg-warn-soft p-3 text-[12px] leading-5 text-ink"><span className="text-warn"><Icon name="info" size={16} /></span>این نسخه ته‌نقش دارد: نام تو، زمان دیدن و <span className="fig">{r.ref}</span> روی هر صفحه. هر دیدن در دفتر دسترسی ثبت میشود.</p> : <p className="text-[12px] text-muted">هر دیدن در دفتر دسترسی ثبت میشود.</p>}
        {needs && !file.url ? (
          <div className="flex flex-col items-center gap-3 rounded-[14px] bg-tile p-6 text-center">
            <span className="flex size-12 items-center justify-center rounded-full bg-neg-soft text-neg"><Icon name="lock" size={22} /></span>
            <span className="text-[14px] font-semibold text-ink">دیدن سند «{lvl?.title_fa}» با passkey است</span>
            <span className="text-[12px] text-muted">یک بار، فقط برای همین سند (<span className="fig">archive.view</span>، هدف <span className="fig">{r.ref}</span>).</span>
            <Button variant="primary" icon="lock" loading={file.busy} onClick={() => void file.open()}>با passkey باز کن</Button>
          </div>
        ) : null}
        {file.error ? <ErrorLine error={file.error} /> : null}
        {file.busy && !file.url ? <Skeleton className="h-64" /> : null}
        {file.url ? (
          image ? (
            // eslint-disable-next-line @next/next/no-img-element -- the record's own file, served (and watermarked) by the hub
            <img src={file.url} alt={f.name} className="max-h-[70dvh] w-full rounded-[12px] bg-page object-contain" />
          ) : (
            <div className="flex flex-col items-center gap-3 rounded-[14px] bg-tile p-6 text-center">
              <span className="text-gold-ink"><Icon name="report" size={28} /></span>
              <span className="text-[13px] text-sec">فایل آماده است.</span>
              <div className="flex flex-wrap justify-center gap-2">
                <a href={file.url} target="_blank" rel="noopener" className="inline-flex h-10 items-center gap-2 rounded-[10px] bg-gold px-4 text-[13px] font-bold text-on-gold hover:bg-gold-bright"><Icon name="share" size={18} />باز کردن در زبانه‌ی تازه</a>
                <a href={file.url} download={f.name} className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-strong px-4 text-[13px] font-semibold text-ink hover:bg-hover"><Icon name="download" size={18} />دریافت</a>
              </div>
            </div>
          )
        ) : null}
      </div>
    </Sheet>
  );
}

function VersionSheet({ r, onClose }: { r: ArchiveRecord; onClose: () => void }) {
  const act = useRecordAction();
  const toast = useToast();
  const pick = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<Array<{ name: string; id: string | null; pct: number }>>([]);
  const [note, setNote] = useState('');
  const [failure, setFailure] = useState<unknown>(null);
  const add = async (list: FileList) => {
    const fresh = [...list].slice(0, 20);
    setFiles((xs) => [...xs, ...fresh.map((f) => ({ name: f.name, id: null, pct: 0 }))]);
    for (const f of fresh) {
      try {
        const ref = await uploadFile(f, f.name, (pct) => setFiles((xs) => xs.map((x) => (x.name === f.name && !x.id ? { ...x, pct } : x))));
        setFiles((xs) => xs.map((x) => (x.name === f.name && !x.id ? { ...x, id: ref.id, pct: 100 } : x)));
      } catch (e) { setFailure(e); }
    }
  };
  const send = async () => {
    setFailure(null);
    try {
      await act.version.mutateAsync({ ref: r.ref, file_ids: files.filter((x) => x.id).map((x) => x.id!), note_fa: note.trim() });
      toast({ tone: 'ok', text: r.state === 'sealed' ? 'نسخه‌ی تازه آمد؛ نسخه‌ی مُهرشده جایگزین شد و سند دوباره منتظر مُهر است.' : 'نسخه‌ی تازه آمد.' });
      onClose();
    } catch (e) { setFailure(e); }
  };
  const refused = refusedName(failure);
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={520} title="نسخه‌ی تازه" description="اصلاح هیچ‌وقت روی نسخه‌ی قبلی نیست: همه‌ی فایل‌های نسخه‌ی تازه را بیاور؛ نسخه‌ی قبلی جایگزین‌شده میماند."
      footer={<div className="flex gap-2"><Button variant="primary" icon="add" disabled={!files.length || files.some((x) => !x.id) || !note.trim()} loading={act.version.isPending} onClick={send}>نسخه‌ی تازه را ثبت کن</Button><Button variant="ghost" onClick={onClose}>انصراف</Button></div>}>
      <div className="flex flex-col gap-3 text-[13px]">
        <Button variant="secondary" icon="attach" onClick={() => pick.current?.click()} className="self-start">انتخاب فایل</Button>
        <input ref={pick} type="file" multiple hidden aria-label="فایل‌های نسخه‌ی تازه" onChange={(e) => { if (e.target.files) void add(e.target.files); e.target.value = ''; }} />
        {files.length ? <ul className="flex flex-col gap-1">{files.map((f, i) => <li key={i} className={cx('flex items-center gap-2 rounded-[10px] px-3 py-2', refused === f.name ? 'bg-neg-soft' : 'bg-tile')}><span dir="ltr" className="fig min-w-0 flex-1 truncate text-start text-ink">{f.name}</span><span className="fig text-[11px] text-muted">{f.id ? 'ok' : `${f.pct}%`}</span></li>)}</ul> : null}
        <label className="flex flex-col gap-1.5 font-semibold text-sec">چه چیزی عوض شد
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={2000} placeholder="مثلاً: الحاقیه‌ی ۲، کمیسیون تازه" className={fieldArea()} />
        </label>
        {refused ? <p role="alert" className="rounded-[12px] bg-neg-soft p-3 text-[12px] leading-5 text-neg">«<span className="fig">{refused}</span>» رد شد: الگوی رمز، کلید خصوصی یا عبارت بازیابی در آن بود. ذخیره نشد و هیچ بخشی از آن ثبت نشد.</p> : <ErrorLine error={failure} />}
      </div>
    </Sheet>
  );
}

function VersionCard({ r, v, onView }: { r: ArchiveRecord; v: RecordVersion; onView: (f: RecordFile) => void }) {
  const current = v.n === r.current_version;
  return (
    <li className={cx('flex min-w-0 flex-col gap-2 rounded-[14px] p-3', current ? 'bg-tile' : 'bg-page')}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13px] font-semibold text-ink">نسخه‌ی {v.n}</span>
        {current ? <Pill tone="pos" dot className="h-5 text-[11px]">جاری</Pill> : <Pill className="h-5 text-[11px]" icon="refresh">جایگزین‌شده</Pill>}
        {v.sealed ? <Pill tone="gold" icon="seal" className="h-5 text-[11px]">مُهرشده</Pill> : null}
        <span className="flex-1" />
        <span className="text-[11px] text-muted"><JStamp at={v.created_at} year />، {ACTOR_FA(v.created_by)}</span>
      </div>
      {v.note_fa ? <p className="text-[12px] leading-5 text-sec">{v.note_fa}</p> : null}
      <ul className="flex flex-col gap-1.5">
        {v.files.map((f) => (
          <li key={f.file_id} className="flex min-w-0 items-center gap-2.5 rounded-[10px] bg-card px-3 py-2">
            <span className="text-muted"><Icon name={f.mime.startsWith('image/') ? 'image' : 'report'} size={16} /></span>
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span dir="ltr" className="fig truncate text-start text-[13px] text-ink" title={f.name}>{f.name}</span>
              <FileFacts f={f} />
            </span>
            <Button size="sm" variant="ghost" icon="search" onClick={() => onView(f)} aria-label={`نمایش ${f.name}`}>نمایش</Button>
          </li>
        ))}
      </ul>
      <span className="text-[11px] text-muted">manifest: <Sha v={v.manifest_sha256} label="sha256" /></span>
    </li>
  );
}

function FilesPanel({ r }: { r: ArchiveRecord }) {
  const [view, setView] = useState<RecordFile | null>(null);
  const [adding, setAdding] = useState(false);
  const vs = [...r.versions].sort((a, b) => b.n - a.n);
  return (
    <Panel title="فایل‌ها و نسخه‌ها" note="هر فایل با SHA-256 خودش؛ مُهر روی manifest نسخه‌ی جاری است." action={r.state !== 'draft' ? <Button size="sm" variant="ghost" icon="add" onClick={() => setAdding(true)}>نسخه‌ی تازه</Button> : null}>
      <ul className="flex flex-col gap-2">{vs.map((v) => <VersionCard key={v.n} r={r} v={v} onView={setView} />)}</ul>
      {view ? <FileViewer r={r} f={view} onClose={() => setView(null)} /> : null}
      {adding ? <VersionSheet r={r} onClose={() => setAdding(false)} /> : null}
    </Panel>
  );
}

// ------------------------------------------------------------------ links --
function LinkRow({ r, l, onRemove }: { r: ArchiveRecord; l: RecordLink; onRemove: (l: RecordLink) => void }) {
  const m = useArchive();
  const k = m.linkKind(l.kind);
  const held = r.holds.length > 0;
  return (
    <li className="flex min-w-0 flex-wrap items-center gap-2 rounded-[10px] bg-tile px-3 py-2 text-[12px]">
      <span className="font-semibold text-sec">{l.inverse ? k?.inverse_fa ?? l.kind : k?.title_fa ?? l.kind}</span>
      <RefChip r={l.to.ref} note={l.to.kind !== 'record' ? REF_KIND_FA[l.to.kind] ?? l.to.kind : null} />
      {l.title_fa ? <span className="min-w-0 truncate text-ink">{l.title_fa}</span> : null}
      <span className="flex-1" />
      {l.sealed ? <span className="inline-flex items-center gap-1 text-muted" title="با نسخه‌ی مُهرشده آمده؛ برداشته نمیشود"><Icon name="lock" size={12} />مُهرشده</span>
        : l.inverse ? <span className="text-muted">از آن سو</span>
          : <button type="button" disabled={held} onClick={() => onRemove(l)} className="text-muted hover:text-neg disabled:opacity-40" aria-label={`برداشتن پیوند ${l.to.ref}`}><Icon name="close" size={14} /></button>}
    </li>
  );
}

function LinksPanel({ r }: { r: ArchiveRecord }) {
  const m = useArchive();
  const act = useRecordAction();
  const toast = useToast();
  const kinds = (m.schema?.link_kinds ?? []).filter((k) => k.status !== 'retired');
  const [kind, setKind] = useState('');
  const k = kinds.find((x) => x.key === kind) ?? kinds[0];
  const [toKind, setToKind] = useState('');
  const tk = k?.to_kinds.includes(toKind) ? toKind : k?.to_kinds[0] ?? 'record';
  const [to, setTo] = useState('');
  const [failure, setFailure] = useState<unknown>(null);
  const [removing, setRemoving] = useState<RecordLink | null>(null);
  const held = r.holds.length > 0;
  const add = async () => {
    if (!k) return;
    setFailure(null);
    try { await act.link.mutateAsync({ ref: r.ref, kind: k.key, to: { kind: tk, ref: to.trim() } }); setTo(''); toast({ tone: 'info', text: 'پیوند اضافه شد.' }); } catch (e) { setFailure(e); }
  };
  const remove = async () => {
    if (!removing) return;
    setFailure(null);
    try { await act.unlink.mutateAsync({ ref: r.ref, kind: removing.kind, to: removing.to }); setRemoving(null); toast({ tone: 'info', text: 'پیوند برداشته شد.' }); } catch (e) { setRemoving(null); setFailure(e); }
  };
  return (
    <Panel title="پیوندها" note={held ? 'توقیف: پیوندها هم تا آزاد شدن دست نمیخورند.' : 'پیوندی که با نسخه‌ی مُهرشده آمده برداشته نمیشود.'}>
      {r.links.length ? <ul className="flex flex-col gap-1.5">{r.links.map((l, i) => <LinkRow key={`${l.kind}-${l.to.ref}-${i}`} r={r} l={l} onRemove={setRemoving} />)}</ul> : <p className="text-[12px] text-muted">پیوندی ندارد.</p>}
      {r.state !== 'draft' && k ? (
        <div className="flex min-w-0 flex-wrap items-end gap-2 border-t border-div pt-3">
          <label className="flex min-w-0 flex-col gap-1 text-[11px] text-muted">نوع پیوند
            <select aria-label="نوع پیوند" value={k.key} onChange={(e) => setKind(e.target.value)} className={field('h-9 w-auto text-[13px]')}>{kinds.map((x) => <option key={x.key} value={x.key}>{x.title_fa}</option>)}</select>
          </label>
          <label className="flex min-w-0 flex-col gap-1 text-[11px] text-muted">به
            <select aria-label="مقصد پیوند از چه نوع" value={tk} onChange={(e) => setToKind(e.target.value)} className={field('h-9 w-auto text-[13px]')}>{k.to_kinds.map((x) => <option key={x} value={x}>{REF_KIND_FA[x] ?? x}</option>)}</select>
          </label>
          <label className="flex min-w-[9rem] flex-1 flex-col gap-1 text-[11px] text-muted">شناسه
            <input aria-label="شناسه‌ی مقصد پیوند" dir="ltr" value={to} onChange={(e) => setTo(e.target.value)} placeholder={tk === 'record' ? 'AR-000000' : tk === 'case' ? 'LC-0001' : tk === 'decision' ? 'D-000000' : ''} className={field('fig h-9 text-left text-[13px]')} />
          </label>
          <Button size="sm" variant="secondary" icon="add" disabled={!to.trim() || held} loading={act.link.isPending} onClick={add}>پیوند</Button>
        </div>
      ) : null}
      <ErrorLine error={failure} />
      <Dialog open={!!removing} onOpenChange={(v) => !v && setRemoving(null)} title="برداشتن پیوند" actions={<>
        <Button variant="danger" loading={act.unlink.isPending} onClick={remove}>بردار</Button>
        <Button variant="secondary" onClick={() => setRemoving(null)}>نه</Button>
      </>}><p>پیوند «{removing ? m.linkKind(removing.kind)?.title_fa ?? removing.kind : ''}» به <span className="fig">{removing?.to.ref}</span> برداشته میشود. خود سندها دست نمیخورند.</p></Dialog>
    </Panel>
  );
}

// ------------------------------------------------------------------ seal and level --
function SealPanel({ r }: { r: ArchiveRecord }) {
  const m = useArchive();
  const act = useRecordAction();
  const toast = useToast();
  const { data: companies } = useCompanies();
  const co = companyOf(companies, r.scope);
  const [failure, setFailure] = useState<unknown>(null);
  const [level, setLevel] = useState<string | null>(null);
  const cur = r.versions.find((v) => v.n === r.current_version);
  const held = r.holds.length > 0;
  const lower = level != null && m.rank(level) < m.rank(r.level);
  const seal = async () => {
    setFailure(null);
    try { await act.seal.mutateAsync(r); toast({ tone: 'ok', text: <>سند <span className="fig">{r.ref}</span> مُهر شد؛ از این به بعد فقط نسخه‌ی تازه.</> }); } catch (e) { setFailure(e); }
  };
  const changeLevel = async () => {
    if (!level) return;
    setFailure(null);
    try {
      if (lower) await act.declassify.mutateAsync({ r, level }); else await act.patch.mutateAsync({ r, body: { level } });
      toast({ tone: 'info', text: `سطح سند «${m.level(level)?.title_fa ?? level}» شد.` });
      setLevel(null);
    } catch (e) { setLevel(null); setFailure(e); }
  };
  return (
    <Panel title="مُهر و سطح" id="seal">
      {r.state === 'sealed' ? (
        <div className="flex items-center gap-3">
          <Seal code={r.scope} nameFa={co.nameFa} nameEn={co.nameEn} holding={co.holding} state="sealed" size={64} />
          <div className="flex min-w-0 flex-col gap-1 text-[12px] text-sec">
            <span className="text-[13px] font-semibold text-ink">مُهر خورد، <JStamp at={r.sealed_at} year /></span>
            <span>روی manifest نسخه‌ی {r.current_version}: <Sha v={cur?.manifest_sha256} /></span>
            <span>اصلاح فقط با نسخه‌ی تازه؛ نسخه‌ی مُهرشده جایگزین‌شده میماند.</span>
          </div>
        </div>
      ) : r.state === 'filed' ? (
        <div className="flex flex-col items-center gap-2 rounded-[14px] bg-tile p-4 text-center">
          <SealButton code={r.scope} nameFa={co.nameFa} nameEn={co.nameEn} holding={co.holding} busy={act.seal.isPending} disabled={held} onSealed={seal} size={80} />
          <span className="text-[12px] leading-5 text-sec">مُهر روی manifest نسخه‌ی {r.current_version} است: <Sha v={cur?.manifest_sha256} /></span>
          <span className="text-[11px] text-muted">{held ? 'توقیف: مُهر هم تا آزاد شدن صبر میکند.' : 'با passkey تو (archive.seal). بعد از مُهر، سند و پیوندهایش دست نمیخورند.'}</span>
        </div>
      ) : <p className="text-[12px] text-muted">{r.state === 'draft' ? 'پیش‌نویس مُهر نمیشود؛ اول ثبتش کن.' : 'این سند مُهر نمیشود.'}</p>}
      {r.state !== 'draft' ? (
        <div className="flex min-w-0 flex-col gap-2 border-t border-div pt-3">
          <span className="flex flex-wrap items-center gap-2 text-[12px] text-sec">سطح فعلی <LevelPill level={r.level} /></span>
          {r.state === 'sealed' && !held ? <p className="text-[11px] leading-5 text-muted">سطح بیرون از manifest است: عوض کردنش مُهر را برنمیدارد و فقط همین سطح عوض میشود.</p> : null}
          {held ? <p className="text-[11px] leading-5 text-muted">توقیف: سطح هم تا آزاد شدن عوض نمیشود.</p> : (
            <div className="flex flex-wrap gap-1.5">
              {m.levels.filter((l) => l.key !== r.level && l.status !== 'retired').map((l) => (
                <Button key={l.key} size="sm" variant={m.rank(l.key) < m.rank(r.level) ? 'secondary' : 'ghost'} icon={m.rank(l.key) < m.rank(r.level) ? 'lock' : undefined} onClick={() => setLevel(l.key)}>{m.rank(l.key) < m.rank(r.level) ? 'پایین به' : 'بالا به'} {l.title_fa}</Button>
              ))}
            </div>
          )}
        </div>
      ) : null}
      <ErrorLine error={failure} />
      <Dialog open={!!level} onOpenChange={(v) => !v && setLevel(null)} title={lower ? 'پایین آوردن سطح' : 'بالا بردن سطح'} actions={<>
        <Button variant="primary" icon={lower ? 'lock' : undefined} loading={act.declassify.isPending || act.patch.isPending} onClick={changeLevel}>{lower ? 'با passkey پایین بیاور' : 'بالا ببر'}</Button>
        <Button variant="secondary" onClick={() => setLevel(null)}>انصراف</Button>
      </>}>
        {lower ? (
          <p>از «{m.level(r.level)?.title_fa}» به «{m.level(level)?.title_fa}». فقط کار توست و با passkey بسته به همین سند، همین نسخه و همین سطح: <span className="fig">{r.ref}@{r.version}:{level}</span>. هر کس مجوز سطح تازه را دارد آن را خواهد دید.{r.state === 'sealed' ? ' مُهر و manifest دست نمیخورند.' : ''}</p>
        ) : <p>از «{m.level(r.level)?.title_fa}» به «{m.level(level)?.title_fa}». بالا بردن passkey نمیخواهد؛ پایین آوردنش میخواهد.</p>}
      </Dialog>
    </Panel>
  );
}

// ------------------------------------------------------------------ holds, retention, reminders, access --
function HoldsPanel({ r }: { r: ArchiveRecord }) {
  const q = useHolds({ state: 'active' });
  const hs = (q.data ?? []).filter((h) => r.holds.includes(h.ref));
  if (!r.holds.length) return null;
  return (
    <Panel title="توقیف قانونی" className="ring-1 ring-[var(--hq-neg-line)]" note="جز نسخه‌ی تازه هیچ تغییری پذیرفته نمیشود و امحا نمیشود.">
      <ul className="flex flex-col gap-2">
        {r.holds.map((ref) => {
          const h = hs.find((x) => x.ref === ref);
          return (
            <li key={ref} className="flex flex-col gap-1 rounded-[12px] bg-neg-soft p-3">
              <span className="flex flex-wrap items-center gap-2 text-[13px]"><Icon name="lock" size={14} /><Link href={`/archive/holds?ref=${ref}`} className="fig text-neg hover:underline">{ref}</Link><span className="font-semibold text-ink">{h?.title_fa}</span>{h?.case ? <RefChip r={h.case} note="پرونده" /> : null}</span>
              {h?.reason_md ? <Md text={h.reason_md} className="text-[12px] leading-6 text-sec" /> : null}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function RetentionPanel({ r }: { r: ArchiveRecord }) {
  const m = useArchive();
  const now = useNow();
  const rule = m.schema?.retention.find((x) => x.ref === r.retention.rule);
  const c = m.cls(r.class);
  const fieldFa = (k: string) => c?.fields.find((f) => f.key === k)?.title_fa ?? k;
  // When it ends: the review date the server gives, else the trigger plus the rule's term.
  const end = r.retention.review_at ?? (rule && rule.keep !== 'permanent' && r.retention.trigger_at ? addKeep(r.retention.trigger_at, rule.keep) : null);
  if (r.state === 'draft') return null;
  return (
    <Panel title="نگهداری و یادآور">
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 text-[12px]">
        <dt className="text-muted">قاعده</dt><dd className="flex min-w-0 flex-wrap items-center gap-1.5 text-ink">{r.retention.rule ? <RefChip r={r.retention.rule} /> : null}{rule ? <span>{rule.title_fa}</span> : <span className="text-muted">—</span>}</dd>
        {r.retention.trigger_at ? <><dt className="text-muted">آغاز</dt><dd><JDay d={r.retention.trigger_at} /></dd></> : null}
        {rule ? <><dt className="text-muted">پایان</dt><dd className="text-ink">{rule.keep === 'permanent' ? 'دائمی' : end ? <><JDay d={end} />، {THEN_FA[rule.then]}</> : <>{THEN_FA[rule.then]}؛ {rule.trigger === 'case_closed' ? 'شمارش از بسته شدن پرونده' : rule.trigger === 'superseded' ? 'شمارش از جایگزین شدن' : rule.trigger.startsWith('field:') ? `شمارش از «${fieldFa(rule.trigger.slice(6))}» که هنوز پر نشده` : 'شمارش از ثبت'}</>}</dd></> : null}
        {r.retention.disposable ? <><dt className="text-muted">وضع</dt><dd><Pill tone="warn" icon="time">نگهداری تمام شده؛ در کارت امحا</Pill></dd></> : null}
      </dl>
      {r.reminders.length ? (
        <ul className="flex flex-col gap-1.5">
          {r.reminders.map((x) => {
            const left = daysTo(x.at, now);
            return (
              <li key={x.field + x.at} className="flex flex-wrap items-center gap-2 rounded-[10px] bg-tile px-3 py-2 text-[12px]">
                <Icon name="time" size={14} /><span className="text-ink">{fieldFa(x.field)}</span><JDay d={x.at} />
                <span className="flex-1" />
                <span className={cx(x.state === 'done' ? 'text-muted' : left <= 7 ? 'text-neg' : left <= 30 ? 'text-warn' : 'text-sec')}>{x.state === 'done' ? 'انجام شد' : now ? daysLeftFa(left) : ''}</span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </Panel>
  );
}

function AccessPanel({ r }: { r: ArchiveRecord }) {
  const q = useAccessLog(r.ref);
  const files = new Map(r.versions.flatMap((v) => v.files.map((f) => [f.file_id, f.name] as const)));
  return (
    <Panel title="دفتر دسترسی" note="چه کسی چه چیزی را کی دید یا دریافت کرد، و هر تغییر سطح؛ فقط تو میبینی." id="access">
      {q.error ? <ErrorLine error={q.error} /> : q.isLoading ? <Skeleton className="h-16" /> : !q.data?.length ? <p className="text-[12px] text-muted">هنوز کسی فایل‌های این سند را باز نکرده و سطحش عوض نشده.</p> : (
        <ul className="flex flex-col gap-1.5">
          {q.data.map((a, i) => {
            const k = ACCESS_FA[a.action] ?? { fa: a.action, icon: 'info' as const };
            return (
              <li key={i} className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 rounded-[10px] bg-tile px-3 py-2 text-[12px]">
                <Icon name={k.icon} size={14} /><span className="text-ink">{ACTOR_FA(a.actor)}</span><span className="text-sec">{k.fa}</span>
                {a.action === 'level' ? <span className="inline-flex items-center gap-1 text-sec">از <LevelPill level={a.level_from ?? null} className="h-5 text-[11px]" /> به <LevelPill level={a.level_to ?? null} className="h-5 text-[11px]" /></span> : null}
                {a.file_id ? <span dir="ltr" className="fig min-w-0 truncate text-muted">{files.get(a.file_id) ?? a.file_id}</span> : null}
                {a.version ? <span className="text-muted">نسخه‌ی {a.version}</span> : null}
                <span className="flex-1" />
                {a.step_up ? <span className="inline-flex items-center gap-0.5 text-gold-ink" title="با passkey"><Icon name="lock" size={12} />passkey</span> : null}
                {a.watermarked ? <span className="text-muted">ته‌نقش</span> : null}
                <JStamp at={a.at} className="text-muted" />
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

// ------------------------------------------------------------------ the page --
export function RecordView({ refId }: { refId: string }) {
  const q = useRecord(refId);
  const m = useArchive();
  const r = q.data;
  if (q.error) {
    if (q.error instanceof ApiError && (q.error.code === 'clearance' || q.error.status === 404)) {
      return (
        <>
          <PageHeader eyebrow={<span className="fig">{refId}</span>} title="بایگانی" />
          <Empty icon={q.error.code === 'clearance' ? 'lock' : 'search'} title={faError(q.error)} body="از بایگانی جستجو کن یا فیلترها را عوض کن." action={<Link href="/archive" className="text-[13px] font-semibold text-gold-ink hover:underline">بایگانی</Link>} />
        </>
      );
    }
    return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  }
  if (!r || m.q.isLoading) return <><Skeleton className="h-16 w-2/3" /><Skeleton className="h-64" /></>;
  if (r.state === 'disposed') return <Tombstone r={r} />;
  return (
    <>
      <PageHeader
        eyebrow={<span className="flex flex-wrap items-center gap-x-2 gap-y-1"><span className="fig">{r.ref}</span><ClassTag cls={r.class} /><ScopeTag scope={r.scope} /></span>}
        title={r.title_fa}
        actions={<Link href="/archive" className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-strong px-4 text-[13px] font-semibold text-ink hover:bg-hover"><Icon name="back" size={18} mirror />بایگانی</Link>}>
        <div className="flex flex-wrap items-center gap-2">
          <StatePill state={r.state} />
          <LevelPill level={r.level} />
          {r.holds.length ? <Pill tone="neg" icon="lock">توقیف {r.holds.length > 1 ? `(${r.holds.length})` : ''}</Pill> : null}
          {r.source.kind === 'system' ? <Pill tone="lapis" icon="settings">بایگانی خودکار</Pill> : null}
          {r.doc_date ? <span className="text-[12px] text-muted">تاریخ سند <JDay d={r.doc_date} className="text-sec" /></span> : null}
        </div>
      </PageHeader>
      {r.state === 'draft' ? <DraftPanel key={r.version} r={r} /> : null}
      <div className="grid min-w-0 grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-4">
          <MetadataPanel r={r} />
          <FilesPanel r={r} />
          <LinksPanel r={r} />
        </div>
        <aside className="flex min-w-0 flex-col gap-4">
          <SealPanel r={r} />
          <HoldsPanel r={r} />
          <RetentionPanel r={r} />
          <AccessPanel r={r} />
        </aside>
      </div>
    </>
  );
}
