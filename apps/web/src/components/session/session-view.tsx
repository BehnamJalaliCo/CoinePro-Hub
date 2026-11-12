'use client';

// ⟨1.17⟩ Contract §34–§35 «هر فرمان یک جلسه»: the order is a session the owner talks in.
// ⟨1.0.1⟩ Part C, the session redesigned (C2.2), with the workshop inside it and the direct session's display:
// - a one-line header: the short title, «کار ۳ از ۴», the pace, the mood light; a tap opens «جزئیات» (the whole order, the plan, the
//   people, the files); it folds once the talk has scrolled; under it the plan as a segmented line;
// - the talk is the body: the order's steps are thin centred lines at their time, an output is its files as a strip of tiles where it
//   arrived (a video plays in place), the live steps follow at the end;
// - right above the composer, never stacked banners: the «الان» bar while something works (with the build ring of a workshop or direct
//   turn, and «نگه دار»), then ONE of the owner's things: the «منتظر تو» card with its ready answers, or the «گره» card with its one
//   action, or the decision bar («تأیید و انتشار» of what the session waits on, else «تأیید و بستن»): the page's one full gold;
// - ⟨2026-11-11⟩ an open session that nobody works on and that none of those explains is «ایستاده» after twenty minutes: one calm card
//   there says so, with the last thing done and «ادامه بده» (looked at again every minute);
// - a closed session ends with its end leaf. Nothing here shows a ref or a code, and nothing sends the owner elsewhere.

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useMutationState, useQueries } from '@tanstack/react-query';
import { Icon } from '@/components/icon';
import { Button, IconButton } from '@/components/ui/button';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { KitCard, OrderReportView, RouteLine } from '@/components/v29/report';
import { EraseButton } from '@/components/erase/erase-button';
import { MessageMedia } from '@/components/media/attachments';
import { CompanyMark } from '@/components/brand/marks';
import { SplitParts, WorkspaceCard } from '@/components/v33/parallel';
import type { OrderParallel } from '@/lib/api/v33';
import { OrderStatePill, PlainPara, PlainText } from '@/components/v29/bits';
import { errText, field } from '@/components/v31/kit';
import { useCompanies } from '@/lib/api/hooks';
import { useRoles } from '@/lib/api/v14';
import { outputKey, readOutput, type Output } from '@/lib/api/v21';
import { OUTPUT_KIND_FA, useOrderFix, type OutputKind } from '@/lib/api/v29';
import {
  BADGE, PACE_FA, PLAYERS, sessionTalk, useOrderSession, useSessionActions, type Pace, type Participant, type SessionReport, type SessionTask,
} from '@/lib/api/v34';
import { useConversation } from '@/lib/api/v32';
import { coverOf, publishPanelKey, publishable, readPublishPanel, type PublishPanel } from '@/lib/api/v44';
import { cx, jDateTime } from '@/lib/format';
import { FromPlaybook, MakePlaybook, MemoryCard } from '@/components/v40/playbook';
import { useDraftPlaybook } from '@/lib/api/v40';
import { madeWith, type OrderGaps } from '@/lib/api/v47';
import { DIRECT_FA, type DirectReport } from '@/lib/api/v55';
import { Routines } from '@/components/v47/routines';
import { SessionPublishes } from '@/components/v47/session-publishes';
import { StallWatch, useLastStep, useLiveBadge } from '@/components/live/session-pulse';
import { nudgeKey, useSessionActivity } from '@/lib/api/v41';
import { DecisionBar, type DecisionState } from '@/components/look/decision-bar';
import { FilesStrip, type StripFile } from '@/components/look/files';
import { useFillHeight } from '@/components/look/fill';
import { faceOf, usageOf } from '@/components/look/output';
import { PublishFor, PublishUnder, leadFile } from '@/components/look/publish';
import { DrawnTick } from '@/components/look/ring';
import { AnswerSent, EndLeaf, IdleNudge, KnotCard, LiveSheet, LiveTail, MoodLight, NowBar, SegmentLine, SessionCards, StillCard, WaitingCard, activityOfReport, isCall, liveActivity, moodOf, stillOf, taskFa, taskOf } from '@/components/look/session';
import { useTick } from '@/components/live/motion';
import { SpringSheet } from '@/components/look/spring-sheet';
import { Facts, Ltr } from '@/components/look/text';
import { SysRow } from './system-group';
import { ConversationPane, Face, playerName, type PaneApi } from './conversation-pane';

/** How long «جوابت رفت» stays said where the question was. */
const SAID_MS = 6000;
const FIXED: Array<{ key: string; fa: string }> = [{ key: 'advisor', fa: 'مشاور کل' }, { key: 'overseer', fa: 'ناظر کل' }, { key: 'assistant', fa: 'دستیار شخصی' }, { key: 'secretary', fa: 'منشی هلدینگ' }];

export function BadgePill({ badge }: { badge: keyof typeof BADGE }) {
  const b = BADGE[badge];
  return <Pill tone={b.tone === 'gold' || b.tone === 'lapis' ? 'silver' : b.tone} dot>{b.fa}</Pill>;
}

export function SessionView({ refId }: { refId: string }) {
  const q = useOrderSession(refId);
  const r = q.data;
  if (q.isLoading) return <><Skeleton className="h-16 w-2/3" /><Skeleton className="h-32 rounded-[16px]" /><Skeleton className="h-96 rounded-[16px]" /></>;
  if (q.error && !r) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!r) {
    return (
      <>
        <PageHeader eyebrow={<Link href="/s" className="hover:text-ink">جلسه‌ها</Link>} title="جلسه" />
        <Card><Empty icon="messages" title="این جلسه هنوز آماده نیست" body="هر فرمان بعد از به‌روزرسانی ستاد یک جلسه‌ی زنده میشود؛ تا آن موقع از «جلسه‌ها» دنبالش کن." action={<Button variant="secondary" icon="next" onClick={() => history.back()}>بازگشت</Button>} /></Card>
      </>
    );
  }
  // A hub from before §35 answers the report without the session: the older read-only page stays.
  if (!r.session) return <OrderReportView refId={refId} />;
  return <Session refId={refId} r={r as Full} />;
}

