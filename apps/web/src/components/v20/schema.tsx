'use client';

import { useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { FilterChip, Pill, Segmented, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import type { IconName } from '@/generated/icons';
import { ApiError, type Schemas } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { faError, useSchemaAction, type Impact, type SchemaPart, type SchemaResult } from '@/lib/api/v20';
import { ROLE_FA } from '@/lib/labels';
import { cx } from '@/lib/format';
import { ACTION_FA, CHANNEL_FA, ErrorLine, EVENT_FA, NOTIFY_LEVEL_FA, OP_FA, REF_KIND_FA, THEN_FA, bad, levelTone, reminderToFa, useArchive, type ArchiveMaps, field, fieldArea } from './bits';

export type Row = Record<string, unknown>;
type Opt = { v: string; t: string };
type Company = Schemas['Company'];

// ================================================================== the descriptors ==
// Every editor below is drawn from these rows of data: an attribute's kind picks the input, its source picks the options from the
// schema the server sent (`GET /archive/schema`, its `vocab` included). A new value in the closed vocabulary (a field type, an event,
// an action, a currency) appears in the editors without a release; a new part of the schema gets the generic editor (`inferAttrs`).
export type Kind = 'text' | 'key' | 'int' | 'bool' | 'select' | 'multi' | 'fields' | 'keep' | 'trigger' | 'lead_days' | 'to' | 'when' | 'do' | 'scopes' | 'grants' | 'subject' | 'color' | 'json' | 'list';
export type Source = 'levels' | 'folders' | 'classes' | 'retention' | 'link_kinds' | 'party_kinds' | 'events' | 'actions' | 'ops' | 'ref_kinds' | 'currencies' | 'mimes' | 'companies' | 'then' | 'channels' | 'date_fields' | 'ref_fields' | 'scope_folders' | 'icons';
export type Attr = { key: string; fa: string; kind: Kind; source?: Source; help?: string; nullable?: boolean; locked?: (row: Row, saved: boolean) => string | null; wide?: boolean };
export type PartUI = {
  fa: string; icon: IconName; note: string; by: 'key' | 'ref' | 'subject'; attrs: Attr[]; retire: boolean;
  blank: (m: ArchiveMaps) => Row; usage?: (row: Row) => string | null; sub?: (row: Row, m: ArchiveMaps, companies?: Company[]) => ReactNode;
};
const used = (row: Row) => Number(row.records ?? 0);
const lockedKey = (_: Row, saved: boolean) => (saved ? 'کلید بعد از ساخت عوض نمیشود' : null);

export const PART_UI: Record<string, PartUI> = {
  classes: {
    fa: 'نوع سندها', icon: 'report', by: 'key', retire: true, note: 'هر نوع سند و فیلدهایش؛ تغییر یک نسخه‌ی تازه میسازد و سندها نسخه‌ی خودشان را نگه میدارند.',
    attrs: [
      { key: 'title_fa', fa: 'عنوان', kind: 'text' },
      { key: 'parent', fa: 'زیرنوعِ', kind: 'select', source: 'classes', nullable: true },
      { key: 'scopes', fa: 'برای', kind: 'scopes' },
      { key: 'icon', fa: 'نشانه', kind: 'select', source: 'icons' },
      { key: 'default_level', fa: 'سطح پیش‌فرض', kind: 'select', source: 'levels' },
      { key: 'default_folder', fa: 'پوشه‌ی پیش‌فرض', kind: 'select', source: 'folders', nullable: true },
      { key: 'retention', fa: 'قاعده‌ی نگهداری', kind: 'select', source: 'retention', nullable: true },
      { key: 'required_files', fa: 'کمترین تعداد فایل', kind: 'int' },
      { key: 'ocr', fa: 'OCR روی اسکن‌ها', kind: 'bool' },
      { key: 'allowed_mime', fa: 'نوع فایل‌های مجاز', kind: 'multi', source: 'mimes', wide: true },
      { key: 'fields', fa: 'فیلدها', kind: 'fields', wide: true },
      { key: 'reminder_fields', fa: 'فیلدهای یادآور', kind: 'multi', source: 'date_fields', wide: true },
      { key: 'auto_link', fa: 'پیوند خودکار', kind: 'list', source: 'ref_fields', wide: true },
    ],
    blank: (m) => ({ key: '', title_fa: '', parent: null, scopes: 'all', icon: 'report', default_level: m.levels.find((l) => l.key === 'internal')?.key ?? m.levels[0]?.key ?? '', default_folder: null, fields: [], required_files: 1, allowed_mime: ['application/pdf'], ocr: true, retention: null, reminder_fields: [], auto_link: [] }),
    usage: (r) => (used(r) ? `${used(r)} سند` : null),
    sub: (r) => `${(r.fields as unknown[] | undefined)?.length ?? 0} فیلد`,
  },
  folders: {
    fa: 'طرح پوشه‌ها', icon: 'deliverable', by: 'ref', retire: true, note: 'درخت پوشه‌های هر دامنه؛ اولین پوشه‌ای که نوع سند را بپذیرد پیش‌فرض آن نوع است.',
    attrs: [
      { key: 'title_fa', fa: 'عنوان', kind: 'text' },
      { key: 'scope', fa: 'دامنه', kind: 'select', source: 'companies', locked: (_r, saved) => (saved ? 'دامنه‌ی پوشه بعد از ساخت عوض نمیشود' : null) },
      { key: 'parent', fa: 'زیرپوشه‌ی', kind: 'select', source: 'scope_folders', nullable: true },
      { key: 'classes', fa: 'نوع سندهایی که میپذیرد', kind: 'multi', source: 'classes', wide: true },
      { key: 'default_level', fa: 'کمترین سطح', kind: 'select', source: 'levels', nullable: true },
      { key: 'order', fa: 'ترتیب', kind: 'int' },
    ],
    blank: () => ({ title_fa: '', scope: 'HQ', parent: null, classes: [], default_level: null, order: 0 }),
    usage: (r) => (used(r) ? `${used(r)} سند` : null),
    sub: (r, m) => <span className="inline-flex flex-wrap items-center gap-1"><span className="fig">{String(r.scope)}</span>{r.parent ? <>· زیر {m.folder(String(r.parent))?.title_fa ?? String(r.parent)}</> : null}</span>,
  },
  levels: {
    fa: 'سطح‌ها', icon: 'lock', by: 'key', retire: true, note: 'سطح دسترسی هر سند؛ رتبه‌ی سطحی که سند دارد دیگر عوض نمیشود. سطح تازه را با رتبه‌ای میان دو سطح بساز.',
    attrs: [
      { key: 'title_fa', fa: 'عنوان', kind: 'text' },
      { key: 'rank', fa: 'رتبه', kind: 'int', help: 'بزرگ‌تر یعنی محرمانه‌تر', locked: (r) => (used(r) ? `رتبه‌ی سطحی که ${used(r)} سند دارد عوض نمیشود` : null) },
      { key: 'color_index', fa: 'رنگ', kind: 'color' },
      { key: 'watermark', fa: 'ته‌نقش روی هر نمایش', kind: 'bool' },
      { key: 'encrypt', fa: 'رمزگذاری با کلید OpenBao', kind: 'bool' },
      { key: 'step_up_to_view', fa: 'دیدن با passkey', kind: 'bool' },
      { key: 'agents_max', fa: 'سقف مجوز ایجنت‌ها', kind: 'bool', help: 'هیچ ایجنتی بالاتر از این سطح مجوز نمیگیرد' },
    ],
    blank: (m) => ({ key: '', title_fa: '', rank: (m.levels.at(-1)?.rank ?? 0) + 5, color_index: 4, watermark: false, encrypt: false, step_up_to_view: false, agents_max: false }),
    usage: (r) => (used(r) ? `${used(r)} سند` : null),
    sub: (r) => <span>رتبه‌ی <span className="fig">{String(r.rank)}</span>{r.watermark ? '، ته‌نقش' : ''}{r.encrypt ? '، رمزگذاری' : ''}{r.step_up_to_view ? '، passkey' : ''}{r.agents_max ? '، سقف ایجنت‌ها' : ''}</span>,
  },
  clearance: {
    fa: 'مجوز دیدن', icon: 'owner', by: 'subject', retire: false, note: 'هر نقش یا کارمند تا چه سطحی در کدام دامنه میبیند؛ تو همه چیز را میبینی. ذخیره با passkey (archive.clearance).',
    attrs: [
      { key: 'subject', fa: 'برای', kind: 'subject', locked: (_r, saved) => (saved ? 'برای کس دیگر، ردیف تازه بساز' : null) },
      { key: 'grants', fa: 'مجوزها', kind: 'grants', wide: true },
      { key: 'metadata_level', fa: 'مشخصات سندهایی که خودش ثبت میکند تا سطح', kind: 'select', source: 'levels', nullable: true, help: 'برای بایگان: مشخصات هر سندی را که خودش ثبت میکند میبیند، حتی بالاتر از سطح محتوایش' },
    ],
    blank: () => ({ subject: { kind: 'role', ref: '' }, grants: [{ scope: 'own', level: 'internal' }], metadata_level: null }),
    sub: (r, m) => <span className="inline-flex flex-wrap items-center gap-x-1.5"><AttrValue a={{ key: 'grants', fa: '', kind: 'grants' }} v={r.grants} m={m} row={r} />{r.metadata_level ? <span>· مشخصات تا {m.level(String(r.metadata_level))?.title_fa ?? String(r.metadata_level)}</span> : null}</span>,
  },
  retention: {
    fa: 'نگهداری', icon: 'memory', by: 'ref', retire: true, note: 'هر سند چه مدت میماند و بعدش چه میشود؛ پیش‌فرض‌اند، نه نظر حقوقی. امحا فقط با مُهر تو روی کارت.',
    attrs: [
      { key: 'title_fa', fa: 'عنوان', kind: 'text', wide: true },
      { key: 'trigger', fa: 'شمارش از', kind: 'trigger' },
      { key: 'keep', fa: 'مدت', kind: 'keep' },
      { key: 'then', fa: 'بعد از آن', kind: 'select', source: 'then' },
    ],
    blank: () => ({ title_fa: '', trigger: 'filed', keep: { years: 5 }, then: 'review' }),
    sub: (r, m) => <span>{keepFa(r.keep)}{r.keep === 'permanent' ? '' : ` از ${triggerFa(r.trigger, m)}`}، بعد {THEN_FA[String(r.then)] ?? String(r.then)}</span>,
    usage: (r) => (used(r) ? `${used(r)} سند` : null),
  },
  reminders: {
    fa: 'یادآورها', icon: 'time', by: 'ref', retire: true, note: 'چند روز پیش از یک تاریخ، به چه کسی و کجا.',
    attrs: [
      { key: 'class', fa: 'نوع سند', kind: 'select', source: 'classes' },
      { key: 'field', fa: 'فیلد تاریخ', kind: 'select', source: 'date_fields' },
      { key: 'lead_days', fa: 'چند روز پیش', kind: 'lead_days' },
      { key: 'to', fa: 'برای', kind: 'to' },
      { key: 'channel', fa: 'کجا', kind: 'select', source: 'channels' },
    ],
    blank: () => ({ class: '', field: '', lead_days: [30, 7], to: 'owner', channel: 'cartable' }),
    sub: (r, m) => <span>{m.cls(String(r.class))?.title_fa ?? String(r.class)} · {m.cls(String(r.class))?.fields.find((f) => f.key === r.field)?.title_fa ?? String(r.field)} · <span className="fig">{((r.lead_days as number[]) ?? []).join('، ')}</span> روز پیش · {reminderToFa(r.to as never)}</span>,
  },
  party_kinds: {
    fa: 'نوع طرف‌ها', icon: 'companies', by: 'key', retire: true, note: 'صرافی، تأمین‌کننده، نهاد دولتی… و شناسه‌هایی که هر کدام دارد.',
    attrs: [
      { key: 'title_fa', fa: 'عنوان', kind: 'text' },
      { key: 'identifier_fields', fa: 'شناسه‌ها', kind: 'fields', wide: true },
    ],
    blank: () => ({ key: '', title_fa: '', identifier_fields: [] }),
    usage: (r) => (Number(r.parties ?? 0) ? `${Number(r.parties)} طرف` : null),
    sub: (r) => `${(r.identifier_fields as unknown[] | undefined)?.length ?? 0} شناسه`,
  },
  link_kinds: {
    fa: 'نوع پیوندها', icon: 'share', by: 'key', retire: true, note: 'سندها چطور به هم و به کارت، پرونده و کار وصل میشوند؛ هر پیوند از آن سو هم خوانده میشود.',
    attrs: [
      { key: 'title_fa', fa: 'عنوان', kind: 'text' },
      { key: 'inverse_fa', fa: 'از آن سو', kind: 'text' },
      { key: 'to_kinds', fa: 'به', kind: 'multi', source: 'ref_kinds', wide: true },
    ],
    blank: () => ({ key: '', title_fa: '', inverse_fa: '', to_kinds: ['record'] }),
    usage: (r) => (used(r) ? `${used(r)} سند` : null),
    sub: (r) => `${String(r.title_fa)} ↔ ${String(r.inverse_fa)}`,
  },
  automations: {
    fa: 'خودکارها', icon: 'refresh', by: 'ref', retire: true, note: 'فقط قاعده، هرگز مدل: یک رویداد، چند شرط و چند اقدام از واژگان بسته.',
    attrs: [
      { key: 'title_fa', fa: 'عنوان', kind: 'text', wide: true },
      { key: 'on', fa: 'رویداد', kind: 'select', source: 'events' },
      { key: 'when', fa: 'شرط‌ها', kind: 'when', wide: true },
      { key: 'do', fa: 'اقدام‌ها', kind: 'do', wide: true },
    ],
    blank: (m) => ({ title_fa: '', on: m.vocab?.events[0] ?? 'filed', when: {}, do: [] }),
    usage: (r) => (Number(r.runs_30d ?? 0) ? `${Number(r.runs_30d)} اجرا در ۳۰ روز` : null),
    sub: (r) => EVENT_FA[String(r.on)] ?? String(r.on),
  },
};
/** The parts in their tab order; any other array the schema returns is a part too, with the generic editor. */
export const PART_ORDER = ['classes', 'folders', 'levels', 'clearance', 'retention', 'reminders', 'party_kinds', 'link_kinds', 'automations'];
const NOT_PARTS = new Set(['field_types', 'parties', 'sources', 'vocab']);
export const extraParts = (schema: Record<string, unknown> | undefined) => Object.keys(schema ?? {}).filter((k) => !PART_ORDER.includes(k) && !NOT_PARTS.has(k) && Array.isArray(schema![k]));
/** A part the app has no descriptor for: its attributes read off its rows. */
export function inferAttrs(rows: Row[]): Attr[] {
  const skip = new Set(['key', 'ref', 'version', 'status', 'records', 'parties', 'runs_30d', 'last_run_at']);
  const sample = rows[0] ?? { title_fa: '' };
  return Object.entries(sample).filter(([k]) => !skip.has(k)).map(([k, v]) => ({
    key: k, fa: k, kind: typeof v === 'boolean' ? 'bool' : typeof v === 'number' ? 'int' : typeof v === 'string' ? 'text' : 'json', wide: typeof v === 'object',
  }));
}
export function partUI(part: string, rows: Row[] = []): PartUI {
  return PART_UI[part] ?? { fa: part, icon: 'settings', note: 'بخشی تازه از طرح بایگانی.', by: rows.some((r) => 'ref' in r) ? 'ref' : 'key', attrs: inferAttrs(rows), retire: true, blank: () => Object.fromEntries(inferAttrs(rows).map((a) => [a.key, a.kind === 'bool' ? false : a.kind === 'int' ? 0 : a.kind === 'json' ? null : ''])) };
}
export const rowKey = (part: string, ui: PartUI, row: Row): string => (ui.by === 'subject' ? `${(row.subject as { kind: string; ref: string }).kind}:${(row.subject as { kind: string; ref: string }).ref}` : String(row[ui.by] ?? ''));
/** Clearance arrives one row per grant (or already grouped, §23.12); the editor saves one subject at a time. */
function clearanceRows(raw: Row[]): Row[] {
  const by = new Map<string, Row>();
  for (const c of raw) {
    const s = typeof c.subject === 'string' ? { kind: String(c.subject).split(':')[0], ref: String(c.subject).split(':').slice(1).join(':') } : (c.subject as { kind: string; ref: string });
    const k = `${s.kind}:${s.ref}`;
    const cur = by.get(k) ?? { subject: s, grants: [], metadata_level: c.metadata_level ?? null, version: c.version ?? null };
    const grants = Array.isArray(c.grants) ? (c.grants as Row[]) : [{ scope: c.scope, level: c.level }];
    cur.grants = [...(cur.grants as Row[]), ...grants];
    by.set(k, cur);
  }
  return [...by.values()];
}
/** The rows of one part of the schema, as its editor reads them. */
export function rowsOf(m: ArchiveMaps, part: string): Row[] {
  const raw = ((m.schema as unknown as Record<string, unknown> | undefined)?.[part] ?? []) as Row[];
  return part === 'clearance' ? clearanceRows(raw) : raw;
}
/** The exact body of a PUT: the descriptor's attributes, nothing the server computes. */
export const bodyOf = (ui: PartUI, row: Row): Row => Object.fromEntries(ui.attrs.map((a) => [a.key, row[a.key] ?? null]));

// ================================================================== options --
const ICONS: IconName[] = ['report', 'found', 'share', 'lock', 'budget', 'globe', 'send', 'seal', 'image', 'meeting', 'attach', 'deliverable', 'companies', 'knowledge', 'server', 'decision', 'chart', 'treasury'];
export function options(src: Source | undefined, m: ArchiveMaps, row: Row, companies: Company[] | undefined): Opt[] {
  const v = m.vocab;
  switch (src) {
    case 'levels': return m.levels.filter((l) => l.status !== 'retired').map((l) => ({ v: l.key, t: l.title_fa }));
    case 'folders': return m.folders.filter((f) => f.status !== 'retired').map((f) => ({ v: f.ref, t: `${f.title_fa} · ${f.scope}` }));
    case 'scope_folders': return m.folders.filter((f) => f.status !== 'retired' && f.scope === row.scope && f.ref !== row.ref && !m.folderPath(f.ref).some((x) => x.ref === row.ref)).map((f) => ({ v: f.ref, t: f.title_fa }));
    case 'classes': return m.classes.filter((c) => c.status !== 'retired' && c.key !== row.key).map((c) => ({ v: c.key, t: c.title_fa }));
    case 'retention': return (m.schema?.retention ?? []).filter((r) => r.status !== 'retired').map((r) => ({ v: r.ref, t: r.title_fa }));
    case 'link_kinds': return (m.schema?.link_kinds ?? []).filter((k) => k.status !== 'retired').map((k) => ({ v: k.key, t: k.title_fa }));
    case 'party_kinds': return (m.schema?.party_kinds ?? []).filter((k) => k.status !== 'retired').map((k) => ({ v: k.key, t: k.title_fa }));
    case 'events': return (v?.events ?? []).map((k) => ({ v: k, t: EVENT_FA[k] ?? k }));
    case 'actions': return (v?.actions ?? []).map((k) => ({ v: k, t: ACTION_FA[k] ?? k }));
    case 'ops': return (v?.ops ?? []).map((k) => ({ v: k, t: OP_FA[k] ?? k }));
    case 'ref_kinds': return (v?.ref_kinds ?? []).map((k) => ({ v: k, t: REF_KIND_FA[k] ?? k }));
    case 'currencies': return (v?.currencies ?? []).map((k) => ({ v: k, t: k }));
    case 'mimes': return (v?.mimes ?? []).map((k) => ({ v: k, t: k.replace('application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'docx').replace(/^application\//, '').replace('message/rfc822', 'eml') }));
    case 'companies': return (companies ?? []).map((c) => ({ v: c.code, t: c.name_fa ?? c.code }));
    case 'then': return [{ v: 'review', t: THEN_FA.review! }, { v: 'dispose_card', t: THEN_FA.dispose_card! }];
    case 'channels': return Object.entries(CHANNEL_FA).map(([k, t]) => ({ v: k, t }));
    case 'date_fields': {
      // The date fields of this row: its own (a class) or its class's (a reminder rule).
      const fs = Array.isArray(row.fields) ? (row.fields as Row[]) : m.cls(String(row.class ?? ''))?.fields ?? [];
      return (fs as Row[]).filter((f) => (f.type === 'date' || f.type === 'date_range') && f.status !== 'retired' && f.key).map((f) => ({ v: String(f.key), t: String(f.title_fa || f.key) }));
    }
    case 'ref_fields': return ((row.fields as Row[]) ?? []).filter((f) => f.type === 'ref' && f.status !== 'retired').map((f) => ({ v: String(f.key), t: String(f.title_fa || f.key) }));
    case 'icons': return ICONS.map((k) => ({ v: k, t: k }));
    default: return [];
  }
}
const ROLES = ['archivist', 'legal_counsel', 'ceo', 'manager', 'advisor', 'overseer', 'revenue_analyst', 'support_lead'];
const roleFa = (r: string) => (r === '*' ? 'هر نقش ایجنت' : ROLE_FA[r] ?? r);
export const subjectFa = (s: { kind: string; ref: string }) => (s.kind === 'role' ? roleFa(s.ref) : s.ref);
const scopeFa = (s: string, companies?: Company[]) => (s === 'own' ? 'شرکت خودش' : s === 'all' ? 'همه‌ی دامنه‌ها' : companies?.find((c) => c.code === s)?.name_fa ?? s);
const keepFa = (k: unknown) => (k === 'permanent' ? 'دائمی' : k && typeof k === 'object' ? [(k as { years?: number }).years ? `${(k as { years: number }).years} سال` : '', (k as { months?: number }).months ? `${(k as { months: number }).months} ماه` : ''].filter(Boolean).join(' و ') || '—' : '—');
export const triggerFa = (t: unknown, m: ArchiveMaps) => {
  const s = String(t ?? '');
  if (s === 'filed') return 'ثبت سند';
  if (s === 'case_closed') return 'بسته شدن پرونده';
  if (s === 'superseded') return 'جایگزین شدن';
  if (s.startsWith('field:')) { const k = s.slice(6); return `فیلد «${m.classes.flatMap((c) => c.fields).find((f) => f.key === k)?.title_fa ?? k}»`; }
  return s;
};

// ================================================================== reading a value --
/** One attribute as words, for row summaries and the cartable diff. */
export function AttrValue({ a, v, m, row }: { a: Attr; v: unknown; m: ArchiveMaps; row: Row }) {
  const { data: companies } = useCompanies();
  if (v == null || v === '' || (Array.isArray(v) && !v.length)) return <span className="text-muted">—</span>;
  const label = (x: unknown) => options(a.source, m, row, companies).find((o) => o.v === x)?.t ?? String(x);
  switch (a.kind) {
    case 'bool': return <span>{v ? 'بله' : 'نه'}</span>;
    case 'int': case 'color': return <span className="fig">{String(v)}</span>;
    case 'select': return <span>{label(v)}</span>;
    case 'multi': return <span>{(v as unknown[]).map(label).join('، ')}</span>;
    case 'scopes': return <span>{v === 'all' ? 'همه‌ی دامنه‌ها' : (v as string[]).map((s) => scopeFa(s, companies)).join('، ')}</span>;
    case 'keep': return <span>{keepFa(v)}</span>;
    case 'trigger': return <span>{triggerFa(v, m)}</span>;
    case 'lead_days': return <span><span className="fig">{(v as number[]).join('، ')}</span> روز پیش</span>;
    case 'to': return <span>{reminderToFa(v as never)}</span>;
    case 'subject': return <span>{subjectFa(v as { kind: string; ref: string })}</span>;
    case 'grants': return <span>{(v as Array<{ scope: string; level: string }>).map((g) => `${scopeFa(g.scope, companies)}: ${m.level(g.level)?.title_fa ?? g.level}`).join('؛ ')}</span>;
    case 'when': return <WhenFa w={v as Row} m={m} />;
    case 'do': return <span className="flex flex-col gap-0.5">{(v as Row[]).map((s, i) => <StepFa key={i} s={s} m={m} />)}</span>;
    case 'list': return <span>{(v as Array<{ field: string; link_kind: string }>).map((x) => `${x.field} → ${m.linkKind(x.link_kind)?.title_fa ?? x.link_kind}`).join('، ')}</span>;
    case 'fields': return <span>{(v as Row[]).length} فیلد</span>;
    case 'json': return <span dir="ltr" className="fig break-all">{JSON.stringify(v)}</span>;
    default: return <span className="break-words">{String(v)}</span>;
  }
}
function WhenFa({ w, m }: { w: Row; m: ArchiveMaps }) {
  const { data: companies } = useCompanies();
  const parts: string[] = [];
  if (w.class) parts.push(`نوع «${m.cls(String(w.class))?.title_fa ?? String(w.class)}»`);
  if (w.scope) parts.push(`دامنه‌ی ${scopeFa(String(w.scope), companies)}`);
  if (w.level_min) parts.push(`سطح دست‌کم ${m.level(String(w.level_min))?.title_fa ?? String(w.level_min)}`);
  const f = w.field as { key?: string; op?: string; value?: unknown } | undefined;
  if (f?.key) parts.push(`«${m.cls(String(w.class ?? ''))?.fields.find((x) => x.key === f.key)?.title_fa ?? f.key}» ${OP_FA[f.op ?? ''] ?? f.op} ${String(f.value ?? '')}`);
  return <span>{parts.length ? parts.join(' و ') : 'هر سندی'}</span>;
}
function StepFa({ s, m }: { s: Row; m: ArchiveMaps }) {
  const a = (s.args ?? {}) as Row;
  const act = String(s.action);
  const what = act === 'notify' ? `اعلان «${NOTIFY_LEVEL_FA[String(a.level)] ?? a.level}» به ${a.to === 'owner' ? 'تو' : roleFa(String(a.to ?? ''))}: ${String(a.text_fa ?? '')}`
    : act === 'work_item' ? `کار برای ${roleFa(String(a.role ?? ''))}: ${String(a.title_fa ?? '')}`
      : act === 'move_to_folder' ? `به پوشه‌ی ${m.folder(String(a.folder))?.title_fa ?? String(a.folder)}`
        : act === 'raise_level' ? `سطح دست‌کم ${m.level(String(a.level))?.title_fa ?? String(a.level)}`
          : act === 'add_reminder' ? `یادآور روی ${String(a.field ?? '')}، ${((a.lead_days as number[]) ?? []).join('، ')} روز پیش`
            : act === 'link' ? `پیوند ${m.linkKind(String(a.kind))?.title_fa ?? String(a.kind)} به ${String((a.to as Row | undefined)?.ref ?? '')}`
              : `${act} ${JSON.stringify(a)}`;
  return <span>{ACTION_FA[act] ? `${ACTION_FA[act]}: ` : ''}{what}</span>;
}

// ================================================================== inputs --
const fieldCls = (err?: string | null, ...xs: Array<string | false | null | undefined>) => field(err && bad, ...xs);
const toInts = (s: string) => s.replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))).split(/[\s,،]+/).filter(Boolean).map(Number).filter((n) => Number.isInteger(n));
/** Errors under a prefix (`fields.amount.type` → under `fields`), for the editors of nested parts. */
export const under = (errors: Record<string, string>, prefix: string) => Object.fromEntries(Object.entries(errors).filter(([k]) => k === prefix || k.startsWith(`${prefix}.`)).map(([k, v]) => [k.slice(prefix.length + 1), v]));

function Sel({ value, onChange, opts, label, nullable, err, disabled, className }: { value: unknown; onChange: (v: string | null) => void; opts: Opt[]; label: string; nullable?: boolean; err?: string | null; disabled?: boolean; className?: string }) {
  const known = opts.some((o) => o.v === value);
  return (
    <select aria-label={label} disabled={disabled} value={value == null ? '' : String(value)} onChange={(e) => onChange(e.target.value || null)} className={fieldCls(err, className, disabled && 'opacity-70')}>
      {nullable || value == null || value === '' ? <option value="">{nullable ? '— هیچ —' : '— انتخاب کن —'}</option> : null}
      {opts.map((o) => <option key={o.v} value={o.v}>{o.t}</option>)}
      {value && !known ? <option value={String(value)}>{String(value)}</option> : null}
    </select>
  );
}
function Chips({ value, onChange, opts, ltr }: { value: string[]; onChange: (v: string[]) => void; opts: Opt[]; ltr?: boolean }) {
  return (
    <span className="flex flex-wrap gap-1.5">
      {opts.map((o) => <FilterChip key={o.v} selected={value.includes(o.v)} onClick={() => onChange(value.includes(o.v) ? value.filter((x) => x !== o.v) : [...value, o.v])}>{ltr ? <span className="fig">{o.t}</span> : o.t}</FilterChip>)}
      {!opts.length ? <span className="text-[12px] text-muted">گزینه‌ای نیست.</span> : null}
    </span>
  );
}

/** The field list of a class or a party kind: the type only from the closed list, a saved field never deleted (only retired),
 *  and a saved field's key and type fixed. */
function FieldsEditor({ value, onChange, saved, errors }: { value: Row[]; onChange: (v: Row[]) => void; saved: Set<string>; errors: Record<string, string> }) {
  const m = useArchive();
  const types = m.schema?.field_types ?? [];
  const set = (i: number, p: Row) => onChange(value.map((f, j) => (j === i ? { ...f, ...p } : f)));
  return (
    <div className="flex flex-col gap-2">
      {value.map((f, i) => {
        const k = String(f.key || i);
        const e = under(errors, k);
        const isSaved = saved.has(String(f.key));
        const retired = f.status === 'retired';
        const t = String(f.type);
        return (
          <div key={i} className={cx('flex min-w-0 flex-col gap-2 rounded-[12px] border border-div p-3', retired && 'opacity-60')}>
            <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)]">
              <label className="flex min-w-0 flex-col gap-1 text-[11px] text-muted">عنوان
                <input aria-label={`فیلد ${i + 1}: عنوان`} value={String(f.title_fa ?? '')} onChange={(ev) => set(i, { title_fa: ev.target.value })} className={fieldCls(e.title_fa, 'h-9 text-[13px]')} />
              </label>
              <label className="flex min-w-0 flex-col gap-1 text-[11px] text-muted">کلید
                <input aria-label={`فیلد ${i + 1}: کلید`} dir="ltr" disabled={isSaved} value={String(f.key ?? '')} onChange={(ev) => set(i, { key: ev.target.value.trim() })} placeholder="snake_case" className={fieldCls(e.key, 'fig h-9 text-left text-[13px]', isSaved && 'opacity-70')} />
              </label>
              <label className="flex min-w-0 flex-col gap-1 text-[11px] text-muted">نوع
                <Sel label={`فیلد ${i + 1}: نوع`} value={f.type} disabled={isSaved} onChange={(v) => set(i, { type: v ?? 'text' })} opts={types.map((x) => ({ v: x.key, t: x.title_fa }))} err={e.type} className="h-9 text-[13px]" />
              </label>
            </div>
            {t === 'enum' || t === 'multi_enum' ? (
              <OptionsEditor value={(f.options as Array<{ key: string; title_fa: string }>) ?? []} onChange={(o) => set(i, { options: o })} err={e.options} />
            ) : null}
            {t === 'ref' ? <span className="flex flex-col gap-1 text-[11px] text-muted">به چه چیزی<Chips value={(f.ref_kinds as string[]) ?? []} onChange={(v) => set(i, { ref_kinds: v })} opts={options('ref_kinds', m, {}, undefined)} />{e.ref_kinds ? <span className="text-neg">{e.ref_kinds}</span> : null}</span> : null}
            {t === 'money' ? <label className="flex w-40 flex-col gap-1 text-[11px] text-muted">واحد پول<Sel label={`فیلد ${i + 1}: واحد`} value={f.currency} onChange={(v) => set(i, { currency: v })} opts={options('currencies', m, {}, undefined)} err={e.currency} className="fig h-9 text-[13px]" /></label> : null}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[12px] text-sec">
              {([['required', 'لازم'], ['searchable', 'در جستجو'], ['sensitive', 'حساس (پنهان زیر محرمانه)']] as const).map(([key, fa]) => (
                <span key={key} className="flex items-center gap-2"><Switch label={`فیلد ${i + 1}: ${fa}`} checked={!!f[key]} disabled={retired && key === 'required'} onChange={(v) => set(i, { [key]: v })} />{fa}</span>
              ))}
              <span className="flex-1" />
              {isSaved ? (
                <Button size="sm" variant="ghost" icon={retired ? 'refresh' : 'pause'} onClick={() => set(i, { status: retired ? 'active' : 'retired', required: false })}>{retired ? 'برگردان' : 'بازنشسته کن'}</Button>
              ) : <Button size="sm" variant="ghost" icon="close" onClick={() => onChange(value.filter((_, j) => j !== i))}>بردار</Button>}
            </div>
            <input aria-label={`فیلد ${i + 1}: راهنما`} value={String(f.help_fa ?? '')} onChange={(ev) => set(i, { help_fa: ev.target.value || null })} placeholder="راهنما (اختیاری)" className={field('h-9 text-[12px]')} />
            {Object.entries(e).filter(([x]) => !['title_fa', 'key', 'type', 'options', 'ref_kinds', 'currency'].includes(x)).map(([x, msg]) => <span key={x} className="text-[12px] text-neg">{msg}</span>)}
          </div>
        );
      })}
      {Object.entries(errors).filter(([k]) => !value.some((f, i) => k.startsWith(`${String(f.key || i)}.`) || k === String(f.key))).map(([k, msg]) => <span key={k} className="text-[12px] text-neg">{msg}</span>)}
      {Object.entries(errors).filter(([k]) => value.some((f) => k === String(f.key))).map(([k, msg]) => <span key={k} className="text-[12px] text-neg">{msg}</span>)}
      <Button size="sm" variant="secondary" icon="add" className="self-start" onClick={() => onChange([...value, { key: '', title_fa: '', type: 'text', required: false, searchable: false, sensitive: false, help_fa: null, status: 'active' }])}>فیلد تازه</Button>
    </div>
  );
}
function OptionsEditor({ value, onChange, err }: { value: Array<{ key: string; title_fa: string }>; onChange: (v: Array<{ key: string; title_fa: string }>) => void; err?: string | null }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-[10px] bg-tile p-2">
      <span className="text-[11px] text-muted">گزینه‌ها</span>
      {value.map((o, j) => (
        <div key={j} className="flex min-w-0 gap-1.5">
          <input aria-label={`گزینه ${j + 1}: عنوان`} value={o.title_fa} onChange={(e) => onChange(value.map((x, k) => (k === j ? { ...x, title_fa: e.target.value } : x)))} className={field('h-8 flex-1 text-[12px]')} />
          <input aria-label={`گزینه ${j + 1}: کلید`} dir="ltr" value={o.key} onChange={(e) => onChange(value.map((x, k) => (k === j ? { ...x, key: e.target.value.trim() } : x)))} className={field('fig h-8 w-28 flex-none text-left text-[12px]')} />
          <button type="button" aria-label="برداشتن گزینه" onClick={() => onChange(value.filter((_, k) => k !== j))} className="flex-none text-muted hover:text-neg"><Icon name="close" size={14} /></button>
        </div>
      ))}
      {err ? <span className="text-[12px] text-neg">{err}</span> : null}
      <button type="button" onClick={() => onChange([...value, { key: '', title_fa: '' }])} className="self-start text-[12px] font-semibold text-gold-ink hover:underline">+ گزینه</button>
    </div>
  );
}

