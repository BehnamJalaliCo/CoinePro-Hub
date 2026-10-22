'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Pill, Skeleton } from '@/components/ui/primitives';
import { RefChip } from '@/components/v17/bits';
import type { Schemas } from '@/lib/api/client';
import { useRecordsByRef, type DisposalCardPayload, type SchemaCardPayload } from '@/lib/api/v20';
import { cx } from '@/lib/format';
import { ClassTag, JDay, useArchive, type ArchiveMaps } from './bits';
import { AttrValue, ImpactLine, partUI, rowKey, rowsOf, type Attr, type Row } from './schema';

type Decision = Schemas['Decision'];
const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/** The schema row an `archive_schema` card was written against, and whether the card is void (that row changed since, §23.12). */
export function useSchemaCard(d: Decision): { p: SchemaCardPayload; current: Row | null; void: boolean | null } {
  const m = useArchive();
  const p = (d.payload ?? {}) as SchemaCardPayload;
  if (!m.schema) return { p, current: null, void: null };
  const rows = rowsOf(m, p.part);
  const ui = partUI(p.part, rows);
  const current = rows.find((r) => rowKey(p.part, ui, r) === p.key) ?? null;
  const v = current ? Number(current.version ?? 0) || null : null;
  return { p, current, void: d.status === 'pending' && v !== (p.base_version ?? null) };
}

function Change({ label, before, after, isNew }: { label: string; before?: ReactNode; after: ReactNode; isNew: boolean }) {
  return (
    <li className="flex min-w-0 flex-col gap-1 rounded-[10px] bg-tile p-2.5 text-[13px]">
      <span className="text-[11px] text-muted">{label}</span>
      {isNew ? <span className="min-w-0 break-words text-ink">{after}</span> : (
        <span className="flex min-w-0 flex-wrap items-center gap-1.5">
          <span className="min-w-0 break-words rounded-[6px] bg-neg-soft px-1.5 text-sec line-through decoration-[var(--hq-neg-line)]">{before}</span>
          <span aria-hidden className="text-muted">←</span>
          <span className="min-w-0 break-words rounded-[6px] bg-pos-soft px-1.5 text-ink">{after}</span>
        </span>
      )}
    </li>
  );
}

const FIELD_ATTRS: Array<[string, string]> = [['title_fa', 'عنوان'], ['required', 'لازم'], ['searchable', 'در جستجو'], ['sensitive', 'حساس'], ['options', 'گزینه‌ها'], ['ref_kinds', 'به'], ['currency', 'واحد'], ['help_fa', 'راهنما']];
const fieldVal = (k: string, v: unknown) => (v == null || v === '' ? '—' : typeof v === 'boolean' ? (v ? 'بله' : 'نه') : Array.isArray(v) ? v.map((x) => (x && typeof x === 'object' ? (x as { title_fa?: string }).title_fa ?? JSON.stringify(x) : String(x))).join('، ') : String(v));
/** A class's (or a party kind's) fields, field by field: new, retired, changed, and the rest unchanged. */
function FieldsDiff({ before, after, m }: { before: Row[]; after: Row[]; m: ArchiveMaps }) {
  const rows: ReactNode[] = [];
  for (const f of after) {
    const old = before.find((x) => x.key === f.key);
    const tag = (
      <span className="flex flex-wrap items-center gap-1.5">
        <span className="font-semibold text-ink">{String(f.title_fa)}</span><span className="fig text-[11px] text-muted">{String(f.key)}</span>
        <span className="text-[11px] text-sec">{m.typeFa(String(f.type))}{f.type === 'money' && f.currency ? <> · <span className="fig">{String(f.currency)}</span></> : null}</span>
        {f.required ? <Pill tone="warn" className="h-5 text-[11px]">لازم</Pill> : null}
      </span>
    );
    if (!old) { rows.push(<li key={String(f.key)} className="flex flex-col gap-1 rounded-[10px] bg-pos-soft p-2.5 text-[12px]"><span className="text-[11px] font-semibold text-pos">فیلد تازه</span>{tag}{(f.options as unknown[] | undefined)?.length ? <span className="text-sec">گزینه‌ها: {fieldVal('options', f.options)}</span> : null}</li>); continue; }
    if (old.status !== 'retired' && f.status === 'retired') { rows.push(<li key={String(f.key)} className="flex flex-col gap-1 rounded-[10px] bg-neg-soft p-2.5 text-[12px]"><span className="text-[11px] font-semibold text-neg">بازنشسته میشود؛ مقدارهایش میمانند</span>{tag}</li>); continue; }
    const diffs = FIELD_ATTRS.filter(([k]) => !same(old[k], f[k]));
    if (diffs.length) rows.push(<li key={String(f.key)} className="flex flex-col gap-1 rounded-[10px] bg-tile p-2.5 text-[12px]">{tag}{diffs.map(([k, fa]) => <span key={k} className="flex flex-wrap items-center gap-1.5 text-sec">{fa}: <span className="line-through decoration-[var(--hq-neg-line)]">{fieldVal(k, old[k])}</span><span aria-hidden>←</span><span className="text-ink">{fieldVal(k, f[k])}</span></span>)}</li>);
  }
  const untouched = after.filter((f) => { const o = before.find((x) => x.key === f.key); return o && same(o, { ...o, ...f }) && o.status === f.status; }).length;
  return (
    <div className="flex flex-col gap-1.5">
      {rows.length ? <ul className="flex flex-col gap-1.5">{rows}</ul> : null}
      {before.length && untouched ? <span className="text-[11px] text-muted">{untouched} فیلد دیگر همان است.</span> : null}
    </div>
  );
}

