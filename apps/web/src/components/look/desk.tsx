'use client';

// ⟨1.0.1⟩ Part C, «میز انتشار» (C2.3, feature 43; contract §55.2): one place for everything that can go out, is set to go out, or
// went out, of every company. Three sections, each hidden while it is empty: «آماده‌ی انتشار» (the media itself, large, in its network's
// shape, with the company, the account, the caption, the account's best hour, and «تأیید و انتشار»: only the FIRST card's is the full
// gold, the others are outlined), «در صف» (set for an hour or on its way, soonest first, each taken back in place) and «منتشرشده» (the
// last seven days: its link, a failure with its reason and a quiet «دوباره», a cancelled one as «لغو شد»). A company whose publishing
// path is not set yet has no action and says the technical team sets it: never the owner's step. On a hub before §55 the page says so
// and its entries are hidden.
// ⟨1.0.3⟩ §58.5 the desk is its own page: the home keeps one line «انتشار: ۶ آماده | ۲ در صف»; the page has a tab per channel the cards
// go out on (today «اینستاگرام»), each with its «آماده | در صف | منتشرشده». §58.4 a published card says what stayed and what went:
// «بایگانی شد | 38 MB آزاد شد».

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useMemo, useRef, useState, type TouchEvent } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { Icon } from '@/components/icon';
import { Arc } from '@/components/live/motion';
import { Button, IconButton } from '@/components/ui/button';
import { Card, Empty, ErrorState, Skeleton } from '@/components/ui/primitives';
import { PlainText } from '@/components/v29/bits';
import { FaText } from '@/components/v29/text';
import { publishNote, useCancel } from '@/components/v47/cancel';
import { KIND_FA } from '@/lib/api/v44';
import { bestHourOf } from '@/lib/api/v47';
import { deskDayFa, usePublishDesk, type DeskCard, type PublishDesk } from '@/lib/api/v55';
import { ARCHIVED_FA, PUBLISH_FA, channelFa, channelOf, freedFa, sweptOf } from '@/lib/api/v58';
import { fileSize } from '@/components/media/attachments';
import { ago, cx } from '@/lib/format';
import { plain } from '@/lib/plain';
import { DESK_HREF } from '@/components/shell/nav';
import { useScope } from '@/lib/scope';
import { FileFace, HeroMedia } from './files';
import { haptic } from './haptics';
import { OpenLink, PublishFor, PublishState, ROUTE_WAITS_FA, type PublishSeed } from './publish';
import { stagger } from './stagger';
import { Facts, Ltr, clock, faCount } from './text';

export const DESK_FA = 'میز انتشار';
export const DESK_EMPTY_FA = 'چیزی آماده‌ی انتشار نیست؛ هر خروجی تأییدشدنی همین‌جا می‌آید.';
export const DESK_ROUTE_FA = ROUTE_WAITS_FA;
export { DESK_HREF };

/** «خروجی‌ها | میز انتشار»: the two halves of where outputs live. Nothing on a hub that does not serve the desk. */
export function OutputsTabs() {
  const pathname = usePathname();
  const desk = usePublishDesk(null);
  if (!desk.data) return null;
  const ready = desk.data.ready?.length ?? 0;
  const tabs = [{ href: '/outputs', label: 'خروجی‌ها' }, { href: DESK_HREF, label: DESK_FA, count: ready }];
  return (
    <nav aria-label="خروجی‌ها و میز انتشار" data-testid="outputs-tabs" className="flex w-full max-w-sm rounded-[10px] bg-tile p-1">
      {tabs.map((t) => {
        const on = t.href === DESK_HREF ? pathname.startsWith(DESK_HREF) : pathname === '/outputs';
        return (
          <Link key={t.href} href={t.href} aria-current={on ? 'page' : undefined}
            className={cx('flex h-8 flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-[8px] px-3 text-[13px]', on ? 'bg-raised font-semibold text-ink shadow-[inset_0_0_0_1px_var(--hq-silver-line)]' : 'text-sec hover:text-ink')}>
            {t.label}{t.count ? <span className="text-[12px] text-muted">{faCount(t.count)}</span> : null}
          </Link>
        );
      })}
    </nav>
  );
}

