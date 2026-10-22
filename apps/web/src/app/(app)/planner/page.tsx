'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Button, IconButton } from '@/components/ui/button';
import { Card, ErrorState, FilterChip, PageHeader, Segmented, Skeleton } from '@/components/ui/primitives';
import { NewOrder } from '@/components/work/new-order';
import { useCompanies, useDepartments, usePlanner } from '@/lib/api/hooks';
import { companyColor } from '@/lib/company';
import { useScope } from '@/lib/scope';
import { WORK_STATUS } from '@/lib/labels';
import { cx, jTime } from '@/lib/format';

const TZ = 'Asia/Tehran';
const fmtDay = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { weekday: 'long', day: 'numeric', month: 'long', timeZone: TZ });
const fmtRange = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { day: 'numeric', month: 'long', year: 'numeric', timeZone: TZ });
const fmtMonth = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { month: 'long', year: 'numeric', timeZone: TZ });
const pDay = new Intl.DateTimeFormat('en-u-ca-persian', { day: 'numeric', timeZone: TZ });
const gRange = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: TZ });
const WEEKDAYS = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'];

const utc = (d: Date) => new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
const addDays = (d: Date, n: number) => { const x = new Date(d); x.setUTCDate(x.getUTCDate() + n); return x; };
const key = (d: Date) => d.toISOString().slice(0, 10);
/** The Persian week starts on Saturday; the calendar runs right→left (planner rule). */
const weekStart = (d: Date) => addDays(utc(d), -((d.getUTCDay() + 1) % 7));
const jDayOf = (d: Date) => Number(pDay.format(new Date(`${key(d)}T12:00:00Z`)));
const jStart = (d: Date) => addDays(d, 1 - jDayOf(d));
/** First and last day of the Persian month `offset` months from today (a month is at most 31 days, so +32 lands in the next one). */
function jMonth(offset: number) {
  let first = jStart(utc(new Date()));
  for (let i = 0; i < Math.abs(offset); i++) first = offset > 0 ? jStart(addDays(first, 32)) : jStart(addDays(first, -1));
  return { first, last: addDays(jStart(addDays(first, 32)), -1) };
}

type Item = { ref: string; title: string; company: string; priority: string; status: string; at: string; recurring: boolean };

function Chip({ it, companies }: { it: Item; companies: ReturnType<typeof useCompanies>['data'] }) {
  return (
    <Link href={`/work/${it.ref}`} className="flex flex-col gap-1 rounded-[10px] bg-tile p-2.5 hover:bg-hover" style={{ boxShadow: `inset -3px 0 0 ${companyColor(companies, it.company)}` }}>
      <span className="flex items-center gap-1.5 text-[11px] text-muted">{jTime(it.at)}{it.recurring ? <Icon name="refresh" size={12} /> : null}<span className="flex-1" /><CompanyMark code={it.company} height={11} mono /></span>
      <span className={cx('text-[13px] leading-5', it.status === 'done' ? 'text-muted line-through' : 'text-ink')}>{it.title}</span>
      <span className="flex items-center gap-1.5 text-[11px]"><span className={cx('fig rounded-[4px] px-1', it.priority <= 'P1' ? 'bg-neg-soft text-neg' : 'text-muted')}>{it.priority}</span><span className="text-muted">{WORK_STATUS[it.status] ?? it.status}</span></span>
    </Link>
  );
}

