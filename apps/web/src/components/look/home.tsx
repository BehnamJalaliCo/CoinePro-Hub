'use client';

// ⟨1.0.1⟩ Part C, the home rebuilt (C3.1). The top of the office is the «نوبت تو» row: one large gold count and, under it, what waits
// for the owner as cards that are answered right there (a session's question with its ready answers, one tap; a decision with its own
// action). Then open sessions as cards with three states only («منتظر تو», «در کار», «تمام»), each opening out of itself (M14).
// Nothing here sends the owner elsewhere to answer; the first decision's «تأیید» is the page's only full gold.

import Link from 'next/link';
import { useState, type MouseEvent } from 'react';
import { useQueries, useQueryClient } from '@tanstack/react-query';
import { CompanyMark } from '@/components/brand/marks';
import { needsStepUp } from '@/components/cartable/decision-detail';
import { LiveFigure } from '@/components/live/motion';
import { useLiveBadge } from '@/components/live/session-pulse';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';
import { Empty, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { PlainText } from '@/components/v29/bits';
import { ApiError, type Schemas } from '@/lib/api/client';
import { useDecide } from '@/lib/api/hooks';
import { call } from '@/lib/api/v13';
import { sealTarget } from '@/lib/api/v19';
import { orderReport } from '@/lib/api/v29';
import { PACE_FA, bySessionOrder, type Badge, type Office, type SessionCard, type SessionReport } from '@/lib/api/v34';
import { DECIDE_YOURSELF_FA, readyAnswers } from '@/lib/api/v55';
import { stepUp } from '@/lib/auth';
import { cx } from '@/lib/format';
import { DECISION_KIND, RISK } from '@/lib/labels';
import { plain } from '@/lib/plain';
import { haptic } from './haptics';
import { DrawnTick } from './ring';
import { stagger } from './stagger';
import { Facts, faCount } from './text';
import { useViewNav } from './transition';

type Decision = Schemas['Decision'];

// ============================================================================================== the three states ==
export type SessionState3 = 'waiting' | 'working' | 'done';
/** Three states only: what waits for the owner (his turn, or ready for his approval), what is being worked on (a session stuck on
 *  something that is not his says so in its own line), and what is finished. */
export const state3 = (b: Badge): SessionState3 => (b === 'closed' ? 'done' : b === 'your_turn' || b === 'ready' ? 'waiting' : 'working');
export const STATE3_FA: Record<SessionState3, string> = { waiting: 'منتظر تو', working: 'در کار', done: 'تمام' };

/** A shape and a word, never colour alone: a gold dot (waits for him), a silver ring (work), a tick (done). */
export function StateMark({ state }: { state: SessionState3 }) {
  return (
    <span className={cx('inline-flex flex-none items-center gap-1.5 text-[12px] font-semibold', state === 'waiting' ? 'text-gold-ink' : state === 'working' ? 'text-silver-ink' : 'text-muted')} data-state3={state}>
      {state === 'waiting' ? <span aria-hidden className="size-2 rounded-full bg-current" />
        : state === 'working' ? <span aria-hidden className="size-2.5 rounded-full border-[1.5px] border-current" />
        : <svg aria-hidden width="12" height="12" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></svg>}
      {STATE3_FA[state]}
    </span>
  );
}

/** «۶ دقیقه منتظر», «۲ ساعت منتظر»: how long something has waited for him (a count in a sentence). */
export function waitedFa(iso: string | null | undefined, now = Date.now()): string | null {
  if (!iso) return null;
  const m = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60_000));
  if (!Number.isFinite(m)) return null;
  if (m < 1) return 'همین الان';
  if (m < 60) return `${m} دقیقه منتظر`;
  const h = Math.round(m / 60);
  return h < 48 ? `${h} ساعت منتظر` : `${Math.round(h / 24)} روز منتظر`;
}

const sessionHref = (ref: string) => `/s/${encodeURIComponent(ref)}`;
/** A plain left click opens the page out of the card (M14); any other click is the link's own. */
function useCardNav() {
  const go = useViewNav();
  return (href: string) => (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    go(href, e.currentTarget.closest<HTMLElement>('[data-card]') ?? e.currentTarget);
  };
}

// ====================================================================================== a session that waits for him ==
/** A card that waits for him: the thin gold line at its start edge is the only gold it carries. */
const CARD = 'hq-edge rounded-[14px] bg-card p-3.5';
const SEE = 'inline-flex h-9 flex-none items-center rounded-[10px] border border-strong px-3 text-[13px] font-semibold text-ink hover:bg-hover';
const answerCls = 'inline-flex min-h-10 items-center rounded-[12px] border border-strong px-3.5 py-1.5 text-start text-[13px] font-semibold leading-5 text-ink hover:bg-hover disabled:text-disabled';

