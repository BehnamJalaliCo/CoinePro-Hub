'use client';

// The holding's live orbit and its last moments, moved off the owner's home in ⟨1.11⟩ (§29.13: nothing technical on the home) to the
// companies' page, where the companies already are. ⟨1.24⟩ The orbit's guess (direction read from `work.*` type names) is gone: the card
// shows the holding network map (components/live/holding-map.tsx), where every particle is one `holding.flow` or `server.call`.

import Link from 'next/link';
import { CompanyMark } from '@/components/brand/marks';
import { HoldingMap } from '@/components/live/holding-map';
import { Card, SectionTitle } from '@/components/ui/primitives';
import { FeedLine, feedRowOf } from '@/components/v21/feed';
import { useLive } from '@/lib/live';

export function HoldingLive() {
  const { feed } = useLive();
  // ⟨1.24⟩ What the map already draws (flows, ticks, people's states, links) is not repeated as a line.
  const rows = feed.filter((e) => !['activity.changed', 'run.step', 'llm.tick', 'employee.state', 'holding.flow', 'network.link', 'session.activity'].includes(e.type));
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="استریم زنده‌ی هلدینگ" note="ذره‌ی طلایی فرمان تو، نقره‌ای کار ایجنت‌ها، لاجوردی داده و سرورها" action={<span className="flex items-center gap-2"><Link href="/network" className="text-[12px] font-semibold text-gold-ink hover:underline">نقشه‌ی کامل</Link></span>} />
      <HoldingMap compact />
      {/* 0.4.0: each line in words — who did what to which work, by its ref and title; never an id. */}
      <ul className="flex flex-col border-t border-div pt-2" aria-label="آخرین رویدادها">
        {rows.slice(0, 4).map((e) => (
          <li key={e.id} className="flex items-center gap-2">
            {e.company ? <span className="text-sec"><CompanyMark code={e.company} height={12} mono /></span> : null}
            <span className="min-w-0 flex-1"><FeedLine r={feedRowOf(e)} compact /></span>
          </li>
        ))}
        {!rows.length ? <li className="py-1 text-[12px] text-muted">هنوز رویدادی نرسیده؛ ایجنت‌ها تا رسیدن کار خواب‌اند.</li> : null}
      </ul>
    </Card>
  );
}
