'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useRef, useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Empty, FilterChip, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ScopeChips } from '@/components/v17/bits';
import { ApiError } from '@/lib/api/client';
import { uploadFile } from '@/lib/api/v13';
import {
  faError, useFixity, useIntake, useRecordAction, useRecords,
  type ArchiveRecord, type Field, type Intake, type RecordFile,
} from '@/lib/api/v20';
import { useNow } from '@/lib/store';
import { ago, cx } from '@/lib/format';
import { ClassTag, ErrorLine, FieldValue, JDay, JStamp, LevelPill, ScopeTag, Sha, StatePill, SuggestionLine, TEXT_STATE, bad, bytesFig, daysLeftFa, daysTo, defaultFolder, fieldErrors, useArchive, type ArchiveMaps, field } from './bits';
import { FieldInput, emptyValue, metaErrors, missingRequired } from './field-input';

// ------------------------------------------------------------------ search highlight --
/** The same deterministic normaliser the hub searches with (§23.9), one character at a time so a match maps back onto the snippet. */
function normChar(c: string): string {
  if (/[ً-ْٰـ]/.test(c)) return ''; // diacritics and tatweel
  if (c === 'ي' || c === 'ى') return 'ی';
  if (c === 'ك') return 'ک';
  if (c === 'ة') return 'ه';
  if ('أإآ'.includes(c)) return 'ا';
  if (c === 'ؤ') return 'و';
  if ('‌‏‎'.includes(c)) return ' ';
  const fa = '۰۱۲۳۴۵۶۷۸۹'.indexOf(c);
  if (fa >= 0) return String(fa);
  const ar = '٠١٢٣٤٥٦٧٨٩'.indexOf(c);
  if (ar >= 0) return String(ar);
  return c.toLowerCase();
}
export const normalise = (s: string) => [...s].map(normChar).join('').replace(/\s+/g, ' ');
/** The snippet with every query term marked, whatever letters or digits the text and the query were typed with. */
export function Highlight({ text, q }: { text: string; q: string }) {
  const terms = normalise(q).split(' ').filter((t) => t.length >= 2);
  if (!terms.length) return <>{text}</>;
  const chars = [...text];
  let norm = '';
  const at: number[] = [];
  chars.forEach((c, i) => { for (const n of normChar(c)) { norm += n; at.push(i); } });
  const marks: Array<[number, number]> = [];
  for (const t of terms) for (let i = norm.indexOf(t); i >= 0; i = norm.indexOf(t, i + t.length)) marks.push([at[i]!, at[i + t.length - 1]! + 1]);
  marks.sort((a, b) => a[0] - b[0]);
  const out: ReactNode[] = [];
  let last = 0;
  marks.forEach(([s, e], i) => {
    if (s < last) return;
    if (s > last) out.push(chars.slice(last, s).join(''));
    out.push(<mark key={i} className="rounded-[3px] bg-gold-soft px-0.5 text-ink">{chars.slice(s, e).join('')}</mark>);
    last = e;
  });
  out.push(chars.slice(last).join(''));
  return <>{out}</>;
}
const latin = (s: string) => !/[؀-ۿ]/.test(s);

// ------------------------------------------------------------------ a record in a list --
export function RecordRow({ r, snippet, q }: { r: ArchiveRecord; snippet?: string | null; q?: string }) {
  const m = useArchive();
  return (
    <Link href={`/archive/${r.ref}`} className="flex min-w-0 flex-col gap-1.5 rounded-[12px] px-3 py-2.5 transition-colors hover:bg-hover">
      <span className="flex min-w-0 items-center gap-2">
        <span className="flex size-8 flex-none items-center justify-center rounded-[10px] bg-tile text-gold-ink"><ClassIcon cls={r.class} m={m} /></span>
        <span className="min-w-0 flex-1 truncate text-[14px] font-semibold text-ink">{q ? <Highlight text={r.title_fa} q={q} /> : r.title_fa}</span>
        <LevelPill level={r.level} className="h-5 text-[11px]" />
      </span>
      <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 pr-10 text-[11px] text-muted">
        <span className="fig text-sec">{r.ref}</span>
        <ScopeTag scope={r.scope} />
        <ClassTag cls={r.class} />
        {r.doc_date ? <JDay d={r.doc_date} /> : null}
        {r.state !== 'filed' ? <StatePill state={r.state} className="h-5 text-[11px]" /> : null}
        {r.holds.length ? <Pill tone="neg" icon="lock" className="h-5 text-[11px]">توقیف</Pill> : null}
        {r.versions.length > 1 ? <span>{r.versions.length} نسخه</span> : null}
      </span>
      {snippet ? <span dir={latin(snippet) ? 'ltr' : 'rtl'} className={cx('line-clamp-2 pr-10 text-start text-[12px] leading-6 text-sec', latin(snippet) && 'fig')}><Highlight text={snippet} q={q ?? ''} /></span> : null}
    </Link>
  );
}
function ClassIcon({ cls, m }: { cls: string | null; m: ArchiveMaps }) {
  return <Icon name={(m.cls(cls)?.icon as never) ?? 'deliverable'} size={16} />;
}

