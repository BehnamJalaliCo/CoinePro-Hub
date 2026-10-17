'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Button, IconButton } from '@/components/ui/button';
import { Card, ErrorState, PageHeader, Segmented, Skeleton } from '@/components/ui/primitives';
import { NewOrder } from '@/components/work/new-order';
import { usePlanner } from '@/lib/api/hooks';
import { companyColor } from '@/lib/company';
import { useCompanies } from '@/lib/api/hooks';
import { useScope } from '@/lib/scope';
import { WORK_STATUS } from '@/lib/labels';
import { cx, jTime } from '@/lib/format';

const fmtDay = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'Asia/Tehran' });
const fmtRange = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Tehran' });
const gRange = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'Asia/Tehran' });

/** The Persian week starts on Saturday; the calendar runs right→left (planner rule). */
function weekStart(d: Date) {
  const day = (d.getUTCDay() + 1) % 7; // Sat = 0
  const s = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - day));
  return s;
}

export default function PlannerPage() {
  const { company } = useScope();
  const { data: companies } = useCompanies();
  const [offset, setOffset] = useState(0);
  const [view, setView] = useState<'week' | 'agenda'>('week');
  const [order, setOrder] = useState(false);
  const start = useMemo(() => { const s = weekStart(new Date()); s.setUTCDate(s.getUTCDate() + offset * 7); return s; }, [offset]);
  const end = useMemo(() => { const e = new Date(start); e.setUTCDate(e.getUTCDate() + 6); return e; }, [start]);
  const q = usePlanner({ from: start.toISOString().slice(0, 10), to: end.toISOString().slice(0, 10) });
  const todayKey = new Date().toISOString().slice(0, 10);
  const days = Array.from({ length: 7 }, (_, i) => { const d = new Date(start); d.setUTCDate(d.getUTCDate() + i); const key = d.toISOString().slice(0, 10); return { key, date: d, items: (q.data?.days.find((x) => x.date === key)?.items ?? []).filter((it) => !company || it.company === company) }; });

  return (
    <>
      <PageHeader eyebrow={<span>{fmtRange.format(start)} تا {fmtRange.format(end)} · <span className="fig" dir="ltr">{gRange.format(start)} – {gRange.format(end)}</span></span>} title="پلنر" actions={<>
        <IconButton icon="next" label="هفته‌ی قبل" onClick={() => setOffset(offset - 1)} />
        <Button variant="secondary" size="sm" onClick={() => setOffset(0)}>این هفته</Button>
        <IconButton icon="next" label="هفته‌ی بعد" mirror onClick={() => setOffset(offset + 1)} />
        <Button variant="primary" icon="command" onClick={() => setOrder(true)}>فرمان تازه</Button>
      </>}>
        <div className="max-w-xs"><Segmented label="نما" value={view} onChange={setView} options={[{ value: 'week', label: 'هفته' }, { value: 'agenda', label: 'فهرست' }]} /></div>
      </PageHeader>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-[480px] rounded-[16px]" /> : view === 'week' ? (
        <div className="overflow-x-auto no-scrollbar">
          <div className="grid min-w-[980px] grid-cols-7 gap-2">
            {days.map((d) => (
              <Card key={d.key} className={cx('flex min-h-[420px] flex-col gap-2 p-2.5', d.key === todayKey && 'tahrir')}>
                <div className="flex items-center gap-2 px-1 pb-1">
                  <span className={cx('text-[13px] font-semibold', d.key === todayKey ? 'text-gold-ink' : 'text-ink')}>{fmtDay.format(d.date).split(' ')[0]}</span>
                  <span className="text-[12px] text-muted">{fmtDay.format(d.date).split(' ').slice(1).join(' ')}</span>
                </div>
                {d.items.map((it) => (
                  <Link key={it.ref} href={`/work/${it.ref}`} className="flex flex-col gap-1 rounded-[10px] bg-tile p-2.5 hover:bg-hover" style={{ boxShadow: `inset -3px 0 0 ${companyColor(companies, it.company)}` }}>
                    <span className="flex items-center gap-1.5 text-[11px] text-muted">{jTime(it.at)}{it.recurring ? <Icon name="refresh" size={12} /> : null}<span className="flex-1" /><CompanyMark code={it.company} height={11} mono /></span>
                    <span className={cx('text-[13px] leading-5', it.status === 'done' ? 'text-muted line-through' : 'text-ink')}>{it.title}</span>
                    <span className="flex items-center gap-1.5 text-[11px]"><span className={cx('fig rounded-[4px] px-1', it.priority <= 'P1' ? 'bg-neg-soft text-neg' : 'text-muted')}>{it.priority}</span><span className="text-muted">{WORK_STATUS[it.status] ?? it.status}</span></span>
                  </Link>
                ))}
                {!d.items.length ? <span className="px-1 pt-2 text-[12px] text-muted">آزاد</span> : null}
              </Card>
            ))}
          </div>
        </div>
      ) : (
        <Card className="flex flex-col p-2">
          {days.filter((d) => d.items.length).map((d) => (
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