/** «when» of an automation: class, scope, a minimum level, and one field condition; each optional. */
function WhenEditor({ value, onChange, errors }: { value: Row; onChange: (v: Row) => void; errors: Record<string, string> }) {
  const m = useArchive();
  const { data: companies } = useCompanies();
  const f = (value.field ?? null) as { key: string; op: string; value: unknown } | null;
  const set = (p: Row) => onChange(Object.fromEntries(Object.entries({ ...value, ...p }).filter(([, v]) => v != null && v !== '')));
  const fields = m.cls(String(value.class ?? ''))?.fields ?? [];
  return (
    <div className="grid min-w-0 grid-cols-1 gap-2 rounded-[12px] bg-tile p-3 sm:grid-cols-3">
      <label className="flex min-w-0 flex-col gap-1 text-[11px] text-muted">نوع سند<Sel label="شرط: نوع سند" nullable value={value.class} onChange={(v) => set({ class: v, field: v === value.class ? value.field : null })} opts={options('classes', m, {}, companies)} err={errors.class} className="h-9 text-[13px]" /></label>
      <label className="flex min-w-0 flex-col gap-1 text-[11px] text-muted">دامنه<Sel label="شرط: دامنه" nullable value={value.scope} onChange={(v) => set({ scope: v })} opts={options('companies', m, {}, companies)} err={errors.scope} className="h-9 text-[13px]" /></label>
      <label className="flex min-w-0 flex-col gap-1 text-[11px] text-muted">سطح دست‌کم<Sel label="شرط: سطح دست‌کم" nullable value={value.level_min} onChange={(v) => set({ level_min: v })} opts={options('levels', m, {}, companies)} err={errors.level_min} className="h-9 text-[13px]" /></label>
      <div className="flex min-w-0 flex-wrap items-end gap-1.5 sm:col-span-3">
        <label className="flex min-w-[8rem] flex-1 flex-col gap-1 text-[11px] text-muted">فیلد
          {fields.length ? <Sel label="شرط: فیلد" nullable value={f?.key} onChange={(v) => set({ field: v ? { key: v, op: f?.op ?? 'eq', value: f?.value ?? '' } : null })} opts={fields.filter((x) => x.status !== 'retired').map((x) => ({ v: x.key, t: x.title_fa }))} className="h-9 text-[13px]" />
            : <input aria-label="شرط: کلید فیلد" dir="ltr" value={f?.key ?? ''} onChange={(e) => set({ field: e.target.value.trim() ? { key: e.target.value.trim(), op: f?.op ?? 'eq', value: f?.value ?? '' } : null })} placeholder="field_key" className={field('fig h-9 text-left text-[13px]')} />}
        </label>
        {f ? (
          <>
            <label className="flex w-32 flex-col gap-1 text-[11px] text-muted">چطور<Sel label="شرط: عملگر" value={f.op} onChange={(v) => set({ field: { ...f, op: v ?? 'eq' } })} opts={options('ops', m, {}, companies)} className="h-9 text-[13px]" /></label>
            <label className="flex min-w-[6rem] flex-1 flex-col gap-1 text-[11px] text-muted">مقدار<input aria-label="شرط: مقدار" dir="auto" value={String(f.value ?? '')} onChange={(e) => set({ field: { ...f, value: /^-?\d+(\.\d+)?$/.test(e.target.value.trim()) ? Number(e.target.value.trim()) : e.target.value } })} className={field('h-9 text-[13px]', typeof f.value === 'number' && 'fig text-left')} /></label>
          </>
        ) : null}
      </div>
      {errors.field ? <span className="text-[12px] text-neg sm:col-span-3">{errors.field}</span> : null}
    </div>
  );
}

