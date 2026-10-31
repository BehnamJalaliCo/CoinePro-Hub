'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Bar, Card, Empty, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import type { IconName } from '@/generated/icons';
import { useCompanies } from '@/lib/api/hooks';
import { useOwnerOrders, useTreeEvents, useWorkDetail, type Work } from '@/lib/api/v21';
import { useLive } from '@/lib/live';
import {
  STAGES, endOf, holdersOf, lastActivityOf, outputsOf, progressOf, reasonOf, stageLabel, stageOf, timelineOf, type Moment, type OrderTrack, type Part,
} from '@/lib/orders';
import { ago, cx, jDate, jTime } from '@/lib/format';
import { ownerDay, RefButton, useTick } from './bits';
import { PriorityTag } from './priority';
import { PlayerTag } from '@/components/work/player';

// «فرمان‌های من» (0.4.0; contract §4 ⟨1.7.4⟩; the Android app's ui/work/Orders.kt): every order the owner gave, from the moment it is given
// to the moment it is closed — the stage on a stepper, an honest estimate, who holds it now, when it last moved, and its output.

export const ACTIVE = new Set(['queued', 'in_progress', 'waiting']);
export const DELIVERED = new Set(['delivered', 'done']);
export const ENDED = new Set(['failed', 'cancelled']);

/** One order's track: its detail (children two levels down) and, when [full], its tree's events. */
export function useTrack(id: string | null | undefined, full = false): { track: OrderTrack | null; loading: boolean; error: unknown } {
  const d = useWorkDetail(id ?? null);
  const ev = useTreeEvents(full || (d.data && ENDED.has(d.data.status)) ? d.data?.id ?? null : null);
  return { track: d.data ? { root: d.data, events: ev.data } : null, loading: d.isLoading, error: d.error };
}

// ---------------------------------------------------------------------------------------------------------- stepper --
/** The six stages, right to left: finished in gold, the current one ringed (breathing while it moves), the rest waiting. A failed or
 *  cancelled order marks the stage it stopped at; a finished one is green throughout. */
