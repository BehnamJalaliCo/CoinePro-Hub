'use client';

import { safeHref } from '@/lib/format';
import Link from 'next/link';
import { useMemo, useState, type ComponentProps, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { MdInline } from '@/components/ui/md';
import { Pill } from '@/components/ui/primitives';
import { CoMark, RefChip } from '@/components/v17/bits';
import type { IconName } from '@/generated/icons';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import {
  faError, useArchiveSchema,
  type ArchiveRecord, type ArchiveSchema, type Field, type FolderNode, type Level, type Money, type Party, type RecordClass, type RecordState, type ReminderTo, type TextState,
} from '@/lib/api/v20';
import { companyOf } from '@/lib/company';
import { ROLE_FA } from '@/lib/labels';
import { OWNER_TZ, cx } from '@/lib/format';

type Tone = ComponentProps<typeof Pill>['tone'];

// ------------------------------------------------------------------ labels (§23) --
// Every map below is a translation of a value the server sends; an unknown value (a new event, action or kind added on the hub)
// falls back to its key in Latin figures, so the screens keep working without a new release.
export const STATE: Record<RecordState | string, { fa: string; tone: Tone; icon: IconName }> = {
  draft: { fa: 'پیش‌نویس', tone: 'lapis', icon: 'edit' }, filed: { fa: 'ثبت‌شده', tone: 'silver', icon: 'deliverable' }, sealed: { fa: 'مُهرشده', tone: 'gold', icon: 'seal' },
  superseded: { fa: 'جایگزین‌شده', tone: 'neutral', icon: 'refresh' }, disposed: { fa: 'امحاشده', tone: 'neutral', icon: 'close' },
};
export const TEXT_STATE: Record<TextState | string, string> = { none: 'بی‌متن', text_layer: 'لایه‌ی متن', ocr: 'OCR', failed: 'OCR نشد' };
export const SOURCE_KIND: Record<string, string> = { owner: 'مدیر کل', agent: 'ایجنت', system: 'خودکار' };
export const EVENT_FA: Record<string, string> = {
  filed: 'وقتی ثبت شد', sealed: 'وقتی مُهر خورد', reminder_due: 'وقتی یادآور رسید', retention_due: 'وقتی نگهداری تمام شد', hold_set: 'وقتی توقیف شد', version_added: 'وقتی نسخه‌ی تازه آمد',
};
export const ACTION_FA: Record<string, string> = {
  notify: 'اعلان', work_item: 'کار برای یک نقش', link: 'پیوند', move_to_folder: 'انتقال به پوشه', raise_level: 'بالا بردن سطح', add_reminder: 'افزودن یادآور',
};
export const OP_FA: Record<string, string> = { eq: 'برابر با', lt: 'کمتر از', gt: 'بیشتر از', contains: 'شامل' };
export const REF_KIND_FA: Record<string, string> = {
  decision: 'کارت تصمیم', resolution: 'مصوبه', case: 'پرونده‌ی حقوقی', work: 'کار', record: 'سند بایگانی', employee: 'کارمند', revenue_account: 'حساب درآمد',
};
export const THEN_FA: Record<string, string> = { review: 'بازبینی بایگان', dispose_card: 'کارت امحا برای تو' };
export const CHANNEL_FA: Record<string, string> = { cartable: 'کارتابل', digest: 'خلاصه‌ی روزانه' };
/** Who a reminder goes to (§23.6): the owner, a role, or the company's CEO. */
export const reminderToFa = (t: ReminderTo) => (t === 'owner' ? 'تو' : 'role' in t ? ROLE_FA[t.role] ?? t.role : 'مدیرعامل همان شرکت');
export const NOTIFY_LEVEL_FA: Record<string, string> = { info: 'اطلاع', report: 'گزارش', decision: 'تصمیم' };
export const ACCESS_FA: Record<string, { fa: string; icon: IconName }> = {
  view: { fa: 'دید', icon: 'search' }, download: { fa: 'دریافت کرد', icon: 'download' }, metadata: { fa: 'مشخصات را خواند', icon: 'report' },
  level: { fa: 'سطح را عوض کرد', icon: 'lock' },
};
/** Level colour by its stored slot; colour is never alone, the title always goes with it. */
const LEVEL_TONE: Tone[] = ['neutral', 'silver', 'warn', 'neg', 'lapis', 'learn'];
export const levelTone = (l: Pick<Level, 'color_index'> | null | undefined): Tone => LEVEL_TONE[l?.color_index ?? 0] ?? 'neutral';

// ------------------------------------------------------------------ the schema, as maps --
export type ArchiveMaps = ReturnType<typeof buildMaps>;
function buildMaps(s: ArchiveSchema | undefined) {
  const classes = s?.classes ?? [];
  const levels = [...(s?.levels ?? [])].sort((a, b) => a.rank - b.rank);
  const folders = [...(s?.folders ?? [])].sort((a, b) => a.order - b.order);
  const parties = s?.parties ?? [];
  const byKey = <T extends { key: string }>(xs: T[]) => new Map(xs.map((x) => [x.key, x]));
  const cm = byKey(classes), lm = byKey(levels), lk = byKey(s?.link_kinds ?? []), pk = byKey(s?.party_kinds ?? []), ft = byKey(s?.field_types ?? []);
  const fm = new Map(folders.map((f) => [f.ref, f])), pm = new Map(parties.map((p) => [p.ref, p]));
  const path = (ref: string | null | undefined): FolderNode[] => {
    const out: FolderNode[] = [];
    for (let f = ref ? fm.get(ref) : undefined; f && out.length < 12; f = f.parent ? fm.get(f.parent) : undefined) out.unshift(f);
    return out;
  };
  return {
    schema: s, classes, levels, folders, parties,
    cls: (k: string | null | undefined): RecordClass | undefined => (k ? cm.get(k) : undefined),
    level: (k: string | null | undefined): Level | undefined => (k ? lm.get(k) : undefined),
    rank: (k: string | null | undefined) => (k ? lm.get(k)?.rank ?? 0 : 0),
    folder: (r: string | null | undefined) => (r ? fm.get(r) : undefined),
    folderPath: path,
    party: (r: unknown): Party | undefined => (typeof r === 'string' ? pm.get(r) : undefined),
    linkKind: (k: string) => lk.get(k),
    partyKind: (k: string) => pk.get(k),
    typeFa: (k: string) => ft.get(k as never)?.title_fa ?? k,
    vocab: s?.vocab,
  };
}
/** The archive's schema (§23.10) as lookups every screen shares. */
export function useArchive() {
  const q = useArchiveSchema();
  const maps = useMemo(() => buildMaps(q.data), [q.data]);
  return { ...maps, q };
}

/** The default folder of a class in a scope (§23.12): the first folder of that scope that lists the class, else the class's own default. */
export function defaultFolder(m: ArchiveMaps, scope: string, cls: string | null): string | null {
  if (!cls) return null;
  const f = m.folders.find((x) => x.scope === scope && x.status === 'active' && x.classes.includes(cls));
  if (f) return f.ref;
  const d = m.cls(cls)?.default_folder;
  return d && m.folder(d)?.scope === scope ? d : null;
}

// ------------------------------------------------------------------ dates and figures --
const DAY = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { timeZone: OWNER_TZ, day: 'numeric', month: 'long', year: 'numeric' });
const DAY_SHORT = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { timeZone: OWNER_TZ, day: 'numeric', month: 'long' });
const TIME = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { timeZone: OWNER_TZ, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
/** A stored calendar day ("YYYY-MM-DD") read at noon UTC, so no time zone moves it to the next or previous day. */
const asInstant = (d: string) => new Date(/^\d{4}-\d{2}-\d{2}$/.test(d) ? `${d}T12:00:00Z` : d);

/** A Jalali day with Latin figures and the Persian month name, in reading order («12 مرداد 1405»). */
export function JDay({ d, year = true, className }: { d: string | null | undefined; year?: boolean; className?: string }) {
  if (!d) return <span className={cx('text-muted', className)}>—</span>;
  const t = asInstant(d);
  if (Number.isNaN(t.getTime())) return <span className={cx('fig', className)}>{d}</span>;
  const parts = (year ? DAY : DAY_SHORT).formatToParts(t);
  return (
    <span className={cx('whitespace-nowrap', className)} title={d.slice(0, 10)}>
      {parts.map((p, i) => (p.type === 'day' || p.type === 'year' ? <span key={i} className="fig">{p.value}</span> : <span key={i}>{p.value}</span>))}
    </span>
  );
}
/** A moment: the Jalali day and the time, both in Latin figures. */
export function JStamp({ at, year = false, className }: { at: string | null | undefined; year?: boolean; className?: string }) {
  if (!at) return <span className={cx('text-muted', className)}>—</span>;
  return <span className={cx('whitespace-nowrap', className)}><JDay d={at} year={year} />، <span className="fig">{TIME.format(new Date(at))}</span></span>;
}
/** Whole days from today to a calendar day (negative = past), in the owner's time zone. */
export function daysTo(d: string, now: number): number {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: OWNER_TZ }).format(new Date(now || Date.parse(d)));
  return Math.round((Date.parse(`${d.slice(0, 10)}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / 86_400_000);
}
/** «۲۵ روز مانده» / «امروز» / «۳ روز گذشته»: a count, so Persian digits. */
export const daysLeftFa = (n: number) => (n === 0 ? 'امروز' : n > 0 ? `${n} روز مانده` : `${-n} روز گذشته`);

/** A decimal string with thousands separators, its fraction exactly as stored. */
export function amountFig(amount: string): string {
  const [i = '', f] = amount.trim().split('.');
  const neg = i.startsWith('-');
  const int = (neg ? i.slice(1) : i).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return `${neg ? '-' : ''}${int}${f != null ? `.${f}` : ''}`;
}
export const moneyFig = (m: Money) => `${amountFig(m.amount)} ${m.currency}`;
export const isMoney = (v: unknown): v is Money => !!v && typeof v === 'object' && 'amount' in v && typeof (v as Money).amount === 'string';

/** A SHA-256 shortened for reading (the whole hash on hover). */
export function Sha({ v, label = 'sha256', className }: { v: string | null | undefined; label?: string; className?: string }) {
  if (!v) return null;
  return <span className={cx('fig whitespace-nowrap text-muted', className)} title={v}>{label} {v.slice(0, 10)}…{v.slice(-4)}</span>;
}
export function bytesFig(n: number): string {
  if (n >= 1_048_576) return `${(n / 1_048_576).toFixed(1)} MB`;
  if (n >= 1024) return `${Math.round(n / 1024)} KB`;
  return `${n} B`;
}

// ------------------------------------------------------------------ small pieces --
export function LevelPill({ level, className }: { level: Level | string | null | undefined; className?: string }) {
  const m = useArchive();
  const l = typeof level === 'string' ? m.level(level) : level;
  if (!l) return typeof level === 'string' ? <Pill className={className}><span className="fig">{level}</span></Pill> : null;
  return <Pill tone={levelTone(l)} icon={l.step_up_to_view ? 'lock' : undefined} dot={!l.step_up_to_view} className={className}>{l.title_fa}</Pill>;
}
export function StatePill({ state, className }: { state: RecordState | string; className?: string }) {
  const s = STATE[state] ?? { fa: state, tone: 'neutral' as Tone, icon: 'info' as IconName };
  return <Pill tone={s.tone} icon={s.icon} className={className}>{s.fa}</Pill>;
}
export function ClassTag({ cls, className }: { cls: string | null | undefined; className?: string }) {
  const m = useArchive();
  const c = m.cls(cls);
  if (!cls) return <span className={cx('inline-flex items-center gap-1 text-muted', className)}><Icon name="info" size={13} />نوع‌نشده</span>;
  return <span className={cx('inline-flex items-center gap-1', className)}><Icon name={(c?.icon as IconName) ?? 'report'} size={13} />{c?.title_fa ?? <span className="fig">{cls}</span>}</span>;
}
export function ScopeTag({ scope, className }: { scope: string; className?: string }) {
  const { data } = useCompanies();
  return <span className={cx('inline-flex items-center gap-1', className)}><CoMark code={scope} height={11} />{companyOf(data, scope).nameFa}</span>;
}
/** A party of the registry as a chip that opens its records. */
export function PartyChip({ refId, role, className }: { refId: string; role?: string | null; className?: string }) {
  const m = useArchive();
  const p = m.party(refId);
  return (
    <Link href={`/archive?party=${refId}`} className={cx('inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-full bg-tile px-2.5 py-1 text-[12px] text-ink hover:bg-hover', className)} title={refId}>
      <Icon name={p?.kind === 'person' ? 'owner' : p?.kind === 'government' ? 'holding' : 'companies'} size={13} />
      <span className="truncate">{p?.name_fa ?? <span className="fig">{refId}</span>}</span>
      {role ? <span className="truncate text-muted">· {role}</span> : null}
    </Link>
  );
}
/** A folder as its path in the file plan, each step a filter. */
export function FolderPath({ refId, className }: { refId: string | null | undefined; className?: string }) {
  const m = useArchive();
  const path = m.folderPath(refId);
  if (!refId) return <span className={cx('text-muted', className)}>بی‌پوشه</span>;
  if (!path.length) return <span className={cx('fig', className)}>{refId}</span>;
  return (
    <span className={cx('inline-flex flex-wrap items-center gap-1', className)}>
      {path.map((f, i) => (
        <span key={f.ref} className="inline-flex items-center gap-1">
          {i ? <span className="text-muted" aria-hidden>‹</span> : null}
          <Link href={`/archive?folder=${f.ref}`} className="hover:underline">{f.title_fa}</Link>
        </span>
      ))}
    </span>
  );
}

/** The last four characters of an identifier; the rest as dots (§23.2 `id_code`, `iban`). */
export const last4 = (s: string) => (s.length <= 4 ? s : `•••• ${s.slice(-4)}`);
function Masked4({ v }: { v: string }) {
  const [show, setShow] = useState(false);
  return (
    <span className="inline-flex items-center gap-1.5">
      <span dir="ltr" className="fig">{show ? v : last4(v)}</span>
      <button type="button" onClick={() => setShow((x) => !x)} className="text-[11px] font-normal text-gold-ink hover:underline">{show ? 'پنهان' : 'نمایش'}</button>
    </span>
  );
}

/** One metadata value, typed by its field (§23.2, §23.12 values). `plain` for a value inside a button or a link (no nested controls). */
export function FieldValue({ f, v, masked, plain }: { f: Pick<Field, 'type' | 'options' | 'currency'> & { key?: string }; v: unknown; masked?: boolean; plain?: boolean }) {
  const { data: companies } = useCompanies();
  const m = useArchive();
  if (plain && v != null && v !== '') {
    if (f.type === 'id_code' || f.type === 'iban') return <span dir="ltr" className="fig">{last4(String(v))}</span>;
    if (f.type === 'url' || f.type === 'email' || f.type === 'phone') return <span dir="ltr" className="fig break-all">{String(v)}</span>;
    if (f.type === 'party') return <span>{m.party(v)?.name_fa ?? String(v)}</span>;
    if (f.type === 'ref') return <span className="fig">{(v as { ref?: string }).ref ?? ''}</span>;
  }
  if (masked) return <span className="inline-flex items-center gap-1 text-muted"><Icon name="lock" size={13} />{typeof v === 'string' && v ? <span className="fig">{v}</span> : 'پنهان برای سطح تو'}</span>;
  if (v == null || v === '' || (Array.isArray(v) && !v.length)) return <span className="text-muted">—</span>;
  const opt = (k: unknown) => f.options?.find((o) => o.key === k)?.title_fa ?? String(k);
  switch (f.type) {
    case 'money': return isMoney(v) ? <span className="fig">{moneyFig(v)}</span> : <span className="fig">{String(v)}</span>;
    case 'percent': return <span className="fig">{String(v)}%</span>;
    case 'number': return <span className="fig">{typeof v === 'number' ? v.toLocaleString('en-US') : String(v)}</span>;
    case 'date': return <JDay d={String(v)} />;
    case 'date_range': {
      const r = v as { from?: string; to?: string };
      return <span className="inline-flex flex-wrap items-center gap-1"><JDay d={r.from} /><span className="text-muted">تا</span><JDay d={r.to} /></span>;
    }
    case 'enum': return <span>{opt(v)}</span>;
    case 'multi_enum': return <span className="inline-flex flex-wrap gap-1">{(Array.isArray(v) ? v : [v]).map((k) => <span key={String(k)} className="rounded-full bg-tile px-2 py-0.5 text-[12px]">{opt(k)}</span>)}</span>;
    case 'boolean': return <span>{v ? 'بله' : 'نه'}</span>;
    case 'party': return typeof v === 'string' ? <PartyChip refId={v} /> : <span className="fig">{JSON.stringify(v)}</span>;
    case 'company': return <span className="inline-flex items-center gap-1"><CoMark code={String(v)} height={11} />{companyOf(companies, String(v)).nameFa}</span>;
    case 'ref': {
      const r = v as { kind?: string; ref?: string };
      return r?.ref ? <RefChip r={r.ref} note={r.kind ? REF_KIND_FA[r.kind] ?? r.kind : null} /> : <span className="fig">{String(v)}</span>;
    }
    case 'url': { const href = safeHref(v); return href ? <a href={href} target="_blank" rel="noreferrer noopener" dir="ltr" className="fig break-all text-gold-ink hover:underline">{String(v)}</a> : <span dir="ltr" className="fig break-all">{String(v)}</span>; }
    case 'email': return <a href={`mailto:${String(v)}`} dir="ltr" className="fig break-all text-gold-ink hover:underline">{String(v)}</a>;
    case 'phone': return <span dir="ltr" className="fig">{String(v)}</span>;
    case 'id_code': case 'iban': return <Masked4 v={String(v)} />;
    case 'long_text': return <span className="whitespace-pre-wrap break-words font-normal leading-7">{String(v)}</span>;
    default: return /[A-Za-z0-9]/.test(String(v)) && !/[؀-ۿ]/.test(String(v)) ? <span dir="ltr" className="fig break-words">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span> : <span className="break-words">{String(v)}</span>;
  }
}

/** The field errors a refused call named (`fields`), keyed as the server keys them. */
export const fieldErrors = (e: unknown): Record<string, string> => (e instanceof ApiError && e.fields ? { ...e.fields } : {});
/** A refusal in Persian, next to what it refers to (sealed_record 409, held 423, schema_invalid 422 …). */
export function ErrorLine({ error, className }: { error: unknown; className?: string }) {
  if (!error) return null;
  const code = error instanceof ApiError ? error.code : null;
  return (
    <p role="alert" className={cx('flex items-start gap-2 rounded-[12px] bg-neg-soft p-3 text-[13px] leading-6 text-ink', className)}>
      <span className="mt-0.5 text-neg"><Icon name={code === 'held' || code === 'sealed_record' ? 'lock' : 'urgent'} size={16} /></span>
      <span className="min-w-0 flex-1"><MdInline text={faError(error)} />{code ? <span className="fig mr-2 text-[11px] text-muted">{code}</span> : null}</span>
    </p>
  );
}

/** A labelled block of a record page. */
export function Panel({ title, note, action, children, className, id }: { title: ReactNode; note?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={cx('flex min-w-0 flex-col gap-3 rounded-[16px] bg-card p-4', className)}>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-0 flex-1 flex-col">
          <h2 className="text-[14px] font-semibold text-ink">{title}</h2>
          {note ? <p className="text-[12px] text-muted">{note}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

// Inputs: a height, a width, a text size and a border colour by default, each dropped when the caller names its own (two utilities of
// one property in one class list are resolved by stylesheet order, not by the order written, so they must never meet).
type Cls = string | false | null | undefined;
const DEFAULTS: Array<[RegExp, string]> = [[/^h-/, 'h-10'], [/^w-/, 'w-full'], [/^text-\[\d+px\]$/, 'text-[14px]'], [/^border-(?![0-9]|[xytblrse](-|$))/, 'border-strong']];
const merged = (base: string, defaults: Array<[RegExp, string]>, xs: Cls[]) => {
  const extra = cx(...xs);
  const toks = extra.split(/\s+/);
  return [base, ...defaults.filter(([re]) => !toks.some((t) => re.test(t))).map(([, d]) => d), extra].filter(Boolean).join(' ');
};
/** A one-line input or select; `field('w-24', invalid && bad)`. */
export const field = (...xs: Cls[]) => merged('min-w-0 rounded-[10px] border bg-card px-3 text-ink outline-none focus:border-gold-ink', DEFAULTS, xs);
/** A text area. */
export const fieldArea = (...xs: Cls[]) => merged('min-w-0 rounded-[10px] border bg-card p-3 leading-6 text-ink outline-none focus:border-gold-ink', DEFAULTS.filter(([re]) => re.source !== '^h-'), xs);
export const bad = 'border-[var(--hq-neg-line)]';

/** The draft's suggestion, said as what it is: never filed by itself. */
export function SuggestionLine({ r }: { r: Pick<ArchiveRecord, 'suggestion'> }) {
  const s = r.suggestion;
  const m = useArchive();
  if (!s) return null;
  return (
    <span className="flex flex-wrap items-center gap-1.5 text-[12px] text-sec">
      <span className="inline-flex items-center gap-1 rounded-full bg-learn-soft px-2 py-0.5 font-semibold text-learn"><Icon name={s.by === 'archivist' ? 'agent' : 'settings'} size={12} />{s.by === 'archivist' ? 'پیشنهاد بایگان' : 'پیشنهاد قاعده‌ها'}</span>
      {s.class ? <span>نوع: <span className="text-ink">{m.cls(s.class)?.title_fa ?? s.class}</span></span> : <span>نوع پیدا نشد</span>}
      {Object.keys(s.metadata ?? {}).length ? <span>· {Object.keys(s.metadata).length} فیلد</span> : null}
      {s.parties?.length ? <span>· {s.parties.map((p) => m.party(p)?.name_fa ?? p).join('، ')}</span> : null}
    </span>
  );
}
