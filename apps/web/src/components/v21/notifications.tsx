'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Icon } from '@/components/icon';
import { CompanyMark, Monogram } from '@/components/brand/marks';
import { needsStepUp } from '@/components/cartable/decision-detail';
import { Button, IconButton } from '@/components/ui/button';
import { Empty, ErrorState, Segmented, Skeleton } from '@/components/ui/primitives';
import { MdInline } from '@/components/ui/md';
import { Dialog } from '@/components/ui/overlay';
import { useToast } from '@/components/ui/toast';
import { useTick } from '@/components/live/motion';
import { haptic } from '@/components/look/haptics';
import { DrawnTick, Ring } from '@/components/look/ring';
import { stagger } from '@/components/look/stagger';
import { Facts, Ltr, clock, faCount, seps } from '@/components/look/text';
import { RowCheck, SelectAll, useSelection } from '@/components/v28/outputs';
import { ApiError, type Schemas } from '@/lib/api/client';
import { useCompanies, useDecide, useDecisions } from '@/lib/api/hooks';
import { sealTarget } from '@/lib/api/v19';
import { useNotificationActions, useNotificationPages, type Notification } from '@/lib/api/v21';
import { useDeleteNotifications, useServed } from '@/lib/api/v28';
import { closeSystem } from '@/lib/alerts';
import { stepUp } from '@/lib/auth';
import { ago, cx, until } from '@/lib/format';
import { LEVEL3_FA, LEVELS3, asksOwner, categoryOf, dayKey, dayLabel, groupNotifications, humanize, level3, splitNotifications, type Level3, type NotificationGroup } from '@/lib/notify';
import { plain } from '@/lib/plain';
import { linkRoute } from '@/lib/refs';
import { UndoBar, type Undo } from './bits';

type Decision = Schemas['Decision'];

// Notifications (0.5.0; contract §6, §25), ⟨1.0.1⟩ rebuilt (part C, C3.5): three levels only («فوری» red, «تصمیم» gold, «خبر» silent:
// the hub's report, info and learning together), one filter bar, and one list. On top, fixed, «از تو کاری میخواهد»: what is urgent or
// a decision and not answered yet, each with its own action right there («تأیید», «ببین», the ready answers) and its deadline as a
// ring that empties. Then everything else by day («امروز», «دیروز», the date). A row is compact: the level's sign, the title, one
// line, the time; unread is a thin gold line at its edge and nothing else. A swipe (or the small tick that shows under the pointer)
// is «خوانده شد», with a drawn tick and a light haptic, and a few seconds to take it back. The same alert raised again and again is
// one row with its count. A title the machine wrote is said in Persian; its raw text is one tap away.
// ⟨1.10.1⟩ §28.5: «انتخاب» lets the owner choose rows (a box each, shift for a range, «انتخاب همه»): marked read, or deleted for
// good (`DELETE /notifications`, after a plain confirmation; hidden on a hub without it).

const GRACE_MS = 5_000;
/** Kinds sealed on their own page against a digest: the row leads there instead of approving in place. */
const OWN_PAGE = new Set(['server_plan', 'media_series', 'server_destructive']);

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
  // The mutations are new objects on every render: the sender reads them through a ref, so it stays the same function and the flush
  // below runs only when the page is left (it used to run on the next render and send at once, leaving «برگردان» nothing to undo).
  const latest = useRef({ act, toast });
  useEffect(() => { latest.current = { act, toast }; });
  const send = useCallback(async (ids: string[], all: { before: string | null; level: string | null } | null) => {
    const { act: a, toast: t } = latest.current;
    try {
      if (all) await a.readAll.mutateAsync(all); else await a.read.mutateAsync(ids);
      void closeSystem({ ids });
    } catch (e) {
      setMarked((m) => { const n = { ...m }; for (const id of ids) delete n[id]; return n; });
      t({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'علامت خوانده‌شده به هاب نرسید.' });
    }
  }, []);
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