/** A session in his turn: the full question, its ready answers (one tap sends that answer through the session's own reply), how
 *  long it has waited and which task stands still. Anything else that waits (ready for his approval, stuck) says why and opens. */
function WaitingSession({ s, i, report }: { s: SessionCard; i: number; report: { data: SessionReport | null | undefined; isLoading: boolean } }) {
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useCardNav();
  const turn = report.data?.turn ?? null;
  const [sent, setSent] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const question = turn?.question_fa ?? null;
  const answers = s.badge === 'your_turn' && question ? readyAnswers(plain(question), (report.data as { quick_replies?: string[] } | null | undefined)?.quick_replies) : [];
  const waited = waitedFa(turn?.at ?? s.last_at);
  const standing = s.tasks.total > 0 && s.tasks.done < s.tasks.total ? `کار ${s.tasks.done + 1} از ${s.tasks.total} ایستاده` : null;
  const reply = async (text: string) => {
    if (busy) return;
    setBusy(text);
    try {
      await call('POST', `/orders/${encodeURIComponent(s.ref)}/reply`, { text });
      haptic('seal');
      setSent(text);
      await Promise.all(['orders', 'office', 'home', 'talk'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
    } catch (e) {
      haptic('error');
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'جوابت نرسید؛ دوباره بزن.' });
    } finally {
      setBusy(null);
    }
  };
  const who = turn?.who_fa ?? (s.holder ? `${s.holder.title_fa} ${s.holder.company_fa}` : 'مشاور کل');
  const asks = s.badge === 'your_turn' && !!question;
  const head = (
    <Link href={sessionHref(s.ref)} onClick={nav(sessionHref(s.ref))} className="flex min-w-0 flex-1 flex-col gap-1 rounded-[8px]">
      <span className="flex items-center gap-1.5 text-[11px] text-muted">
        {s.holder ? <CompanyMark code={s.holder.company} height={11} mono /> : null}
        <Facts>{asks ? `${who} میپرسد` : who}{waited}{standing}</Facts>
      </span>
      <span className={cx('text-[14px] font-semibold leading-6 text-ink', !asks && 'line-clamp-2')}><PlainText text={question ?? s.reason_fa} /></span>
      {asks ? <span className="line-clamp-1 text-[12px] text-sec"><PlainText text={s.title_fa} /></span> : null}
    </Link>
  );
  const item = { ...stagger(i) };
  if (!asks && !sent) {
    // Nothing to answer in a word (ready for his approval, or a block of his to lift): one row that opens the session.
    return (
      <li {...item} data-card data-wait="session" data-ref={s.ref} className={cx(CARD, 'flex items-center gap-3', item.className)}>
        {head}
        {report.isLoading && s.badge === 'your_turn' ? null : <Link href={sessionHref(s.ref)} onClick={nav(sessionHref(s.ref))} className={SEE}>ببین</Link>}
      </li>
    );
  }
  return (
    <li {...item} data-card data-wait="session" data-ref={s.ref} className={cx(CARD, 'flex flex-col gap-2.5', item.className)}>
      {head}
      {sent ? (
        <span role="status" className="hq-m2-in flex items-center gap-1.5 text-[13px] text-sec"><span className="text-pos"><DrawnTick size={16} /></span>جوابت رفت: {sent}</span>
      ) : (
        <div role="group" aria-label="جواب‌های آماده" className="flex flex-col items-start gap-1.5">
          {answers.length ? (
            <div className="flex flex-wrap gap-2">
              {answers.map((a) => <button key={a} type="button" disabled={!!busy} onClick={() => void reply(a)} className={answerCls}>{a}</button>)}
            </div>
          ) : null}
          <Button variant="text" size="sm" className="-ms-2" disabled={!!busy} loading={busy === DECIDE_YOURSELF_FA} onClick={() => void reply(DECIDE_YOURSELF_FA)}>{DECIDE_YOURSELF_FA}</Button>
        </div>
      )}
    </li>
  );
}

// ============================================================================================ a decision, in place ==
/** Kinds that are sealed on their own page against a digest: the card leads there instead of sealing in place. */
const OWN_PAGE = new Set(['server_plan', 'media_series', 'server_destructive']);

/** One card of the cartable, answered here: «تأیید» is one tap (the passkey only where the hub's rule asks for it: money, a permanent
 *  delete, keys and access, a destructive server command), «رد» asks a short reason. [lead]: the page's one full gold. */
