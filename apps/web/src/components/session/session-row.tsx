'use client';

// One session in a list (the office, «جلسه‌ها»): the order's words, the badge in words, why, whose it is, who is in it and how far its tasks are.
// ⟨1.24⟩ SS-1: the badge follows the stream (`session.updated`), the stall watch says when the last step was with the ring toward the hub's
// idle sweep, and the work band runs under the row only while the session moves.
// ⟨1.0.3⟩ §58.2 a closed session that left its working group in the library says so in one line.

import Link from 'next/link';
import { CompanyMark } from '@/components/brand/marks';
import { PlainText } from '@/components/v29/bits';
import { LiveBadge, SessionBand, StallWatch, useLastStep, useLiveBadge } from '@/components/live/session-pulse';
import { PACE_FA, type SessionCard } from '@/lib/api/v34';
import { PLAYBOOK_KEPT_FA, playbookKept } from '@/lib/api/v58';
import { cx } from '@/lib/format';

export function SessionRow({ s, className }: { s: SessionCard; className?: string }) {
  const people = s.participants.filter((p) => p.kind !== 'holder');
  const badge = useLiveBadge(s.ref, s.badge, s.last_at);
  const last = useLastStep(s.ref, s.last_at);
  const kept = badge === 'closed' ? playbookKept(s, (s as { session?: unknown }).session) : null;
  return (
    <Link href={`/s/${encodeURIComponent(s.ref)}`} data-badge={badge} className={cx('flex flex-col gap-1.5 rounded-[12px] px-3 py-2.5 transition-colors hover:bg-hover', badge === 'your_turn' && 'bg-gold-soft/50', className)}>
      <span className="flex items-start gap-2">
        <span className="line-clamp-2 min-w-0 flex-1 text-[14px] font-semibold leading-6 text-ink"><PlainText text={s.title_fa} /></span>
        <LiveBadge badge={badge} />
      </span>
      <span className="line-clamp-2 text-[12px] leading-5 text-sec"><PlainText text={s.reason_fa} /></span>
      {kept ? <span className="text-[12px] leading-5 text-silver-ink" data-playbook-kept>{PLAYBOOK_KEPT_FA}</span> : null}
      <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
        {s.holder ? <span className="inline-flex items-center gap-1"><CompanyMark code={s.holder.company} height={11} mono />{s.holder.title_fa} {s.holder.company_fa}</span> : <span>مشاور کل</span>}
        {people.length ? <span>با {people.map((p) => p.title_fa).join('، ')}</span> : null}
        {s.tasks.total ? <span><span className="fig">{s.tasks.done}</span> از <span className="fig">{s.tasks.total}</span> کار</span> : null}
        {s.pace === 'step' ? <span>{PACE_FA.step}</span> : null}
        {badge !== 'closed' ? <StallWatch badge={badge} lastAt={last.at} wokeAt={last.wokeAt} /> : null}
      </span>
      <SessionBand moving={badge === 'moving'} />
    </Link>
  );
}