type Full = SessionReport & Required<Pick<SessionReport, 'session' | 'brief' | 'tasks' | 'participants'>>;

// ================================================================================================ the outputs ==
/** A session's output with what its page knows of it: its files (the deliverable's attachments) and where their publications stand. */
type SessionOutput = { ref: string; title_fa: string; kind: string; d: Output | null; loading: boolean; panel: PublishPanel | null };
const OUTPUTS_SHOWN = 12;

/** The deliverable and the publish panel of each output of the session: the same cached reads the output's own page uses. */
function useSessionOutputs(outputs: SessionReport['outputs']): SessionOutput[] {
  const list = useMemo(() => outputs.slice(0, OUTPUTS_SHOWN), [outputs]);
  const ds = useQueries({ queries: list.map((o) => ({ queryKey: outputKey(o.ref), queryFn: () => readOutput(o.ref), staleTime: 30_000 })) });
  const ps = useQueries({
    queries: list.map((o, i) => ({
      queryKey: publishPanelKey(o.ref), queryFn: () => readPublishPanel(o.ref), staleTime: 5_000,
      enabled: !!ds[i]?.data?.attachments?.some((f) => publishable(f.mime)),
      refetchInterval: (q: { state: { data?: PublishPanel | null } }) => (q.state.data?.publishes.some((p) => p.state === 'publishing') ? 5_000 : q.state.data?.publishes.some((p) => p.state === 'scheduled') ? 60_000 : false as const),
    })),
  });
  return list.map((o, i) => ({ ref: o.ref, title_fa: o.title_fa, kind: o.kind, d: ds[i]?.data ?? null, loading: !!ds[i]?.isLoading, panel: ps[i]?.data ?? null }));
}

const OUT_FA: Record<string, string> = { final: 'خروجی', part: 'بخشی از کار', partial: 'خروجی ناقص' };
const outKindFa = (kind: string) => OUT_FA[kind] ?? OUTPUT_KIND_FA[kind as OutputKind] ?? 'خروجی';
const outHref = (ref: string) => `/outputs?ref=${encodeURIComponent(ref)}&tab=all`;

/**
 * One output in the talk, where it arrived: a calm ticked line with its title, then its files as a strip of tiles (a video plays in
 * place). Under a file that can be published, its quiet «تأیید و انتشار» or where its publication stands; what the session waits on
 * ([lead]) is in the decision bar instead. The last quiet line says how it was made.
 */
function OutputTiles({ o, lead, onAsk }: { o: SessionOutput; lead: string | null; onAsk: (output: string, file: string) => void }) {
  const files: StripFile[] = o.d?.attachments ?? [];
  const made = madeWith(o.d?.produced_with);
  // One package, one action: under the output's video, else under its first picture (its other pictures go with it as a carousel).
  // A reel's cover goes out with its reel.
  const main = faceOf(files)?.id ?? null;
  const cover = files.some((f) => f.mime.startsWith('video/')) ? coverOf(files.filter((f) => f.mime.startsWith('image/')))?.id ?? null : null;
  return (
    <section aria-label={`خروجی: ${o.title_fa}`} data-output={o.ref} className="flex w-full max-w-[46rem] flex-col gap-2 self-start">
      <div className="flex items-center gap-2 text-[12px] leading-5 text-sec">
        <span className="flex-none text-pos"><DrawnTick size={15} /></span>
        <span className="min-w-0 flex-1"><Facts>{o.kind === 'partial' ? 'خروجی ناقص رسید' : 'خروجی تحویل شد'}<span className="font-semibold text-ink"><PlainText text={o.title_fa} /></span>{files.length ? null : outKindFa(o.kind)}</Facts></span>
        <Link href={outHref(o.ref)} className="flex-none rounded-[8px] px-2 py-0.5 text-[12px] font-semibold text-silver-ink hover:bg-[var(--hq-silver-soft)] hover:text-ink">باز کن</Link>
      </div>
      {files.length ? (
        <FilesStrip files={files} label={`فایل‌های ${o.title_fa}`} under={(f) => (f.id === main ? <PublishUnder f={f} panel={o.panel} lead={lead === f.id} onAsk={() => onAsk(o.ref, f.id)} />
          : f.id === cover ? <span className="text-[11px] leading-4 text-muted" data-tile-publish="cover">کاور ریلز</span> : null)} />
      ) : o.loading ? <Skeleton className="h-[148px] w-[116px] rounded-[12px]" /> : null}
      {made ? <span className="text-[11px] text-muted" data-testid="made-with">ساخت: <Facts><Ltr tabular={false}>{made.model}</Ltr>{made.effort}</Facts></span> : null}
    </section>
  );
}

