'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Empty, ErrorState, FilterChip, Segmented, Skeleton } from '@/components/ui/primitives';
import { MdInline } from '@/components/ui/md';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useNotificationActions, useNotificationPages, type Notification } from '@/lib/api/v21';
import { closeSystem } from '@/lib/alerts';
import { LEVEL } from '@/lib/labels';
import { categoryOf, countLine, groupNotifications, splitNotifications, type NotificationGroup } from '@/lib/notify';
import { linkRoute } from '@/lib/refs';
import { ago, cx, jTime } from '@/lib/format';
import { UndoBar, type Undo } from './bits';

// Notifications (0.5.0; contract §6, §25; the Android app's ui/notifications): «خوانده‌نشده» holds only what the owner has not read; opening
// one reads it and it leaves the list, a row's «خوانده شد» marks it read (with a few seconds to undo), «همه خوانده شد» moves everything there.
// «خوانده‌شده» keeps the rest. The same alert raised again and again is one row with its count, opened to see each time. A label says what
// each one is about (from its link). Approvals never happen here: a card only opens the cartable.

const LEVELS = ['urgent', 'decision', 'report', 'info', 'learning'] as const;
const TONE: Record<string, string> = { neg: 'text-neg bg-neg-soft', warn: 'text-warn bg-warn-soft', lapis: 'text-lapis bg-lapis-soft', pos: 'text-pos bg-pos-soft', learn: 'text-learn bg-learn-soft' };
const INK: Record<string, string> = { neg: 'text-neg', warn: 'text-warn', lapis: 'text-lapis', pos: 'text-pos', learn: 'text-learn' };
const GRACE_MS = 5_000;

/**
 * Marking read, kept on the hub (`POST /notifications/read {ids}`, `/read-all`). The hub has no way to mark one unread again, so a row's button or
 * «همه خوانده شد» waits a few seconds before it is sent: «برگردان» in that time simply never sends it. Opening one sends at once. Leaving
 * the page sends what is waiting.
 */
function useReads() {
  const act = useNotificationActions();
  const toast = useToast();
  const [marked, setMarked] = useState<Record<string, string>>({});
  const waiting = useRef(new Map<number, { ids: string[]; all: { before: string | null; level: string | null } | null; timer: ReturnType<typeof setTimeout> }>());
  const send = useCallback(async (ids: string[], all: { before: string | null; level: string | null } | null) => {
    try {
      if (all) await act.readAll.mutateAsync(all); else await act.read.mutateAsync(ids);
      void closeSystem({ ids });
    } catch (e) {
      setMarked((m) => { const n = { ...m }; for (const id of ids) delete n[id]; return n; });
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'علامت خوانده‌شده به هاب نرسید.' });
    }
  }, [act.read, act.readAll, toast]);
  const open = useCallback((id: string) => {
    setMarked((m) => (m[id] ? m : { ...m, [id]: new Date().toISOString() }));
    void send([id], null);
  }, [send]);
  const mark = useCallback((ids: string[], all: { before: string | null; level: string | null } | null = null): number => {
    const at = new Date().toISOString();
    setMarked((m) => ({ ...m, ...Object.fromEntries(ids.filter((id) => !m[id]).map((id) => [id, at])) }));
    const token = Date.now() + Math.random();
    const timer = setTimeout(() => { const b = waiting.current.get(token); if (!b) return; waiting.current.delete(token); void send(b.ids, b.all); }, GRACE_MS);
    waiting.current.set(token, { ids, all, timer });
    return token;
  }, [send]);
  const undo = useCallback((token: number) => {
    const b = waiting.current.get(token);
    if (!b) return;
    clearTimeout(b.timer);
    waiting.current.delete(token);
    setMarked((m) => { const n = { ...m }; for (const id of b.ids) delete n[id]; return n; });
  }, []);
  // What waits for its grace time is sent when the owner leaves.
  useEffect(() => () => { for (const b of waiting.current.values()) { clearTimeout(b.timer); void send(b.ids, b.all); } waiting.current.clear(); }, [send]);
  return { marked, open, mark, undo, answer: act.answer };
}

function Badge({ n, count }: { n: Notification; count?: number }) {
  const lv = LEVEL[n.level] ?? LEVEL.info!;
  return (
    <span className="relative flex-none">
      <span className={cx('flex size-9 items-center justify-center rounded-full', TONE[lv.tone])}><Icon name={lv.icon} size={18} /></span>
      {count && count > 1 ? <span className="absolute -bottom-1 -start-1 flex size-[18px] items-center justify-center rounded-full bg-gold text-[10px] font-bold text-on-gold">{count}</span> : null}
    </span>
  );
}