/** The arguments each action of the closed list takes (§23.12); an action without a row here gets a JSON box. */
type ArgSpec = { key: string; fa: string; kind: 'text' | 'select' | 'lead_days' | 'target'; source?: Source | 'recipients' | 'roles' | 'notify_levels' };
const ACTION_ARGS: Record<string, ArgSpec[]> = {
  notify: [{ key: 'to', fa: 'به', kind: 'select', source: 'recipients' }, { key: 'level', fa: 'سطح اعلان', kind: 'select', source: 'notify_levels' }, { key: 'text_fa', fa: 'متن', kind: 'text' }],
  work_item: [{ key: 'role', fa: 'نقش', kind: 'select', source: 'roles' }, { key: 'title_fa', fa: 'عنوان کار', kind: 'text' }],
  link: [{ key: 'kind', fa: 'نوع پیوند', kind: 'select', source: 'link_kinds' }, { key: 'to', fa: 'به', kind: 'target' }],
  move_to_folder: [{ key: 'folder', fa: 'پوشه', kind: 'select', source: 'folders' }],
  raise_level: [{ key: 'level', fa: 'سطح', kind: 'select', source: 'levels' }],
  add_reminder: [{ key: 'field', fa: 'فیلد تاریخ', kind: 'text' }, { key: 'lead_days', fa: 'چند روز پیش', kind: 'lead_days' }],
};
function argOptions(src: ArgSpec['source'], m: ArchiveMaps): Opt[] {
  if (src === 'recipients') return [{ v: 'owner', t: 'تو' }, ...ROLES.map((r) => ({ v: r, t: roleFa(r) }))];
  if (src === 'roles') return ROLES.map((r) => ({ v: r, t: roleFa(r) }));
  // Never `urgent` (§6): only the fixity alarm is.
  if (src === 'notify_levels') return Object.entries(NOTIFY_LEVEL_FA).map(([v, t]) => ({ v, t }));
  return options(src as Source, m, {}, undefined);
}
function DoEditor({ value, onChange, errors }: { value: Row[]; onChange: (v: Row[]) => void; errors: Record<string, string> }) {
  const m = useArchive();
  const set = (i: number, p: Row) => onChange(value.map((s, j) => (j === i ? { ...s, ...p } : s)));
  const setArg = (i: number, k: string, v: unknown) => set(i, { args: { ...((value[i]?.args as Row) ?? {}), [k]: v } });
  return (
    <div className="flex flex-col gap-2">
      {value.map((s, i) => {
        const act = String(s.action ?? '');
        const spec = ACTION_ARGS[act];
        const a = (s.args ?? {}) as Row;
        const e = under(errors, String(i));
        return (
          <div key={i} className="flex min-w-0 flex-col gap-2 rounded-[12px] bg-tile p-3">
            <div className="flex min-w-0 items-end gap-2">
              <label className="flex min-w-0 flex-1 flex-col gap-1 text-[11px] text-muted">اقدام {i + 1}
                <Sel label={`اقدام ${i + 1}`} value={act} onChange={(v) => set(i, { action: v, args: {} })} opts={options('actions', m, {}, undefined)} err={e.action} className="h-9 text-[13px]" />
              </label>
              <button type="button" aria-label={`برداشتن اقدام ${i + 1}`} onClick={() => onChange(value.filter((_, j) => j !== i))} className="mb-2 flex-none text-muted hover:text-neg"><Icon name="close" size={16} /></button>
            </div>
            {spec ? (
              <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2">
                {spec.map((x) => (
                  <label key={x.key} className={cx('flex min-w-0 flex-col gap-1 text-[11px] text-muted', x.kind === 'text' && 'sm:col-span-2')}>{x.fa}
                    {x.kind === 'select' ? <Sel label={`اقدام ${i + 1}: ${x.fa}`} value={a[x.key]} onChange={(v) => setArg(i, x.key, v)} opts={argOptions(x.source, m)} err={e[x.key]} className="h-9 text-[13px]" />
                      : x.kind === 'lead_days' ? <input aria-label={`اقدام ${i + 1}: ${x.fa}`} dir="ltr" defaultValue={((a[x.key] as number[]) ?? []).join(', ')} onChange={(ev) => setArg(i, x.key, toInts(ev.target.value))} placeholder="30, 7" className={field('fig h-9 text-left text-[13px]')} />
                        : x.kind === 'target' ? (
                          <span className="flex gap-1.5">
                            <Sel label={`اقدام ${i + 1}: مقصد از چه نوع`} value={(a.to as Row | undefined)?.kind ?? 'record'} onChange={(v) => setArg(i, 'to', { kind: v ?? 'record', ref: (a.to as Row | undefined)?.ref ?? '' })} opts={options('ref_kinds', m, {}, undefined)} className="h-9 w-auto text-[13px]" />
                            <input aria-label={`اقدام ${i + 1}: شناسه‌ی مقصد`} dir="ltr" value={String((a.to as Row | undefined)?.ref ?? '')} onChange={(ev) => setArg(i, 'to', { kind: (a.to as Row | undefined)?.kind ?? 'record', ref: ev.target.value.trim() })} className={field('fig h-9 text-left text-[13px]')} />
                          </span>
                        ) : <input aria-label={`اقدام ${i + 1}: ${x.fa}`} value={String(a[x.key] ?? '')} onChange={(ev) => setArg(i, x.key, ev.target.value)} className={field('h-9 text-[13px]', e[x.key] && bad)} />}
                  </label>
                ))}
              </div>
            ) : act ? <JsonBox label={`اقدام ${i + 1}: ورودی‌ها`} value={a} onChange={(v) => set(i, { args: v ?? {} })} /> : null}
            {Object.entries(e).filter(([k]) => k !== 'action' && !spec?.some((x) => x.key === k)).map(([k, msg]) => <span key={k} className="text-[12px] text-neg">{msg}</span>)}
          </div>
        );
      })}
      {errors[''] ? <span className="text-[12px] text-neg">{errors['']}</span> : null}
      <Button size="sm" variant="secondary" icon="add" className="self-start" onClick={() => onChange([...value, { action: m.vocab?.actions[0] ?? 'notify', args: {} }])}>اقدام تازه</Button>
    </div>
  );
}
function JsonBox({ value, onChange, label }: { value: unknown; onChange: (v: Row | null) => void; label: string }) {
  const [text, setText] = useState(() => JSON.stringify(value ?? null, null, 2));
  const [badJson, setBad] = useState(false);
  return (
    <span className="flex flex-col gap-1">
      <textarea aria-label={label} dir="ltr" rows={4} value={text} onChange={(e) => { setText(e.target.value); try { onChange(JSON.parse(e.target.value) as Row); setBad(false); } catch { setBad(true); } }} className={fieldArea('fig text-left text-[12px]', badJson && bad)} />
      {badJson ? <span className="text-[11px] text-neg">JSON درست نیست.</span> : null}
    </span>
  );
}