/**
 * One line for the home: «انتشار: ۶ آماده | ۲ در صف», and the way to the desk (§58.5: the desk itself is never in the middle of the
 * home). Nothing on a hub without the desk.
 */
export function DeskLine() {
  const desk = usePublishDesk(null);
  if (!desk.data) return null;
  const ready = desk.data.ready?.length ?? 0;
  const queue = desk.data.queue?.length ?? 0;
  return (
    <Link href={DESK_HREF} data-testid="desk-line" aria-label={`${DESK_FA}: ${faCount(ready)} آماده، ${faCount(queue)} در صف`} className="flex min-h-11 items-center gap-2 rounded-[12px] px-3 text-[13px] text-sec hover:bg-hover hover:text-ink">
      <span className="font-semibold text-ink">{PUBLISH_FA}:</span>
      <span className="min-w-0 flex-1 truncate text-[13px]"><Facts>{`${faCount(ready)} آماده`}{`${faCount(queue)} در صف`}</Facts></span>
      <span className="flex-none text-muted"><Icon name="next" size={16} mirror /></span>
    </Link>
  );
}

// ---------------------------------------------------------------------------------------------- the cards --
const RATIO: Record<DeskCard['kind'], number> = { reel: 9 / 16, story: 9 / 16, post: 4 / 5, carousel: 1 };
const seedOf = (c: DeskCard): PublishSeed => ({ caption: c.caption ?? null, account: c.account ?? null, cover: c.cover?.id ?? null, best: c.best ?? null });

function Who({ c }: { c: DeskCard }) {
  const accounts = c.accounts ?? [];
  return (
    <span className="flex min-w-0 items-center gap-1.5 text-[12px] text-sec" data-desk-who>
      <CompanyMark code={c.company} height={14} mono />
      <Facts>
        <span className="font-semibold text-ink">{c.company_fa}</span>
        {channelFa(channelOf(c))}
        {c.account ? <Ltr tabular={false}>@{c.account}</Ltr> : accounts.length > 1 ? `${faCount(accounts.length)} حساب` : null}
      </Facts>
    </span>
  );
}

/** A small poster: the cover when there is one, else the file itself. */
function Thumb({ c }: { c: DeskCard }) {
  return <span className="relative flex h-16 w-12 flex-none items-center justify-center overflow-hidden rounded-[10px] bg-tile shadow-[inset_0_0_0_1px_var(--hq-line-divider)]"><FileFace f={c.cover ?? c.file} sign={22} /></span>;
}

function ReadyCard({ c, lead, i, onAsk }: { c: DeskCard; lead: boolean; i: number; onAsk: () => void }) {
  const [all, setAll] = useState(false);
  const best = bestHourOf(c.best);
  const item = stagger(i);
  return (
    <li {...item} data-desk="ready" data-output={c.output} data-kind={c.kind} className={cx('flex flex-col gap-3 rounded-[16px] bg-card p-3.5', item.className)}>
      <Who c={c} />
      <HeroMedia f={c.file} cover={c.cover ?? null} ratio={RATIO[c.kind] ?? 1} maxHeight={300} />
      <div className="flex flex-col gap-1.5">
        <span className="flex flex-wrap items-baseline gap-x-2 text-[14px] font-semibold leading-6 text-ink">
          <Link href={`/outputs?ref=${encodeURIComponent(c.output)}&tab=all`} className="min-w-0 hover:underline"><PlainText text={c.title_fa} /></Link>
          <span className="text-[11px] font-normal text-muted"><Facts>{KIND_FA[c.kind]}{c.files && c.files > 1 ? `${faCount(c.files)} فایل` : null}</Facts></span>
        </span>
        {c.caption ? (
          <button type="button" aria-expanded={all} onClick={() => setAll(!all)} data-desk-caption className={cx('whitespace-pre-line text-start text-[13px] leading-6 text-sec [overflow-wrap:anywhere]', !all && 'line-clamp-2')}>
            <FaText text={c.caption} />
          </button>
        ) : null}
        {best ? <span className="text-[12px] text-sec" data-desk-best>بهترین ساعت این حساب: <Ltr>{best}</Ltr></span> : null}
        {c.group_fa ? <span className="text-[11px] text-muted">کارگروه «{plain(c.group_fa)}»</span> : null}
      </div>
      {c.route_ready === false
        ? <span className="text-[12px] leading-5 text-sec" data-route-not-ready>{DESK_ROUTE_FA}</span>
        : <Button variant={lead ? 'primary' : 'secondary'} size="lg" className="w-full" onClick={onAsk}>تأیید و انتشار</Button>}
    </li>
  );
}

