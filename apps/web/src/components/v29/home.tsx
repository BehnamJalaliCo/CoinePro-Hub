'use client';

// ⟨1.11⟩ Contract §29.13 «خانه‌ی مالک»: the business at a glance. Three cards on top (an effective and a good suggestion, each with «اجرا کن /
// بعداً / نه» and «نه» asking a short reason; real progress, before → after from a real connection), the five morning lines, each working
// group's KPI per company, «فرمان‌های من» with their state, and only critical items. Nothing technical: that lives under «شرکت ← فنی».

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Spark } from '@/components/v14/bits';
import { Button } from '@/components/ui/button';
import { Card, Empty, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { CRITICAL_FA, sourceFa, useSuggestionAction, type Home, type HomeGroup, type Notification29, type Progress, type Suggestion } from '@/lib/api/v29';
import { linkRoute } from '@/lib/refs';
import { useNow } from '@/lib/store';
import { ago, cx, jDate } from '@/lib/format';
import { FaPara, FaText, OrderStatePill, fig } from './bits';

const SOURCE: Record<Suggestion['source'], string> = { council: 'از شورای مشاوران', group: 'از کارگروه', advisor: 'از مشاور کل' };
const inputCls = 'h-10 min-w-0 flex-1 rounded-[10px] border border-strong bg-tile px-3 text-[14px] text-ink outline-none focus:border-gold-ink';

function useName() {
  const { data } = useCompanies();
  return (code: string) => data?.find((c) => c.code === code)?.name_fa ?? code;
}

/** «پیشنهاد مؤثر» or «پیشنهاد خوب»: run it (an order is made), later, or no with a short reason the secretary remembers. */
export function SuggestionCard({ kind, s }: { kind: 'effective' | 'good'; s: Suggestion | null }) {
  const router = useRouter();
  const toast = useToast();
  const act = useSuggestionAction();
  const name = useName();
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState('');
  const title = kind === 'effective' ? 'پیشنهاد مؤثر' : 'پیشنهاد خوب';
  const label = `${title}${s ? `: ${s.title_fa}` : ''}`;
  const go = (action: 'run' | 'later' | 'no', reason_fa?: string) => act.mutate({ id: s!.id, action, reason_fa }, {
    onSuccess: (out) => {
      setAsking(false); setReason('');
      if (action === 'run') toast({ tone: 'ok', text: 'فرمانش ساخته شد؛ گزارشش زنده است.', action: out?.order_ref ? { label: 'گزارش فرمان', run: () => router.push(`/orders/${out.order_ref}`) } : undefined });
      else toast({ tone: 'info', text: action === 'later' ? 'بعداً دوباره میاید.' : 'دلیلت در حافظه‌ی منشی ماند؛ این پیشنهاد دیگر نمیاید.' });
    },
    onError: (e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' }),
  });
  return (
    <Card as="article" aria-label={label} className={cx('flex min-w-0 flex-col gap-3 p-4', kind === 'effective' && 'tahrir')}>
      <div className="flex items-center gap-2">
        <span className={cx('flex size-8 items-center justify-center rounded-[10px]', kind === 'effective' ? 'bg-gold-soft text-gold-ink' : 'bg-lapis-soft text-lapis')}><Icon name={kind === 'effective' ? 'star' : 'rate'} size={17} active={kind === 'effective'} /></span>
        <h2 className="flex-1 text-[15px] font-semibold">{title}</h2>
        {s ? <span className="flex items-center gap-1.5 text-[12px] text-sec"><CompanyMark code={s.company} height={12} mono />{name(s.company)}</span> : null}
      </div>
      {!s ? <p className="py-4 text-[13px] text-muted">پیشنهاد تازه‌ای نیست؛ کارگروه‌ها و مشاوران هر روز صبح پیشنهاد تازه میدهند.</p> : (
        <>
          <p className="text-[15px] font-semibold leading-7"><FaText text={s.title_fa} /></p>
          <FaPara text={s.why_fa} className="text-[13px] leading-6 text-sec" />
          <dl className="grid grid-cols-2 gap-2">
            <div className="flex flex-col gap-0.5 rounded-[10px] bg-tile p-2.5"><dt className="text-[11px] text-muted">اثر</dt><dd className="text-[12px] font-semibold leading-5"><FaText text={s.impact_fa} /></dd></div>
            <div className="flex flex-col gap-0.5 rounded-[10px] bg-tile p-2.5"><dt className="text-[11px] text-muted">هزینه</dt><dd className="text-[12px] font-semibold leading-5"><FaText text={s.cost_fa} /></dd></div>
          </dl>
          <span className="text-[11px] text-muted">{SOURCE[s.source] ?? ''}</span>
          {s.state === 'run' ? (
            <div className="flex flex-wrap items-center gap-2 rounded-[10px] bg-pos-soft px-3 py-2 text-[13px] text-pos">
              <Icon name="seal" size={16} active />فرمانش ساخته شد
              {s.order_ref ? <Link href={`/orders/${s.order_ref}`} className="ms-auto font-semibold text-gold-ink hover:underline">گزارش فرمان</Link> : null}
            </div>
          ) : asking ? (
            <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); if (reason.trim()) go('no', reason.trim()); }}>
              <label className="flex flex-col gap-1.5">
                <span className="text-[12px] text-sec">چرا نه؟ (کوتاه؛ منشی یادش میماند)</span>
                <span className="flex gap-2">
                  <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} aria-label="دلیل نه" className={inputCls} placeholder="مثلاً: الان وقتش نیست" />
                  <Button type="submit" size="md" variant="secondary" disabled={!reason.trim()} loading={act.isPending}>ثبت</Button>
                </span>
              </label>
              <button type="button" onClick={() => setAsking(false)} className="self-start text-[12px] text-muted hover:text-ink">انصراف</button>
            </form>
          ) : (
            <div className="mt-auto flex flex-wrap gap-2">
              <Button variant={kind === 'effective' ? 'primary' : 'secondary'} icon="send" loading={act.isPending && act.variables?.action === 'run'} onClick={() => go('run')}>اجرا کن</Button>
              <Button variant="ghost" icon="time" disabled={act.isPending} onClick={() => go('later')}>بعداً</Button>
              <Button variant="ghost" icon="close" disabled={act.isPending} onClick={() => setAsking(true)}>نه</Button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

/** «پیشرفت واقعی»: one figure before and after, from a real connection, never a guess. */
export function ProgressCard({ p }: { p: Progress | null }) {
  const name = useName();
  const delta = p ? p.after.value - p.before.value : 0;
  const pct = p && p.before.value ? (delta / p.before.value) * 100 : null;
  return (
    <Card as="article" aria-label="پیشرفت واقعی" className="flex min-w-0 flex-col gap-3 p-4">
      <div className="flex items-center gap-2">
        <span className="flex size-8 items-center justify-center rounded-[10px] bg-pos-soft text-pos"><Icon name="chart" size={17} /></span>
        <h2 className="flex-1 text-[15px] font-semibold">پیشرفت واقعی</h2>
        {p ? <span className="flex items-center gap-1.5 text-[12px] text-sec"><CompanyMark code={p.company} height={12} mono />{name(p.company)}</span> : null}
      </div>
      {!p ? (
        <div className="flex flex-col items-start gap-2 py-2">
          <p className="text-[13px] text-muted">هنوز عددی از اتصال واقعی نرسیده؛ پیشرفت فقط از عدد واقعی ساخته میشود.</p>
          <Link href="/connections" className="text-[13px] font-semibold text-gold-ink hover:underline">وصل کردن اتصال‌ها</Link>
        </div>
      ) : (
        <>
          <p className="text-[15px] font-semibold leading-7"><FaText text={p.title_fa} /></p>
          <div className="flex items-end gap-3" dir="ltr" aria-label={`از ${fig(p.before.value)} به ${fig(p.after.value)}`}>
            <span className="flex flex-col items-start"><span className="fig text-[18px] text-sec">{fig(p.before.value)}</span><span className="text-[11px] text-muted" dir="rtl">{jDate(p.before.at)}</span></span>
            <Icon name="next" size={18} className="mb-5 text-muted" />
            <span className="flex flex-col items-start"><span className="fig text-[26px] font-semibold leading-8 text-ink">{fig(p.after.value)}</span><span className="text-[11px] text-muted" dir="rtl">{jDate(p.after.at)}</span></span>
          </div>
          <span className={cx('text-[13px] font-semibold', delta >= 0 ? 'text-pos' : 'text-neg')}>
            <span className="fig">{delta >= 0 ? '+' : '−'}{fig(Math.abs(delta))}</span>{pct != null ? <> (<span className="fig">{delta >= 0 ? '+' : '−'}{Math.abs(pct).toFixed(1)}%</span>)</> : null}
          </span>
          <span className="mt-auto text-[11px] text-muted">منبع: {sourceFa(p.source)}</span>
        </>
      )}
    </Card>
  );
}

/** The five morning lines (08:00 Tehran, rule-based). */
export function MorningCard({ lines }: { lines: string[] }) {
  return (
    <Card className="flex flex-col gap-2 p-4" aria-label="خلاصه‌ی صبح">
      <SectionTitle title="خلاصه‌ی صبح" note="پنج خط، ساعت ۸ به وقت تهران" />
      {!lines.length ? <p className="py-2 text-[13px] text-muted">خلاصه‌ی امروز هنوز نوشته نشده.</p> : (
        <ol className="flex flex-col gap-1.5">
          {lines.slice(0, 5).map((l, i) => (
            <li key={i} className="flex items-start gap-2.5 text-[14px] leading-7">
              <span className="fig mt-1.5 flex size-5 flex-none items-center justify-center rounded-full bg-tile text-[11px] text-sec">{i + 1}</span>
              <span className="min-w-0 flex-1 text-justify [text-align-last:start]"><FaText text={l} /></span>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

/** A group's KPI per company: the latest value, its change over the days shown, and a small chart. */
export function GroupKpiCard({ g }: { g: HomeGroup }) {
  return (
    <Card className="flex flex-col gap-3 p-4" aria-label={`شاخص‌های ${g.title_fa}`}>
      <SectionTitle title={g.title_fa} note="شاخص اصلی هر شرکت، از اتصال‌های واقعی" action={<Link href={`/groups/${g.key}`} className="text-[12px] font-semibold text-gold-ink hover:underline">کارگروه</Link>} />
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {g.companies.map((c) => {
          const vs = (c.kpi?.series ?? []).map((p) => p.value).filter((v): v is number => v != null);
          const last = vs.at(-1);
          const first = vs[0];
          const ch = last != null && first ? ((last - first) / first) * 100 : null;
          return (
            <Link key={c.code} href={`/groups/${g.key}?company=${c.code}`} className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3 transition-colors hover:bg-hover">
              <span className="flex items-center gap-1.5 text-[12px] text-sec"><CompanyMark code={c.code} height={12} mono /><span className="truncate">{c.name_fa}</span></span>
              {c.kpi && last != null ? (
                <>
                  <span className="text-[11px] text-muted">{c.kpi.title_fa}</span>
                  <span className="flex items-end justify-between gap-2">
                    <span className="flex flex-col">
                      <span className="fig text-[18px] font-semibold leading-6">{fig(last)}{c.kpi.unit ? ` ${c.kpi.unit}` : ''}</span>
                      {ch != null ? <span className={cx('fig text-[11px] font-semibold', ch >= 0 ? 'text-pos' : 'text-neg')}>{ch >= 0 ? '+' : '−'}{Math.abs(ch).toFixed(1)}%</span> : null}
                    </span>
                    <Spark values={vs} width={88} height={28} />
                  </span>
                </>
              ) : <span className="py-2 text-[12px] text-muted">هنوز عددی نیست؛ اتصالش را وصل کن.</span>}
            </Link>
          );
        })}
      </div>
    </Card>
  );
}

/** «فرمان‌های من»: each order with its state and its one-line summary; a way into its report. */
export function HomeOrders({ orders, onNewOrder }: { orders: Home['orders']; onNewOrder: () => void }) {
  return (
    <Card className="flex flex-col gap-1 p-4" aria-label="فرمان‌های من">
      <SectionTitle title="فرمان‌های من" note="هر فرمان جواب میگیرد: رسید، برنامه، گیر و رفع، خروجی" action={<Link href="/orders" className="text-[12px] font-semibold text-gold-ink hover:underline">همه</Link>} />
      {!orders.length ? (
        <div className="flex flex-col items-start gap-2 pt-2">
          <span className="text-[12px] text-muted">هر فرمانی بدهی این‌جا با وضعیتش دیده میشود.</span>
          <Button size="sm" icon="command" onClick={onNewOrder}>فرمان تازه</Button>
        </div>
      ) : (
        <ul className="flex flex-col">
          {orders.map((o) => (
            <li key={o.ref} className="border-t border-div first:border-0">
              <Link href={`/orders/${o.ref}`} className="flex flex-col gap-1 py-2.5 hover:bg-hover/40">
                <span className="flex items-start gap-2">
                  <span className="line-clamp-2 min-w-0 flex-1 text-[13px] font-semibold leading-6"><FaText text={o.text_fa} /></span>
                  <OrderStatePill state={o.state} />
                </span>
                {o.summary_fa ? <span className="line-clamp-2 text-[12px] leading-5 text-sec"><FaText text={o.summary_fa} /></span> : null}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** Only what §29.1 calls critical (a data leak, a product down, money, legal); nothing else technical reaches the home. */
export function CriticalCard({ items }: { items: Notification29[] }) {
  const now = useNow();
  if (!items.length) return null;
  return (
    <Card as="section" aria-label="بحرانی" className="flex flex-col gap-2 p-4 ring-1 ring-[var(--hq-neg-line)]">
      <div className="flex items-center gap-2 text-neg"><Icon name="urgent" size={18} /><h2 className="text-[15px] font-semibold">بحرانی</h2></div>
      <ul className="flex flex-col gap-2">
        {items.map((n) => {
          const href = linkRoute(n.link?.kind, n.link?.ref) ?? `/companies/${n.company}?tab=tech`;
          return (
            <li key={n.id}>
              <Link href={href} className="flex flex-col gap-1 rounded-[12px] bg-neg-soft p-3 hover:opacity-90">
                <span className="flex flex-wrap items-center gap-2">
                  {n.critical_reason ? <Pill tone="neg" dot>{CRITICAL_FA[n.critical_reason] ?? 'بحرانی'}</Pill> : null}
                  <span className="text-sec"><CompanyMark code={n.company} height={12} mono /></span>
                  <span className="text-[11px] text-muted">{now ? ago(n.created_at, now) : ''}</span>
                </span>
                <span className="text-[14px] font-semibold text-ink"><FaText text={n.title_fa} /></span>
                <FaPara text={n.body_fa} className="text-[13px] leading-6 text-sec" />
              </Link>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

export function HomeSkeleton() {
  return (
    <>
      <div className="grid gap-4 lg:grid-cols-3">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-60 rounded-[16px]" />)}</div>
      <div className="grid gap-4 xl:grid-cols-2"><Skeleton className="h-56 rounded-[16px]" /><Skeleton className="h-56 rounded-[16px]" /></div>
    </>
  );
}

export function HomeNotServed() {
  return <Card><Empty icon="holding" title="خانه‌ی تازه بعد از به‌روزرسانی ستاد پر میشود" body="پیشنهادها، پیشرفت واقعی، خلاصه‌ی صبح و شاخص‌های کارگروه‌ها از ستاد میایند." /></Card>;
}
