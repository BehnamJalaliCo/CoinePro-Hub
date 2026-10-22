'use client';

import { useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark, Monogram } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { CAL_KIND, CAL_RISK, CAL_STATUS, CONFLICT_RULE, RefChip, ScopeChips } from '@/components/v17/bits';
import { useCompanies } from '@/lib/api/hooks';
import { faError, useCalendar, useCalendarAction, type CalendarEvent, type CalendarIn, type CalendarKind, type Conflict } from '@/lib/api/v17';
import { useScope } from '@/lib/scope';
import { useNow } from '@/lib/store';
import { cx, jDate, jTime, jWeekday } from '@/lib/format';

const DAY = 86_400_000;
const KINDS: CalendarKind[] = ['deploy', 'freeze', 'campaign', 'event', 'maintenance', 'meeting', 'holiday'];
const OWNED: CalendarIn['kind'][] = ['campaign', 'event', 'maintenance', 'freeze'];
const field = 'w-full rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink';
const tehranDay = (iso: string) => new Date(Date.parse(iso) + 3.5 * 3_600_000).toISOString().slice(0, 10);
const dayIso = (key: string) => `${key}T08:30:00Z`;

function sourceRef(e: CalendarEvent): string | null {
  return e.source.decision ?? e.source.meeting ?? e.source.work ?? e.source.order ?? null;
}
function Span({ e }: { e: CalendarEvent }) {
  const a = tehranDay(e.starts_at), b = tehranDay(new Date(Date.parse(e.ends_at) - 1).toISOString());
  if (e.kind === 'holiday') return <span>{a === b ? 'تمام روز' : `${jDate(e.starts_at)} تا ${jDate(e.ends_at)}`}</span>;
  if (a === b) return <span className="fig">{jTime(e.starts_at)}–{jTime(e.ends_at)}</span>;
  return <span>{jDate(e.starts_at)} <span className="fig">{jTime(e.starts_at)}</span> تا {jDate(e.ends_at)} <span className="fig">{jTime(e.ends_at)}</span></span>;
}

/** Lanes per company across the days (right to left, the Jalali way); a bar per event, a conflict ringed in red. */
function Lanes({ events, conflicts, from, days }: { events: CalendarEvent[]; conflicts: Conflict[]; from: string; days: number }) {
  const { data: companies } = useCompanies();
  const lanes = [...new Set(events.map((e) => e.company ?? '*'))].sort((a, b) => (a === '*' ? -1 : b === '*' ? 1 : a === 'HQ' ? -1 : b === 'HQ' ? 1 : a.localeCompare(b)));
  const hot = new Set(conflicts.flatMap((c) => [c.a, c.b]));
  const keys = Array.from({ length: days }, (_, i) => new Date(Date.parse(dayIso(from)) + i * DAY).toISOString().slice(0, 10));
  const now = useNow();
  const today = now ? tehranDay(new Date(now).toISOString()) : '';
  const col = (iso: string) => Math.max(0, Math.min(days - 1, keys.indexOf(tehranDay(iso)) === -1 ? (iso < dayIso(from) ? 0 : days - 1) : keys.indexOf(tehranDay(iso))));
  const name = (c: string) => (c === '*' ? 'همه' : companies?.find((x) => x.code === c)?.name_fa ?? c);
  return (
    <Card className="hidden flex-col gap-2 p-4 md:flex">
      <SectionTitle title="نمای کلی" note={`${days} روز؛ امروز با خط طلایی`} />
      <div className="grid gap-y-1.5" style={{ gridTemplateColumns: `7rem repeat(${days}, minmax(0, 1fr))` }}>
        <span />
        {keys.map((k, i) => <span key={k} className={cx('text-center text-[10px] text-muted', k === today && 'font-semibold text-gold-ink')}>{i % 7 === 0 || k === today ? jDate(dayIso(k)) : ''}</span>)}
        {lanes.map((lane, li) => (
          <div key={lane} className="contents">
            <span className="flex items-center gap-1.5 truncate text-[12px] text-sec" style={{ gridRow: li + 2, gridColumn: 1 }}>{lane === '*' ? null : lane === 'HQ' ? <Monogram size={12} /> : <CompanyMark code={lane} height={12} mono />}{name(lane)}</span>
            {keys.map((k, i) => <span key={k} className={cx('h-7 border-s border-div', k === today && 'border-s-2 border-[var(--hq-gold-ink)]')} style={{ gridRow: li + 2, gridColumn: i + 2 }} />)}
            {events.filter((e) => (e.company ?? '*') === lane && e.status !== 'cancelled').map((e) => {
              const a = col(e.starts_at), b = col(new Date(Date.parse(e.ends_at) - 1).toISOString());
              return (
                <span key={e.ref} title={`${CAL_KIND[e.kind]?.fa}: ${e.title_fa}`} className={cx('z-[1] mx-px h-5 self-center rounded-[6px]', hot.has(e.ref) && 'ring-2 ring-[var(--hq-negative)]', e.status === 'done' && 'opacity-50')}
                  style={{ gridRow: li + 2, gridColumn: `${a + 2} / ${b + 3}`, background: CAL_KIND[e.kind]?.color ?? 'var(--hq-silver-ink)', opacity: e.kind === 'freeze' || e.kind === 'campaign' || e.kind === 'holiday' ? 0.55 : 1 }} />
              );
            })}
          </div>
        ))}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 pt-1">{KINDS.map((k) => <li key={k} className="flex items-center gap-1.5 text-[11px] text-sec"><span className="size-2.5 rounded-[3px]" style={{ background: CAL_KIND[k]!.color }} />{CAL_KIND[k]!.fa}</li>)}</ul>
    </Card>
  );
}

