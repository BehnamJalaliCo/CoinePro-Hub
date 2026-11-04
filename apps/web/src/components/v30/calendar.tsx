'use client';

// ⟨1.12⟩ Contract §30.5 the publishing calendar: every company's lines by day (what goes out when and where, and how each run went),
// a week at a time, optionally one company.

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, FilterChip, Pill, Skeleton } from '@/components/ui/primitives';
import { useCompanies } from '@/lib/api/hooks';
import { RUN_STATE_FA, LINE_STATE_FA, platformFa, useCalendar, type CalendarItem, type LineState, type RunState } from '@/lib/api/v30';
import { jDate, jTime, jWeekday } from '@/lib/format';
import { FaText } from './bits';

const iso = (d: Date) => d.toISOString().slice(0, 10);
const addDays = (d: string, n: number) => iso(new Date(Date.parse(`${d}T12:00:00Z`) + n * 86_400_000));

function StateOf({ it }: { it: CalendarItem }) {
  const r = RUN_STATE_FA[it.state as RunState];
  if (r) return <Pill tone={r.tone} dot={!r.live} live={r.live}>{r.fa}</Pill>;
  const l = LINE_STATE_FA[it.state as LineState];
  return l ? <Pill tone={l.tone} dot>{l.fa}</Pill> : <Pill>{it.state}</Pill>;
}

export function LinesCalendar() {
  const [from, setFrom] = useState(() => iso(new Date()));
  const [company, setCompany] = useState<string | null>(null);
  const to = addDays(from, 6);
  const q = useCalendar(from, to, company);
  const cs = useCompanies();
  const name = (code: string) => cs.data?.find((c) => c.code === code)?.name_fa ?? code;
  const days = useMemo(() => (q.data ?? []).filter((d) => d.items.length).sort((a, b) => a.day.localeCompare(b.day)), [q.data]);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" icon="next" aria-label="هفته‌ی قبل" className="[&_svg]:rotate-180" onClick={() => setFrom(addDays(from, -7))} />
        <span className="min-w-0 flex-1 text-center text-[14px] font-semibold">{jDate(`${from}T12:00:00Z`, true)} تا {jDate(`${to}T12:00:00Z`, true)}</span>
        <Button size="sm" icon="back" aria-label="هفته‌ی بعد" className="[&_svg]:rotate-180" onClick={() => setFrom(addDays(from, 7))} />
        <Button size="sm" onClick={() => setFrom(iso(new Date()))}>امروز</Button>
      </div>
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1" role="group" aria-label="شرکت">
        <FilterChip selected={company === null} onClick={() => setCompany(null)}>همه</FilterChip>
        {(cs.data ?? []).filter((c) => c.code !== 'HQ').map((c) => <FilterChip key={c.code} selected={company === c.code} onClick={() => setCompany(c.code)}>{c.name_fa ?? c.code}</FilterChip>)}
      </div>
      {q.isLoading ? <Skeleton className="h-64 rounded-[16px]" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data === null ? (
        <Card><Empty icon="planner" title="تقویم انتشار بعد از به‌روزرسانی ستاد میاید" body="هر خطی که زمان‌بندی دارد این‌جا روزش را پیدا میکند." /></Card>
      ) : !days.length ? (
        <Card><Empty icon="planner" title="این هفته چیزی منتشر نمیشود" body="زمان‌بندی خط‌ها را از صفحه‌ی هر خط بگذار." /></Card>
      ) : (
        <div className="flex flex-col gap-3">
          {days.map((d) => (
            <Card key={d.day} as="section" className="hq-rise flex flex-col gap-1 p-4" aria-label={`روز ${jDate(`${d.day}T12:00:00Z`)}`}>
              <h2 className="pb-1 text-[14px] font-semibold">{jWeekday(`${d.day}T12:00:00Z`)}، {jDate(`${d.day}T12:00:00Z`)}</h2>
              <ul className="flex flex-col">
                {d.items.sort((a, b) => a.at.localeCompare(b.at)).map((it, i) => (
                  <li key={`${it.line}-${it.at}-${i}`} className="flex flex-wrap items-center gap-3 border-t border-div py-2.5 first:border-0">
                    <span className="fig w-12 text-[13px] font-semibold">{jTime(it.at)}</span>
                    <span className="inline-flex min-w-0 flex-[1_1_10rem] items-center gap-2 text-[13px]"><CompanyMark code={it.company} height={12} mono />{name(it.company)}<span className="text-muted">· {platformFa(it.platform)}</span></span>
                    <Link href={`/lines/${it.line}`} className="text-[12px] font-semibold text-gold-ink hover:underline"><FaText text={it.title_fa ?? it.line} /></Link>
                    <StateOf it={it} />
                    {it.run ? <Link href={`/line-runs/${it.run}`} className="text-[12px] text-sec hover:text-ink"><span className="fig">{it.run}</span></Link> : null}
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
