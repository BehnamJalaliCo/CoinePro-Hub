'use client';

import Link from 'next/link';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Orbit } from '@/components/live/orbit';
import { DecisionRow } from '@/components/cartable/decision-row';
import { Button } from '@/components/ui/button';
import { Bar, Card, Empty, ErrorState, Pill, SectionTitle, Skeleton, StatTile, budgetTone } from '@/components/ui/primitives';
import { useAway, useCompanies, useDecisions, useInbox, usePlanner, usePresence, useTreasury } from '@/lib/api/hooks';
import { useLive } from '@/lib/live';
import { useScope } from '@/lib/scope';
import { WORK_STATUS } from '@/lib/labels';
import { ago, cx, jTime, jWeekday, tokens, usd } from '@/lib/format';

function Greeting() {
  const { data: presence } = usePresence();
  const today = new Date();
  const g = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(today);
  const h = Number(new Intl.DateTimeFormat('en-US', { hour: 'numeric', hourCycle: 'h23', timeZone: 'Asia/Tehran' }).format(today));
  const hello = h < 12 ? 'صبح بخیر' : h < 17 ? 'روز بخیر' : 'عصر بخیر';
  return (
    <header className="flex flex-wrap items-end gap-x-4 gap-y-2">
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-caption text-muted">{jWeekday(today.toISOString())} <span className="fig">· {g}</span></span>
        <h1 className="text-display font-semibold">{hello}، مدیر کل</h1>
      </div>
      {presence?.khalvat ? <Pill tone="learn" icon="khalvat">خلوت روشن؛ فقط فوری میرسد</Pill> : null}
    </header>
  );
}

function AwayBanner() {
  const { data } = useAway();
  if (!data) return null;
  const n = data.decisions.new + data.deliverables.new + data.messages.new;
  if (!n) return null;
  return (
    <Card className="flex flex-wrap items-center gap-4 p-4">
      <span className="flex size-10 items-center justify-center rounded-full bg-gold-soft text-gold-ink"><Icon name="khalvat" size={20} /></span>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-[14px] font-semibold">در نبودت چه گذشت</span>
        <span className="text-caption text-sec">از {ago(data.since)}: {data.decisions.new} تصمیم تازه، {data.deliverables.new} خروجی، {data.messages.new} پیام</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {data.companies.filter((c) => c.decisions_new + c.deliverables_new + c.messages_new > 0).map((c) => (
          <span key={c.company} className="inline-flex h-8 items-center gap-2 rounded-full bg-tile px-3 text-[12px] text-sec">
            <CompanyMark code={c.company} height={13} mono />{c.decisions_new + c.deliverables_new + c.messages_new}
          </span>
        ))}
      </div>
    </Card>
  );
}

function Stats() {
  const { data: inbox, isLoading } = useInbox();
  const { data: t } = useTreasury({ period: 'day' });
  if (isLoading || !inbox) return <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[104px] rounded-[14px]" />)}</div>;
  const r = inbox.decisions_by_risk;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Link href="/cartable" className="rounded-[14px] focus-visible:outline-2"><StatTile label="منتظر مُهر تو" value={inbox.decisions_pending} sub={r.high ? <span className="text-neg">{r.high} با ریسک بالا</span> : 'بدون ریسک بالا'} /></Link>
      <Link href="/outputs" className="rounded-[14px]"><StatTile label="خروجی بی‌امتیاز" value={inbox.deliverables_unrated} sub="امتیاز تو ۴۰٪ نمره‌ی کارمند است" /></Link>
      <Link href="/messages" className="rounded-[14px]"><StatTile label="پیام نخوانده" value={inbox.messages_unread} sub="از مدیرعامل‌ها و مشاور" /></Link>
      <Link href="/treasury" className="rounded-[14px]"><StatTile label="مصرف امروز (معادل)" value={<span className="fig">{usd(t?.totals.equiv_cost_usd)}</span>} sub={<span><span className="fig">{tokens((t?.totals.input_tokens ?? 0) + (t?.totals.output_tokens ?? 0))}</span> توکن، {t?.totals.calls ?? 0} فراخوانی</span>} /></Link>
    </div>
  );
}

function Cartable() {
  const { company } = useScope();
  const q = useDecisions({ status: 'pending', company: company ? [company] : undefined });
  return (
    <Card className="flex flex-col gap-2 p-4">
      <SectionTitle title="کارتابل" note="فقط چیزهایی که مُهر تو را لازم دارند" action={<Button variant="text" size="sm" iconEnd="next" onClick={() => location.assign('/cartable')}>همه</Button>} />
      {q.isLoading ? <div className="flex flex-col gap-2">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-[72px]" />)}</div>
        : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : !q.data?.items.length ? <Empty icon="seal" title="کارتابل خالی است" body="هر تصمیمی که امضای تو را بخواهد این‌جا میاید." />
        : <div className="flex flex-col gap-0.5">{q.data.items.slice(0, 5).map((d) => <DecisionRow key={d.ref} d={d} href={`/cartable?ref=${d.ref}`} />)}</div>}
    </Card>
  );
}