function QueueCard({ c, i }: { c: DeskCard; i: number }) {
  const p = c.publish ?? null;
  const cancel = useCancel(p);
  const note = publishNote(p) ?? (c.state === 'waiting_setup' ? null : p?.note_fa ?? null);
  const at = p?.scheduled_at ?? c.at;
  const item = stagger(i);
  return (
    <li {...item} data-desk="queue" data-output={c.output} data-state={c.state} className={cx('flex flex-col gap-1.5 rounded-[14px] bg-card p-3', item.className)}>
      <div className="flex items-center gap-3">
        <Thumb c={c} />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-[15px] font-semibold leading-6 text-ink" data-desk-time>
            {c.state === 'publishing' ? 'در حال انتشار' : c.state === 'waiting_setup' ? 'در حال وصل شدن' : c.state === 'waiting_seal' ? 'منتظر تأیید' : <>{deskDayFa(at)} <Ltr>{clock(at)}</Ltr></>}
          </span>
          <span className="line-clamp-1 text-[13px] text-sec"><PlainText text={c.title_fa} /></span>
          <span className="text-[11px] leading-5 text-muted"><Facts>{c.company_fa}{c.account ? <Ltr tabular={false}>@{c.account}</Ltr> : null}{KIND_FA[c.kind]}{p?.auto ? 'خودکار' : null}</Facts></span>
        </span>
        {cancel.button}
      </div>
      {c.state === 'waiting_setup' ? <span className="text-[12px] leading-5 text-sec" data-route-not-ready>{DESK_ROUTE_FA}</span> : null}
      {note ? <span className="text-[11px] leading-5 text-muted" data-publish-note><FaText text={note} /></span> : null}
      {cancel.under}
    </li>
  );
}

function DoneCard({ c, i, onAgain }: { c: DeskCard; i: number; onAgain: () => void }) {
  const p = c.publish ?? null;
  const when = p?.published_at ?? c.at;
  // §58.4 only a publication that went out keeps its package (and frees the rest); a failed or cancelled one deleted nothing.
  const swept = c.state === 'published' ? sweptOf(c, p) : null;
  const item = stagger(i);
  return (
    <li {...item} data-desk="done" data-output={c.output} data-state={c.state} className={cx('flex flex-col gap-1.5 rounded-[14px] bg-card p-3', item.className)}>
      <div className="flex items-start gap-3">
        <Thumb c={c} />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="line-clamp-2 text-[14px] font-semibold leading-6 text-ink"><PlainText text={c.title_fa} /></span>
          <span className="text-[11px] leading-5 text-muted"><Facts>{c.company_fa}{c.account ? <Ltr tabular={false}>@{c.account}</Ltr> : null}{KIND_FA[c.kind]}</Facts></span>
          {/* Where it stands and when, and the one thing to do about it, on a line of their own (a title is never cut for them). */}
          <span className="flex min-h-8 flex-wrap items-center gap-x-2 gap-y-1">
            {p ? <PublishState p={p} /> : null}
            <span className="text-[11px] text-muted" data-desk-when>{ago(when)}</span>
            <span className="flex-1" />
            {c.state === 'published' && p?.url ? <OpenLink url={p.url} /> : null}
            {c.state === 'failed' && c.route_ready !== false ? <Button variant="secondary" size="sm" onClick={onAgain}>دوباره</Button> : null}
          </span>
        </span>
      </div>
      {c.state === 'failed' && p?.note_fa ? <span className="text-[12px] leading-5 text-neg" data-desk-note><FaText text={p.note_fa} /></span> : null}
      {swept ? (
        <span className="text-[11px] leading-5 text-muted" data-desk-swept>
          <Facts>{swept.archived ? ARCHIVED_FA : null}{swept.freed ? freedFa(fileSize(swept.freed)) : null}</Facts>
        </span>
      ) : null}
    </li>
  );
}

