'use client';

// ⟨1.15⟩ Contract §33.8 «سفر شرکت»: from founding to the first sale and break-even on one timeline. Each stage is reached by code from existing
// rows and carries its evidence; the one line about what comes next is written only when a stage changes.

import Link from 'next/link';
import { CompanyMark } from '@/components/brand/marks';
import { Card, Empty, ErrorState, Pill, SectionTitle } from '@/components/ui/primitives';
import { FaText, fig } from '@/components/v29/text';
import { notYet } from '@/components/v31/kit';
import { useJourney, useJourneys, type Journey } from '@/lib/api/v33';
import { cx, jDate } from '@/lib/format';
import { linkRoute, refRoute } from '@/lib/refs';
import { Loading, useCompanyName } from './bits';

const progressOf = (j: Journey) => j.stages.filter((s) => s.reached_at).length;

function Evidence({ e }: { e: { kind: string; ref: string } }) {
  const href = refRoute(e.ref) ?? linkRoute(e.kind, e.ref);
  const t = <span className="fig text-[11px]">{e.ref}</span>;
  return href ? <Link href={href} className="text-gold-ink hover:underline">{t}</Link> : <span className="text-muted">{t}</span>;
}

/** One company's journey, vertical: reached stages with their date and evidence, the current one marked, the rest still ahead. */
export function JourneyTimeline({ j }: { j: Journey }) {
  return (
    <ol className="relative flex flex-col" aria-label="مرحله‌های سفر">
      {j.stages.map((s, i) => {
        const done = !!s.reached_at;
        const cur = s.key === j.current;
        return (
          <li key={s.key} className="flex gap-3" aria-current={cur ? 'step' : undefined} aria-label={`${s.title_fa}: ${done ? 'رسیده' : cur ? 'مرحله‌ی فعلی' : 'پیش رو'}`}>
            <span className="flex flex-none flex-col items-center">
              <span className={cx('mt-1 flex size-5 flex-none items-center justify-center rounded-full border-2 text-[10px] font-bold', done ? 'border-pos bg-pos text-on-gold' : cur ? 'border-gold-ink bg-gold-soft' : 'border-strong bg-tile')}>{done ? '✓' : ''}</span>
              {i < j.stages.length - 1 ? <span className={cx('w-px flex-1', done ? 'bg-pos' : 'bg-div')} /> : null}
            </span>
            <div className="flex min-w-0 flex-1 flex-col gap-0.5 pb-4">
              <span className="flex flex-wrap items-center gap-2"><span className={cx('text-[14px]', done || cur ? 'font-semibold text-ink' : 'text-muted')}>{s.title_fa}</span>{cur ? <Pill tone="gold" dot>الان این‌جا</Pill> : null}</span>
              {done ? <span className="flex flex-wrap items-center gap-x-2 text-[12px] text-sec">{jDate(s.reached_at, true)}{s.evidence ? <Evidence e={s.evidence} /> : null}</span> : <span className="text-[12px] text-muted">هنوز نرسیده</span>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function NextLine({ j }: { j: Journey }) {
  return (
    <div className="flex flex-col gap-1 rounded-[12px] bg-gold-soft p-3" aria-label="قدم بعدی">
      <h3 className="text-[12px] font-semibold text-gold-ink">قدم بعدی</h3>
      <p className="text-[14px] leading-7">{j.next_fa ? <FaText text={j.next_fa} /> : <span className="text-sec">وقتی مرحله‌ای عوض شود، یک خط درباره‌ی قدم بعدی این‌جا میاید.</span>}</p>
      {j.days_in_stage != null ? <span className="text-[11px] text-muted"><span className="fig">{fig(j.days_in_stage)}</span> روز است در همین مرحله</span> : null}
    </div>
  );
}

/** `/companies/[code]/journey`. */
export function CompanyJourney({ code }: { code: string }) {
  const q = useJourney(code);
  if (q.isLoading) return <Loading h="h-80" />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return notYet('planner', 'سفر شرکت بعد از به‌روزرسانی ستاد میاید', 'از تأسیس تا اولین فروش و سربه‌سر، روی یک خط زمان.');
  const j = q.data;
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <Card as="section" className="flex flex-col gap-3 p-5" aria-label="سفر شرکت">
        <SectionTitle title="سفر شرکت" note={<><span className="fig">{fig(progressOf(j))}</span> از <span className="fig">{fig(j.stages.length)}</span> مرحله</>} />
        <JourneyTimeline j={j} />
      </Card>
      <NextLine j={j} />
    </div>
  );
}

/** `/journeys`: every company on one timeline, the furthest first. Companies are data: any number of rows. */
export function AllJourneys() {
  const q = useJourneys();
  if (q.isLoading) return <Loading h="h-80" />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return notYet('planner', 'سفر شرکت‌ها بعد از به‌روزرسانی ستاد میاید', 'همه‌ی شرکت‌ها روی یک خط زمان.');
  if (!q.data.length) return <Card><Empty icon="companies" title="شرکتی نیست" /></Card>;
  const rows = [...q.data].sort((a, b) => progressOf(b) - progressOf(a) || a.company.localeCompare(b.company));
  return (
    <div className="flex flex-col gap-3" aria-label="سفر همه‌ی شرکت‌ها">
      {rows.map((j) => <JourneyRow key={j.company} j={j} />)}
    </div>
  );
}

function JourneyRow({ j }: { j: Journey }) {
  const { name } = useCompanyName(j.company);
  const cur = j.stages.find((s) => s.key === j.current);
  return (
    <Card as="section" className="flex flex-col gap-3 p-4" aria-label={`سفر ${name}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Link href={`/companies/${j.company}/journey`} className="inline-flex items-center gap-2 text-[15px] font-semibold hover:text-gold-ink"><CompanyMark code={j.company} height={14} mono />{name}</Link>
        <span className="text-[12px] text-sec"><span className="fig">{fig(progressOf(j))}</span> از <span className="fig">{fig(j.stages.length)}</span>{cur ? <> · الان «{cur.title_fa}»</> : ''}</span>
      </div>
      {/* The stages in a row that wraps: a dot per stage (filled when reached) with its title and date. */}
      <ol className="flex flex-wrap gap-x-1 gap-y-3">
        {j.stages.map((s) => {
          const done = !!s.reached_at;
          const here = s.key === j.current;
          return (
            <li key={s.key} className="flex w-[7.5rem] flex-col gap-1" aria-label={`${s.title_fa}: ${done ? 'رسیده' : here ? 'مرحله‌ی فعلی' : 'پیش رو'}`}>
              <span className="flex items-center gap-1"><span className={cx('size-3.5 flex-none rounded-full border-2', done ? 'border-pos bg-pos' : here ? 'border-gold-ink bg-gold-soft' : 'border-strong bg-tile')} /><span className={cx('h-px flex-1', done ? 'bg-pos' : 'bg-div')} /></span>
              <span className={cx('text-[12px] leading-5', done || here ? 'font-semibold' : 'text-muted')}>{s.title_fa}</span>
              <span className="fig text-[11px] text-muted">{s.reached_at ? jDate(s.reached_at) : here ? 'الان' : '—'}</span>
            </li>
          );
        })}
      </ol>
      {j.next_fa ? <p className="text-[12px] leading-6 text-sec"><FaText text={j.next_fa} /></p> : null}
    </Card>
  );
}