// =============================================================================================== the session ==
function Session({ refId, r }: { refId: string; r: Full }) {
  const router = useRouter();
  const search = useSearchParams();
  const toast = useToast();
  const act = useSessionActions(refId);
  const fix = useOrderFix(refId);
  const [pane, setPane] = useState<PaneApi | null>(null);
  const bindPane = useCallback((a: PaneApi | null) => setPane(a), []);
  const [to, setTo] = useState<string>('');
  const [closing, setClosing] = useState(false);
  const [people, setPeople] = useState(false);
  const [details, setDetails] = useState(false);
  const [live, setLive] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [asking, setAsking] = useState<{ output: string; file: string } | null>(null);
  const [closeState, setCloseState] = useState<DecisionState>('idle');
  const closed = r.session.state === 'closed';
  const talk = sessionTalk(r);
  const conv = useConversation(talk);
  const company = r.route?.companies[0] ?? r.ack?.assigned[0]?.company ?? null;
  const holder = r.participants.find((p) => p.kind === 'holder') ?? null;
  const titleOf = (by: string) => r.participants.find((p) => p.key === by)?.title_fa ?? (by.startsWith('player:') ? playerName(by) : undefined);
  const failed = (e: unknown, fallback: string) => toast({ tone: 'error', text: errText(e, fallback) });
  const runFix = (f: NonNullable<typeof r.blockers[number]['fix']>) => fix.mutateAsync(f);
  const hide = () => act.hide.mutate(undefined, { onSuccess: () => { toast({ tone: 'info', text: 'جلسه از فهرست رفت. چیزی پاک نشد؛ از «بایگانی» برمیگردد.' }); router.push('/s'); }, onError: (e) => failed(e, 'پنهان نشد.') });
  const target = to && r.participants.some((p) => p.key === to) ? to : to === 'all' ? 'all' : '';
  const setPace = (v: Pace) => v === (r.pace ?? 'auto') || act.pace.isPending ? undefined : act.pace.mutate(v, { onSuccess: () => toast({ tone: 'ok', text: v === 'step' ? 'از این به بعد قدم‌به‌قدم با تو.' : 'از این به بعد خودش تا آخر میرود.' }), onError: (e) => failed(e, 'عوض نشد؛ دوباره بزن.') });

  // What the session is doing now, and its mood.
  const [said, setSaid] = useState<string | null>(null);
  const saidTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (saidTimer.current) clearTimeout(saidTimer.current); }, []);
  const act41 = useSessionActivity(refId, !closed);
  // ⟨2026-11-12⟩ The activity's GET failed with nothing before it: the report stands in, so the still watch runs (a hub before §41 still
  // answers null: no activity, no nudge). A call the hub dropped without a word stops counting once past its deadline, looked at every
  // minute while one is listed, so the minute's watch below can reach `stillOf`.
  const fallback = useMemo(() => (act41.isError && act41.data === undefined ? activityOfReport() : undefined), [act41.isError, act41.data]);
  const raw = act41.data === undefined ? fallback : act41.data;
  const callTick = useTick(60_000, !closed && !!raw?.working.some(isCall));
  const activity = useMemo(() => liveActivity(raw, callTick), [raw, callTick]);
  const badge = useLiveBadge(refId, r.session.badge, r.updated_at);
  // ⟨1.24⟩ SS-1 the stall watch: when the last step was, and the ring toward the hub's idle sweep. While someone works the «الان» bar
  // says it; once no one does, the header's facts carry it.
  const lastStep = useLastStep(refId, r.steps.at(-1)?.at, activity?.last.at(-1)?.at);
  const asked = !!r.turn && !closed;
  // ⟨2026-11-11⟩ An open session nobody works on, that the hub has not explained, is «ایستاده» with its own card (looked at again every
  // minute); never «آرام» for hours with nothing to press.
  // «نگه دار» in the «الان» bar: while the owner holds the work, the bar's «ادامه بده» is the one way back (no still card beside it).
  // The hold ends whenever the work starts again, whichever way: «ادامه بده» from any place (the bar, «کار زنده», the details, a
  // card), or the work at work again after it was seen stopped (the owner's word, the hub's own wake).
  const [heldAt, setHeldAt] = useState<number | null>(null);
  const nudged = useMutationState({ filters: { mutationKey: nudgeKey(refId), status: 'success' }, select: (m) => m.state.submittedAt });
  const held = heldAt != null && !nudged.some((at) => at > heldAt);
  const sawStopped = useRef(false);
  useEffect(() => {
    if (!held) { sawStopped.current = false; return; }
    if (!activity?.working.length) sawStopped.current = true;
    else if (sawStopped.current) setHeldAt(null);
  }, [held, activity]);
  // The hub takes «ادامه بده» where it serves the session's activity (§41: a hub before it answers the activity with nothing).
  const nudgeOn = activity != null;
  // The minute is looked at only while a still card can come: open, not held, nothing asked or waiting, nobody at work.
  const stillCan = !closed && !held && !asked && badge !== 'ready' && badge !== 'your_turn' && !r.blockers.length && !(r.cards ?? []).length
    && !!activity && !activity.working.length && !activity.waiting_fa && !activity.stuck_fa;
  const minute = useTick(60_000, stillCan);
  const still = stillCan ? stillOf(r, activity, badge, minute) : null;
  const mood = still ? 'still' : moodOf(activity, { closed, badge, asked });
  const task = taskOf(r.tasks);
  const outs = useSessionOutputs(r.outputs);

  // The ONE thing of the owner's above the composer, and where the page's one full gold is.
  const ready = badge === 'ready' && !closed;
  const blockers = closed ? [] : r.blockers;
  const knot = !closed && !asked && (blockers.length > 0 || (mood === 'stuck' && !!activity?.stuck_fa));
  // What the session waits on: the first file of its outputs that can be published and has no publication that stands.
  const waiting = ready ? outs.map((o) => ({ output: o.ref, f: leadFile(o.panel, o.d?.attachments ?? []) })).find((x) => x.f) : undefined;
  const waitsOn = waiting?.f ? { output: waiting.output, file: waiting.f.id } : null;
  const bar = (ready && !asked) || closeState !== 'idle';
  const close = (verdict: 'ok') => {
    setCloseState('working');
    act.close.mutate({ verdict }, {
      onSuccess: () => { setCloseState('done'); toast({ tone: 'ok', text: 'جلسه بسته و بایگانی شد.' }); },
      onError: (e) => { setCloseState('idle'); failed(e, 'بسته نشد؛ دوباره بزن.'); },
    });
  };
  // A ready answer that went stays said for a moment where the question was (the hub's next report takes the question away at once).
  const reply = (text: string) => new Promise<boolean>((done) => act.reply.mutate(text, {
    onSuccess: () => { setSaid(text); if (saidTimer.current) clearTimeout(saidTimer.current); saidTimer.current = setTimeout(() => setSaid(null), SAID_MS); done(true); },
    onError: (e) => { failed(e, 'جوابت نرفت؛ دوباره بزن.'); done(false); },
  }));

  // «اصلاح» of an output's page lands here with the output named: the composer opens with it quoted.
  const about = search.get('about');
  useEffect(() => {
    if (!about || !pane || closed) return;
    const o = r.outputs.find((x) => x.ref === about);
    pane.draft(`درباره‌ی «${o?.title_fa ?? 'این خروجی'}»: `);
    router.replace(`/s/${encodeURIComponent(refId)}`, { scroll: false });
  }, [about, pane, closed, r.outputs, refId, router]);

  // The talk is the body: the order's steps sit in it as thin lines at their time, and each output where it arrived.
  const lead = waitsOn?.file ?? null;
  const ask = (output: string, file: string) => setAsking({ output, file });
  const placed = outs.filter((o) => o.d?.created_at);
  const unplaced = outs.filter((o) => !o.d?.created_at);
  const timeline = [
    ...r.steps.map((s, i) => ({ key: `step-${s.at}-${i}`, at: s.at, node: <SysRow at={s.at} who={s.who_fa} text={s.what_fa} />, sys: { who: s.who_fa, text: s.what_fa } })),
    ...placed.map((o) => ({ key: `out-${o.ref}`, at: o.d!.created_at, node: <OutputTiles o={o} lead={lead} onAsk={ask} /> })),
  ];
  const allFiles = outs.flatMap((o) => o.d?.attachments ?? []);
  const used = outs.reduce((n, o) => n + (o.d ? usageOf(o.d).used ?? 0 : 0), 0);
  const tail = (
    <>
      {unplaced.map((o) => <OutputTiles key={o.ref} o={o} lead={lead} onAsk={ask} />)}
      {closed ? null : <LiveTail a={activity} />}
      {closed ? (
        <EndLeaf r={r} used={used || null} outputs={r.outputs.length}
          made={allFiles.length ? <FilesStrip files={allFiles} label="آنچه ساخته شد" /> : null}
          action={<Button variant="secondary" size="sm" icon="refresh" loading={act.reopen.isPending} onClick={() => act.reopen.mutate(undefined, { onError: (e) => failed(e, 'باز نشد.') })}>دوباره باز کن</Button>} />
      ) : null}
    </>
  );

  const extras = !!r.kit || !!(r as OrderParallel).parts?.length || !!(r as OrderParallel).workspaces?.length;
  const bottom = useCallback(() => (window.matchMedia('(min-width: 1024px)').matches ? 40 : extras ? 112 : 88), [extras]);
  const frame = useFillHeight<HTMLDivElement>(bottom);
  const pace = r.pace ?? 'auto';

  return (
    <>
      <div ref={frame} data-testid="session" data-mood={mood} data-held={held ? '' : undefined} className={cx('mx-auto flex w-full max-w-[58rem] flex-col gap-2.5', !extras && '-mb-6 lg:mb-0')}>
        {/* ⟨1.0.1⟩ M14: the card that was tapped (the home's, the command sheet) grows into this header; M18: it folds to one line. */}
        <header data-stuck={scrolled ? '' : undefined} onClick={() => setDetails(true)} className="hq-vt-hero hq-m18 flex flex-none cursor-pointer flex-col gap-1.5">
          <div className="hq-m18-fold flex items-center gap-2 text-caption text-muted">
            <Link href="/s" onClick={(e) => e.stopPropagation()} className="hover:text-ink">جلسه‌ها</Link>
            {r.session.source ? <span onClick={(e) => e.stopPropagation()}><FromPlaybook refId={r.session.source} /></span> : null}
          </div>
          <div className="flex items-center gap-2.5">
            <h1 className="min-w-0 flex-1 truncate text-[17px] font-semibold leading-8 text-ink"><PlainText text={r.text_fa} /></h1>
            {task ? <span className="hq-m18-only flex-none text-[12px] text-sec">{taskFa(task)}</span> : null}
            <MoodLight mood={mood} word={activity?.mood && activity.mood === mood ? activity.mood_fa : null} />
            <IconButton icon="more" label="جزئیات" size={36} aria-haspopup="dialog" onClick={(e) => { e.stopPropagation(); setDetails(true); }} />
          </div>
          <div className="hq-m18-fold text-[12px] leading-5 text-sec" data-session-facts>
            <Facts>{task ? taskFa(task) : null}{closed ? null : PACE_FA[pace]}{holder ? <PlainText text={holder.title_fa} /> : null}{closed || activity?.working.length ? null : <StallWatch badge={badge} lastAt={lastStep.at} wokeAt={lastStep.wokeAt} className="align-[-2px]" />}</Facts>
          </div>
          <SegmentLine tasks={r.tasks} waiting={asked || ready} />
        </header>

        {talk ? (
          <ConversationPane
            variant="session" fill conversationRef={talk} face={holder?.key ?? 'secretary'} to={target || null} titleOf={titleOf} readOnly={closed || !!conv.data?.closed_at} onApi={bindPane} onScrolled={setScrolled}
            quietSend={bar || knot || (!!still && nudgeOn)} answer={asked ? reply : undefined}
            above={(
              <>
                {closed ? null : <NowBar refId={refId} a={activity} r={r} onOpen={() => setLive(true)} held={held} onHeld={(on) => setHeldAt(on ? Date.now() : null)} />}
                {asked ? <WaitingCard r={r} busy={act.reply.isPending} onReply={reply} /> : said && !closed ? <AnswerSent text={said} /> : null}
                {closed ? null : <SessionCards cards={r.cards ?? []} />}
                {knot ? <KnotCard refId={refId} stuckFa={blockers.length ? null : activity?.stuck_fa} blockers={blockers} company={company} run={runFix} lead={!bar} /> : null}
                {still ? <StillCard refId={refId} still={still} now={minute} lead={!bar} canNudge={nudgeOn} /> : null}
                {bar ? (
                  <DecisionBar place="flow" label={waitsOn ? 'تأیید و انتشار' : 'تأیید و بستن'} state={closeState} doneLabel="جلسه بسته شد" onLeft={() => setCloseState('idle')}
                    context={waitsOn ? 'کار تمام شده؛ با تأیید تو همین فایل منتشر میشود.' : 'کار تمام شده؛ با تأیید تو جلسه بسته و بایگانی میشود.'}
                    primary={waitsOn ? { label: 'تأیید و انتشار', onClick: () => setAsking(waitsOn) } : { label: 'تأیید و بستن', onClick: () => close('ok') }}
                    quiet={waitsOn ? [{ label: 'اصلاح', onClick: () => pane?.draft('') }, { label: 'فقط ببند', onClick: () => close('ok') }] : [{ label: 'اصلاح', onClick: () => pane?.draft('') }]} />
                ) : null}
                <Room r={r} closed={closed} to={target} onTo={setTo} />
              </>
            )}
            timeline={timeline} tail={tail} placeholder="به مسئول بگو چه بکند…"
            emptyTitle="هنوز حرفی زده نشده" emptyBody="هر چه بگویی همین‌جا به مسئول فرمان میرسد." />
        ) : (
          <Card className="p-5"><Empty icon="messages" title="گفتگوی این جلسه هنوز باز نشده" action={<Button icon="messages" loading={act.talk.isPending} onClick={() => act.talk.mutate(undefined, { onError: (e) => failed(e, 'باز نشد.') })}>گفتگو را شروع کن</Button>} /></Card>
        )}
      </div>

      {/* ⟨1.13⟩ §31.2: a «new company» order: the kit's form, preview and seal, right in its session. */}
      {r.kit ? <KitCard refId={refId} kit={r.kit} /> : null}
      {/* ⟨1.15⟩ §33.7 and §33.10: the parallel parts with their merge, and the workspace on the company's own server. */}
      <SplitParts r={r as OrderParallel} />
      <WorkspaceCard r={r as OrderParallel} />

      <SpringSheet open={details} onOpenChange={setDetails} title="جزئیات جلسه" description="همه‌ی چیزهایی که کنار گفتگو لازم میشوند" width={560}>
        <div className="flex flex-col gap-4 pb-2">
          <section aria-label="متن فرمان" className="flex flex-col gap-1">
            <h3 className="text-[12px] font-semibold text-muted">متن فرمان</h3>
            <PlainPara text={r.text_fa} className="text-[14px] leading-7 text-ink" />
          </section>
          <Brief r={r} />
          {allFiles.length ? (
            <Card className="flex flex-col gap-2 p-4" aria-label="فایل‌های خروجی">
              <SectionTitle title="فایل‌های خروجی" note="هر چه در این جلسه ساخته شد" />
              <FilesStrip files={allFiles} label="فایل‌های خروجی این جلسه" />
            </Card>
          ) : null}
          <MemoryCard md={r.memory_md} />
          <MakePlaybook order={refId} onDone={() => setDetails(false)} />
          {/* ⟨1.0.1⟩ §50 a standing routine from one sentence, and this session's routines */}
          <Routines order={refId} routines={(r as OrderGaps).routines} closed={closed} />
          <Card className="flex flex-col gap-2 p-4" aria-label="وضعیت و روش کار">
            <div className="flex flex-wrap items-center gap-2"><BadgePill badge={r.session.badge} /><OrderStatePill state={r.state} />{closed && r.session.closed_at ? <span className="text-[12px] text-muted">بسته شد {jDateTime(r.session.closed_at)}</span> : null}</div>
            {closed ? (
              <Pill tone="neutral" icon="time">روش کار: {PACE_FA[pace]}</Pill>
            ) : (
              <Segmented<Pace> label="روش کار" value={pace} onChange={setPace} options={[{ value: 'step', label: PACE_FA.step }, { value: 'auto', label: PACE_FA.auto }]} />
            )}
            {/* ⟨1.0.1⟩ §54 a direct session: its holder is one session with the hub's tools; nothing else changes for the owner. */}
            {(r as DirectReport).direct ? <p className="text-[12px] leading-5 text-sec" data-testid="direct-session">{DIRECT_FA}</p> : null}
            {/* §41 a quiet session never stalls unseen: when it last worked, and one tap that takes it up again. */}
            {/* (the page's still card carries that tap once the session stands still; the line stays here) */}
            {!closed && !asked && (mood === 'idle' || mood === 'still') ? <IdleNudge refId={refId} a={activity} button={!still} /> : null}
          </Card>
          <Participants r={r} closed={closed} onAddPerson={() => setPeople(true)} />
          <Tasks r={r} closed={closed} />
          <Plan r={r} />
          <Results r={r} closed={closed} />
          {/* ⟨1.0.1⟩ §44.5, §51 what went out from this session and what is set to go, each cancellable until it is out */}
          <SessionPublishes publishes={(r as OrderGaps).publishes} />
          <FilesCard r={r} />
          <Card className="flex flex-col gap-2 p-4" aria-label="بستن و پنهان کردن">
            <SectionTitle title="پایان جلسه" />
            <div className="flex flex-wrap items-center gap-2">
              {closed ? (
                <Button variant="secondary" icon="refresh" loading={act.reopen.isPending} onClick={() => act.reopen.mutate(undefined, { onSuccess: () => setDetails(false), onError: (e) => failed(e, 'باز نشد.') })}>دوباره باز کن</Button>
              ) : (
                <Button variant="secondary" icon="seal" onClick={() => { setDetails(false); setClosing(true); }}>تأیید و بستن</Button>
              )}
              {closed ? (
                <Button variant="secondary" onClick={() => (r.session.hidden ? act.unhide : act.hide).mutate(undefined, { onError: (e) => failed(e, 'انجام نشد.') })}>{r.session.hidden ? 'برگردان به فهرست' : 'از فهرست بردار'}</Button>
              ) : (
                <Button variant="secondary" onClick={hide}>از فهرست بردار</Button>
              )}
              <EraseButton kind="session" refId={refId} variant="ghost" size="md" onGone={() => router.push('/s')} />
            </div>
          </Card>
        </div>
      </SpringSheet>
      <LiveSheet open={live} onOpenChange={setLive} a={activity} refId={refId} ready={ready} />
      <PersonSheet open={people} onOpenChange={setPeople} r={r} />
      <CloseSheet open={closing} onOpenChange={setClosing} r={r} onAsk={(t) => { setClosing(false); void pane?.send(t); }} onClosed={() => { setClosing(false); toast({ tone: 'ok', text: 'جلسه بسته و بایگانی شد.' }); }} />
      {asking ? <PublishFor output={asking.output} fileId={asking.file} onClose={() => setAsking(null)} /> : null}
    </>
  );
}

