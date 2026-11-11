'use client';

/**
 * ⟨1.0.1⟩ §44.5, §51 a session's publishes, in its details: what went to Instagram from this session and what is set to go, newest
 * first, each with where it stands. One that is not out yet can be taken back right here («لغو»). Hidden while there is none.
 */
import { Icon } from '@/components/icon';
import { OpenLink, PublishFacts, PublishState } from '@/components/look/publish';
import { Ltr } from '@/components/look/text';
import { Card, SectionTitle } from '@/components/ui/primitives';
import { FaText } from '@/components/v29/text';
import type { SessionPublish } from '@/lib/api/v44';
import { publishNote, useCancel } from './cancel';

function Line({ p }: { p: SessionPublish }) {
  const cancel = useCancel(p);
  const note = publishNote(p);
  // one that failed or waits says why in the hub's own words, under its facts
  const why = p.state === 'failed' || p.state === 'waiting_seal' || p.state === 'waiting_setup' ? p.note_fa : null;
  return (
    <li className="flex flex-col gap-1.5 py-2.5" data-publish={p.state}>
      <div className="flex items-center gap-3">
        <span className="flex-none text-sec"><Icon name={p.kind === 'reel' ? 'video' : 'image'} size={18} /></span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <Ltr tabular={false} className="truncate text-[13px] text-ink">{p.file_name || 'فایل'}</Ltr>
          <span className="text-[11px] leading-5 text-sec"><PublishFacts p={p} /></span>
        </div>
        <span className="flex flex-none items-center gap-1">
          <PublishState p={p} />
          {p.state === 'published' && p.url ? <OpenLink url={p.url} /> : null}
          {cancel.button}
        </span>
      </div>
      {why ? <span className={p.state === 'failed' ? 'text-[11px] leading-5 text-neg' : 'text-[11px] leading-5 text-sec'}><FaText text={why} /></span> : null}
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
      <ul className="flex flex-col divide-y divide-[var(--hq-line-divider)]">
        {publishes.map((p, i) => <Line key={`${p.job ?? p.file_id}-${p.kind}-${i}`} p={p} />)}
      </ul>
    </Card>
  );
}
