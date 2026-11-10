'use client';

/**
 * ⟨1.0.1⟩ §44.5, §51 a session's publishes, in its details: what went to Instagram from this session and what is set to go, newest
 * first, each with where it stands. One that is not out yet can be taken back right here («لغو»). Hidden while there is none.
 */
import { Icon } from '@/components/icon';
import { Card, Pill, SectionTitle } from '@/components/ui/primitives';
import { FaText } from '@/components/v29/text';
import { KIND_FA, type SessionPublish } from '@/lib/api/v44';
import { jDateTime } from '@/lib/format';
import { publishNote, useCancel } from './cancel';

function Line({ p }: { p: SessionPublish }) {
  const cancel = useCancel(p);
  const note = publishNote(p);
  const where = [
    KIND_FA[p.kind] ?? 'پست', p.state === 'scheduled' && p.scheduled_at ? jDateTime(p.scheduled_at) : null,
    // the handle is Latin inside a Persian line: isolated left-to-right, so «@» stays in front of it
    p.account ? `⁦@${p.account}⁩` : null, p.auto ? 'خودکار' : null,
  ].filter(Boolean).join(' · ');
  return (
    <li className="flex flex-col gap-1.5 py-2.5" data-publish={p.state}>
      <div className="flex items-center gap-3">
        <span className="flex-none text-sec"><Icon name={p.kind === 'reel' ? 'video' : 'image'} size={18} /></span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span dir="ltr" className="fig truncate text-right text-[13px] text-ink">{p.file_name || 'فایل'}</span>
          <span className={p.state === 'failed' ? 'text-[11px] text-neg' : 'truncate text-[11px] text-sec'}>
            {p.state === 'failed' || p.state === 'waiting_seal' || p.state === 'waiting_setup' ? [where, p.note_fa].filter(Boolean).join(' · ') : where}
          </span>
        </div>
        <span className="flex flex-none items-center gap-1">
          {p.state === 'publishing' ? <Pill tone="gold" dot live>در حال انتشار</Pill>
            : p.state === 'scheduled' ? <Pill tone="gold" dot>زمان‌بندی شد</Pill>
            : p.state === 'published' ? <Pill tone="pos" dot>منتشر شد</Pill>
            : p.state === 'cancelled' ? <Pill tone="silver" dot>لغو شد</Pill>
            : p.state === 'waiting_seal' ? <Pill tone="warn" dot>منتظر مُهر</Pill>
            : p.state === 'waiting_setup' ? <Pill tone="neutral" dot>در حال وصل شدن</Pill>
            : <Pill tone="neg" dot>انجام نشد</Pill>}
          {p.state === 'published' && p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center rounded-[8px] px-2 text-[12px] font-semibold text-gold-ink hover:bg-gold-soft">باز کن</a> : null}
          {cancel.button}
        </span>
      </div>
      {note ? <span className="text-[11px] leading-5 text-muted" data-publish-note><FaText text={note} /></span> : null}
      {cancel.under}
    </li>
  );
}

export function SessionPublishes({ publishes }: { publishes: SessionPublish[] | undefined }) {
  if (!publishes?.length) return null;
  return (
    <Card className="flex flex-col gap-1 p-5" aria-label="انتشارها">
      <SectionTitle title="انتشارها" note="آنچه از این جلسه به اینستاگرام رفته یا در نوبت رفتن است" />
      <ul className="flex flex-col divide-y divide-[var(--hq-div)]">
        {publishes.map((p, i) => <Line key={`${p.job ?? p.file_id}-${p.kind}-${i}`} p={p} />)}
      </ul>
    </Card>
  );
}