/** The top line of a row: what it is about in its level's tone, the company, when, and an unread dot. */
function Head({ n, unread, time }: { n: Notification; unread: boolean; time: string }) {
  const lv = LEVEL[n.level] ?? LEVEL.info!;
  return (
    <span className="flex items-center gap-1.5 text-[11px]">
      <span className={cx('font-semibold', INK[lv.tone])}>{categoryOf(n)}</span>
      {n.company ? <span className="text-muted"><CompanyMark code={n.company} height={11} mono /></span> : null}
      <span className="min-w-0 flex-1 truncate text-muted">{time}</span>
      {unread ? <span className="size-2 flex-none rounded-full bg-gold" aria-label="خوانده‌نشده" /> : null}
    </span>
  );
}

function Row({ g, unreadTab, expanded, onToggle, onOpen, onRead, onAnswer }: {
  g: NotificationGroup; unreadTab: boolean; expanded: boolean; onToggle: () => void; onOpen: (n: Notification) => void; onRead: () => void; onAnswer: (n: Notification, choice: string) => void;
}) {
  const n = g.latest;
  const unread = g.items.some((x) => !x.read_at);
  const route = linkRoute(n.link?.kind, n.link?.ref);
  if (g.folded) {
    // The same alert raised [count] times: its latest words, «۵ بار، آخرین …», and every time on opening the row.
    return (
      <div className="hq-rise flex flex-col rounded-[14px] bg-card p-3">
        <button type="button" onClick={onToggle} aria-expanded={expanded} className="flex gap-3 text-start">
          <Badge n={n} count={g.count} />
          <span className="flex min-w-0 flex-1 flex-col gap-0.5">
            <Head n={n} unread={unread} time={countLine(g)} />
            <span className={cx('text-[14px] leading-6', unread ? 'font-bold text-ink' : 'font-semibold text-sec')}><MdInline text={n.title_fa} /></span>
            {n.body_fa && !expanded ? <span className="line-clamp-2 text-[12px] leading-5 text-sec">{n.body_fa}</span> : null}
          </span>
        </button>
        <span className="flex items-center gap-1 ps-12 pt-1 text-[12px] text-muted">
          <span className={cx('transition-transform', expanded && 'rotate-180')}><Icon name="chevron" size={14} /></span>
          <span className="flex-1">{expanded ? 'بستن' : `هر ${g.count} بار`}</span>
          {unreadTab ? <Button variant="text" size="sm" icon="seal" onClick={onRead}>همه خوانده شد</Button> : null}
        </span>
        {expanded ? (
          <ul className="hq-rise mt-2 flex flex-col divide-y divide-div ps-12">
            {g.items.map((x) => {
              const r = linkRoute(x.link?.kind, x.link?.ref);
              return (
                <li key={x.id}>
                  <button type="button" disabled={!r} onClick={() => onOpen(x)} className="flex w-full items-center gap-2.5 rounded-[8px] py-2 text-start enabled:hover:bg-hover">
                    <span className="fig w-11 text-[12px] text-sec">{jTime(x.created_at)}</span>
                    <span className="min-w-0 flex-1 truncate text-[11px] text-muted">{ago(x.created_at)}</span>
                    {!x.read_at ? <span className="size-1.5 rounded-full bg-gold" /> : null}
                    {x.link?.ref ? <span className={cx('fig text-[12px]', r ? 'text-gold-ink' : 'text-muted')}>{x.link.ref}</span> : null}
                    {r ? <span className="text-muted"><Icon name="next" size={14} mirror /></span> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    );
  }
  const choices = n.choices ?? [];
  return (
    <div className={cx('hq-rise flex gap-3 rounded-[14px] p-3', unread ? 'bg-card' : 'bg-card/60', unread && n.level === 'urgent' && 'tahrir')}>
      <Badge n={n} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <button type="button" onClick={() => onOpen(n)} disabled={!route && !unread} className="flex flex-col gap-0.5 text-start" aria-label={route ? 'باز کن' : 'خوانده شد'}>
          <Head n={n} unread={unread} time={ago(n.created_at)} />
          <span className={cx('text-[14px] leading-6', unread ? 'font-bold text-ink' : 'font-semibold text-sec')}><MdInline text={n.title_fa} /></span>
          {n.body_fa ? <span className="line-clamp-3 text-[12px] leading-5 text-sec"><MdInline text={n.body_fa} /></span> : null}
        </button>
        {choices.length ? (
          <div className="flex flex-wrap gap-2 pt-1.5">
            {choices.map((c) => (
              <button key={c.id} type="button" disabled={!!n.answer} onClick={() => onAnswer(n, c.id)}
                className={cx('h-8 rounded-full px-3 text-[13px] transition-colors', n.answer === c.id ? 'bg-gold-soft text-gold-ink' : 'bg-tile text-sec enabled:hover:text-ink')}>{c.label_fa}</button>
            ))}
          </div>
        ) : null}
        {unreadTab && route && !choices.length ? <span className="flex justify-end"><Button variant="text" size="sm" icon="seal" onClick={onRead}>خوانده شد</Button></span> : null}
      </div>
    </div>
  );
}

/** The notifications: the bell's sheet (compact) and the page. */
export function NotificationsView({ onNavigate, compact }: { onNavigate?: () => void; compact?: boolean }) {
  const router = useRouter();
  const toast = useToast();
  const [tab, setTab] = useState<'unread' | 'read'>('unread');
  const [level, setLevel] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [undo, setUndo] = useState<Undo | null>(null);
  const unreadQ = useNotificationPages({ unread: true, level });
  const readQ = useNotificationPages({ unread: false, level });
  const r = useReads();
  const [unread, read] = useMemo(() => splitNotifications(unreadQ.data?.pages.flatMap((p) => p.items) ?? [], readQ.data?.pages.flatMap((p) => p.items) ?? [], r.marked), [unreadQ.data, readQ.data, r.marked]);
  const groups = useMemo(() => groupNotifications(tab === 'unread' ? unread : read), [tab, unread, read]);
  const q = tab === 'unread' ? unreadQ : readQ;

  const markRead = (g: NotificationGroup) => {
    const ids = g.ids.filter((id) => !r.marked[id]);
    if (!ids.length) return;
    const token = r.mark(ids);
    setUndo({ id: token, text: g.folded ? `${g.count} اعلان خوانده شد` : 'خوانده شد', run: () => r.undo(token) });
  };
  const openOne = (n: Notification) => {
    if (!n.read_at) r.open(n.id);
    const to = linkRoute(n.link?.kind, n.link?.ref);
    if (to) { onNavigate?.(); router.push(to); }
  };
  const all = () => {
    const ids = unread.map((n) => n.id);
    // Up to the newest the owner sees, of the level on show: what arrives meanwhile stays unread.
    const token = r.mark(ids, { before: unread.reduce((a, n) => (n.created_at > a ? n.created_at : a), ''), level });
    setUndo({ id: token, text: `${ids.length} اعلان خوانده شد`, run: () => r.undo(token) });
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-[14rem] flex-1"><Segmented label="اعلان‌ها" value={tab} onChange={setTab} options={[
          // Rows, not raw notifications: the hourly finding raised five times is one row to read.
          { value: 'unread', label: unreadQ.data && unread.length ? `خوانده‌نشده (${groupNotifications(unread).length})` : 'خوانده‌نشده' }, { value: 'read', label: 'خوانده‌شده' },
        ]} /></div>
        {tab === 'unread' && unread.length ? <Button variant="secondary" size="sm" icon="seal" onClick={all}>همه خوانده شد</Button> : null}
      </div>
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
        <FilterChip selected={!level} onClick={() => setLevel(null)}>همه</FilterChip>
        {LEVELS.map((l) => <FilterChip key={l} selected={level === l} onClick={() => setLevel(level === l ? null : l)}>{LEVEL[l]?.fa ?? l}</FilterChip>)}
      </div>
      {q.isLoading ? <div className="flex flex-col gap-2">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[76px] rounded-[14px]" />)}</div>
        : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : !groups.length ? (tab === 'unread'
          ? <Empty icon="bell" title="همه را خوانده‌ای" body="اعلان تازه این‌جا میاید؛ خوانده‌شده‌ها در «خوانده‌شده» میمانند." />
          : <Empty icon="bell" title="هنوز اعلانی خوانده نشده" body="اعلانی را باز کن یا «خوانده شد» را بزن تا این‌جا بیاید." />) : (
          <>
            {tab === 'unread' && !compact ? <span className="text-[12px] text-muted">بزن تا باز شود؛ «خوانده شد» آن را به خوانده‌شده میبرد؛ تکراری‌ها یک ردیف‌اند.</span> : null}
            <div className="flex flex-col gap-2">
              {groups.map((g) => (
                <Row key={`${g.key}:${g.latest.id}`} g={g} unreadTab={tab === 'unread'} expanded={open.has(g.key)} onToggle={() => setOpen((s) => { const n = new Set(s); if (n.has(g.key)) n.delete(g.key); else n.add(g.key); return n; })}
                  onOpen={openOne} onRead={() => markRead(g)}
                  onAnswer={(n, c) => r.answer.mutate({ id: n.id, choice: c }, { onError: (e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' }) })} />
              ))}
            </div>
            {tab === 'read' && readQ.hasNextPage ? <Button variant="secondary" icon="next" loading={readQ.isFetchingNextPage} onClick={() => readQ.fetchNextPage()}>بیشتر</Button> : null}
          </>
        )}
      <UndoBar undo={undo} onDone={(id) => setUndo((u) => (u?.id === id ? null : u))} />
    </div>
  );
}