function Section({ title, count, action, children }: { title: string; count: number; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section aria-label={title} className="flex flex-col gap-2.5">
      <div className="flex min-h-9 items-center gap-2">
        <h2 className="flex min-w-0 flex-1 items-baseline gap-2 text-h3 font-semibold text-ink">{title}<span className="text-[12px] font-normal text-muted">{faCount(count)}</span></h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/** Pull down at the top of the page to read again (a touch screen); the button does the same anywhere. */
function usePull(refresh: () => Promise<unknown>) {
  const [pull, setPull] = useState(0);
  const [busy, setBusy] = useState(false);
  const from = useRef<number | null>(null);
  const run = () => { if (busy) return; setBusy(true); void refresh().finally(() => setBusy(false)); };
  return {
    pull, busy, run,
    handlers: {
      onTouchStart: (e: TouchEvent) => { from.current = window.scrollY <= 0 ? e.touches[0]?.clientY ?? null : null; },
      onTouchMove: (e: TouchEvent) => { if (from.current == null) return; const d = (e.touches[0]?.clientY ?? 0) - from.current; setPull(d > 0 ? Math.min(88, d * 0.5) : 0); },
      onTouchEnd: () => { if (pull >= 56) { haptic('tick'); run(); } setPull(0); from.current = null; },
    },
  };
}

const sections = (d: PublishDesk, ch: string | null) => {
  const mine = (l: DeskCard[] | undefined) => (l ?? []).filter((c) => !ch || channelOf(c) === ch);
  return { ready: mine(d.ready), queue: mine(d.queue), done: mine(d.done) };
};
/** The channels the desk's cards go out on, in the order they first appear (Instagram today). */
const channelsOf = (d: PublishDesk | null | undefined): string[] => {
  const out: string[] = [];
  for (const c of [...(d?.ready ?? []), ...(d?.queue ?? []), ...(d?.done ?? [])]) { const ch = channelOf(c); if (!out.includes(ch)) out.push(ch); }
  return out;
};

/** §58.5 a tab per channel, each with its «آماده | در صف | منتشرشده». */
function ChannelTabs({ d, channels, on, onPick }: { d: PublishDesk; channels: string[]; on: string; onPick: (ch: string) => void }) {
  return (
    <div role="tablist" aria-label="کانال‌های انتشار" data-testid="desk-channels" className="no-scrollbar flex gap-1.5 overflow-x-auto">
      {channels.map((ch) => {
        const n = sections(d, ch);
        const sel = ch === on;
        return (
          <button key={ch} type="button" role="tab" aria-selected={sel} aria-controls="desk-channel-panel" data-channel={ch} onClick={() => onPick(ch)}
            className={cx('flex min-w-0 flex-none flex-col items-start gap-0.5 rounded-[12px] px-3.5 py-2 text-start', sel ? 'bg-raised shadow-[inset_0_0_0_1px_var(--hq-silver-line)]' : 'bg-tile hover:bg-hover')}>
            <span className={cx('text-[14px] leading-6', sel ? 'font-semibold text-ink' : 'text-sec')}>{channelFa(ch)}</span>
            <span className="text-[11px] leading-4 text-muted" data-channel-counts>
              <Facts>{`${faCount(n.ready.length)} آماده`}{`${faCount(n.queue.length)} در صف`}{`${faCount(n.done.length)} منتشرشده`}</Facts>
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** The desk itself. */
export function PublishDeskView() {
  const { company } = useScope();
  const q = usePublishDesk(company);
  const [asking, setAsking] = useState<DeskCard | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const p = usePull(() => q.refetch());
  const channels = useMemo(() => channelsOf(q.data), [q.data]);
  if (q.isLoading) return <div className="flex flex-col gap-3"><Skeleton className="h-72 rounded-[16px]" /><Skeleton className="h-20 rounded-[14px]" /></div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <Card><Empty icon="send" title="میز انتشار بعد از به‌روزرسانی ستاد می‌آید" body="تا آن وقت، هر خروجی را از صفحه‌ی خودش منتشر کن." /></Card>;
  // The channel he picked while it still has cards, else the first.
  const channel = picked && channels.includes(picked) ? picked : channels[0] ?? null;
  const { ready, queue, done } = sections(q.data, channel);
  const empty = !ready.length && !queue.length && !done.length;
  // Only the first card that can be published carries the full gold.
  const lead = ready.find((c) => c.route_ready !== false)?.output ?? null;
  // Pulled down, or the quiet button beside the first heading: the desk is read again.
  const refresh = (
    <span className="flex flex-none items-center gap-2">
      <span role="status" className="text-[12px] text-muted">{p.busy || q.isFetching ? 'در حال خواندن…' : ''}</span>
      <IconButton icon="refresh" label="تازه کن" size={36} onClick={p.run} />
    </span>
  );
  return (
    <div className="mx-auto flex w-full max-w-[44rem] flex-col gap-6" data-testid="publish-desk" {...p.handlers}>
      {p.pull > 0 ? <div aria-hidden className="flex items-end justify-center" style={{ height: p.pull }}>{p.pull > 8 ? <Arc size={16} word="در حال خواندن" /> : null}</div> : null}
      {channel ? <ChannelTabs d={q.data} channels={channels} on={channel} onPick={setPicked} /> : null}
      <div id="desk-channel-panel" role={channel ? 'tabpanel' : undefined} aria-label={channel ? channelFa(channel) : undefined} className="flex flex-col gap-6">
      {empty ? <div className="flex flex-col gap-1"><div className="flex justify-end">{refresh}</div><Card><p className="px-5 py-10 text-center text-[14px] leading-7 text-sec" data-testid="desk-empty">{DESK_EMPTY_FA}</p></Card></div> : null}
      {ready.length ? (
        <Section title="آماده‌ی انتشار" count={ready.length} action={refresh}>
          <ul className="grid gap-3 sm:grid-cols-2">{ready.map((c, i) => <ReadyCard key={c.output} c={c} i={i} lead={c.output === lead} onAsk={() => setAsking(c)} />)}</ul>
        </Section>
      ) : null}
      {queue.length ? (
        <Section title="در صف" count={queue.length} action={ready.length ? null : refresh}>
          <ul className="flex flex-col gap-2">{queue.map((c, i) => <QueueCard key={`${c.output}-${c.publish?.job ?? c.file.id}`} c={c} i={i} />)}</ul>
        </Section>
      ) : null}
      {done.length ? (
        <Section title="منتشرشده" count={done.length} action={ready.length || queue.length ? null : refresh}>
          <ul className="flex flex-col gap-2">{done.map((c, i) => <DoneCard key={`${c.output}-${c.publish?.job ?? c.file.id}`} c={c} i={i} onAgain={() => setAsking(c)} />)}</ul>
        </Section>
      ) : null}
      </div>
      {asking ? <PublishFor output={asking.output} fileId={asking.file.id} seed={seedOf(asking)} onClose={() => setAsking(null)} /> : null}
    </div>
  );
}