// ------------------------------------------------------------------------------------------------- the pieces --
const SIGN: Record<Level3, { icon: 'urgent' | 'level-decision' | 'info'; cls: string }> = {
  urgent: { icon: 'urgent', cls: 'bg-neg-soft text-neg' },
  decision: { icon: 'level-decision', cls: 'text-gold-ink shadow-[inset_0_0_0_1px_var(--hq-line-tahrir)]' },
  news: { icon: 'info', cls: 'bg-tile text-muted' },
};
/** The level's sign: a shape and its word (for a reader), with the count of a folded row. */
function Sign({ level, count }: { level: Level3; count?: number }) {
  const g = SIGN[level];
  return (
    <span className="relative flex-none self-start" data-level={level}>
      <span className={cx('flex size-8 items-center justify-center rounded-full', g.cls)}><Icon name={g.icon} size={16} label={LEVEL3_FA[level]} /></span>
      {count && count > 1 ? <span className="absolute -bottom-1 -start-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-raised px-1 text-[10px] font-bold text-ink" data-count={count}>{faCount(count)}</span> : null}
    </span>
  );
}

/** A deadline as a ring that empties, with how long is left in words. */
function Deadline({ from, to }: { from: string; to: string }) {
  const now = useTick(30_000);
  const total = new Date(to).getTime() - new Date(from).getTime();
  const left = new Date(to).getTime() - now;
  const share = total > 0 ? Math.max(0, Math.min(1, left / total)) : 0;
  const words = until(to, now);
  return (
    <span className="inline-flex flex-none items-center gap-1.5 text-[11px] text-sec" data-deadline>
      <Ring value={share} size={18} stroke={2.5} tone={share < 0.2 ? 'neg' : share < 0.5 ? 'warn' : 'silver'} label={`مهلت: ${words}`} />
      {words}
    </span>
  );
}

const SWIPE_PX = 88;
/** A swipe along the row is «خوانده شد»: the row follows the finger, a tick draws itself under it, and past the threshold it is read. */
function SwipeRead({ on, onRead, children }: { on: boolean; onRead: () => void; children: ReactNode }) {
  const row = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: number; x: number; y: number; dx: number; live: boolean } | null>(null);
  const [past, setPast] = useState(false);
  // A swipe may begin on the row's own tap area; the tap that would follow it is swallowed.
  const swiped = useRef(false);
  if (!on) return <>{children}</>;
  const down = (e: ReactPointerEvent<HTMLDivElement>) => {
    swiped.current = false;
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    if ((e.target as HTMLElement).closest('input, label, summary, [data-actions]')) return;
    drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY, dx: 0, live: false };
  };
  const move = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    const el = row.current;
    if (!d || d.id !== e.pointerId || !el) return;
    const dx = Math.abs(e.clientX - d.x);
    if (!d.live) {
      if (dx < 10 || dx < Math.abs(e.clientY - d.y) * 1.2) return;
      d.live = true;
      e.currentTarget.setPointerCapture(e.pointerId);
      el.style.transition = 'none';
    }
    d.dx = dx;
    el.style.transform = `translateX(${e.clientX - d.x}px)`;
    setPast(dx >= SWIPE_PX);
  };
  const up = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    const el = row.current;
    if (!d || d.id !== e.pointerId) return;
    drag.current = null;
    if (!el || !d.live) return;
    swiped.current = true;
    el.style.transition = 'transform var(--hq-dur-state) var(--hq-ease-standard)';
    el.style.transform = '';
    setPast(false);
    if (d.dx >= SWIPE_PX) { haptic('tick'); onRead(); }
  };
  return (
    <div className="relative overflow-hidden rounded-[12px]" data-swipe>
      <span aria-hidden className={cx('absolute inset-0 flex items-center justify-between px-5 text-[12px]', past ? 'text-pos' : 'text-muted')}>
        <span className="flex items-center gap-1.5">{past ? <DrawnTick size={18} /> : null}خوانده شد</span>
        <span className="flex items-center gap-1.5">خوانده شد{past ? <DrawnTick size={18} /> : null}</span>
      </span>
      <div ref={row} className="relative touch-pan-y bg-page" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}
        onClickCapture={(e) => { if (swiped.current) { swiped.current = false; e.preventDefault(); e.stopPropagation(); } }}>{children}</div>
    </div>
  );
}

type Check = { on: boolean; onToggle: (range: boolean) => void };
type RowProps = {
  g: NotificationGroup; i: number; ask?: boolean; lead?: boolean; expanded: boolean; onToggle: () => void; onOpen: (n: Notification) => void; onRead: () => void;
  onAnswer: (n: Notification, choice: string) => void; check?: Check | null; decision?: Decision | null; onApprove?: (n: Notification, d: Decision) => Promise<void>; nameOf: (code: string) => string | null;
  holding: (code: string) => boolean;
};