function WaitingDecision({ d, lead, i }: { d: Decision; lead: boolean; i: number }) {
  const toast = useToast();
  const qc = useQueryClient();
  const decide = useDecide();
  const k = DECISION_KIND[d.kind] ?? { fa: d.kind, icon: 'decision' as const };
  const r = RISK[d.risk] ?? RISK.medium!;
  const [reject, setReject] = useState(false);
  const [note, setNote] = useState('');
  const done = () => { void qc.invalidateQueries({ queryKey: ['office'] }); void qc.invalidateQueries({ queryKey: ['inbox'] }); };
  const fail = (e: unknown) => { haptic('error'); toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد.' }); };
  const passkey = needsStepUp(d);
  const approve = async () => {
    try {
      const token = passkey ? await stepUp('decision.approve', sealTarget(d)) : undefined;
      await decide.mutateAsync({ ref: d.ref, verdict: 'approve', stepUpToken: token });
      haptic('seal');
      toast({ tone: 'ok', text: 'تأیید شد.' });
      done();
    } catch (e) { fail(e); }
  };
  const own = OWN_PAGE.has(d.kind);
  const href = `/cartable?ref=${d.ref}`;
  return (
    <li {...stagger(i)} data-card data-wait="decision" data-kind={d.kind} className={cx(CARD, 'flex flex-col gap-2.5', stagger(i).className)}>
      <div className="flex flex-col gap-1">
        <span className="flex items-center gap-1.5 text-[11px] text-muted">
          <CompanyMark code={d.company} height={11} mono />
          <Facts>{k.fa}{waitedFa(d.created_at)}{`ریسک ${r.fa}`}</Facts>
        </span>
        <span className="text-[14px] font-semibold leading-6 text-ink"><PlainText text={d.title} /></span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {own ? <Link href={href} className={SEE}>ببین و تأیید کن</Link>
          : <Button size="sm" variant={lead ? 'primary' : 'secondary'} icon={passkey ? 'seal' : undefined} aria-label={passkey ? 'تأیید با اثر انگشت' : 'تأیید'} loading={decide.isPending} onClick={() => void approve()}>تأیید</Button>}
        {!own ? <Button size="sm" variant="ghost" onClick={() => setReject(true)}>رد</Button> : null}
        <Link href={href} className="inline-flex h-9 items-center px-2 text-[12px] text-muted hover:text-ink">جزئیات</Link>
      </div>
      <Dialog open={reject} onOpenChange={setReject} title="رد این کارت" actions={(
        <Button variant="danger" loading={decide.isPending} onClick={() => decide.mutate({ ref: d.ref, verdict: 'reject', note: note.trim() || undefined }, { onSuccess: () => { setReject(false); toast({ tone: 'info', text: 'رد شد.' }); done(); }, onError: fail })}>رد کن</Button>
      )}>
        <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">چرا؟ (کوتاه)</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} dir="auto" aria-label="دلیل رد" className="h-10 w-full rounded-[10px] border border-strong bg-tile px-3 text-[14px] text-ink outline-none focus:border-[var(--hq-silver-ink)]" />
        </label>
      </Dialog>
    </li>
  );
}

// ==================================================================================================== «نوبت تو» ==
const SHOWN = 3;
const REPORTS = 8;
/** What waits for the owner: sessions in his turn or ready for his approval, and the cards for his decision. The same count the
 *  pulse shows. */
export function turnCount(o: Pick<Office, 'sessions' | 'approvals' | 'approvals_total'>): number {
  return o.sessions.filter((s) => state3(s.badge) === 'waiting').length + Math.max(o.approvals_total, o.approvals.length);
}

/** The top of the home: how many things wait for him, and each of them answered right there. */
export function TurnRow({ o }: { o: Office }) {
  const [all, setAll] = useState(false);
  const waiting = o.sessions.filter((s) => state3(s.badge) === 'waiting').sort(bySessionOrder);
  const mine = waiting.filter((s) => s.badge === 'your_turn');
  const ready = waiting.filter((s) => s.badge !== 'your_turn');
  // The question itself is in the session's report (the card carries only its first words): the same cached read the session uses.
  const reports = useQueries({
    queries: mine.slice(0, REPORTS).map((s) => ({ queryKey: ['orders', 'report', s.ref], queryFn: () => orderReport(s.ref) as Promise<SessionReport | null>, staleTime: 8_000 })),
  });
  const reportOf = (ref: string) => { const i = mine.findIndex((s) => s.ref === ref); const q = i >= 0 ? reports[i] : undefined; return { data: q?.data, isLoading: !!q?.isLoading }; };
  // A question he can answer in a word comes first, then the cards for his decision; then what he must open to lift or approve.
  const asks = mine.filter((s) => !!reportOf(s.ref).data?.turn);
  const lift = mine.filter((s) => !reportOf(s.ref).data?.turn);
  const total = turnCount(o);
  if (!total) {
    return (
      <section aria-label="نوبت تو" data-testid="turn-row" data-count={0} className="flex items-center gap-2 text-[13px] text-sec">
        <span className="text-pos"><DrawnTick size={16} /></span>چیزی منتظر تو نیست.
      </section>
    );
  }
  type Item = { key: string; session?: SessionCard; decision?: Decision };
  const items: Item[] = [...asks.map((s) => ({ key: s.ref, session: s })), ...o.approvals.map((d) => ({ key: d.ref, decision: d })), ...[...lift, ...ready].map((s) => ({ key: s.ref, session: s }))];
  const shown = all ? items : items.slice(0, SHOWN);
  const lead = items.find((x) => x.decision && !OWN_PAGE.has(x.decision.kind))?.key;
  const elsewhere = total - items.length;
  return (
    <section aria-label="نوبت تو" data-testid="turn-row" data-count={total} className="flex flex-col gap-3">
      <div className="flex items-end gap-3">
        <LiveFigure sig={String(total)} glint="gold" rule={false}><span className="text-[44px] font-bold leading-[48px] text-gold-ink" data-turn-count>{faCount(total)}</span></LiveFigure>
        <div className="flex min-w-0 flex-1 flex-col pb-1">
          <h2 className="text-h3 font-semibold text-ink">نوبت تو</h2>
          <span className="text-[12px] text-muted">همین‌جا جواب بده؛ کار از همان‌جا ادامه پیدا میکند.</span>
        </div>
      </div>
      <ul aria-label="منتظر تو" className="flex flex-col gap-2">
        {shown.map((x, i) => (x.session ? <WaitingSession key={x.key} s={x.session} i={i} report={reportOf(x.key)} /> : <WaitingDecision key={x.key} d={x.decision!} lead={x.key === lead} i={i} />))}
      </ul>
      {!all && items.length > SHOWN ? (
        <Button variant="text" size="sm" className="-ms-2 self-start" aria-expanded={false} onClick={() => setAll(true)}>{faCount(items.length - SHOWN)} مورد دیگر</Button>
      ) : elsewhere > 0 ? (
        <Link href="/cartable" className="self-start text-[12px] font-semibold text-silver-ink hover:text-ink hover:underline">{faCount(elsewhere)} کارت دیگر در کارتابل</Link>
      ) : null}
    </section>
  );
}

// ============================================================================================== the open sessions ==
/** One open session as a card: its words, its state (three only), why, whose it is and how far its tasks are. It opens out of itself. */
function SessionCardRow({ s, i }: { s: SessionCard; i: number }) {
  const nav = useCardNav();
  const badge = useLiveBadge(s.ref, s.badge, s.last_at);
  const st = state3(badge);
  return (
    <li {...stagger(i)}>
      <Link href={sessionHref(s.ref)} onClick={nav(sessionHref(s.ref))} data-card data-badge={badge} data-state3={st}
        className={cx('flex flex-col gap-1 rounded-[12px] px-3 py-2.5 hover:bg-hover', st === 'waiting' && 'hq-edge')}>
        <span className="flex items-start gap-2">
          <span className="line-clamp-2 min-w-0 flex-1 text-[14px] font-semibold leading-6 text-ink"><PlainText text={s.title_fa} /></span>
          <StateMark state={st} />
        </span>
        <span className="line-clamp-2 text-[12px] leading-5 text-sec"><PlainText text={s.reason_fa} /></span>
        <span className="flex items-center gap-1.5 text-[11px] text-muted">
          {s.holder ? <CompanyMark code={s.holder.company} height={11} mono /> : null}
          <Facts>
            {s.holder ? `${s.holder.title_fa} ${s.holder.company_fa}` : 'مشاور کل'}
            {s.tasks.total ? `کار ${Math.min(s.tasks.total, s.tasks.done + (st === 'done' ? 0 : 1))} از ${s.tasks.total}` : null}
            {s.pace === 'step' ? PACE_FA.step : null}
          </Facts>
        </span>
      </Link>
    </li>
  );
}

export function SessionCards({ sessions, limit = 8 }: { sessions: SessionCard[]; limit?: number }) {
  const list = sessions.slice().sort(bySessionOrder);
  if (!list.length) return <Empty icon="messages" title="جلسه‌ی بازی نیست" body="بنویس چه میخواهی تا جلسه‌اش باز شود." />;
  return <ul className="flex flex-col">{list.slice(0, limit).map((s, i) => <SessionCardRow key={s.ref} s={s} i={i} />)}</ul>;
}