// ------------------------------------------------------------------ the record form (intake, a draft, a correction) --
export type RecordDraft = { class: string | null; title_fa: string; metadata: Record<string, unknown>; level: string | null; folder: string | null };
const cleanMeta = (md: Record<string, unknown>) => Object.fromEntries(Object.entries(md).filter(([, v]) => !emptyValue(v)));
/** The metadata to send: only the class's fields (a suggestion may carry keys of another class), nothing empty. */
export const metaFor = (m: ArchiveMaps, d: RecordDraft) => {
  const keys = new Set((m.cls(d.class)?.fields ?? []).map((f) => f.key));
  return cleanMeta(Object.fromEntries(Object.entries(d.metadata).filter(([k]) => keys.has(k))));
};
/** Parties of a record, read from its party fields (the field's title is the role), then any other the suggestion named. */
export function partiesFor(m: ArchiveMaps, d: RecordDraft, extra: string[] = []): Array<{ party: string; role_fa: string }> {
  const out: Array<{ party: string; role_fa: string }> = [];
  for (const f of m.cls(d.class)?.fields ?? []) {
    const v = d.metadata[f.key];
    if (f.type === 'party' && typeof v === 'string' && !out.some((x) => x.party === v)) out.push({ party: v, role_fa: f.title_fa });
  }
  for (const p of extra) if (!out.some((x) => x.party === p)) out.push({ party: p, role_fa: 'طرف' });
  return out;
}