function GrantsEditor({ value, onChange, errors }: { value: Array<{ scope: string; level: string }>; onChange: (v: Array<{ scope: string; level: string }>) => void; errors: Record<string, string> }) {
  const m = useArchive();
  const { data: companies } = useCompanies();
  const scopes: Opt[] = [{ v: 'own', t: 'شرکت خودش' }, { v: 'all', t: 'همه‌ی دامنه‌ها' }, ...options('companies', m, {}, companies)];
  return (
    <div className="flex flex-col gap-1.5">
      {value.map((g, i) => (
        <div key={i} className="flex min-w-0 flex-col gap-1">
          <div className="flex min-w-0 items-center gap-1.5">
            <Sel label={`مجوز ${i + 1}: دامنه`} value={g.scope} onChange={(v) => onChange(value.map((x, j) => (j === i ? { ...x, scope: v ?? 'own' } : x)))} opts={scopes} err={errors[`${i}.scope`]} className="h-9 flex-1 text-[13px]" />
            <Sel label={`مجوز ${i + 1}: سطح`} value={g.level} onChange={(v) => onChange(value.map((x, j) => (j === i ? { ...x, level: v ?? '' } : x)))} opts={options('levels', m, {}, companies)} err={errors[`${i}.level`]} className="h-9 flex-1 text-[13px]" />
            <button type="button" aria-label={`برداشتن مجوز ${i + 1}`} onClick={() => onChange(value.filter((_, j) => j !== i))} className="flex-none text-muted hover:text-neg"><Icon name="close" size={16} /></button>
          </div>
          {errors[`${i}.scope`] || errors[`${i}.level`] ? <span className="text-[12px] text-neg">{errors[`${i}.level`] ?? errors[`${i}.scope`]}</span> : null}
        </div>
      ))}
      <Button size="sm" variant="secondary" icon="add" className="self-start" onClick={() => onChange([...value, { scope: 'own', level: m.levels[1]?.key ?? m.levels[0]?.key ?? '' }])}>مجوز</Button>
    </div>
  );
}

