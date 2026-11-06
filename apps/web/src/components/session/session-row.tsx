'use client';

// One session in a list (the office, «جلسه‌ها»): the order's words, the badge in words, why, whose it is, who is in it and how far its tasks are.

import Link from 'next/link';
import { CompanyMark } from '@/components/brand/marks';
import { PlainText } from '@/components/v29/bits';
import { PACE_FA, type SessionCard } from '@/lib/api/v34';
import { cx } from '@/lib/format';
import { BadgePill } from './session-view';

export function SessionRow({ s, className }: { s: SessionCard; className?: string }) {
  const people = s.participants.filter((p) => p.kind !== 'holder');
  return (
    <Link href={`/s/${encodeURIComponent(s.ref)}`} data-badge={s.badge} className={cx('flex flex-col gap-1.5 rounded-[12px] px-3 py-2.5 transition-colors hover:bg-hover', s.badge === 'your_turn' && 'bg-gold-soft/50', className)}>
      <span className="flex items-start gap-2">
        <span className="line-clamp-2 min-w-0 flex-1 text-[14px] font-semibold leading-6 text-ink"><PlainText text={s.title_fa} /></span>
        <BadgePill badge={s.badge} />
      </span>
      <span className="line-clamp-2 text-[12px] leading-5 text-sec"><PlainText text={s.reason_fa} /></span>
      <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
        {s.holder ? <span className="inline-flex items-center gap-1"><CompanyMark code={s.holder.company} height={11} mono />{s.holder.title_fa} {s.holder.company_fa}</span> : <span>مشاور کل</span>}
        {people.length ? <span>با {people.map((p) => p.title_fa).join('، ')}</span> : null}
        {s.tasks.total ? <span><span className="fig">{s.tasks.done}</span> از <span className="fig">{s.tasks.total}</span> کار</span> : null}
        {s.pace === 'step' ? <span>{PACE_FA.step}</span> : null}
      </span>
    </Link>
  );
}