/** Class, title, metadata by the class's fields, level and folder: everything a record is filed with, typed by the schema. */
export function RecordForm({ scope, value, onChange, errors, lockClass, hideLevel }: { scope: string; value: RecordDraft; onChange: (d: RecordDraft) => void; errors: Record<string, string>; lockClass?: boolean; hideLevel?: boolean }) {
  const m = useArchive();
  const c = m.cls(value.class);
  const me = metaErrors(errors);
  const fields: Field[] = (c?.fields ?? []).filter((f) => f.status === 'active' || !emptyValue(value.metadata[f.key]));
  const classes = m.classes.filter((x) => (x.status === 'active' && (x.scopes === 'all' || x.scopes.includes(scope))) || x.key === value.class);
  const setClass = (k: string | null) => {
    const nc = m.cls(k);
    onChange({ ...value, class: k, level: nc?.default_level ?? value.level, folder: defaultFolder(m, scope, k) ?? value.folder });
  };
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="grid min-w-0 gap-3 sm:grid-cols-2">
        <label className="flex min-w-0 flex-col gap-1.5 text-[12px] font-semibold text-sec">نوع سند
          {lockClass ? <span className="flex h-10 items-center"><ClassTag cls={value.class} className="text-[14px] font-normal text-ink" /></span> : (
            <select aria-label="نوع سند" value={value.class ?? ''} onChange={(e) => setClass(e.target.value || null)} className={field(errors.class && bad)}>
              <option value="">— انتخاب کن —</option>
              {classes.map((x) => <option key={x.key} value={x.key}>{x.title_fa}{x.status === 'retired' ? ' (بازنشسته)' : ''}</option>)}
            </select>
          )}
          {errors.class ? <span className="font-normal text-neg">{errors.class}</span> : null}
        </label>
        <label className="flex min-w-0 flex-col gap-1.5 text-[12px] font-semibold text-sec">عنوان
          <input aria-label="عنوان سند" value={value.title_fa} onChange={(e) => onChange({ ...value, title_fa: e.target.value })} maxLength={200} className={field(errors.title_fa && bad)} />
          {errors.title_fa ? <span className="font-normal text-neg">{errors.title_fa}</span> : null}
        </label>
      </div>
      {c ? (
        <div className="grid min-w-0 gap-3 sm:grid-cols-2">
          {fields.map((f) => (
            <div key={f.key} className={cx('min-w-0', (f.type === 'long_text' || f.type === 'date_range' || f.type === 'multi_enum') && 'sm:col-span-2')}>
              <FieldInput f={f} value={value.metadata[f.key]} scope={scope} error={me[f.key] ?? null} onChange={(v) => onChange({ ...value, metadata: { ...value.metadata, [f.key]: v } })} />
            </div>
          ))}
        </div>
      ) : <p className="rounded-[12px] bg-tile p-3 text-[13px] text-sec">نوع سند را انتخاب کن تا فیلدهایش بیاید.</p>}
      <div className="grid min-w-0 gap-3 sm:grid-cols-2">
        {hideLevel ? null : (
          <label className="flex min-w-0 flex-col gap-1.5 text-[12px] font-semibold text-sec">سطح
            <select aria-label="سطح" value={value.level ?? ''} onChange={(e) => onChange({ ...value, level: e.target.value || null })} className={field(errors.level && bad)}>
              {m.levels.filter((l) => l.status !== 'retired').map((l) => <option key={l.key} value={l.key}>{l.title_fa}</option>)}
            </select>
          </label>
        )}
        <label className="flex min-w-0 flex-col gap-1.5 text-[12px] font-semibold text-sec">پوشه
          <select aria-label="پوشه" value={value.folder ?? ''} onChange={(e) => onChange({ ...value, folder: e.target.value || null })} className={field(errors.folder && bad)}>
            <option value="">بی‌پوشه</option>
            {m.folders.filter((f) => f.scope === scope && (f.status === 'active' || f.ref === value.folder)).map((f) => <option key={f.ref} value={f.ref}>{'— '.repeat(m.folderPath(f.ref).length - 1)}{f.title_fa}</option>)}
          </select>
          {errors.folder ? <span className="font-normal text-neg">{errors.folder}</span> : null}
        </label>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ files as the hub read them --
export function FileFacts({ f }: { f: RecordFile }) {
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted">
      <span className="fig">{bytesFig(f.size_bytes)}</span>
      {f.pages ? <span>{f.pages} صفحه</span> : null}
      <span className={f.text_state === 'failed' ? 'text-warn' : undefined}>{TEXT_STATE[f.text_state] ?? f.text_state}{f.ocr_confidence != null ? <> <span className="fig">{Math.round(f.ocr_confidence * 100)}%</span></> : null}</span>
      <Sha v={f.sha256} />
    </span>
  );
}

// ------------------------------------------------------------------ intake (§23.12 POST /archive/intake) --
type Up = { key: string; file: File; pct: number; id: string | null; error: string | null; refused: boolean };
const stem = (n: string) => n.replace(/\.[A-Za-z0-9]+$/, '').replace(/[-_]+/g, ' ');

/** «سند تازه»: drop or choose files; the hub scans them for secrets, hashes them, reads their text and suggests; the owner makes a draft
 *  (or files it at once). A file with a secret pattern is refused by name, never by what it held. */