/** One attribute's input, by its kind and source. */
function AttrInput({ a, row, set, errors, saved }: { a: Attr; row: Row; set: (p: Row) => void; errors: Record<string, string>; saved: boolean }) {
  const m = useArchive();
  const { data: companies } = useCompanies();
  const v = row[a.key];
  const err = errors[a.key] ?? null;
  const lock = a.locked?.(row, saved) ?? null;
  const opts = options(a.source, m, row, companies);
  let body: ReactNode;
  switch (a.kind) {
    case 'text': body = <input aria-label={a.fa} value={String(v ?? '')} onChange={(e) => set({ [a.key]: e.target.value })} disabled={!!lock} className={fieldCls(err)} />; break;
    case 'int': body = <input aria-label={a.fa} dir="ltr" inputMode="numeric" disabled={!!lock} value={v == null ? '' : String(v)} onChange={(e) => set({ [a.key]: e.target.value === '' ? null : Number(e.target.value.replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))) })} className={fieldCls(err, 'fig w-32 text-left', lock && 'opacity-70')} />; break;
    case 'bool': body = <span className="flex h-10 items-center"><Switch label={a.fa} checked={!!v} onChange={(x) => set({ [a.key]: x })} /></span>; break;
    case 'select': body = <Sel label={a.fa} value={v} onChange={(x) => set({ [a.key]: x })} opts={opts} nullable={a.nullable} err={err} disabled={!!lock} className={a.source === 'icons' || a.source === 'mimes' ? 'fig' : undefined} />; break;
    case 'multi': body = <Chips value={(v as string[]) ?? []} onChange={(x) => set({ [a.key]: x })} opts={opts} ltr={a.source === 'mimes'} />; break;
    case 'color': body = (
      <span role="radiogroup" aria-label={a.fa} className="flex flex-wrap gap-1.5">
        {[0, 1, 2, 3, 4, 5].map((i) => <button key={i} type="button" role="radio" aria-checked={v === i} aria-label={`رنگ ${i}`} onClick={() => set({ [a.key]: i })} className={cx('rounded-full p-0.5', v === i ? 'ring-2 ring-[var(--hq-gold-ink)]' : '')}><Pill tone={levelTone({ color_index: i })} dot><span className="fig">{i}</span></Pill></button>)}
      </span>
    ); break;
    case 'scopes': {
      const all = v === 'all';
      body = (
        <span className="flex flex-wrap gap-1.5">
          <FilterChip selected={all} onClick={() => set({ [a.key]: all ? [] : 'all' })}>همه‌ی دامنه‌ها</FilterChip>
          {!all ? (companies ?? []).map((c) => { const xs = Array.isArray(v) ? (v as string[]) : []; return <FilterChip key={c.code} selected={xs.includes(c.code)} onClick={() => set({ [a.key]: xs.includes(c.code) ? xs.filter((x) => x !== c.code) : [...xs, c.code] })}>{c.name_fa}</FilterChip>; }) : null}
        </span>
      );
      break;
    }
    case 'keep': {
      const perm = v === 'permanent';
      const k = (perm || !v ? {} : v) as { years?: number; months?: number };
      body = (
        <span className="flex flex-wrap items-center gap-2">
          <Segmented<'term' | 'permanent'> label={a.fa} value={perm ? 'permanent' : 'term'} onChange={(x) => set({ [a.key]: x === 'permanent' ? 'permanent' : { years: 5 } })} options={[{ value: 'term', label: 'مدت‌دار' }, { value: 'permanent', label: 'دائمی' }]} />
          {!perm ? (
            <>
              <input aria-label="سال" dir="ltr" inputMode="numeric" value={k.years ?? ''} onChange={(e) => set({ [a.key]: { ...k, years: e.target.value ? Number(e.target.value) : undefined } })} className={fieldCls(err, 'fig w-20 text-left')} /><span className="text-[12px] text-muted">سال</span>
              <input aria-label="ماه" dir="ltr" inputMode="numeric" value={k.months ?? ''} onChange={(e) => set({ [a.key]: { ...k, months: e.target.value ? Number(e.target.value) : undefined } })} className={fieldCls(err, 'fig w-20 text-left')} /><span className="text-[12px] text-muted">ماه</span>
            </>
          ) : null}
        </span>
      );
      break;
    }
    case 'trigger': {
      const dateKeys = [...new Map(m.classes.flatMap((c) => c.fields).filter((f) => f.type === 'date' || f.type === 'date_range').map((f) => [f.key, f.title_fa])).entries()];
      body = <Sel label={a.fa} value={v} onChange={(x) => set({ [a.key]: x })} err={err} opts={[{ v: 'filed', t: 'ثبت سند' }, { v: 'case_closed', t: 'بسته شدن پرونده' }, { v: 'superseded', t: 'جایگزین شدن' }, ...dateKeys.map(([k, t]) => ({ v: `field:${k}`, t: `فیلد «${t}» (${k})` }))]} />;
      break;
    }
    case 'lead_days': body = <input aria-label={a.fa} dir="ltr" defaultValue={((v as number[]) ?? []).join(', ')} onChange={(e) => set({ [a.key]: toInts(e.target.value) })} placeholder="60, 30, 7" className={fieldCls(err, 'fig text-left')} />; break;
    case 'to': {
      const kind = v === 'owner' ? 'owner' : v && typeof v === 'object' && 'company_ceo' in v ? 'ceo' : 'role';
      body = (
        <span className="flex flex-wrap items-center gap-1.5">
          <Sel label={a.fa} value={kind} onChange={(x) => set({ [a.key]: x === 'owner' ? 'owner' : x === 'ceo' ? { company_ceo: true } : { role: 'archivist' } })} opts={[{ v: 'owner', t: 'تو' }, { v: 'ceo', t: 'مدیرعامل همان شرکت' }, { v: 'role', t: 'یک نقش' }]} err={err} className="w-auto" />
          {kind === 'role' ? <Sel label={`${a.fa}: نقش`} value={(v as { role?: string })?.role} onChange={(x) => set({ [a.key]: { role: x ?? 'archivist' } })} opts={ROLES.map((r) => ({ v: r, t: roleFa(r) }))} className="w-auto" /> : null}
        </span>
      );
      break;
    }
    case 'subject': {
      const s = (v ?? { kind: 'role', ref: '' }) as { kind: string; ref: string };
      body = (
        <span className="flex flex-wrap items-center gap-1.5">
          <Sel label={`${a.fa}: نوع`} disabled={!!lock} value={s.kind} onChange={(x) => set({ [a.key]: { kind: x ?? 'role', ref: '' } })} opts={[{ v: 'role', t: 'نقش' }, { v: 'employee', t: 'کارمند' }]} className="w-auto" />
          {s.kind === 'role' ? <Sel label={a.fa} disabled={!!lock} value={s.ref} onChange={(x) => set({ [a.key]: { ...s, ref: x ?? '' } })} opts={['*', ...ROLES].map((r) => ({ v: r, t: roleFa(r) }))} err={errors.key} className="w-auto" />
            : <input aria-label={`${a.fa}: کد کارمند`} dir="ltr" disabled={!!lock} value={s.ref} onChange={(e) => set({ [a.key]: { ...s, ref: e.target.value.trim() } })} placeholder="FX-TECH-MGR" className={fieldCls(errors.key, 'fig w-48 text-left')} />}
        </span>
      );
      break;
    }
    case 'grants': body = <GrantsEditor value={(v as Array<{ scope: string; level: string }>) ?? []} onChange={(x) => set({ [a.key]: x })} errors={under(errors, a.key)} />; break;
    case 'fields': body = <FieldsEditor value={(v as Row[]) ?? []} onChange={(x) => set({ [a.key]: x })} saved={new Set(saved ? ((row.__saved_fields as string[]) ?? []) : [])} errors={under(errors, a.key)} />; break;
    case 'when': body = <WhenEditor value={(v as Row) ?? {}} onChange={(x) => set({ [a.key]: x })} errors={under(errors, a.key)} />; break;
    case 'do': body = <DoEditor value={(v as Row[]) ?? []} onChange={(x) => set({ [a.key]: x })} errors={{ ...under(errors, a.key), ...(errors[a.key] ? { '': errors[a.key] } : {}) }} />; break;
    case 'list': {
      const xs = (v as Array<{ field: string; link_kind: string }>) ?? [];
      body = (
        <span className="flex flex-col gap-1.5">
          {xs.map((x, i) => (
            <span key={i} className="flex items-center gap-1.5">
              <Sel label={`پیوند خودکار ${i + 1}: فیلد`} value={x.field} onChange={(f) => set({ [a.key]: xs.map((y, j) => (j === i ? { ...y, field: f ?? '' } : y)) })} opts={opts} className="h-9 flex-1 text-[13px]" />
              <Sel label={`پیوند خودکار ${i + 1}: نوع`} value={x.link_kind} onChange={(k) => set({ [a.key]: xs.map((y, j) => (j === i ? { ...y, link_kind: k ?? '' } : y)) })} opts={options('link_kinds', m, row, companies)} className="h-9 flex-1 text-[13px]" />
              <button type="button" aria-label={`برداشتن پیوند خودکار ${i + 1}`} onClick={() => set({ [a.key]: xs.filter((_, j) => j !== i) })} className="text-muted hover:text-neg"><Icon name="close" size={14} /></button>
            </span>
          ))}
          {opts.length ? <button type="button" onClick={() => set({ [a.key]: [...xs, { field: opts[0]!.v, link_kind: m.schema?.link_kinds[0]?.key ?? 'about' }] })} className="self-start text-[12px] font-semibold text-gold-ink hover:underline">+ پیوند خودکار</button> : <span className="text-[12px] text-muted">فیلد ارجاعی ندارد.</span>}
        </span>
      );
      break;
    }
    default: body = <JsonBox label={a.fa} value={v} onChange={(x) => set({ [a.key]: x })} />;
  }
  return (
    <div className={cx('flex min-w-0 flex-col gap-1.5', a.wide && 'sm:col-span-2')}>
      <span className="text-[12px] font-semibold text-sec">{a.fa}</span>
      {body}
      {err && !['grants', 'fields', 'when', 'do'].includes(a.kind) ? <span className="text-[12px] text-neg">{err}</span> : lock ? <span className="text-[11px] text-muted">{lock}</span> : a.help ? <span className="text-[11px] text-muted">{a.help}</span> : null}
    </div>
  );
}