function EventRow({ e, flags }: { e: CalendarEvent; flags: Conflict[] }) {
  const act = useCalendarAction();
  const toast = useToast();
  const k = CAL_KIND[e.kind] ?? { fa: e.kind, icon: 'time' as const, color: 'var(--hq-silver-ink)' };
  const r = CAL_RISK[e.risk];
  const ref = sourceRef(e);
  const mine = (OWNED as string[]).includes(e.kind) && e.status === 'planned';
  const set = (status: CalendarEvent['status'], ok: string) => act.patch.mutateAsync({ e, patch: { status } }).then(() => toast({ tone: 'ok', text: ok })).catch((x) => toast({ tone: 'error', text: faError(x) }));
  return (
    <li className={cx('flex flex-col gap-2 rounded-[12px] border border-div p-3', flags.some((f) => f.severity === 'high') && 'border-[var(--hq-neg-line)]', e.status !== 'planned' && 'opacity-60')}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex size-7 flex-none items-center justify-center rounded-[8px] text-on-gold" style={{ background: k.color }}><Icon name={k.icon} size={15} /></span>
        <span className="min-w-0 flex-[1_1_10rem] text-[14px] font-semibold text-ink">{e.title_fa}</span>
        {e.company ? (e.company === 'HQ' ? <Monogram size={12} /> : <CompanyMark code={e.company} height={12} mono />) : null}
        <Pill className="h-5 text-[11px]">{k.fa}</Pill>
        {e.kind === 'deploy' && r ? <Pill tone={r.tone} dot className="h-5 text-[11px]">{r.fa}</Pill> : null}
        {e.status !== 'planned' ? <Pill className="h-5 text-[11px]">{CAL_STATUS[e.status]}</Pill> : null}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-muted">
        <Span e={e} />
        {ref ? <RefChip r={ref} tone="neutral" /> : null}
        <span className="fig">{e.ref}</span>
        <span className="flex-1" />
        {mine ? <><Button size="sm" variant="ghost" onClick={() => void set('done', 'انجام‌شده ثبت شد.')}>انجام شد</Button><Button size="sm" variant="ghost" onClick={() => void set('cancelled', 'لغو شد.')}>لغو</Button></> : null}
      </div>
      {flags.map((f, i) => (
        <p key={i} className={cx('flex items-start gap-2 rounded-[8px] px-2 py-1.5 text-[12px] leading-5', f.severity === 'high' ? 'bg-neg-soft text-ink' : 'bg-warn-soft text-ink')}>
          <span className={f.severity === 'high' ? 'text-neg' : 'text-warn'}><Icon name="urgent" size={13} /></span>
          <span><span className="font-semibold">{CONFLICT_RULE[f.rule] ?? f.rule}</span> · {f.note_fa}</span>
        </p>
      ))}
    </li>
  );
}