/** `archive_schema`: the exact PUT, read against the current row; void when that row changed after the card was written. */
function SchemaCard({ d }: { d: Decision }) {
  const m = useArchive();
  const { p, current, void: isVoid } = useSchemaCard(d);
  if (!m.schema) return <Skeleton className="h-40" />;
  const rows = rowsOf(m, p.part);
  const ui = partUI(p.part, rows);
  const body = (p.body ?? {}) as Row;
  const isNew = !current;
  const view = { ...(current ?? {}), ...body } as Row;
  const empty = (v: unknown) => v == null || v === '' || (Array.isArray(v) && !v.length);
  // A new row lists what it sets; a change lists what differs from the current row.
  const changed = ui.attrs.filter((a) => a.key in body && (isNew ? !empty(body[a.key]) : !same(current?.[a.key], body[a.key])));
  const simple = changed.filter((a) => a.kind !== 'fields');
  const fields = changed.find((a) => a.kind === 'fields');
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-[12px] font-semibold text-gold-ink">تغییر طرح بایگانی</h3>
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
        <Pill tone="neutral" icon={ui.icon}>{ui.fa}</Pill>
        <span className="fig text-ink">{p.key}</span>
        {isNew ? <Pill tone="pos" icon="add">تازه</Pill> : p.base_version == null ? <span>کارت برای کلید تازه نوشته شده؛ الان نسخه‌ی <span className="fig">{String(current?.version ?? '—')}</span> هست</span> : <span>نسخه‌ی پایه <span className="fig">{String(p.base_version)}</span>، الان <span className="fig">{String(current?.version ?? '—')}</span></span>}
        <Link href={`/archive/settings?tab=${p.part}${current ? `&ref=${encodeURIComponent(p.key)}` : ''}`} className="font-semibold text-gold-ink hover:underline">در طرح بایگانی</Link>
      </div>
      {isVoid ? (
        <p role="alert" className="flex items-start gap-2 rounded-[12px] bg-neg-soft p-3 text-[13px] leading-6 text-ink">
          <span className="mt-0.5 text-neg"><Icon name="urgent" size={16} /></span>
          <span>این کارت باطل است: {p.base_version == null ? 'این کلید بعد از نوشتن کارت ساخته شد' : <>این بخش بعد از نوشتن کارت عوض شده (کارت روی نسخه‌ی <span className="fig">{String(p.base_version ?? '—')}</span>، الان <span className="fig">{String(current?.version ?? '—')}</span>)</>}. مُهر نمیخورد؛ بایگان پیشنهاد تازه مینویسد.</span>
        </p>
      ) : null}
      {simple.length ? <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">{simple.map((a: Attr) => <Change key={a.key} label={a.fa} isNew={isNew} before={<AttrValue a={a} v={current?.[a.key]} m={m} row={current ?? view} />} after={<AttrValue a={a} v={body[a.key]} m={m} row={view} />} />)}</ul> : null}
      {fields ? (
        <div className="flex flex-col gap-1.5">
          <span className="text-[12px] font-semibold text-sec">{fields.fa}</span>
          <FieldsDiff before={(current?.[fields.key] as Row[]) ?? []} after={(body[fields.key] as Row[]) ?? []} m={m} />
        </div>
      ) : null}
      {!changed.length ? <p className="text-[12px] text-muted">با ردیف فعلی فرقی ندارد.</p> : null}
      {p.impact ? <ImpactLine impact={p.impact} part={p.part} /> : null}
      <p className="text-[12px] text-muted">با مُهر، دقیقاً همین بدنه اعمال میشود و نسخه‌ی تازه‌ای از این بخش ساخته میشود؛ چیزی حذف نمیشود. سندهای ثبت‌شده نسخه‌ی خودشان را نگه میدارند.</p>
    </section>
  );
}