// ================================================================== the save flow --
/** «N records, M missing a required field» in plain Persian (counts, so Persian digits). */
export function ImpactLine({ impact, part }: { impact: Impact; part: string }) {
  return (
    <p className="flex items-start gap-2 rounded-[12px] bg-tile p-3 text-[13px] leading-6 text-ink" aria-live="polite">
      <span className="mt-0.5 text-gold-ink"><Icon name="chart" size={16} /></span>
      <span>
        {impact.records
          ? `${impact.records} سند ${part === 'clearance' ? 'با این مجوز دیده میشود' : part === 'automations' ? 'زیر این خودکار میآید' : 'از این استفاده میکند'}`
          : `هیچ سندی ${part === 'clearance' ? 'با این مجوز دیده نمیشود' : part === 'automations' ? 'فعلاً زیر این خودکار نمیآید' : 'از این استفاده نمیکند'}`}
        {impact.missing_required ? <>؛ <b className="font-semibold text-warn">{impact.missing_required} سند فیلد اجباری را ندارد</b> و بایگان یک کار برای پر کردنشان میگیرد.</> : '.'}
        {part === 'classes' ? ' سندهای ثبت‌شده نسخه‌ی خودشان را نگه میدارند.' : ''}
      </span>
    </p>
  );
}

/** The editor of one row: every save is a dry run first (the impact, and the server's validation next to the inputs), then the
 *  passkey, then the PUT with If-Match. Retire, never delete. */
