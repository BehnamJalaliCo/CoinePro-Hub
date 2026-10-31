'use client';

// ⟨1.10⟩ §28.2 «کاتالوگ کامل»: a deep, read-only extraction of everything on a company's paired servers (a `claude` job on each, with a
// fixed exhaustive brief), in six parts with tables — products and services, automations and schedules, data, interfaces, code, risks —
// filed in the archive as a report. The owner starts it or refreshes it here; a weekly protocol refreshes it and sends the diff.

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Card, Empty, ErrorState, FilterChip, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { RefChip } from '@/components/v17/bits';
import { ApiError } from '@/lib/api/client';
import { CATALOGUE_PARTS, notServed, partOf, useCatalogue, useStartCatalogue, type Catalogue, type CatalogueCell, type CatalogueSection, type CatalogueTable } from '@/lib/api/v28';
import { serverNameOf } from '@/lib/api/v26-model';
import { ago, cx, jDateTime } from '@/lib/format';

const PERSIAN = /[؀-ۿ]/;
/** A cell as it reads: numbers and Latin names in Latin figures, Persian prose as it is. */
function Cell({ v }: { v: CatalogueCell }) {
  if (v == null || v === '') return <span className="text-muted">—</span>;
  if (typeof v === 'boolean') return <span>{v ? 'بله' : 'نه'}</span>;
  if (typeof v === 'number') return <span className="fig">{v.toLocaleString('en-US')}</span>;
  return <span className={cx(!PERSIAN.test(v) && 'fig')}>{v}</span>;
}