// ================================================================================================ the brief ==
/** «چه شد · حالا چه · از تو چه», stacked, in the details sheet. */
function Brief({ r }: { r: Full }) {
  const rows = [['چه شد', r.brief.done_fa, 'seal', 'text-pos'], ['حالا چه', r.brief.now_fa, 'time', 'text-silver-ink'], ['از تو چه', r.brief.need_fa, 'owner', 'text-gold-ink']] as const;
  return (
    <section className="flex flex-col gap-2" aria-label="خلاصه‌ی جلسه">
      {rows.map(([t, v, icon, tint]) => (
        <section key={t} className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3">
          <h3 className="flex items-center gap-1.5 text-[13px] font-semibold text-ink"><span className={tint}><Icon name={icon} size={15} /></span>{t}</h3>
          {v ? <PlainPara text={v} className="text-[13px] leading-6 text-ink" /> : <p className="text-[13px] text-muted">—</p>}
        </section>
      ))}
    </section>
  );
}

// ====================================================================================== who is in the room ==
function Room({ r, closed, to, onTo }: { r: Full; closed: boolean; to: string; onTo: (k: string) => void }) {
  if (closed) return null;
  const others = r.participants.filter((p) => p.kind !== 'holder');
  if (!others.length) return null;
  return (
    <div className="no-scrollbar flex flex-none items-center gap-1.5 overflow-x-auto" role="radiogroup" aria-label="به چه کسی میگویی">
      <span className="text-[12px] text-muted">میگویی به</span>
      <FilterChip selected={to === ''} onClick={() => onTo('')}>مسئول فرمان</FilterChip>
      {others.map((p) => <FilterChip key={p.key} selected={to === p.key} onClick={() => onTo(p.key)}>{p.title_fa}</FilterChip>)}
      <FilterChip selected={to === 'all'} onClick={() => onTo('all')}>نظر همه</FilterChip>
    </div>
  );
}