export function IntakeSheet({ onClose, scope: scope0 }: { onClose: () => void; scope: string | null }) {
  const m = useArchive();
  const router = useRouter();
  const toast = useToast();
  const intake = useIntake();
  const act = useRecordAction();
  const pick = useRef<HTMLInputElement>(null);
  const [scope, setScope] = useState<string | null>(scope0);
  const [ups, setUps] = useState<Up[]>([]);
  // Uploads finish out of order and in callbacks: the ref is the list as it is now, the state is what renders.
  const upsRef = useRef<Up[]>([]);
  const put = (next: Up[]) => { upsRef.current = next; setUps(next); };
  const patchUp = (k: string, p: Partial<Up>) => put(upsRef.current.map((x) => (x.key === k ? { ...x, ...p } : x)));
  const [drag, setDrag] = useState(false);
  const [got, setGot] = useState<Intake | null>(null);
  const [touched, setTouched] = useState(false);
  const [form, setForm] = useState<RecordDraft>({ class: null, title_fa: '', metadata: {}, level: null, folder: null });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<unknown>(null);
  // Kept for a retry after a lost answer; a refused attempt (any answer) gets a fresh key with the corrected body.
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [split, setSplit] = useState(false);
  const live = ups.filter((u) => !u.refused);
  const ready = live.length > 0 && live.every((u) => u.id) && !!got;
  const busy = ups.some((u) => !u.id && !u.error && !u.refused) || intake.isPending;

  /** The secret scan, hashes and text of every accepted file; a refused file is named and dropped, the rest go again. */
  const scan = async (list: Up[], keepForm: boolean, sc: string | null = scope) => {
    let ids = list.filter((u) => !u.refused && u.id).map((u) => u.id!);
    setFailure(null);
    while (ids.length) {
      try {
        const out = await intake.mutateAsync(ids);
        setGot(out);
        if (!keepForm) {
          const s = out.suggestion;
          const cls = s?.class ?? null;
          const first = upsRef.current.find((u) => !u.refused && u.id);
          setForm({
            class: cls, title_fa: s?.title_fa ?? (first ? stem(first.file.name) : ''), metadata: { ...(s?.metadata ?? {}) },
            level: m.cls(cls)?.default_level ?? m.levels.find((l) => l.key === 'internal')?.key ?? m.levels[0]?.key ?? null,
            folder: sc ? defaultFolder(m, sc, cls) : null,
          });
        }
        return;
      } catch (e) {
        if (e instanceof ApiError && e.code === 'secret_in_document') {
          // The refusal names the file (its key in `fields`), never what it held.
          const names = Object.keys(e.fields ?? {});
          const hit = list.find((u) => !u.refused && u.id && ids.includes(u.id) && names.includes(u.file.name)) ?? list.find((u) => u.id === ids[0]);
          if (!hit) { setFailure(e); return; }
          patchUp(hit.key, { refused: true });
          ids = ids.filter((id) => id !== hit.id);
          if (!ids.length) setGot(null);
          continue;
        }
        setFailure(e);
        return;
      }
    }
  };
  const add = async (files: FileList | File[]) => {
    const fresh: Up[] = [...files].slice(0, 20).map((file) => ({ key: crypto.randomUUID(), file, pct: 0, id: null, error: null, refused: false }));
    if (!fresh.length) return;
    put([...upsRef.current, ...fresh]);
    await Promise.all(fresh.map(async (u) => {
      try {
        const ref = await uploadFile(u.file, u.file.name, (pct) => patchUp(u.key, { pct }));
        patchUp(u.key, { id: ref.id, pct: 100 });
      } catch (e) { patchUp(u.key, { error: faError(e) }); }
    }));
    await scan(upsRef.current, touched);
  };
  const remove = (k: string) => {
    const next = upsRef.current.filter((u) => u.key !== k);
    put(next);
    if (next.some((u) => !u.refused && u.id)) void scan(next, touched); else setGot(null);
  };
  const edit = (d: RecordDraft) => { setTouched(true); setForm(d); };
  const pickScope = (s: string | null) => { setScope(s); if (s) setForm((f) => ({ ...f, folder: defaultFolder(m, s, f.class) })); };

  const c = m.cls(form.class);
  const lacking = c ? missingRequired(c.fields, form.metadata) : [];
  const enough = !!c && live.length >= (c.required_files ?? 0);
  const make = async (file: boolean) => {
    if (!scope || !form.class) return;
    setErrors({});
    setFailure(null);
    try {
      const r = await act.create.mutateAsync({
        key: `${key}:${file ? 'file' : 'draft'}`,
        body: { scope, class: form.class, title_fa: form.title_fa.trim(), metadata: metaFor(m, form), level: form.level ?? undefined, folder: form.folder, file_ids: live.map((u) => u.id!), parties: partiesFor(m, form, got?.suggestion?.parties ?? []), file },
      });
      toast({ tone: 'ok', text: file ? <>سند <span className="fig">{r.ref}</span> ثبت شد.</> : <>پیش‌نویس <span className="fig">{r.ref}</span> ساخته شد؛ هر وقت کامل شد ثبتش کن.</> });
      onClose();
      router.push(`/archive/${r.ref}`);
    } catch (e) { if (e instanceof ApiError && e.status) setKey(crypto.randomUUID()); setErrors(fieldErrors(e)); setFailure(e); }
  };
  const importAll = async () => {
    if (!scope) return;
    setFailure(null);
    try {
      const out = await act.import.mutateAsync({ scope, file_ids: live.map((u) => u.id!) });
      const n = Array.isArray(out) ? out.length : out.items.length;
      toast({ tone: 'ok', text: `${n} پیش‌نویس ساخته شد؛ بایگان نوع و مشخصاتشان را پیشنهاد میدهد.` });
      onClose();
    } catch (e) { setFailure(e); }
  };

  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={640} title="سند تازه" description="فایل‌ها اول از نظر رمز و کلید بررسی میشوند، hash میگیرند و متنشان خوانده میشود؛ پیشنهاد نوع و مشخصات فقط پیشنهاد است."
      footer={
        <div className="flex flex-wrap items-center gap-2">
          {split && live.length > 1 ? (
            <Button variant="primary" icon="add" disabled={!scope || !ready} loading={act.import.isPending} onClick={importAll}>{live.length} پیش‌نویس بساز</Button>
          ) : (
            <>
              <Button variant="primary" icon="add" disabled={!scope || !ready || !form.class || !form.title_fa.trim()} loading={act.create.isPending} onClick={() => make(false)}>پیش‌نویس بساز</Button>
              <Button variant="secondary" icon="seal" disabled={!scope || !ready || !form.title_fa.trim() || !enough || lacking.length > 0 || act.create.isPending} onClick={() => make(true)}>همین حالا ثبت کن</Button>
            </>
          )}
          <Button variant="ghost" onClick={onClose}>انصراف</Button>
        </div>
      }>
      <div className="flex flex-col gap-5 text-[13px]">
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-2 font-semibold text-sec">برای کجا</legend>
          <ScopeChips value={scope} onChange={pickScope} all={false} />
        </fieldset>
        <div
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); void add(e.dataTransfer.files); }}
          className={cx('flex flex-col items-center gap-2 rounded-[14px] border-2 border-dashed p-5 text-center transition-colors', drag ? 'border-gold-ink bg-gold-soft' : 'border-strong')}
        >
          <span className="text-gold-ink"><Icon name="attach" size={26} /></span>
          <span className="font-semibold text-ink">فایل‌ها را اینجا رها کن</span>
          <span className="text-[12px] text-muted">PDF، اسکن یا عکس؛ هر فایل یک بار، با hash خودش.</span>
          <Button size="sm" variant="secondary" icon="add" onClick={() => pick.current?.click()}>انتخاب فایل</Button>
          <input ref={pick} type="file" multiple hidden aria-label="انتخاب فایل برای بایگانی" onChange={(e) => { if (e.target.files) void add(e.target.files); e.target.value = ''; }} />
        </div>
        {ups.length ? (
          <ul className="flex flex-col gap-1.5" aria-label="فایل‌های این سند">
            {ups.map((u) => {
              const f = got?.files.find((x) => x.file_id === u.id);
              return (
                <li key={u.key} className={cx('flex min-w-0 items-start gap-2.5 rounded-[12px] p-3', u.refused ? 'bg-neg-soft' : 'bg-tile')}>
                  <span className={cx('mt-0.5', u.refused ? 'text-neg' : f ? 'text-pos' : 'text-muted')}><Icon name={u.refused ? 'lock' : f ? 'seal' : 'attach'} size={16} /></span>
                  <span className="flex min-w-0 flex-1 flex-col gap-1">
                    <span dir="ltr" className="fig truncate text-start text-[13px] text-ink">{u.file.name}</span>
                    {u.refused ? (
                      <span role="alert" className="text-[12px] leading-5 text-neg">رد شد: الگوی رمز، کلید خصوصی یا عبارت بازیابی در این فایل بود. ذخیره نشد و هیچ بخشی از آن جایی ثبت نشد. آن بخش را بردار و دوباره بفرست.</span>
                    ) : u.error ? <span className="text-[12px] text-neg">{u.error}</span>
                      : f ? <FileFacts f={f} />
                        : <span className="text-[12px] text-muted">{u.id ? 'بررسی رمز، hash و متن…' : <>در حال بارگذاری <span className="fig">{u.pct}%</span></>}</span>}
                  </span>
                  <button type="button" onClick={() => remove(u.key)} aria-label={`برداشتن ${u.file.name}`} className="flex-none text-muted hover:text-ink"><Icon name="close" size={16} /></button>
                </li>
              );
            })}
          </ul>
        ) : null}
        {busy && !got ? <Skeleton className="h-24" /> : null}
        <ErrorLine error={failure && !(failure instanceof ApiError && failure.code === 'validation_failed') ? failure : null} />
        {live.length > 1 ? (
          <label className="flex items-center gap-2 text-[13px] text-sec">
            <input type="checkbox" checked={split} onChange={(e) => setSplit(e.target.checked)} className="size-4 accent-[var(--hq-gold-fill)]" />
            هر فایل یک پیش‌نویس جدا؛ بایگان نوع و مشخصات هر کدام را پیشنهاد میدهد.
          </label>
        ) : null}
        {got && !split ? (
          <section className="flex flex-col gap-3" aria-label="مشخصات سند">
            {got.suggestion ? (
              <div className="flex flex-col gap-1 rounded-[12px] bg-learn-soft p-3">
                <SuggestionLine r={{ suggestion: got.suggestion }} />
                {got.suggestion.note_fa ? <span className="text-[12px] leading-5 text-ink">{got.suggestion.note_fa}</span> : null}
              </div>
            ) : <p className="rounded-[12px] bg-tile p-3 text-[12px] text-sec">قاعده‌ها نوع این سند را پیدا نکردند؛ خودت انتخاب کن.</p>}
            {scope ? <RecordForm scope={scope} value={form} onChange={edit} errors={errors} /> : <p className="text-[12px] text-warn">اول بگو برای کجاست.</p>}
            {failure instanceof ApiError && failure.code === 'validation_failed' ? <ErrorLine error={failure} /> : null}
            {c && (lacking.length || !enough) ? (
              <p className="text-[12px] leading-5 text-muted">برای ثبت مستقیم کم است: {[...lacking.map((f) => `«${f.title_fa}»`), ...(!enough ? [`دست‌کم ${c.required_files} فایل`] : [])].join('، ')}. پیش‌نویس بدون آن‌ها هم ساخته میشود.</p>
            ) : null}
          </section>
        ) : null}
      </div>
    </Sheet>
  );
}