function Table({ t }: { t: CatalogueTable }) {
  return (
    <div className="flex flex-col gap-1.5">
      {t.title_fa ? <h4 className="text-[12px] font-semibold text-sec">{t.title_fa} <span className="fig font-normal text-muted">({t.rows.length})</span></h4> : null}
      <div className="overflow-x-auto rounded-[12px] border border-div">
        <table className="w-full min-w-[520px] border-collapse text-[12px]">
          <thead><tr className="bg-tile text-right text-[11px] text-muted">{t.columns.map((c) => <th key={c} scope="col" className="px-3 py-2 font-semibold"><Cell v={c} /></th>)}</tr></thead>
          <tbody>
            {t.rows.map((r, i) => (
              <tr key={i} className="border-t border-div align-top">{t.columns.map((_, j) => <td key={j} className="px-3 py-2 leading-5 text-ink"><Cell v={r[j] ?? null} /></td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Section({ s, server }: { s: CatalogueSection; server: (name: string | null | undefined) => string | null }) {
  const part = partOf(s.key);
  return (
    <Card as="section" id={`cat-${part?.key ?? s.key}`} className="flex scroll-mt-24 flex-col gap-3 p-4" aria-label={s.title_fa ?? part?.fa ?? s.key}>
      <div className="flex items-center gap-3">
        <span className="flex size-9 flex-none items-center justify-center rounded-[10px] bg-tile text-silver-ink"><Icon name={part?.icon ?? 'report'} size={18} /></span>
        <div className="flex min-w-0 flex-1 flex-col">
          <h3 className="text-[15px] font-semibold">{s.title_fa ?? part?.fa ?? s.key}</h3>
          {part ? <span className="text-[11px] text-muted">{part.note}</span> : null}
        </div>
        {s.count != null ? <span className="text-[12px] text-sec">{s.count.toLocaleString('fa-IR')} مورد</span> : null}
        {server(s.server) ? <Pill tone="neutral" icon="server">{server(s.server)}</Pill> : null}
      </div>
      {s.summary_md ? <Md text={s.summary_md} className="flex flex-col gap-1 text-[13px] leading-6 text-sec" /> : null}
      {s.tables.map((t, i) => <Table key={i} t={t} />)}
      {s.body_md ? <Md text={s.body_md} /> : null}
    </Card>
  );
}

function Running({ c, server }: { c: Catalogue; server: (name: string | null | undefined) => string | null }) {
  return (
    <Card className="flex flex-col gap-3 p-4 ring-1 ring-[var(--hq-line-tahrir)]">
      <div className="flex items-center gap-3">
        <span className="size-2.5 flex-none rounded-full bg-gold" style={{ animation: 'hq-live 1.4s infinite' }} />
        <span className="flex-1 text-[14px] font-semibold">در حال خواندن سرورها{c.started_at ? <span className="font-normal text-muted">، از {ago(c.started_at)}</span> : null}</span>
      </div>
      <p className="text-[12px] leading-6 text-sec">Claude روی هر سرورِ جفت‌شده‌ی شرکت میخواند و چیزی را تغییر نمیدهد؛ هیچ رمز یا محتوای ردیفی برداشته نمیشود. چند دقیقه طول میکشد.</p>
      {c.servers?.length ? (
        <ul className="flex flex-wrap gap-2">{c.servers.map((s) => (
          <li key={s.id ?? s.name}><Pill tone={s.state === 'done' ? 'pos' : s.state === 'failed' || s.state === 'offline' ? 'neg' : 'gold'} live={s.state === 'running'} dot={s.state !== 'running'}>{server(s.name)}</Pill></li>
        ))}</ul>
      ) : null}
    </Card>
  );
}

export function CompanyCatalogue({ code, nameFa }: { code: string; nameFa: string }) {
  const q = useCatalogue(code);
  const start = useStartCatalogue(code);
  const toast = useToast();
  const [only, setOnly] = useState<string | null>(null);
  const run = async () => {
    try {
      // A hub before §28 has no catalogue: the section goes away quietly.
      if (!(await start.mutateAsync())) return;
      toast({ tone: 'ok', text: `کاتالوگ ${nameFa} شروع شد؛ وقتی تمام شد در بایگانی ثبت میشود و به تو تحویل میشود.` });
    } catch (e) {
      toast({ tone: notServed(e) ? 'info' : 'error', text: notServed(e) ? 'کاتالوگ کامل با به‌روزرسانی هاب فعال میشود.' : e instanceof ApiError ? e.messageFa : 'شروع نشد.' });
    }
  };
  if (q.isLoading) return <div className="flex flex-col gap-3"><Skeleton className="h-24 rounded-[16px]" /><Skeleton className="h-64 rounded-[16px]" /></div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const c = q.data;
  // The owner's rule: a server is called by its company's name; its own name follows only when the company has several.
  const n = c?.servers?.length ?? 1;
  const server = (name: string | null | undefined) => (name ? serverNameOf(code, nameFa, name, n).text : null);
  const running = c?.state === 'running' || start.isPending;
  const sections = (c?.sections ?? []).filter((s) => !only || (partOf(s.key)?.key ?? s.key) === only);
  const present = CATALOGUE_PARTS.filter((p) => (c?.sections ?? []).some((s) => partOf(s.key)?.key === p.key));
  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-3 p-4">
        <SectionTitle title="کاتالوگ کامل" note="همه‌چیزِ روی سرورهای شرکت، با جدول؛ نه خلاصه. فقط خواندن، بدون هیچ تغییر."
          action={<Button variant={c ? 'secondary' : 'primary'} size="sm" icon="refresh" loading={running} disabled={running} onClick={run}>{c ? 'تازه کن' : 'ساختن کاتالوگ'}</Button>} />
        {c && c.state !== 'running' ? (
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
            {c.state === 'failed' ? <Pill tone="neg" dot>ناموفق</Pill> : <Pill tone="pos" icon="seal">کامل</Pill>}
            {c.at ? <span>{jDateTime(c.at)} <span className="text-muted">({ago(c.at)})</span></span> : null}
            {c.servers?.length ? <span className="text-muted">از {n > 1 ? `${n.toLocaleString('fa-IR')} سرور ${nameFa}` : `سرور ${nameFa}`}</span> : null}
            <span className="flex-1" />
            {c.record ? <Link href={`/archive/${c.record}`} className="inline-flex items-center gap-1.5 rounded-full bg-gold-soft px-3 py-1 font-semibold text-gold-ink hover:underline"><Icon name="deliverable" size={14} />سند بایگانی <span className="fig">{c.record}</span></Link> : null}
            {c.deliverable_ref ? <RefChip r={c.deliverable_ref} note="خروجی" /> : null}
          </div>
        ) : null}
        {c?.state === 'failed' && c.reason ? <p className="rounded-[10px] bg-neg-soft p-3 text-[13px] text-ink">{PERSIAN.test(c.reason) ? c.reason : 'ساخت کاتالوگ کامل نشد.'}</p> : null}
        {c?.diff_md || c?.changes?.length ? (
          <div className="flex flex-col gap-2 rounded-[12px] bg-lapis-soft p-3">
            <span className="text-[12px] font-semibold text-lapis">تغییرها از نسخه‌ی پیش</span>
            {c.diff_md ? <Md text={c.diff_md} className="flex flex-col gap-1 text-[13px] leading-6 text-ink" /> : null}
            {(c.changes ?? []).map((x) => (
              <div key={x.key} className="flex flex-col gap-1 text-[12px] leading-5">
                <span className="font-semibold text-ink">{partOf(x.key)?.fa ?? x.key}</span>
                {x.added.length ? <span className="text-pos">تازه: <span className="text-ink">{x.added.map((a, i) => <span key={i} className={cx(!PERSIAN.test(a) && 'fig')}>{i ? '، ' : ''}{a}</span>)}</span></span> : null}
                {x.removed.length ? <span className="text-neg">رفته: <span className="text-ink">{x.removed.map((a, i) => <span key={i} className={cx(!PERSIAN.test(a) && 'fig')}>{i ? '، ' : ''}{a}</span>)}</span></span> : null}
              </div>
            ))}
          </div>
        ) : null}
        {present.length > 1 ? (
          <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1" role="group" aria-label="بخش‌های کاتالوگ">
            <FilterChip selected={!only} onClick={() => setOnly(null)}>همه</FilterChip>
            {present.map((p) => <FilterChip key={p.key} selected={only === p.key} onClick={() => setOnly(only === p.key ? null : p.key)}><Icon name={p.icon} size={14} />{p.fa}</FilterChip>)}
          </div>
        ) : null}
      </Card>
      {c?.state === 'running' ? <Running c={c} server={server} /> : null}
      {!c && !running ? (
        <Card className="p-4"><Empty icon="server" title="هنوز کاتالوگی ساخته نشده" body="«ساختن کاتالوگ» روی هر سرورِ جفت‌شده‌ی شرکت میخواند: سرویس‌ها، خودکارسازی‌ها، داده، رابط‌ها، کد و ریسک‌ها؛ نتیجه در بایگانی ثبت میشود." /></Card>
      ) : null}
      {sections.map((s, i) => <Section key={`${s.key}-${s.server ?? ''}-${i}`} s={s} server={(x) => (n > 1 ? server(x) : null)} />)}
    </div>
  );
}