export function OrderStepper({ t }: { t: OrderTrack }) {
  const stage = stageOf(t);
  const end = endOf(t.root);
  const cur = STAGES.indexOf(stage);
  const done = stage === 'done';
  const past = done ? 'var(--hq-positive)' : 'var(--hq-gold-fill)';
  return (
    <ol className="flex w-full" aria-label={`مرحله: ${stageLabel(stage, t.root)}${end !== 'none' ? '، متوقف' : ''}`}>
      {STAGES.map((s, i) => {
        const current = i === cur;
        return (
          <li key={s} className="flex min-w-0 flex-1 flex-col items-center gap-1.5">
            <span className="relative flex h-4 w-full items-center justify-center">
              {i > 0 ? <span className="absolute start-0 top-1/2 h-0.5 w-1/2 -translate-y-1/2 transition-colors duration-300" style={{ background: i <= cur ? past : 'var(--hq-line-strong)' }} /> : null}
              {i < STAGES.length - 1 ? <span className="absolute end-0 top-1/2 h-0.5 w-1/2 -translate-y-1/2 transition-colors duration-300" style={{ background: i < cur ? past : 'var(--hq-line-strong)' }} /> : null}
              {current && end !== 'none' ? (
                <span className={cx('relative flex size-4 items-center justify-center rounded-full border-[1.5px]', end === 'failed' ? 'border-neg bg-neg-soft text-neg' : 'border-[var(--hq-text-muted)] bg-tile text-muted')}><Icon name="close" size={10} /></span>
              ) : current && done ? (
                <span className="relative flex size-4 items-center justify-center rounded-full bg-pos text-page"><Icon name="seal" size={10} /></span>
              ) : current ? (
                <span className="relative flex size-4 items-center justify-center rounded-full border-2 border-gold-ink bg-page">
                  <span className="size-1.5 rounded-full bg-gold-ink" style={stage !== 'delivered' ? { animation: 'hq-live 1.8s ease-in-out infinite' } : undefined} />
                </span>
              ) : i < cur ? <span className="relative size-3 rounded-full" style={{ background: past }} />
                : <span className="relative size-2.5 rounded-full border-[1.5px] border-strong bg-page" />}
            </span>
            <span className={cx('line-clamp-2 min-h-7 text-center text-[10.5px] leading-[14px]', current ? 'font-bold' : '',
              current && end === 'failed' ? 'text-neg' : current ? 'text-ink' : i < cur ? 'text-sec' : 'text-muted')}>{stageLabel(s, t.root)}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** The estimate as a bar and in words, said to be an estimate. */
export function OrderMeter({ t }: { t: OrderTrack }) {
  const p = progressOf(t);
  const end = endOf(t.root);
  const stage = stageOf(t);
  return (
    <div className="flex flex-col gap-1.5">
      <span className="flex items-center gap-1.5">
        <span className={cx('text-[13px] font-semibold', end === 'failed' ? 'text-neg' : end === 'cancelled' ? 'text-sec' : 'text-ink')}>
          {end === 'failed' ? `ناموفق ماند؛ تا حدود ${p}٪ رسیده بود` : end === 'cancelled' ? `لغو شد؛ تا حدود ${p}٪ رسیده بود` : stage === 'done' ? 'تمام شد' : `حدود ${p}٪`}
        </span>
        {end === 'none' && stage !== 'done' ? <span className="text-[11px] text-muted">تخمینی</span> : null}
      </span>
      <Bar pct={p} tone={end === 'failed' ? 'neg' : end === 'cancelled' ? 'silver' : stage === 'done' ? 'pos' : 'gold'} label="پیشرفت تخمینی فرمان" />
    </div>
  );
}

/** Who holds it now: the path from its assignee down to whoever works on it, the first of them and how many more. */
export function HolderLine({ t }: { t: OrderTrack }) {
  const holders = holdersOf(t);
  const stage = stageOf(t);
  const end = endOf(t.root);
  let text: ReactNode;
  if (end !== 'none') text = reasonOf(t) ? `دلیل: ${reasonOf(t)}` : end === 'failed' ? 'دلیلی ثبت نشده؛ رویدادهایش را ببین.' : 'لغو شد.';
  else if (stage === 'done') text = 'بسته شد؛ چیزی منتظر تو نیست.';
  else if (stage === 'delivered') text = 'منتظر نگاه تو: خروجی را ببین و امتیاز بده تا بسته شود.';
  else if (!holders.length) text = 'در صف؛ هنوز کسی برنداشته.';
  else if (stage === 'received') text = `در صف ${t.root.assignee?.title_fa ?? 'مجری'}؛ هنوز برنداشته.`;
  else text = <>الان دست {holders[0]!.map((e, i) => <span key={e.code}>{i > 0 ? ' ← ' : ''}<span className={i === holders[0]!.length - 1 ? 'font-semibold text-ink' : ''}>{e.title_fa}</span></span>)}{holders.length > 1 ? ` و ${holders.length - 1} نفر دیگر` : ''}</>;
  const icon: IconName = end !== 'none' ? 'urgent' : stage === 'delivered' || stage === 'done' ? 'owner' : 'delegate';
  return (
    <span className={cx('flex items-start gap-2 text-[12px] leading-5', end === 'failed' ? 'text-neg' : 'text-sec')}>
      <span className={cx('mt-0.5 flex-none', end === 'failed' ? 'text-neg' : 'text-muted')}><Icon name={icon} size={15} /></span>
      <span className="line-clamp-3">{text}</span>
    </span>
  );
}

/** Its outputs, each a way into Outputs. */
export function OutputsRow({ t }: { t: OrderTrack }) {
  const refs = outputsOf(t).slice(0, 3);
  if (!refs.length) return null;
  return <div className="flex flex-col gap-1.5">{refs.map((r) => <RefButton key={r} label="دیدن خروجی" refId={r} icon="deliverable" href={`/outputs?ref=${r}`} />)}</div>;
}

/** One order: its company and priority, the title, the stepper, the estimate, who holds it, its output. */
export function OrderCard({ w }: { w: Work }) {
  const router = useRouter();
  const { data: companies } = useCompanies();
  const { track, error } = useTrack(w.id);
  useTick();
  const co = companies?.find((c) => c.code === w.company);
  return (
    <Card className="hq-rise flex flex-col gap-3 p-4">
      <button type="button" onClick={() => router.push(`/work/${w.id}`)} className="flex flex-col gap-1.5 text-start" aria-label={`باز کردن فرمان ${w.ref}`}>
        <span className="flex items-center gap-1.5 text-[12px] text-sec">
          <CompanyMark code={w.company} height={13} mono />
          <span className="truncate">{co?.kind === 'holding' ? 'هلدینگ' : co?.name_fa ?? w.company}</span>
          <span className="text-muted">·</span><span className="fig text-muted">{w.ref}</span>
          <span className="flex-1" />
          {/* ⟨1.9⟩ who plays it, when the owner named a player or called the council. */}
          <PlayerTag player={(w as { player?: string | null }).player} mode={(w as { mode?: string | null }).mode} />
          <PriorityTag code={w.priority} compact />
        </span>
        <span className="line-clamp-2 text-[15px] font-semibold leading-7 hover:text-gold-ink">{w.title}</span>
      </button>
      {!track ? (error ? <span className="text-[12px] text-muted">{(error as { messageFa?: string }).messageFa ?? 'خوانده نشد.'}</span> : <Skeleton className="h-24" />) : (
        <div className="flex flex-col gap-3">
          <OrderStepper t={track} />
          <OrderMeter t={track} />
          <HolderLine t={track} />
          <OutputsRow t={track} />
          <span className="text-[11px] text-muted">آخرین حرکت: {ago(lastActivityOf(track))}</span>
        </div>
      )}
    </Card>
  );
}

// ----------------------------------------------------------------------------------------------------------- the page --
/** On the order's own page: the stepper, the estimate, who holds it and its outputs, with the stream's state. */
export function OrderTrackerCard({ t }: { t: OrderTrack }) {
  const { state } = useLive();
  return (
    <Card className={cx('flex flex-col gap-4 p-5', stageOf(t) === 'delivered' && 'tahrir')}>
      <SectionTitle title="پیگیری فرمان" note="مرحله، پیشرفت تخمینی و این‌که الان دست کیست"
        action={state === 'live' ? <Pill tone="pos" live>زنده</Pill> : state === 'connecting' ? <Pill tone="neutral" dot>در حال وصل</Pill> : <Pill tone="warn" dot>قطع؛ خودکار وصل میشود</Pill>} />
      <OrderStepper t={t} />
      <OrderMeter t={t} />
      <HolderLine t={t} />
      <OutputsRow t={t} />
    </Card>
  );
}

const MOMENT: Record<string, { icon: IconName; tint: string }> = {
  created: { icon: 'command', tint: 'text-gold-ink bg-gold-soft' }, accepted: { icon: 'agent', tint: 'text-gold-ink bg-gold-soft' },
  delegated: { icon: 'delegate', tint: 'text-lapis bg-lapis-soft' }, progress: { icon: 'chart', tint: 'text-silver-ink bg-[var(--hq-silver-soft)]' },
  delivered: { icon: 'deliverable', tint: 'text-pos bg-pos-soft' }, completed: { icon: 'seal', tint: 'text-pos bg-pos-soft' },
  failed: { icon: 'urgent', tint: 'text-neg bg-neg-soft' }, declined: { icon: 'urgent', tint: 'text-neg bg-neg-soft' }, cancelled: { icon: 'close', tint: 'text-muted bg-tile' },
  'run.step': { icon: 'task', tint: 'text-silver-ink bg-[var(--hq-silver-soft)]' },
};
const partsOf = (parts: Part[]) => parts.map((p, i) => (p.fig ? <span key={i} className="fig whitespace-nowrap">{p.text}</span> : <span key={i}>{p.text}</span>));

/** The order's life, newest first: its events, its children's, and the agents' run steps. Live from the stream (the tree refetches). */
export function TimelineCard({ t }: { t: OrderTrack }) {
  const moments = timelineOf(t);
  const [all, setAll] = useState(false);
  if (!moments.length) return null;
  const shown = all ? moments : moments.slice(0, 10);
  return (
    <Card className="flex flex-col gap-2 p-5">
      <SectionTitle title="روند کار" note="رویدادها و قدم‌های اجرا، تازه‌ترین بالا؛ فقط خلاصه" />
      <ol className="flex flex-col">
        {shown.map((m: Moment, i) => {
          const d = ownerDay(m.at);
          const head = i === 0 || ownerDay(shown[i - 1]!.at) !== d ? <li key={`d${d}`} className={cx('pb-1 text-[11px] font-semibold text-muted', i > 0 && 'pt-2')}>{jDate(m.at)}</li> : null;
          const look = MOMENT[m.kind] ?? { icon: 'info' as IconName, tint: 'text-silver-ink bg-[var(--hq-silver-soft)]' };
          const ref = m.parts.find((p) => p.fig && /^[WO]-\d+$/.test(p.text))?.text;
          const body = (
            <>
              <span className="fig w-10 flex-none pt-0.5 text-[11px] text-muted">{jTime(m.at)}</span>
              <span className={cx('mt-0.5 flex size-[22px] flex-none items-center justify-center rounded-full', look.tint)}><Icon name={look.icon} size={12} /></span>
              <span className={cx('line-clamp-3 min-w-0 flex-1', m.sub ? 'ps-1.5 text-[12px] text-sec' : 'text-[13px] text-ink')}>{partsOf(m.parts)}</span>
            </>
          );
          return [head, (
            <li key={`${m.at}-${i}`}>
              {ref ? <Link href={ref.startsWith('O-') ? `/outputs?ref=${ref}` : `/work/${ref}`} className="flex items-start gap-2 rounded-[8px] px-0.5 py-1 hover:bg-hover">{body}</Link>
                : <div className="flex items-start gap-2 px-0.5 py-1">{body}</div>}
            </li>
          )];
        })}
      </ol>
      {moments.length > 10 ? <Button variant="text" size="sm" className="self-start" onClick={() => setAll(!all)}>{all ? 'کمتر' : `همه‌ی ${moments.length} مورد`}</Button> : null}
    </Card>
  );
}

// ---------------------------------------------------------------------------------------------------------------- home --
function HomeOrderRow({ w }: { w: Work }) {
  const { track } = useTrack(w.id);
  const stage = track ? stageOf(track) : null;
  const end = track ? endOf(track.root) : 'none';
  const p = track ? progressOf(track) : 0;
  return (
    <Link href={`/work/${w.id}`} className="flex flex-col gap-1.5 border-t border-div py-2.5 first:border-0 hover:bg-hover/40">
      <span className="flex items-center gap-2">
        <span className="text-sec"><CompanyMark code={w.company} height={12} mono /></span>
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{w.title}</span>
        {!track || !stage ? <Skeleton className="h-3.5 w-16" /> : <span className={cx('text-[11px] font-semibold', end === 'failed' ? 'text-neg' : stage === 'delivered' ? 'text-gold-ink' : 'text-sec')}>{stageLabel(stage, track.root)}</span>}
      </span>
      {!track ? <Skeleton className="h-1.5" /> : (
        <span className="flex items-center gap-2">
          <span className="flex-1"><Bar pct={p} tone={stage === 'done' ? 'pos' : 'gold'} height={5} /></span>
          <span className="text-[11px] text-muted">حدود {p}٪، {ago(lastActivityOf(track))}</span>
        </span>
      )}
    </Link>
  );
}

/** The home card: the orders on their way (or the last delivered), each with its stage and estimate; the way to all of them. */
export function HomeOrdersCard({ onNewOrder }: { onNewOrder: () => void }) {
  const router = useRouter();
  const q = useOwnerOrders();
  const list = q.data;
  const active = (list ?? []).filter((w) => ACTIVE.has(w.status));
  const shown = [...active, ...(list ?? []).filter((w) => DELIVERED.has(w.status))].slice(0, 3);
  return (
    <Card className={cx('flex h-full flex-col gap-1 p-4', (list ?? []).some((w) => w.status === 'delivered') && 'tahrir')}>
      <SectionTitle title="فرمان‌های من" note={!list ? 'از ثبت تا تحویل، زنده' : !active.length ? 'فرمانی در جریان نیست' : `${active.length} فرمان در جریان`}
        action={<Button variant="text" size="sm" iconEnd="next" onClick={() => router.push('/orders')}>همه</Button>} />
      {!list ? <Skeleton className="mt-2 h-36" /> : !shown.length ? (
        <div className="flex flex-col items-start gap-2 pt-2">
          <span className="text-[12px] text-muted">هر فرمانی بدهی این‌جا مرحله‌به‌مرحله دیده میشود.</span>
          <Button size="sm" icon="command" onClick={onNewOrder}>فرمان تازه</Button>
        </div>
      ) : <div className="flex flex-col pt-1">{shown.map((w) => <HomeOrderRow key={w.id} w={w} />)}</div>}
    </Card>
  );
}

export function OrdersEmpty({ tab, onNewOrder }: { tab: string; onNewOrder: () => void }) {
  return (
    <Card>
      <Empty icon="command" title={tab === 'active' ? 'فرمانی در جریان نیست' : tab === 'delivered' ? 'هنوز فرمانی تحویل نشده' : tab === 'ended' ? 'فرمان ناموفق یا لغوشده‌ای نیست' : 'هنوز فرمانی نداده‌ای'}
        body="هر فرمانی که بدهی این‌جا مرحله‌به‌مرحله دیده میشود: ثبت، مدیرعامل، واگذاری، انجام و تحویل." action={<Button icon="command" onClick={onNewOrder}>فرمان تازه</Button>} />
    </Card>
  );
}