function Participants({ r, closed, onAddPerson }: { r: Full; closed: boolean; onAddPerson: () => void }) {
  const toast = useToast();
  const act = useSessionActions(r.ref);
  const [models, setModels] = useState(false);
  const have = new Set(r.participants.map((p) => p.key));
  const addPlayer = (key: string) => act.addParticipant.mutate({ kind: 'player', key }, { onSuccess: () => setModels(false), onError: (e) => toast({ tone: 'error', text: errText(e, 'این مدل نیامد.') }) });
  return (
    <Card className="flex flex-col gap-3 p-5" aria-label="کی در جلسه است">
      <SectionTitle title="کی در جلسه است" note="مسئول فرمان همیشه هست؛ هر کس را بخواهی میاوری" />
      <ul className="flex flex-col gap-1.5">
        {r.participants.map((p) => (
          <li key={p.key} className="flex items-center gap-2.5 rounded-[10px] bg-tile px-3 py-2" data-kind={p.kind}>
            <Face k={p.kind === 'holder' && p.key.includes('@') ? 'manager' : p.key} size={28} />
            <span className="min-w-0 flex-1 text-[13px] font-semibold"><PlainText text={p.title_fa} /></span>
            <span className="text-[11px] text-muted">{p.kind === 'holder' ? 'مسئول' : p.kind === 'player' ? 'مدل' : 'همکار'}</span>
            {p.kind !== 'holder' && !closed ? <IconButton icon="close" size={32} label={`${p.title_fa} را بیرون ببر`} onClick={() => act.removeParticipant.mutate(p.key, { onError: (e) => toast({ tone: 'error', text: errText(e, 'نشد.') }) })} /> : null}
          </li>
        ))}
      </ul>
      {!closed ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" icon="add" onClick={onAddPerson}>آدم</Button>
          <Button size="sm" icon="model" aria-pressed={models} onClick={() => setModels(!models)}>مدل</Button>
        </div>
      ) : null}
      {models && !closed ? (
        <div className="flex flex-wrap gap-1.5" aria-label="مدل‌ها">
          {PLAYERS.map((p) => <FilterChip key={p.key} selected={have.has(`player:${p.key}`)} onClick={() => !have.has(`player:${p.key}`) && addPlayer(p.key)}>{p.fa}</FilterChip>)}
        </div>
      ) : null}
    </Card>
  );
}