export function RowEditor({ part, ui, row: row0, onClose }: { part: string; ui: PartUI; row: Row | null; onClose: () => void }) {
  const m = useArchive();
  const act = useSchemaAction();
  const toast = useToast();
  const saved = !!row0;
  const [row, setRow] = useState<Row>(() => {
    const r = row0 ? structuredClone(row0) : ui.blank(m);
    // Which fields existed when the editor opened: their key and type stay fixed, they are retired, never removed.
    const fs = (r.fields ?? r.identifier_fields) as Row[] | undefined;
    if (row0 && fs) r.__saved_fields = fs.map((f) => String(f.key));
    return r;
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [checked, setChecked] = useState<{ body: string; out: SchemaResult } | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [retiring, setRetiring] = useState<SchemaResult | null>(null);
  const key = saved ? rowKey(part, ui, row0!) : ui.by === 'ref' ? 'new' : ui.by === 'subject' ? rowKey(part, ui, row) : String(row.key ?? '').trim();
  const version = saved ? Number(row0!.version ?? 0) || null : null;
  const body = bodyOf(ui, row);
  const text = JSON.stringify(body);
  const fresh = checked?.body === text;
  const set = (p: Row) => setRow((r) => ({ ...r, ...p }));
  const fail = (e: unknown) => {
    setFailure(e);
    if (e instanceof ApiError && e.fields) setErrors({ ...e.fields });
  };
  const preview = async () => {
    setErrors({}); setFailure(null); setChecked(null);
    try { setChecked({ body: text, out: await act.preview.mutateAsync({ part: part as SchemaPart, key, body, version }) }); } catch (e) { fail(e); }
  };
  const save = async () => {
    setFailure(null);
    try {
      const out = await act.save.mutateAsync({ part: part as SchemaPart, key, body: JSON.parse(text) as Row, version });
      toast({ tone: 'ok', text: <>ذخیره شد؛ نسخه‌ی <span className="fig">{out.version}</span> از «{String(row.title_fa ?? subjectFa((row.subject ?? { kind: '', ref: key }) as never))}».</> });
      onClose();
    } catch (e) { setChecked(null); fail(e); }
  };
  const askRetire = async () => {
    if (!saved || !version) return;
    setFailure(null);
    try { setRetiring(await act.retirePreview.mutateAsync({ part: part as SchemaPart, key, version })); } catch (e) { fail(e); }
  };
  const retire = async () => {
    if (!version) return;
    try { await act.retire.mutateAsync({ part: part as SchemaPart, key, version }); toast({ tone: 'info', text: 'بازنشسته شد؛ هیچ سندی که از آن استفاده میکند پاک نشد.' }); onClose(); } catch (e) { setRetiring(null); fail(e); }
  };
  const loose = Object.entries(errors).filter(([k]) => !ui.attrs.some((a) => k === a.key || k.startsWith(`${a.key}.`)) && k !== 'key');
  const isRetired = row0?.status === 'retired';
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={720}
      title={saved ? <span className="flex flex-wrap items-center gap-2">{String(row0!.title_fa ?? subjectFa((row0!.subject ?? { kind: '', ref: key }) as never))}<span className="fig text-[12px] font-normal text-muted">{key}{version ? ` · v${version}` : ''}</span></span> : `${ui.fa}: تازه`}
      description={ui.note}
      footer={
        <div className="flex flex-col gap-2">
          {checked && fresh ? <ImpactLine impact={checked.out.impact} part={part} /> : checked && !fresh ? <p className="text-[12px] text-warn">بعد از بررسی عوض شد؛ دوباره بررسی کن.</p> : null}
          <div className="flex flex-wrap items-center gap-2">
            {checked && fresh ? (
              <Button variant="primary" icon="lock" loading={act.save.isPending} onClick={save}>ذخیره با passkey</Button>
            ) : (
              <Button variant="primary" icon="search" disabled={isRetired || (!saved && ui.by === 'key' && !key)} loading={act.preview.isPending} onClick={preview}>بررسی اثر</Button>
            )}
            <Button variant="ghost" onClick={onClose}>انصراف</Button>
            <span className="flex-1" />
            {saved && ui.retire && !isRetired ? <Button variant="danger" size="sm" icon="pause" loading={act.retirePreview.isPending} onClick={askRetire}>بازنشسته کن</Button> : null}
          </div>
        </div>
      }>
      <div className="flex flex-col gap-4">
        {isRetired ? <p className="rounded-[12px] bg-tile p-3 text-[12px] text-sec">بازنشسته است: در سندهای قبلی میماند و دیگر برای سند تازه پیشنهاد نمیشود.</p> : null}
        {!saved && ui.by === 'key' ? (
          <label className="flex flex-col gap-1.5 text-[12px] font-semibold text-sec">کلید
            <input aria-label="کلید" dir="ltr" value={String(row.key ?? '')} onChange={(e) => set({ key: e.target.value.trim() })} placeholder="snake_case" className={fieldCls(errors.key, 'fig text-left')} />
            <span className="font-normal text-muted">{errors.key ?? 'حروف کوچک لاتین، عدد و _؛ بعد از ساخت عوض نمیشود.'}</span>
          </label>
        ) : null}
        <div className="grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2">
          {ui.attrs.map((a) => <AttrInput key={a.key} a={a} row={row} set={set} errors={errors} saved={saved} />)}
        </div>
        {loose.length ? <ul className="flex flex-col gap-1 rounded-[12px] bg-neg-soft p-3 text-[12px] text-neg">{loose.map(([k, v]) => <li key={k}><span className="fig ml-1.5 text-muted">{k}</span>{v}</li>)}</ul> : null}
        <ErrorLine error={failure} />
      </div>
      <Dialog open={!!retiring} onOpenChange={(v) => !v && setRetiring(null)} title="بازنشسته کردن" actions={<>
        <Button variant="danger" icon="lock" loading={act.retire.isPending} onClick={retire}>با passkey بازنشسته کن</Button>
        <Button variant="secondary" onClick={() => setRetiring(null)}>نه</Button>
      </>}>
        <div className="flex flex-col gap-2">
          {retiring ? <ImpactLine impact={retiring.impact} part={part} /> : null}
          <p>هیچ چیزی پاک نمیشود؛ سندهایی که از آن استفاده میکنند همان‌طور میمانند و در جستجو هستند. فقط برای سند تازه پیشنهاد نمیشود.</p>
        </div>
      </Dialog>
    </Sheet>
  );
}

/** Text of a failed schema call, for a toast. */
export const schemaError = (e: unknown) => faError(e);
