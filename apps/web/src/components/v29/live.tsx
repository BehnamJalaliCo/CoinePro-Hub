'use client';

// The holding's live orbit and its last moments, moved off the owner's home in ⟨1.11⟩ (§29.13: nothing technical on the home) to the
// companies' page, where the companies already are. The same card the home had.

import { CompanyMark } from '@/components/brand/marks';
import { Orbit } from '@/components/live/orbit';
import { Card, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { FeedLine, feedRowOf } from '@/components/v21/feed';
import { useCompanies } from '@/lib/api/hooks';
import { useLive } from '@/lib/live';

export function HoldingLive() {
  const { data: companies } = useCompanies();
  const { last, feed, state } = useLive();
  const rows = feed.filter((e) => e.type !== 'activity.changed' && e.type !== 'run.step');
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="استریم زنده‌ی هلدینگ" note="ذره‌ی طلایی فرمان تو، نقره‌ای تحویل ایجنت‌ها" action={<Pill tone={state === 'live' ? 'pos' : 'warn'} live={state === 'live'}>{state === 'live' ? 'زنده' : 'در حال اتصال'}</Pill>} />
      {companies ? <Orbit companies={companies} lastEvent={last} size={460} /> : <Skeleton className="mx-auto aspect-square w-full max-w-[520px] rounded-full" />}
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