function PersonSheet({ open, onOpenChange, r }: { open: boolean; onOpenChange: (v: boolean) => void; r: Full }) {
  const toast = useToast();
  const act = useSessionActions(r.ref);
  const companies = useCompanies();
  const roles = useRoles();
  const [co, setCo] = useState<string | null>(null);
  const have = new Set(r.participants.map((p) => p.key));
  const list = (companies.data ?? []).filter((c) => c.kind !== 'holding' && c.code !== 'HQ');
  const rs = (roles.data ?? []).filter((x) => x.scope === 'company' && (x.kind === 'ceo' || x.kind === 'manager') && (!x.company || x.company === co));
  const add = (key: string) => act.addParticipant.mutate({ kind: 'person', key }, {
    onSuccess: () => { setCo(null); onOpenChange(false); },
    onError: (e) => toast({ tone: 'error', text: errText(e, 'این آدم نیامد.') }),
  });
  return (
    <SpringSheet open={open} onOpenChange={onOpenChange} title="کی را بیاورم؟" description="همکار هلدینگ یا مدیر یک شرکت" width={440}>
      <div className="flex flex-col gap-4 pb-2">
        <fieldset className="flex flex-col gap-2"><legend className="pb-1 text-[12px] text-sec">همکارهای هلدینگ</legend>
          <div className="flex flex-wrap gap-1.5">{FIXED.map((p) => <FilterChip key={p.key} selected={have.has(p.key)} onClick={() => !have.has(p.key) && add(p.key)}>{p.fa}</FilterChip>)}</div>
        </fieldset>
        <fieldset className="flex flex-col gap-2"><legend className="pb-1 text-[12px] text-sec">مدیر یک شرکت</legend>
          <div className="flex flex-wrap gap-1.5">{list.map((c) => <FilterChip key={c.code} selected={co === c.code} onClick={() => setCo(c.code)}>{c.name_fa}</FilterChip>)}</div>
        </fieldset>
        {co ? (
          <fieldset className="flex flex-col gap-2"><legend className="pb-1 text-[12px] text-sec">نقش</legend>
            <div className="flex flex-wrap gap-1.5">{rs.map((x) => <FilterChip key={x.role} selected={have.has(`${x.role}@${co}`)} onClick={() => !have.has(`${x.role}@${co}`) && add(`${x.role}@${co}`)}>{x.title_fa}</FilterChip>)}</div>
          </fieldset>
        ) : null}
      </div>
    </SpringSheet>
  );
}