function NewEvent({ onClose }: { onClose: () => void }) {
  const act = useCalendarAction();
  const toast = useToast();
  const [company, setCompany] = useState<string | null>(null);
  const [kind, setKind] = useState<CalendarIn['kind']>('campaign');
  const [title, setTitle] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [risk, setRisk] = useState<CalendarEvent['risk']>('low');
  const valid = !!title.trim() && !!from && !!to && to > from;
  const save = () => act.create.mutateAsync({ company, kind, title_fa: title.trim(), starts_at: new Date(from).toISOString(), ends_at: new Date(to).toISOString(), risk })
    .then((e) => { toast({ tone: 'ok', text: <>رویداد <span className="fig">{e.ref}</span> در تقویم ثبت شد؛ تداخل‌ها را کد میسنجد.</> }); onClose(); })
    .catch((e) => toast({ tone: 'error', text: faError(e) }));
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title="رویداد تازه در تقویم" description="انتشارها از کارت‌های deploy، جلسه‌ها و تعطیلی‌ها خودکار میایند." width={520}
      footer={<Button variant="primary" icon="add" className="w-full" disabled={!valid} loading={act.create.isPending} onClick={() => void save()}>ثبت</Button>}>
      <div className="flex flex-col gap-4 text-[13px]">
        <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">کجا</span><ScopeChips value={company} onChange={setCompany} allLabel="همه‌ی شرکت‌ها" /></div>
        <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">نوع</span><div className="flex flex-wrap gap-2">{OWNED.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{CAL_KIND[k]!.fa}</FilterChip>)}</div></div>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">عنوان<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} className={cx(field, 'h-10')} /></label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5 font-semibold text-sec">از<input type="datetime-local" dir="ltr" value={from} onChange={(e) => setFrom(e.target.value)} className={cx(field, 'fig h-10')} /></label>
          <label className="flex flex-col gap-1.5 font-semibold text-sec">تا<input type="datetime-local" dir="ltr" value={to} onChange={(e) => setTo(e.target.value)} className={cx(field, 'fig h-10')} /></label>
        </div>
        <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">ریسک</span><div className="flex flex-wrap gap-2">{(['low', 'medium', 'high'] as const).map((r) => <FilterChip key={r} selected={risk === r} onClick={() => setRisk(r)}>{CAL_RISK[r]!.fa}</FilterChip>)}</div></div>
      </div>
    </Sheet>
  );
}

/** تقویم تغییرات (contract §20.9): deploys, freezes, campaigns, events, maintenance, meetings and the official holidays, with the
 *  conflicts the code finds. The calendar never decides: a deploy card stays the owner's. */
