'use client';

// ⟨1.15⟩ Contract §33.7 and §33.10: the parts of a split work side by side with the one merge that follows (in the order report and on the
// work's own page), and the progress of a work done on its company's own server — a persistent folder there, until the delivery or a seal —
// which the owner can stop (`POST /work/{id}/stop`; the work stays open).

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Bar, Card, Pill, SectionTitle } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaText, fig } from '@/components/v29/text';
import { errText } from '@/components/v31/kit';
import {
  PART_STATE, SPLIT_STATE, WORKSPACE_LIVE, WORKSPACE_STATE, useStopWorkspace, useWorkSplit,
  type OrderParallel, type SplitPart, type WorkSplit, type WorkspaceProgress,
} from '@/lib/api/v33';
import { ROLE_FA } from '@/lib/labels';
import { cx, jDate, jDateTime, tokens } from '@/lib/format';

const MERGE_FA: Record<WorkSplit['state'], string> = {
  running: 'وقتی همه‌ی بخش‌ها تمام شوند، یک جمع‌بندی نوشته میشود.', merging: 'همه‌ی بخش‌ها آمده‌اند؛ جمع‌بندی در حال نوشتن است.',
  done: 'جمع‌بندی نوشته شد و در خروجی‌های همین کار است.', failed: 'جمع‌بندی نوشته نشد.', cancelled: 'این کار لغو شد.',
};