// ================================================================================================== the tasks ==
const NEXT_STATE: Record<SessionTask['state'], SessionTask['state']> = { todo: 'done', doing: 'done', done: 'todo', dropped: 'todo' };
const STATE_FA: Record<SessionTask['state'], string> = { todo: 'مانده', doing: 'در دست کار', done: 'انجام شد', dropped: 'کنار گذاشته شد' };

function Tasks({ r, closed }: { r: Full; closed: boolean }) {
  const toast = useToast();
  const act = useSessionActions(r.ref);
  const [title, setTitle] = useState('');
  const live = r.tasks.filter((t) => t.state !== 'dropped');
  const dropped = r.tasks.filter((t) => t.state === 'dropped');
  const done = live.filter((t) => t.state === 'done').length;
  const fail = (e: unknown) => toast({ tone: 'error', text: errText(e, 'نشد.') });
  return (
    <Card id="session-plan" className="flex flex-col gap-3 p-5" aria-label="کارها">
      <SectionTitle title="کارها" note={live.length ? `${done} از ${live.length} انجام شد` : 'کارهای این جلسه، قدم به قدم'} />
      {live.length ? (
        <ul className="flex flex-col gap-1">
          {live.map((t) => (
            <li key={t.id} className="flex items-center gap-2.5 rounded-[10px] px-1 py-1" data-state={t.state}>
              <input type="checkbox" checked={t.state === 'done'} disabled={closed} aria-label={`${t.title_fa}: ${STATE_FA[t.state]}`} className="size-5 flex-none accent-[var(--hq-silver-ink)]"
                onChange={() => act.patchTask.mutate({ id: t.id, state: NEXT_STATE[t.state] }, { onError: fail })} />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className={cx('text-[13px] leading-6', t.state === 'done' && 'text-muted line-through')}><PlainText text={t.title_fa} /></span>
                <span className="text-[11px] text-muted">{t.state === 'doing' ? 'در دست کار' : t.by === 'owner' ? 'کار تو' : t.who_fa ?? 'ایجنت'}</span>
              </span>
              {!closed ? <IconButton icon="close" size={32} label={`${t.title_fa} را کنار بگذار`} onClick={() => act.patchTask.mutate({ id: t.id, state: 'dropped' }, { onError: fail })} /> : null}
            </li>
          ))}
        </ul>
      ) : <p className="text-[13px] text-muted">هنوز کاری نوشته نشده.</p>}
      {dropped.length ? <p className="text-[11px] text-muted">{dropped.length} کار کنار گذاشته شده.</p> : null}
      {!closed ? (
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); const t = title.trim(); if (t) act.addTask.mutate(t, { onSuccess: () => setTitle(''), onError: fail }); }}>
          <input value={title} onChange={(e) => setTitle(e.target.value)} dir="auto" aria-label="کار تازه" placeholder="کار تازه…" className={cx(field, 'h-10 min-w-0 flex-1')} />
          <Button type="submit" size="md" icon="add" disabled={!title.trim()} loading={act.addTask.isPending}>بیفزا</Button>
        </form>
      ) : null}
    </Card>
  );
}

// ===================================================================================== the receipt and the plan ==
function Plan({ r }: { r: Full }) {
  const { data: companies } = useCompanies();
  const name = (code: string) => companies?.find((c) => c.code === code)?.name_fa ?? code;
  return (
    <Card className="flex flex-col gap-3 p-5" aria-label="رسید و برنامه">
      <SectionTitle title="رسید و برنامه" note={r.ack ? `${r.ack.by.display_fa ?? 'ستاد'}، ${jDateTime(r.ack.at)}` : 'هر فرمان ظرف ده دقیقه رسید و برنامه میگیرد'} />
      {r.ack ? (
        <>
          <PlainPara text={r.ack.plan_fa} className="text-[13px] leading-6 text-ink" />
          {r.ack.assigned.length ? (
            <div className="flex flex-wrap gap-1.5">
              {r.ack.assigned.map((a) => (
                <Link key={a.code} href={`/employees/${a.code}`} className="inline-flex h-8 items-center gap-1.5 rounded-full bg-tile px-3 text-[12px] hover:bg-hover"><CompanyMark code={a.company} height={12} mono /><Facts>{a.title_fa}<span className="text-muted">{name(a.company)}</span></Facts></Link>
              ))}
            </div>
          ) : null}
          {r.ack.due_at ? <span className="flex items-center gap-1.5 text-[12px] text-sec"><Icon name="time" size={14} />موعد: {jDateTime(r.ack.due_at)} به وقت تهران</span> : null}
        </>
      ) : <p className="text-[13px] text-sec">رسید؛ برنامه‌ی کار تا ده دقیقه‌ی دیگر میرسد.</p>}
      {r.route ? <div className="border-t border-div pt-3"><RouteLine r={r.route} count={(r.route as { count?: number | null }).count} /></div> : null}
    </Card>
  );
}