export default function CalendarPage() {
  const { company: scope } = useScope();
  const { data: companies } = useCompanies();
  const [picked, setPicked] = useState<string | null | undefined>(undefined);
  const raw = picked !== undefined ? picked : scope;
  const company = companies?.find((c) => c.code === raw)?.kind === 'holding' ? null : raw;
  const [kind, setKind] = useState<CalendarKind | null>(null);
  const [create, setCreate] = useState(false);
  const now = useNow();
  // Whole days, so the range (and the query) only moves once a day.
  const from = now ? tehranDay(new Date(now - 7 * DAY).toISOString()) : '';
  const to = now ? tehranDay(new Date(now + 35 * DAY).toISOString()) : '';
  const q = useCalendar({ company, from, to, kind });
  const events = useMemo(() => q.data?.events ?? [], [q.data]);
  const conflicts = useMemo(() => q.data?.conflicts ?? [], [q.data]);
  const byRef = useMemo(() => new Map(events.map((e) => [e.ref, e])), [events]);
  const today = now ? tehranDay(new Date(now).toISOString()) : '';
  const days = useMemo(() => {
    const m = new Map<string, CalendarEvent[]>();
    for (const e of events) {
      const d = tehranDay(e.starts_at) < today && Date.parse(e.ends_at) > now ? today : tehranDay(e.starts_at);
      m.set(d, [...(m.get(d) ?? []), e]);
    }
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [events, today, now]);
  const [past, setPast] = useState(false);
  const shown = days.filter(([d]) => past || d >= today);
  const high = conflicts.filter((c) => c.severity === 'high').length;
  return (
    <>
      <PageHeader eyebrow="انتشار، فریز، کمپین، جلسه و تعطیلی؛ تقویم تصمیم نمیگیرد" title="تقویم تغییرات" actions={<Button variant="primary" icon="add" onClick={() => setCreate(true)}>رویداد تازه</Button>}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">کد از کارت‌های deploy، فریزها، جلسه‌ها، پنجره‌های backup و تعطیلی‌های رسمی پرش میکند. انتشار داخل فریز یا هم‌زمان با کمپین همان شرکت تداخل «بالا» است؛ دو انتشار هم‌زمان، روز ممنوع ماتریس اختیار، تعطیلی و نگه‌داری هم‌زمان «متوسط». تداخل روی خود کارت deploy هم میاید.</p>
      </PageHeader>
      <div className="flex flex-col gap-2">
        <ScopeChips value={company} onChange={setPicked} allLabel="همه" holding={false} />
        <div className="flex flex-wrap gap-2"><FilterChip selected={!kind} onClick={() => setKind(null)}>همه‌ی نوع‌ها</FilterChip>{KINDS.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{CAL_KIND[k]!.fa}</FilterChip>)}</div>
      </div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data ? <Skeleton className="h-80" /> : (
        <>
          {conflicts.length ? (
            <Card className={cx('flex flex-col gap-2 p-4', high ? 'bg-neg-soft' : 'bg-warn-soft')}>
              <SectionTitle title={`${conflicts.length} تداخل`} note={high ? `${high} تداخل بالا` : 'همه متوسط'} />
              <ul className="flex flex-col gap-1.5">
                {conflicts.map((c, i) => {
                  const a = byRef.get(c.a), b = byRef.get(c.b);
                  return (
                    <li key={i} className="flex flex-wrap items-center gap-2 text-[13px]">
                      <Pill tone={c.severity === 'high' ? 'neg' : 'warn'} dot className="h-5 text-[11px]">{c.severity === 'high' ? 'بالا' : 'متوسط'}</Pill>
                      <span className="font-semibold text-ink">{a?.title_fa ?? c.a}</span>
                      {c.b !== c.a ? <><span className="text-muted">با</span><span className="text-ink">{b?.title_fa ?? c.b}</span></> : null}
                      <span className="text-sec">· {CONFLICT_RULE[c.rule] ?? c.rule}</span>
                    </li>
                  );
                })}
              </ul>
            </Card>
          ) : null}
          <Lanes events={events} conflicts={conflicts} from={from} days={42} />
          <div className="flex flex-col gap-4">
            {days.some(([d]) => d < today) ? <Button size="sm" variant="ghost" className="self-start" onClick={() => setPast(!past)}>{past ? 'پنهان کردن گذشته' : 'نشان دادن هفته‌ی گذشته'}</Button> : null}
            {!shown.length ? <Card><Empty icon="time" title="رویدادی در این بازه نیست" /></Card> : shown.map(([d, xs]) => (
              <section key={d} className="flex flex-col gap-2">
                <h2 className={cx('text-[14px] font-semibold', d === today ? 'text-gold-ink' : 'text-ink')}>{d === today ? 'امروز، ' : ''}{jWeekday(dayIso(d))}</h2>
                <ul className="grid gap-2 lg:grid-cols-2">{xs.map((e) => <EventRow key={e.ref} e={e} flags={conflicts.filter((c) => c.a === e.ref)} />)}</ul>
              </section>
            ))}
          </div>
        </>
      )}
      {create ? <NewEvent onClose={() => setCreate(false)} /> : null}
    </>
  );
}