// ------------------------------------------------------------------ the home's blocks --
/** What expires soonest: the nearest open reminder of every record (contract `end`, licence and domain `expires_at`, `review_at` …). */
export function ExpiringStrip() {
  const q = useRecords({ expiring_within_days: 365 });
  const m = useArchive();
  const now = useNow();
  const rows = (q.data?.pages.flatMap((p) => p.items) ?? []).flatMap((r) => {
    const next = r.reminders.filter((x) => x.state !== 'done').sort((a, b) => a.at.localeCompare(b.at))[0];
    return next ? [{ r, x: next, left: daysTo(next.at, now) }] : [];
  }).sort((a, b) => a.left - b.left).slice(0, 8);
  if (q.isLoading) return <Skeleton className="h-28" />;
  if (!rows.length) return null;
  return (
    <section className="flex min-w-0 flex-col gap-2" aria-label="نزدیک‌ترین سررسیدها">
      <div className="flex items-center gap-2">
        <h2 className="flex-1 text-[14px] font-semibold text-ink">نزدیک‌ترین سررسیدها</h2>
        <Link href="/archive/reminders" className="text-[12px] font-semibold text-gold-ink hover:underline">همه‌ی یادآورها</Link>
      </div>
      <ul className="-mx-1 flex snap-x gap-2 overflow-x-auto px-1 pb-1">
        {rows.map(({ r, x, left }) => {
          const tone = left <= 7 ? 'text-neg' : left <= 30 ? 'text-warn' : 'text-sec';
          const f = m.cls(r.class)?.fields.find((y) => y.key === x.field);
          return (
            <li key={`${r.ref}-${x.field}`} className="w-[228px] flex-none snap-start">
              <Link href={`/archive/${r.ref}`} className="flex h-full flex-col gap-1.5 rounded-[14px] bg-card p-3 transition-colors hover:bg-tile">
                <span className={cx('flex items-center gap-1.5 text-[13px] font-semibold', tone)}><Icon name="time" size={14} />{daysLeftFa(now ? left : 0)}</span>
                <span className="line-clamp-2 text-[13px] font-semibold leading-6 text-ink">{r.title_fa}</span>
                <span className="mt-auto flex flex-wrap items-center gap-x-1.5 text-[11px] text-muted">{f?.title_fa ?? x.field}: <JDay d={x.at} /></span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** The drafts waiting to be filed, each with the archivist's or the rules' suggestion. */
export function DraftsBlock({ scope }: { scope: string | null }) {
  const q = useRecords({ state: 'draft', scope });
  const xs = q.data?.pages.flatMap((p) => p.items) ?? [];
  if (q.isLoading) return <Skeleton className="h-24" />;
  if (!xs.length) return null;
  return (
    <section className="flex min-w-0 flex-col gap-2 rounded-[16px] bg-card p-3" aria-label="پیش‌نویس‌های منتظر ثبت">
      <h2 className="flex items-center gap-2 px-1 text-[14px] font-semibold text-ink"><Icon name="edit" size={16} />منتظر ثبت<span className="text-[12px] font-normal text-muted">{xs.length} پیش‌نویس</span></h2>
      <ul className="flex flex-col gap-1">
        {xs.map((r) => (
          <li key={r.ref}>
            <Link href={`/archive/${r.ref}`} className="flex min-w-0 flex-col gap-1.5 rounded-[12px] px-3 py-2.5 transition-colors hover:bg-hover">
              <span className="flex min-w-0 items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-[14px] font-semibold text-ink">{r.title_fa}</span>
                <span className="fig text-[11px] text-muted">{r.ref}</span>
              </span>
              <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-muted">
                <ScopeTag scope={r.scope} />
                <span>{r.versions.at(-1)?.files.length ?? 0} فایل</span>
                <span>{ago(r.created_at)}</span>
              </span>
              {r.suggestion ? <SuggestionLine r={r} /> : <span className="text-[12px] text-muted">بی‌پیشنهاد؛ بایگان هنوز نگاهش نکرده.</span>}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The last fixity run (§23.10): every stored file re-hashed daily; a failure is a data-loss alarm. */
export function FixityLine() {
  const q = useFixity();
  const f = q.data;
  if (!f) return null;
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-sec">
      {f.failed.length ? <Pill tone="neg" icon="urgent">{f.failed.length} فایل با hash خودش نمیخواند</Pill> : <Pill tone="pos" icon="seal">سلامت فایل‌ها</Pill>}
      <span>آخرین بررسی <JStamp at={f.at} />، {f.checked} فایل دوباره hash شد{f.failed.length ? '' : '، همه درست'}.</span>
      {f.failed.length ? f.failed.map((r) => <Link key={r} href={`/archive/${r}`} className="fig text-neg hover:underline">{r}</Link>) : null}
    </p>
  );
}

/** The party a filter names: who it is and the identifiers its kind defines (sensitive ones masked to the last four). */
export function PartyCard({ refId, onClear }: { refId: string; onClear: () => void }) {
  const m = useArchive();
  const p = m.party(refId);
  const k = p ? m.partyKind(p.kind) : undefined;
  return (
    <div className="flex min-w-0 flex-wrap items-start gap-3 rounded-[14px] bg-card p-3">
      <span className="flex size-10 flex-none items-center justify-center rounded-full bg-tile text-gold-ink"><Icon name={p?.kind === 'person' ? 'owner' : 'companies'} size={20} /></span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex flex-wrap items-center gap-2"><span className="text-[15px] font-semibold text-ink">{p?.name_fa ?? refId}</span>{p?.name_en ? <span className="fig text-[12px] text-muted">{p.name_en}</span> : null}<span className="fig text-[11px] text-muted">{refId}</span>{k ? <Pill>{k.title_fa}</Pill> : null}</span>
        {p && k ? (
          <dl className="flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
            {k.identifier_fields.filter((f) => p.identifiers[f.key] != null).map((f) => <div key={f.key} className="flex items-center gap-1.5"><dt className="text-muted">{f.title_fa}</dt><dd className="text-ink"><FieldValue f={f} v={p.identifiers[f.key]} /></dd></div>)}
          </dl>
        ) : null}
      </div>
      <FilterChip selected onClick={onClear}>برداشتن فیلتر <Icon name="close" size={12} /></FilterChip>
    </div>
  );
}

export function RecordsEmpty({ filtered }: { filtered: boolean }) {
  return <Empty icon="deliverable" title={filtered ? 'با این فیلترها سندی نیست' : 'بایگانی هنوز خالی است'} body={filtered ? 'فیلتری را بردار یا جستجو را کوتاه‌تر کن.' : 'اولین سند را با «سند تازه» بیاور؛ اساسنامه و ایمیل‌های حقوقی خودشان می‌آیند.'} />;
}