// ================================================================================================= the results ==
function Results({ r, closed }: { r: Full; closed: boolean }) {
  return (
    <Card className="flex flex-col gap-2 p-5" aria-label="خروجی‌ها">
      <SectionTitle title="نتیجه‌ها" note={r.outputs.length ? 'آنچه تا حالا ساخته شده' : undefined} />
      {r.outputs.length ? (
        <ul className="flex flex-col gap-1.5">
          {r.outputs.map((o) => (
            <li key={o.ref}>
              <Link href={`/outputs?ref=${o.ref}&tab=all`} className="flex items-center gap-2 rounded-[10px] bg-tile px-3 py-2.5 text-[13px] hover:bg-hover">
                <Icon name={o.kind === 'reel' ? 'video' : o.kind === 'post' || o.kind === 'story' ? 'image' : 'deliverable'} size={16} className="text-silver-ink" />
                <span className="min-w-0 flex-1 truncate"><PlainText text={o.title_fa} /></span>
                <span className="text-[11px] text-muted">{outKindFa(o.kind)}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : <p className="text-[13px] text-muted">{closed ? 'نتیجه‌ای ثبت نشد.' : 'هنوز نتیجه‌ای نیست؛ با هر نتیجه این‌جا پر میشود.'}</p>}
    </Card>
  );
}

/** ⟨1.18⟩ §36.3 every file the owner sent in this talk belongs to the order: listed here, newest first, with a download on each. */
function FilesCard({ r }: { r: Full }) {
  const files = r.files ?? [];
  if (!files.length) return null;
  return (
    <Card className="flex flex-col gap-3 p-5" aria-label="فایل‌ها">
      <SectionTitle title="فایل‌ها" note="آنچه برای این جلسه فرستادی؛ کارکنان همین را میبینند" />
      <MessageMedia items={files} />
    </Card>
  );
}

// ================================================================================================ confirm and close ==
/** «تأیید و بستن» with the rest that goes with a close: a working group or a production line first, a note, or cancelling the order. */
function CloseSheet({ open, onOpenChange, r, onAsk, onClosed }: { open: boolean; onOpenChange: (v: boolean) => void; r: Full; onAsk: (text: string) => void; onClosed: () => void }) {
  const toast = useToast();
  const act = useSessionActions(r.ref);
  const draft = useDraftPlaybook(r.ref);
  const [note, setNote] = useState('');
  const [sure, setSure] = useState(false);
  const left = r.tasks.filter((t) => t.state === 'todo' || t.state === 'doing').length;
  const close = (verdict: 'ok' | 'cancel') => act.close.mutate({ verdict, note: note.trim() || undefined }, { onSuccess: onClosed, onError: (e) => toast({ tone: 'error', text: errText(e, 'بسته نشد؛ دوباره بزن.') }) });
  const cancelling = act.close.isPending && act.close.variables?.verdict === 'cancel';
  return (
    <SpringSheet open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) setSure(false); }} title="تأیید و بستن جلسه" description="بعد از بستن، جلسه بایگانی میشود و هر وقت خواستی دوباره بازش میکنی" width={480}
      bar={(
        <DecisionBar label="بستن جلسه" context={sure ? 'با لغو، کارهای باز این فرمان میایستند.' : left ? `${left} کار هنوز مانده؛ با بستن جلسه لغو میشوند.` : null}
          state={act.close.isPending && !cancelling ? 'working' : 'idle'} primary={{ label: 'تأیید و ببند', onClick: () => close('ok') }}
          quiet={sure ? [{ label: 'بله، لغو کن', tone: 'danger', onClick: () => close('cancel'), disabled: cancelling }] : [{ label: 'لغو فرمان', onClick: () => setSure(true) }]} />
      )}>
      <div className="flex flex-col gap-5 pb-1">
        <section className="flex flex-col gap-2" aria-label="پیش از بستن">
          <h3 className="text-[13px] font-semibold text-ink">پیش از بستن، اگر کار تکرارشدنی است</h3>
          <p className="text-[13px] leading-6 text-sec">یک کارگروه یا یک خط تولید راه بینداز تا این کار بعد از بسته شدن جلسه هم ادامه پیدا کند؛ کارتش همین‌جا در گفتگو می‌آید.</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" icon="companies" loading={draft.isPending} onClick={() => draft.mutate(undefined, {
              onSuccess: () => { onOpenChange(false); toast({ tone: 'ok', text: 'پیش‌نویس کارگروه آماده است؛ کارتش در گفتگوست.' }); },
              onError: (e) => toast({ tone: 'error', text: errText(e, 'ساخته نشد؛ دوباره بزن.') }),
            })}>کارگروه از این جلسه</Button>
            <Button size="sm" icon="task" onClick={() => onAsk('برای این کار یک خط تولید راه بینداز')}>خط تولید راه بینداز</Button>
          </div>
        </section>
        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] text-sec">یادداشت (اختیاری)</span>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} dir="auto" aria-label="یادداشت بستن" className={cx(field, 'py-2 leading-6')} />
        </label>
      </div>
    </SpringSheet>
  );
}

export type { Participant };