/** The three-level planner (§1.9): the owner's, a company's or a department's; a view over work, by week, month or list. */
export default function PlannerPage() {
  const { company } = useScope();
  const { data: companies } = useCompanies();
  const depts = useDepartments(company ?? '');
  const [dept, setDept] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [view, setView] = useState<'week' | 'month' | 'agenda'>('week');
  const [order, setOrder] = useState(false);
  const range = useMemo(() => {
    if (view === 'month') return jMonth(offset);
    const first = addDays(weekStart(new Date()), offset * 7);
    return { first, last: addDays(first, 6) };
  }, [view, offset]);
  const scope = company ? (dept ? `department:${company}-${dept}` : `company:${company}`) : 'owner';
  const q = usePlanner({ from: key(range.first), to: key(range.last), scope } as never);
  const todayKey = key(new Date());
  const dayList = useMemo(() => {
    const out: Array<{ key: string; date: Date; items: Item[] }> = [];
    for (let d = range.first; d <= range.last; d = addDays(d, 1)) out.push({ key: key(d), date: d, items: (q.data?.days.find((x) => x.date === key(d))?.items ?? []) as Item[] });
    return out;
  }, [range, q.data]);
  const unit = view === 'month' ? 'ماه' : 'هفته';
  const setV = (v: typeof view) => { setView(v); setOffset(0); };

  return (
    <>
      <PageHeader eyebrow={view === 'month' ? fmtMonth.format(addDays(range.first, 10)) : <span>{fmtRange.format(range.first)} تا {fmtRange.format(range.last)} · <span className="fig" dir="ltr">{gRange.format(range.first)} – {gRange.format(range.last)}</span></span>}
        title={company ? <span className="flex items-center gap-2">پلنر <CompanyMark code={company} height={18} /></span> : 'پلنر'} actions={<>
          <IconButton icon="next" label={`${unit}ی قبل`} onClick={() => setOffset(offset - 1)} />
          <Button variant="secondary" size="sm" onClick={() => setOffset(0)}>{view === 'month' ? 'این ماه' : 'این هفته'}</Button>
          <IconButton icon="next" label={`${unit}ی بعد`} mirror onClick={() => setOffset(offset + 1)} />
          <Button variant="primary" icon="command" onClick={() => setOrder(true)}>فرمان تازه</Button>
        </>}>
        <div className="flex flex-wrap items-center gap-3">
          <div className="w-64"><Segmented label="نما" value={view} onChange={setV} options={[{ value: 'week', label: 'هفته' }, { value: 'month', label: 'ماه' }, { value: 'agenda', label: 'فهرست' }]} /></div>
          {company ? (
            <div className="flex flex-wrap gap-2">
              <FilterChip selected={!dept} onClick={() => setDept(null)}>همه‌ی شرکت</FilterChip>
              {(depts.data ?? []).filter((d) => d.status === 'active').map((d) => <FilterChip key={d.code} selected={dept === d.code} onClick={() => setDept(d.code)}>{d.name_fa}</FilterChip>)}
            </div>
          ) : <span className="text-[12px] text-muted">پلنر تو؛ برای پلنر مدیرعامل یا یک دپارتمان، بالای صفحه شرکت را انتخاب کن.</span>}
        </div>
      </PageHeader>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-[480px] rounded-[16px]" /> : view === 'week' ? (
        <div className="overflow-x-auto no-scrollbar">
          <div className="grid min-w-[980px] grid-cols-7 gap-2">
            {dayList.map((d) => (
              <Card key={d.key} className={cx('flex min-h-[420px] flex-col gap-2 p-2.5', d.key === todayKey && 'tahrir')}>
                <div className="flex items-center gap-2 px-1 pb-1">
                  <span className={cx('text-[13px] font-semibold', d.key === todayKey ? 'text-gold-ink' : 'text-ink')}>{fmtDay.format(d.date).split(' ')[0]}</span>
                  <span className="text-[12px] text-muted">{fmtDay.format(d.date).split(' ').slice(1).join(' ')}</span>
                </div>
                {d.items.map((it) => <Chip key={it.ref} it={it} companies={companies} />)}
                {!d.items.length ? <span className="px-1 pt-2 text-[12px] text-muted">آزاد</span> : null}
              </Card>
            ))}
          </div>
        </div>
      ) : view === 'month' ? (
        <div className="overflow-x-auto no-scrollbar">
          <div className="grid min-w-[760px] grid-cols-7 gap-1.5">
            {WEEKDAYS.map((w) => <span key={w} className="pb-1 text-center text-[12px] text-muted">{w}</span>)}
            {Array.from({ length: (range.first.getUTCDay() + 1) % 7 }, (_, i) => <span key={`pad${i}`} />)}
            {dayList.map((d) => (
              <Card key={d.key} className={cx('flex min-h-[112px] flex-col gap-1 p-1.5', d.key === todayKey && 'tahrir')}>
                <span className={cx('fig px-1 text-[12px] font-semibold', d.key === todayKey ? 'text-gold-ink' : 'text-sec')}>{jDayOf(d.date)}</span>
                {d.items.slice(0, 3).map((it) => (
                  <Link key={it.ref} href={`/work/${it.ref}`} title={it.title} className={cx('truncate rounded-[6px] bg-tile px-1.5 py-0.5 text-[11px] hover:bg-hover', it.status === 'done' ? 'text-muted line-through' : 'text-ink')} style={{ boxShadow: `inset -2px 0 0 ${companyColor(companies, it.company)}` }}>{it.title}</Link>
                ))}
                {d.items.length > 3 ? <button type="button" onClick={() => { setView('week'); setOffset(Math.floor((weekStart(d.date).getTime() - weekStart(new Date()).getTime()) / (7 * 86_400_000))); }} className="px-1 text-start text-[11px] text-gold-ink hover:underline">و {(d.items.length - 3).toLocaleString('fa-IR')} مورد دیگر</button> : null}
              </Card>
            ))}
          </div>
        </div>
      ) : (
        <Card className="flex flex-col p-2">
          {!dayList.some((d) => d.items.length) ? <p className="p-6 text-center text-[13px] text-muted">در این بازه کاری نیست.</p> : null}
          {dayList.filter((d) => d.items.length).map((d) => (
            <section key={d.key} className="flex flex-col">
              <h2 className={cx('px-3 pb-1 pt-4 text-[13px] font-semibold', d.key === todayKey ? 'text-gold-ink' : 'text-sec')}>{fmtDay.format(d.date)}</h2>
              {d.items.map((it) => (
                <Link key={it.ref} href={`/work/${it.ref}`} className="flex items-center gap-3 rounded-[12px] px-3 py-2.5 hover:bg-hover">
                  <span className="w-12 text-[12px] text-muted">{jTime(it.at)}</span>
                  <span className="h-6 w-1 rounded-full" style={{ background: companyColor(companies, it.company) }} />
                  <span className="flex-1 truncate text-[14px]">{it.title}</span>
                  <CompanyMark code={it.company} height={12} mono />
                  <span className="text-[12px] text-muted">{WORK_STATUS[it.status] ?? it.status}</span>
                </Link>
              ))}
            </section>
          ))}
        </Card>
      )}
      <NewOrder open={order} onOpenChange={setOrder} company={company} />
    </>
  );
}