/** One row: the sign, the title, one line, the time. In «از تو کاری میخواهد» it carries its own action and its deadline. */
function Row({ g, i, ask, lead, expanded, onToggle, onOpen, onRead, onAnswer, check, decision, onApprove, nameOf, holding }: RowProps) {
  const n = g.latest;
  const lv = level3(n.level);
  const unread = g.items.some((x) => !x.read_at);
  const route = linkRoute(n.link?.kind, n.link?.ref);
  const title = plain(humanize(n.title_fa, nameOf));
  const body = plain(humanize(n.body_fa, nameOf));
  // The raw text is offered only when the machine's own words were said otherwise (a dropped ref alone is not that).
  const raw = humanize(n.title_fa, nameOf) !== n.title_fa || humanize(n.body_fa, nameOf) !== (n.body_fa ?? '') ? [n.title_fa, n.body_fa].filter(Boolean).join(' · ') : null;
  const choices = n.choices ?? [];
  const [busy, setBusy] = useState(false);
  const approve = decision && onApprove && !OWN_PAGE.has(decision.kind) ? async () => { setBusy(true); try { await onApprove(n, decision); } finally { setBusy(false); } } : null;
  // A tap opens what it is about; a row with nothing to open (or a folded one) opens itself.
  const tap = () => (g.folded || !route ? onToggle() : onOpen(n));
  const item = { ...stagger(i) };
  return (
    <li {...item} data-row={n.id} data-unread={unread ? '' : undefined} className={item.className}>
      <SwipeRead on={unread && !check} onRead={onRead}>
        <div className={cx('group/row flex gap-2.5 rounded-[12px] px-2.5 py-2.5', unread && 'hq-edge', ask ? 'bg-card' : 'hover:bg-hover', check?.on && 'shadow-[inset_0_0_0_1px_var(--hq-silver-line)]')}>
          {check ? <RowCheck on={check.on} label={`انتخاب: ${title}`} onToggle={check.onToggle} /> : null}
          <Sign level={lv} count={g.count} />
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <button type="button" onClick={tap} aria-expanded={g.folded || !route ? expanded : undefined} className="flex flex-col gap-0.5 rounded-[6px] text-start">
              <span className="flex items-baseline gap-2">
                <span className={cx('min-w-0 flex-1 text-[14px] leading-6', expanded || ask ? 'line-clamp-3' : 'line-clamp-1', unread ? 'font-semibold text-ink' : 'text-sec')}><MdInline text={title} links={false} /></span>
                <span className="flex-none text-[11px] text-muted" data-time>{ago(n.created_at)}</span>
              </span>
              <span className={cx('flex min-w-0 items-center gap-1.5 text-[12px] leading-5 text-muted', !(expanded || ask) && 'whitespace-nowrap')}>
                {n.company ? <span className="flex-none">{holding(n.company) ? <Monogram size={11} ink="currentColor" /> : <CompanyMark code={n.company} height={10} mono />}</span> : null}
                <span className={cx('min-w-0', expanded || ask ? 'line-clamp-4' : 'truncate')}>
                  <Facts>{categoryOf(n)}{g.folded ? <span data-times>{faCount(g.count)} بار</span> : null}{body ? <span>{seps(body, (x, k) => <MdInline key={k} text={x} links={false} />)}</span> : null}</Facts>
                </span>
              </span>
            </button>
            {unread ? <span className="sr-only" aria-label="خوانده‌نشده" role="img" /> : null}
            {choices.length ? (
              <div role="group" aria-label="جواب‌های آماده" className="flex flex-wrap gap-2 pt-1.5">
                {choices.map((c) => (
                  <button key={c.id} type="button" disabled={!!n.answer} onClick={() => { haptic('tick'); onAnswer(n, c.id); }}
                    className={cx('h-8 rounded-full px-3 text-[13px]', n.answer === c.id ? 'bg-raised font-semibold text-ink shadow-[inset_0_0_0_1px_var(--hq-silver-line)]' : 'border border-strong text-sec enabled:hover:text-ink')}>{c.label_fa}</button>
                ))}
              </div>
            ) : null}
            {ask && !choices.length ? (
              <div className="flex flex-wrap items-center gap-2 pt-1.5" data-actions>
                {approve ? <Button size="sm" variant={lead ? 'primary' : 'secondary'} icon={needsStepUp(decision!) ? 'seal' : undefined} loading={busy} onClick={() => void approve()}>تأیید</Button> : null}
                {route ? <Button size="sm" variant={approve ? 'ghost' : 'secondary'} onClick={() => onOpen(n)}>ببین</Button> : null}
                <span className="flex-1" />
                {decision?.expires_at ? <Deadline from={decision.created_at} to={decision.expires_at} /> : null}
              </div>
            ) : null}
            {expanded ? (
              <div className="hq-m1-row flex flex-col gap-1.5 pt-1.5">
                {g.folded ? (
                  <ul className="flex flex-col divide-y divide-div">
                    {g.items.map((x) => {
                      const r = linkRoute(x.link?.kind, x.link?.ref);
                      return (
                        <li key={x.id}>
                          <button type="button" disabled={!r} onClick={() => onOpen(x)} className="flex w-full items-center gap-2.5 rounded-[8px] py-1.5 text-start enabled:hover:bg-hover">
                            <Ltr className="w-11 text-[12px] text-sec">{clock(x.created_at)}</Ltr>
                            <span className="min-w-0 flex-1 truncate text-[11px] text-muted">{ago(x.created_at)}</span>
                            {r ? <span className="text-[12px] text-silver-ink">ببین</span> : null}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
                {raw ? (
                  <details className="text-[11px] text-muted">
                    <summary className="w-fit cursor-pointer select-none rounded-[6px]">متن خام</summary>
                    <p dir="auto" className="pt-1 leading-5 [overflow-wrap:anywhere]" data-raw><MdInline text={plain(raw)} links={false} /></p>
                  </details>
                ) : null}
              </div>
            ) : null}
          </div>
          {unread && !check ? (
            <IconButton icon="seal" label={g.folded ? 'همه خوانده شد' : 'خوانده شد'} size={32} onClick={() => { haptic('tick'); onRead(); }}
              className="self-center opacity-0 focus-visible:opacity-100 group-hover/row:opacity-100 [@media(hover:none)]:hidden" />
          ) : null}
        </div>
      </SwipeRead>
    </li>
  );
}

type Filter = 'all' | Level3;

/** The notifications: the bell's sheet (compact) and the page. */
export function NotificationsView({ onNavigate, compact }: { onNavigate?: () => void; compact?: boolean }) {
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>('all');
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [undo, setUndo] = useState<Undo | null>(null);
  const [choosing, setChoosing] = useState(false);
  const unreadQ = useNotificationPages({ unread: true, level: null });
  const readQ = useNotificationPages({ unread: false, level: null });
  const { data: companies } = useCompanies();
  const nameOf = useCallback((code: string) => companies?.find((c) => c.code === code)?.name_fa ?? null, [companies]);
  const holding = useCallback((code: string) => companies?.find((c) => c.code === code)?.kind === 'holding', [companies]);
  const r = useReads();
  const [unread, read] = useMemo(() => splitNotifications(unreadQ.data?.pages.flatMap((p) => p.items) ?? [], readQ.data?.pages.flatMap((p) => p.items) ?? [], r.marked), [unreadQ.data, readQ.data, r.marked]);
  const shown = useCallback((n: Notification) => filter === 'all' || level3(n.level) === filter, [filter]);
  // «از تو کاری میخواهد» stays on top whatever the day; the rest, unread and read together, by day.
  const asking = useMemo(() => groupNotifications(unread.filter((n) => asksOwner(n) && shown(n))), [unread, shown]);
  const rest = useMemo(() => groupNotifications([...unread.filter((n) => !asksOwner(n)), ...read].filter(shown)), [unread, read, shown]);
  const days = useMemo(() => {
    const out: Array<{ key: string; label: string; groups: NotificationGroup[] }> = [];
    for (const g of rest) {
      const k = dayKey(g.latest.created_at);
      const last = out[out.length - 1];
      if (last && last.key === k) last.groups.push(g); else out.push({ key: k, label: dayLabel(g.latest.created_at), groups: [g] });
    }
    return out;
  }, [rest]);
  const groups = useMemo(() => [...asking, ...rest], [asking, rest]);
  const unreadShown = useMemo(() => unread.filter(shown), [unread, shown]);

  // The cards the decision rows speak of: «تأیید» in place needs the card itself (its kind, whether the hub asks for the passkey).
  const wantsCards = asking.some((g) => g.latest.link?.kind === 'decision');
  const cards = useDecisions({ status: 'pending' });
  const cardOf = (n: Notification): Decision | null => (wantsCards && n.link?.kind === 'decision' ? cards.data?.items.find((d) => d.ref === n.link?.ref) ?? null : null);
  const decide = useDecide();

  // ⟨1.10.1⟩ Choosing rows (the page only; the bell's sheet stays a quick look).
  const order = useMemo(() => groups.map((g) => g.key), [groups]);
  const pick = useSelection(order);
  const { clear: clearPick } = pick;
  useEffect(() => { clearPick(); }, [filter, choosing, clearPick]);
  const chosen = groups.filter((g) => pick.has(g.key));
  const chosenIds = chosen.flatMap((g) => g.ids);
  const chosenUnread = chosenIds.filter((id) => unread.some((n) => n.id === id));
  const remove = useDeleteNotifications();
  const canDelete = useServed('notifications.delete');
  const [confirm, setConfirm] = useState(false);
  const del = async () => {
    try {
      const n = await remove.mutateAsync({ ids: chosenIds });
      setConfirm(false);
      pick.clear();
      if (n === null) return; // a hub before ⟨1.10.1⟩: the action is hidden from now on
      toast({ tone: 'ok', text: `${n.toLocaleString('fa-IR')} اعلان برای همیشه پاک شد.` });
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'پاک نشد.' });
    }
  };
  const readChosen = () => {
    const ids = chosenUnread.filter((id) => !r.marked[id]);
    if (!ids.length) return;
    const token = r.mark(ids);
    setUndo({ id: token, text: `${ids.length.toLocaleString('fa-IR')} اعلان خوانده شد`, run: () => r.undo(token) });
    pick.clear();
  };

  const markRead = (g: NotificationGroup) => {
    const ids = g.ids.filter((id) => !r.marked[id] && unread.some((n) => n.id === id));
    if (!ids.length) return;
    const token = r.mark(ids);
    setUndo({ id: token, text: g.folded ? `${ids.length} اعلان خوانده شد` : 'خوانده شد', run: () => r.undo(token) });
  };
  const openOne = (n: Notification) => {
    if (!n.read_at) r.open(n.id);
    const to = linkRoute(n.link?.kind, n.link?.ref);
    if (to) { onNavigate?.(); router.push(to); }
  };
  const all = () => {
    const ids = unreadShown.map((n) => n.id);
    if (!ids.length) return;
    haptic('tick');
    // Everything on show, up to the newest the owner sees: what arrives meanwhile stays unread. One level's rows go by their ids.
    const token = filter === 'all' ? r.mark(ids, { before: unreadShown.reduce((a, n) => (n.created_at > a ? n.created_at : a), ''), level: null }) : r.mark(ids);
    setUndo({ id: token, text: `${ids.length} اعلان خوانده شد`, run: () => r.undo(token) });
  };
  /** «تأیید» on a decision's row: one tap (the passkey only where the hub's rule asks for it), and the row is read. */
  const approve = async (n: Notification, d: Decision) => {
    try {
      const token = needsStepUp(d) ? await stepUp('decision.approve', sealTarget(d)) : undefined;
      await decide.mutateAsync({ ref: d.ref, verdict: 'approve', stepUpToken: token });
      haptic('seal');
      r.open(n.id);
      toast({ tone: 'ok', text: 'تأیید شد.' });
      for (const k of ['office', 'inbox']) void qc.invalidateQueries({ queryKey: [k] });
    } catch (e) {
      haptic('error');
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد.' });
    }
  };
  const toggle = (key: string) => setOpen((s) => { const n = new Set(s); if (n.has(key)) n.delete(key); else n.add(key); return n; });
  const rowProps = (g: NotificationGroup, i: number) => ({
    g, i, expanded: open.has(g.key), onToggle: () => toggle(g.key), onOpen: openOne, onRead: () => markRead(g), nameOf, holding,
    check: choosing && !compact ? { on: pick.has(g.key), onToggle: (range: boolean) => pick.toggle(g.key, range) } : null,
    onAnswer: (n: Notification, c: string) => r.answer.mutate({ id: n.id, choice: c }, { onError: (e: unknown) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' }) }),
  });
  const leadKey = asking.find((g) => { const d = cardOf(g.latest); return d && !OWN_PAGE.has(d.kind); })?.key;
  const loading = unreadQ.isLoading || readQ.isLoading;
  const error = unreadQ.error ?? readQ.error;

  return (
    <div className="flex flex-col gap-3">
      <Segmented<Filter> label="سطح اعلان" value={filter} onChange={setFilter}
        options={[{ value: 'all', label: 'همه' }, ...LEVELS3.map((l) => ({ value: l as Filter, label: LEVEL3_FA[l] }))]} />
      {loading ? <div className="flex flex-col gap-2">{Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-[68px] rounded-[12px]" />)}</div>
        : error ? <ErrorState error={error} onRetry={() => { void unreadQ.refetch(); void readQ.refetch(); }} />
        : !groups.length ? <Empty icon="bell" title={filter === 'all' ? 'اعلانی نیست' : `اعلان «${LEVEL3_FA[filter]}» نیست`} body="هر چه تازه برسد همین‌جا میاید." /> : (
          <>
            <div className="flex min-h-8 flex-wrap items-center gap-x-1 gap-y-1 text-[12px] text-muted">
              <span className="flex-1" data-unread-count={unreadShown.length}>{unreadShown.length ? `${faCount(groupNotifications(unreadShown).length)} خوانده‌نشده` : 'همه را خوانده‌ای'}</span>
              {unreadShown.length ? <Button variant="text" size="sm" onClick={all}>همه خوانده شد</Button> : null}
              {!compact ? <Button variant="text" size="sm" aria-pressed={choosing} onClick={() => setChoosing((v) => !v)}>{choosing ? 'پایان انتخاب' : 'انتخاب'}</Button> : null}
            </div>
            {choosing && !compact ? <SelectAll all={pick.all} some={pick.some} count={groups.length} onToggle={pick.toggleAll} /> : null}
            {asking.length ? (
              <section aria-label="از تو کاری میخواهد" data-testid="asks" className="flex flex-col gap-1.5">
                <h2 className="flex items-center gap-2 px-1 text-[13px] font-semibold text-ink"><span aria-hidden className="size-1.5 rounded-full bg-gold-ink" />از تو کاری میخواهد</h2>
                <ul className="flex flex-col gap-1.5">
                  {asking.map((g, i) => <Row key={`${g.key}:${g.latest.id}`} {...rowProps(g, i)} ask lead={g.key === leadKey} decision={cardOf(g.latest)} onApprove={approve} />)}
                </ul>
              </section>
            ) : null}
            {days.map((d) => (
              <section key={d.key} aria-label={d.label} data-day={d.key} className="flex flex-col gap-0.5">
                <h2 className="px-1 pt-1 text-[12px] font-semibold text-muted">{d.label}</h2>
                <ul className="flex flex-col">
                  {d.groups.map((g, i) => <Row key={`${g.key}:${g.latest.id}`} {...rowProps(g, i)} />)}
                </ul>
              </section>
            ))}
            {readQ.hasNextPage ? <Button variant="secondary" icon="next" loading={readQ.isFetchingNextPage} onClick={() => readQ.fetchNextPage()}>بیشتر</Button> : null}
            {!compact && choosing && chosen.length ? (
              <div role="toolbar" aria-label="کار با اعلان‌های انتخاب‌شده" className="hq-rise sticky bottom-[5.5rem] z-20 flex flex-wrap items-center gap-2 rounded-[14px] bg-raised p-2 shadow-[0_12px_32px_rgba(0,0,0,.35)] ring-1 ring-[var(--hq-silver-line)] md:bottom-3">
                <IconButton icon="close" label="لغو انتخاب" size={32} onClick={pick.clear} />
                <span className="flex-1 text-[13px] font-semibold text-ink" aria-live="polite">{chosen.length.toLocaleString('fa-IR')} انتخاب‌شده</span>
                {chosenUnread.length ? <Button variant="secondary" size="sm" icon="seal" onClick={readChosen}>خوانده‌شده</Button> : null}
                {canDelete ? <Button variant="danger" size="sm" icon="reject" onClick={() => setConfirm(true)}>حذف</Button> : null}
              </div>
            ) : null}
          </>
        )}
      <UndoBar undo={undo} onDone={(id) => setUndo((u) => (u?.id === id ? null : u))} />
      <Dialog open={confirm} onOpenChange={setConfirm} title={`${chosenIds.length.toLocaleString('fa-IR')} اعلان پاک شود؟`}
        actions={<>
          <Button variant="danger" icon="reject" loading={remove.isPending} onClick={del}>حذف</Button>
          <Button variant="ghost" onClick={() => setConfirm(false)}>انصراف</Button>
        </>}>
        <p className="font-semibold text-ink">از دیتابیس پاک میشود و برنمیگردد.</p>
        <p className="pt-1 text-[13px] text-sec">خود رویدادها (کارت، کار، یافته) سر جایشان میمانند؛ فقط این اعلان‌ها میروند.</p>
      </Dialog>
    </div>
  );
}