function Live() {
  const { data: companies } = useCompanies();
  const { last, feed, state } = useLive();
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="استریم زنده‌ی هلدینگ" note="ذره‌ی طلایی فرمان تو، نقره‌ای تحویل ایجنت‌ها" action={<Pill tone={state === 'live' ? 'pos' : 'warn'} live={state === 'live'}>{state === 'live' ? 'زنده' : 'در حال اتصال'}</Pill>} />
      {companies ? <Orbit companies={companies} lastEvent={last} size={460} /> : <Skeleton className="mx-auto aspect-square w-full max-w-[520px] rounded-full" />}
      <ul className="flex flex-col gap-1 border-t border-div pt-3" aria-label="آخرین رویدادها">
        {feed.slice(0, 4).map((e) => (
          <li key={e.id} className="flex items-center gap-2 text-[12px] text-sec">
            <span className="size-1.5 rounded-full bg-silver-ink" />
            {e.company ? <CompanyMark code={e.company} height={12} mono /> : null}
            <span className="fig text-muted">{e.type}</span>
            <span className="flex-1" />
            <span className="text-muted">{ago(e.at)}</span>
          </li>
        ))}
        {!feed.length ? <li className="text-[12px] text-muted">هنوز رویدادی نرسیده؛ ایجنت‌ها تا رسیدن کار خواب‌اند.</li> : null}
      </ul>
    </Card>
  );
}

function Today() {
  const { company } = useScope();
  const { data } = usePlanner({});
  const items = (data?.days[0]?.items ?? []).filter((i) => !company || i.company === company);
  return (
    <Card className="flex flex-col gap-2 p-4">
      <SectionTitle title="امروز" note="از پلنر" action={<Button variant="text" size="sm" iconEnd="next" onClick={() => location.assign('/planner')}>پلنر</Button>} />
      {!data ? <Skeleton className="h-24" /> : !items.length ? <p className="py-4 text-center text-caption text-muted">برای امروز کاری ثبت نشده.</p> : (
        <ol className="flex flex-col">
          {items.map((i) => (
            <li key={i.ref} className="flex items-center gap-3 border-b border-div py-2.5 last:border-0">
              <span className="w-11 text-[12px] text-muted">{jTime(i.at)}</span>
              <span className={cx('size-2 rounded-full', i.status === 'done' ? 'bg-pos' : i.priority <= 'P1' ? 'bg-neg' : 'bg-silver-ink')} />
              <span className="flex-1 truncate text-[13px]">{i.title}</span>
              {i.recurring ? <span className="text-muted" title="دائمی"><Icon name="refresh" size={14} /></span> : null}
              <span className="text-sec"><CompanyMark code={i.company} height={12} mono /></span>
              <span className="text-[11px] text-muted">{WORK_STATUS[i.status] ?? i.status}</span>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

function Budgets() {
  const { data } = useTreasury({ period: 'month' });
  const { data: companies } = useCompanies();
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="بودجه‌ی ماه" note="هشدار در ۷۰٪ و ۹۰٪" action={<Button variant="text" size="sm" iconEnd="next" onClick={() => location.assign('/treasury')}>خزانه</Button>} />
      {!data ? <Skeleton className="h-28" /> : data.budgets.map((b) => (
        <div key={`${b.scope_type}-${b.scope_ref}`} className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2 text-[12px]">
            {b.scope_type === 'holding' ? <span className="text-sec">کل هلدینگ</span> : <span className="flex items-center gap-1.5 text-sec"><CompanyMark code={b.company} height={13} mono />{companies?.find((c) => c.code === b.company)?.name_fa ?? b.scope_ref}</span>}
            <span className="flex-1" />
            <span className="fig text-muted">{tokens(b.tokens_used)} / {tokens(b.token_limit)}</span>
            <span className={cx('w-10 text-left', (b.pct ?? 0) >= 90 ? 'text-neg' : (b.pct ?? 0) >= 70 ? 'text-warn' : 'text-sec')}>{Math.round(b.pct ?? 0)}٪</span>
          </div>
          <Bar pct={b.pct ?? 0} tone={budgetTone(b.pct)} label={`بودجه ${b.scope_ref}`} />
        </div>
      ))}
    </Card>
  );
}

export default function CommandCenter() {
  return (
    <>
      <Greeting />
      <AwayBanner />
      <Stats />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4"><Cartable /><Live /></div>
        <div className="flex min-w-0 flex-col gap-4"><Today /><Budgets /></div>
      </div>
    </>
  );
}