function Part({ p }: { p: SplitPart }) {
  const s = PART_STATE[p.state];
  const who = p.who_fa ?? ROLE_FA[p.role] ?? p.role;
  const used = p.tokens_used ?? 0;
  return (
    <li className={cx('flex min-w-0 flex-col gap-2 rounded-[14px] bg-tile p-4', p.state === 'failed' && 'ring-1 ring-[var(--hq-neg-line)]')} aria-label={`بخش ${p.title_fa}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="fig flex size-6 flex-none items-center justify-center rounded-full bg-card text-[11px] font-semibold text-sec">{p.n}</span>
        <h3 className="min-w-0 flex-1 text-[14px] font-semibold"><FaText text={p.title_fa} /></h3>
        <Pill tone={s.tone} dot live={p.state === 'working'}>{s.fa}</Pill>
      </div>
      <span className="text-[11px] text-muted">{who} · <Link href={`/work/${p.ref}`} className="fig hover:text-gold-ink">{p.ref}</Link></span>
      {p.state === 'working' && p.progress_pct != null ? <Bar pct={p.progress_pct} tone="gold" label={`پیشرفت ${p.title_fa}`} /> : null}
      {p.state === 'failed' ? <p className="rounded-[10px] bg-neg-soft px-3 py-2 text-[13px] leading-6" role="alert"><FaText text={p.failed_fa ?? 'این بخش تمام نشد.'} /></p> : null}
      {p.output_ref ? <Link href={`/outputs?ref=${p.output_ref}&tab=all`} className="flex items-center gap-1.5 text-[12px] text-gold-ink hover:underline"><Icon name="deliverable" size={13} /><FaText text={p.output_title_fa ?? p.output_ref} /></Link> : null}
      {used || p.budget_tokens ? <span className="fig text-[11px] text-muted">{tokens(used)}{p.budget_tokens ? ` از ${tokens(p.budget_tokens)}` : ''} واحد</span> : null}
    </li>
  );
}

/** One split: its parts side by side, then the merge. A failed part is shown as failed, never hidden. */
export function SplitView({ s }: { s: WorkSplit }) {
  const done = s.parts.filter((p) => p.state === 'delivered').length;
  const st = SPLIT_STATE[s.state];
  return (
    <Card as="section" className="flex flex-col gap-3 p-5" aria-label="بخش‌های موازی">
      <SectionTitle title="بخش‌های موازی" note={<><Link href={`/work/${s.work_ref}`} className="fig hover:text-gold-ink">{s.work_ref}</Link> · <span className="fig">{fig(done)}</span> از <span className="fig">{fig(s.parts.length)}</span> بخش تحویل شده</>} />
      <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{[...s.parts].sort((a, b) => a.n - b.n).map((p) => <Part key={p.ref} p={p} />)}</ul>
      <div className="flex flex-col gap-1.5 rounded-[14px] bg-gold-soft p-4" aria-label="جمع‌بندی">
        <div className="flex flex-wrap items-center gap-2"><h3 className="flex-1 text-[14px] font-semibold text-gold-ink">جمع‌بندی</h3><Pill tone={st.tone} dot live={s.state === 'merging'}>{st.fa}</Pill></div>
        <p className="text-[13px] leading-6">{MERGE_FA[s.state]}{s.merge_queued_at && s.state !== 'running' ? <span className="text-muted"> · {jDateTime(s.merge_queued_at)}</span> : null}</p>
      </div>
    </Card>
  );
}

/** In the order report: every split of the order's works. */
export function SplitParts({ r }: { r: OrderParallel }) {
  const xs = r.parts ?? [];
  if (!xs.length) return null;
  return <>{xs.map((s) => <SplitView key={s.work_ref} s={s} />)}</>;
}

/** On a work's own page: `GET /work/{id}/split`, nothing for a work that was never split. */
export function WorkSplitCard({ id }: { id: string }) {
  const q = useWorkSplit(id);
  return q.data ? <SplitView s={q.data} /> : null;
}

function Workspace({ w }: { w: WorkspaceProgress }) {
  const s = WORKSPACE_STATE[w.state];
  const stop = useStopWorkspace();
  const toast = useToast();
  const [sure, setSure] = useState(false);
  const live = WORKSPACE_LIVE.has(w.state);
  return (
    <li className="flex flex-col gap-2 border-t border-div pt-3 first:border-0 first:pt-0" aria-label={`کار ${w.work_ref} روی سرور`}>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="lapis" icon="server">روی سرور شرکت</Pill>
        <Pill tone={s.tone} dot live={w.state === 'working'}>{s.fa}</Pill>
        <span className="text-[12px] text-sec"><FaText text={w.where_fa} /></span>
        <Link href={`/work/${w.work_ref}`} className="fig text-[11px] text-muted hover:text-gold-ink">{w.work_ref}</Link>
      </div>
      {w.last_step_fa ? <p className="text-[13px] leading-6"><span className="text-muted">آخرین کار: </span><FaText text={w.last_step_fa} /></p> : null}
      {w.note_fa ? <p className="text-[13px] leading-6 text-sec"><FaText text={w.note_fa} /></p> : null}
      <span className="text-[11px] text-muted"><span className="fig">{fig(w.turns)}</span> نوبت کار · آخرین خبر {jDateTime(w.updated_at)}</span>
      {w.remove_after ? <span className="text-[11px] text-muted">پوشه‌ی کار تا {jDate(w.remove_after)} می‌ماند و بعد پاک میشود.</span> : null}
      {live ? (
        sure ? (
          <div className="flex flex-wrap items-center gap-2 rounded-[12px] bg-tile p-3" role="group" aria-label="توقف کار روی سرور">
            <span className="min-w-0 flex-1 text-[13px]">کار روی سرور همین حالا متوقف شود؟ خود کار باز می‌ماند.</span>
            <Button size="sm" variant="primary" loading={stop.isPending} onClick={() => stop.mutate(w.work_ref, { onSuccess: () => { setSure(false); toast({ tone: 'ok', text: 'کار روی سرور متوقف شد.' }); }, onError: (e) => toast({ tone: 'error', text: errText(e, 'متوقف نشد.') }) })}>بله، متوقف کن</Button>
            <Button size="sm" onClick={() => setSure(false)}>نه</Button>
          </div>
        ) : <Button size="sm" icon="stop" className="self-start" onClick={() => setSure(true)}>توقف کار روی سرور</Button>
      ) : null}
    </li>
  );
}

/** «روی سرور شرکت»: each workspace of the order's works on its company's own server, with its state; a live one can be stopped. */
export function WorkspaceCard({ r }: { r: OrderParallel }) {
  const xs = r.workspaces ?? [];
  if (!xs.length) return null;
  return (
    <Card as="section" className="flex flex-col gap-3 p-5" aria-label="محیط کاری روی سرور">
      <SectionTitle title="کار روی سرور شرکت" note="یک پوشه‌ی کار ماندگار روی سرور خود شرکت، تا تحویل یا تا وقتی مُهر تو لازم شود" />
      <ul className="flex flex-col gap-3">{xs.map((w) => <Workspace key={w.work_ref} w={w} />)}</ul>
    </Card>
  );
}
