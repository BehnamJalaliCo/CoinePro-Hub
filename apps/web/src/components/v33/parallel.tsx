'use client';

// ⟨1.15⟩ Contract §33.7 and §33.10 in the order report: the parts of a split work side by side with the merge that follows, and the badge and
// progress of a work done on its company's own server (a persistent folder there, until the delivery or a seal).

import Link from 'next/link';
import { Icon } from '@/components/icon';
import { Bar, Card, Pill, SectionTitle } from '@/components/ui/primitives';
import { FaPara, FaText, fig } from '@/components/v29/text';
import { PART_STATE, WORKSPACE_STATE, type OrderParallel, type SplitMerge, type SplitPart, type WorkspaceInfo } from '@/lib/api/v33';
import { cx } from '@/lib/format';

const MERGE_FA: Record<SplitMerge['state'], string> = { waiting: 'منتظر تمام شدن بخش‌ها', running: 'در حال نوشتن', done: 'نوشته شد', failed: 'نشد' };

function Part({ p }: { p: SplitPart }) {
  const s = PART_STATE[p.state];
  return (
    <li className={cx('flex min-w-0 flex-col gap-2 rounded-[14px] bg-tile p-4', p.state === 'failed' && 'ring-1 ring-[var(--hq-neg-line)]')} aria-label={`بخش ${p.title_fa}`}>
      <div className="flex flex-wrap items-center gap-2"><h3 className="min-w-0 flex-1 text-[14px] font-semibold"><FaText text={p.title_fa} /></h3><Pill tone={s.tone} dot live={p.state === 'running'}>{s.fa}</Pill></div>
      {p.role_fa ? <span className="text-[11px] text-muted">{p.role_fa}</span> : null}
      {p.progress_pct != null && p.state !== 'done' ? <Bar pct={p.progress_pct} tone={p.state === 'failed' ? 'neg' : 'gold'} label={`پیشرفت ${p.title_fa}`} /> : null}
      {p.state === 'failed' ? <p className="rounded-[10px] bg-neg-soft px-3 py-2 text-[13px] leading-6" role="alert"><FaText text={p.failed_fa ?? 'این بخش تمام نشد.'} /></p> : p.summary_fa ? <FaPara text={p.summary_fa} className="text-[13px] leading-6 text-sec" /> : null}
      {p.outputs.length ? <ul className="flex flex-col gap-1">{p.outputs.map((o) => <li key={o.ref}><Link href={`/outputs?ref=${o.ref}&tab=all`} className="flex items-center gap-1.5 text-[12px] text-gold-ink hover:underline"><Icon name="deliverable" size={13} /><FaText text={o.title_fa} /></Link></li>)}</ul> : null}
    </li>
  );
}

/** The parts of a split work side by side, then the one merge the parent's assignee writes. A failed part is shown as failed, never hidden. */
export function SplitParts({ r }: { r: OrderParallel }) {
  const parts = r.parts ?? [];
  if (!parts.length) return null;
  const done = parts.filter((p) => p.state === 'done').length;
  const m = r.merge;
  return (
    <Card as="section" className="flex flex-col gap-3 p-5" aria-label="بخش‌های موازی">
      <SectionTitle title="بخش‌های موازی" note={<><span className="fig">{fig(done)}</span> از <span className="fig">{fig(parts.length)}</span> بخش تمام شده؛ بعد از همه، یک ادغام نوشته میشود</>} />
      <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{parts.map((p) => <Part key={p.ref} p={p} />)}</ul>
      {m ? (
        <div className="flex flex-col gap-1.5 rounded-[14px] bg-gold-soft p-4" aria-label="ادغام">
          <div className="flex flex-wrap items-center gap-2"><h3 className="flex-1 text-[14px] font-semibold text-gold-ink">ادغام{m.by_fa ? ` · ${m.by_fa}` : ''}</h3><Pill tone={m.state === 'done' ? 'pos' : m.state === 'failed' ? 'neg' : 'silver'} dot>{MERGE_FA[m.state]}</Pill></div>
          {m.text_fa ? <FaPara text={m.text_fa} className="text-[14px] leading-7" /> : null}
        </div>
      ) : null}
    </Card>
  );
}

/** «روی سرور شرکت»: the workspace of a work done on the company's own server, with its state and progress. */
export function WorkspaceCard({ r }: { r: OrderParallel }) {
  const w: WorkspaceInfo | null | undefined = r.workspace;
  if (!w || w.mode !== 'on_server') return null;
  const s = WORKSPACE_STATE[w.state];
  return (
    <Card as="section" className="flex flex-col gap-2 p-5" aria-label="محیط کاری روی سرور">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="lapis" icon="server">روی سرور شرکت</Pill>
        <Pill tone={s.tone} dot live={w.state === 'working'}>{s.fa}</Pill>
        {w.server_fa ? <span className="text-[12px] text-sec">{w.server_fa}</span> : null}
        {w.folder ? <span className="fig truncate text-[11px] text-muted" dir="ltr">{w.folder}</span> : null}
      </div>
      {w.progress_pct != null ? <Bar pct={w.progress_pct} tone={w.state === 'failed' ? 'neg' : w.state === 'awaiting_seal' ? 'warn' : 'gold'} label="پیشرفت روی سرور" /> : null}
      {w.note_fa ? <p className="text-[13px] leading-6 text-sec"><FaText text={w.note_fa} /></p> : null}
      <p className="text-[11px] text-muted">پوشه‌ی کار ماندگار است و ۳۰ روز بعد از بسته شدن کار پاک میشود. کار را از صفحه‌ی خودش میتوانی متوقف کنی.</p>
    </Card>
  );
}