/** `archive_disposal`: the records the week's batch would destroy; a held one is skipped and stays. */
function DisposalCard({ d }: { d: Decision }) {
  const p = (d.payload ?? {}) as DisposalCardPayload;
  const list = p.records ?? [];
  const qs = useRecordsByRef(list.map((x) => x.ref));
  const m = useArchive();
  const held = qs.filter((q) => (q.data?.holds.length ?? 0) > 0).length;
  const gone = qs.filter((q) => q.data?.state === 'disposed').length;
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-[12px] font-semibold text-gold-ink">سندهای این کارت</h3>
      <p className="text-[13px] leading-6 text-sec">
        {list.length - held - gone} سند امحا میشود{held ? <>؛ <b className="font-semibold text-neg">{held} سند توقیف دارد و رد میشود</b></> : null}{gone ? `؛ ${gone} سند پیش‌تر امحا شده` : ''}.
      </p>
      <ul className="flex flex-col gap-1.5">
        {list.map((x, i) => {
          const r = qs[i]?.data;
          const isHeld = (r?.holds.length ?? 0) > 0;
          const disposed = r?.state === 'disposed';
          const rule = m.schema?.retention.find((y) => y.ref === x.retention_rule);
          return (
            <li key={x.ref} className={cx('flex min-w-0 flex-col gap-1 rounded-[12px] p-3', isHeld ? 'bg-neg-soft' : 'bg-tile')}>
              <span className="flex min-w-0 flex-wrap items-center gap-2">
                <Link href={`/archive/${x.ref}`} className="min-w-0 flex-1 truncate text-[13px] font-semibold text-ink hover:underline">{x.title_fa}</Link>
                {qs[i]?.isLoading ? <Skeleton className="h-5 w-16" /> : isHeld ? <Pill tone="neg" icon="lock">رد میشود: {r!.holds.join('، ')}</Pill> : disposed ? <Pill icon="close">امحا شد</Pill> : qs[i]?.error ? <Pill>دیده نمیشود</Pill> : <Pill tone="warn" icon="time">امحا</Pill>}
              </span>
              <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-muted">
                <span className="fig text-sec">{x.ref}</span><ClassTag cls={x.class} />
                <RefChip r={x.retention_rule} tone="neutral" note={rule?.title_fa ?? null} className="max-w-[18rem]" />
                {x.trigger_at ? <span>آغاز <JDay d={x.trigger_at} className="text-sec" /></span> : null}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="text-[12px] text-muted">با مُهر، فایل‌ها نابود میشوند و برای هر سند سنگ‌نشان میماند (شناسه، نوع، عنوان، تاریخ‌ها، hash و همین تصمیم). سندی که تا لحظه‌ی مُهر توقیف شود رد میشود و میماند.</p>
    </section>
  );
}

/** The payload of a §23 card; null for any other kind. */
export function ArchiveDecisionPayload({ d }: { d: Decision }) {
  if (d.kind === 'archive_schema') return <SchemaCard d={d} />;
  if (d.kind === 'archive_disposal') return <DisposalCard d={d} />;
  return null;
}

/** The seal of an `archive_schema` card, only while the card is not void: a stale card is never sealed (§23.12). */
export function SchemaSealGate({ d, children }: { d: Decision; children: ReactNode }) {
  const { void: isVoid } = useSchemaCard(d);
  if (isVoid == null) return <Skeleton className="size-24 rounded-full" />;
  if (isVoid) return <p className="max-w-sm text-center text-[13px] leading-6 text-sec"><Icon name="urgent" size={16} /> این کارت باطل است و مُهر نمیخورد؛ ردش کن یا با یادداشت برگردان تا بایگان روی نسخه‌ی تازه بنویسد.</p>;
  return <>{children}</>;
}
