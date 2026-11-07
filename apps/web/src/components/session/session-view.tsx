'use client';

// ⟨1.17⟩ Contract §34–§35 «هر فرمان یک جلسه»: the order is a session the owner talks in. The header says what it is and whose turn it is; the
// brief says «چه شد · حالا چه · از تو چه»; the owner's open question is answered right there; the blockers carry their one-tap fix; the
// people and model seats in the room can be added and sent away; the tasks are ticked; the results are listed; and «تأیید و بستن» ends it
// (a working group or a production line first, if he wants one) so no order is left without an owner. Nothing here shows a ref or a code.

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button, IconButton } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { BlockerRow, KitCard, OrderReportView, RouteLine } from '@/components/v29/report';
import { EraseButton } from '@/components/erase/erase-button';
import { MessageMedia } from '@/components/media/attachments';
import { CompanyMark } from '@/components/brand/marks';
import { SplitParts, WorkspaceCard } from '@/components/v33/parallel';
import type { OrderParallel } from '@/lib/api/v33';
import { FixButton, OrderStatePill, PlainPara, PlainText } from '@/components/v29/bits';
import { FaText } from '@/components/v29/text';
import { errText, field } from '@/components/v31/kit';
import { useCompanies } from '@/lib/api/hooks';
import { useRoles } from '@/lib/api/v14';
import { OUTPUT_KIND_FA, useOrderFix, type OutputKind } from '@/lib/api/v29';
import {
  BADGE, PACE_FA, PLAYERS, sessionTalk, useOrderSession, useSessionActions, type Pace, type Participant, type SessionReport, type SessionTask,
} from '@/lib/api/v34';
import { useConversation } from '@/lib/api/v32';
import { cx, jDateTime, jTime } from '@/lib/format';
import { plain } from '@/lib/plain';
import { ConversationPane, Face, playerName, type PaneApi } from './conversation-pane';

const FIXED: Array<{ key: string; fa: string }> = [{ key: 'advisor', fa: 'مشاور کل' }, { key: 'overseer', fa: 'ناظر کل' }, { key: 'assistant', fa: 'دستیار شخصی' }, { key: 'secretary', fa: 'منشی هلدینگ' }];

export function BadgePill({ badge }: { badge: keyof typeof BADGE }) {
  const b = BADGE[badge];
  return <Pill tone={b.tone} dot={!b.live} live={b.live}>{b.fa}</Pill>;
}

export function SessionView({ refId }: { refId: string }) {
  const q = useOrderSession(refId);
  const r = q.data;
  if (q.isLoading) return <><Skeleton className="h-16 w-2/3" /><Skeleton className="h-32 rounded-[16px]" /><Skeleton className="h-96 rounded-[16px]" /></>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
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
  return <Session refId={refId} r={r as SessionReport & Required<Pick<SessionReport, 'session' | 'brief' | 'tasks' | 'participants'>>} />;
}

type Full = SessionReport & Required<Pick<SessionReport, 'session' | 'brief' | 'tasks' | 'participants'>>;

function Session({ refId, r }: { refId: string; r: Full }) {
  const router = useRouter();
  const toast = useToast();
  const act = useSessionActions(refId);
  const fix = useOrderFix(refId);
  const pane = useRef<PaneApi | null>(null);
  const bindPane = useCallback((a: PaneApi | null) => { pane.current = a; }, []);
  const [to, setTo] = useState<string>('');
  const [closing, setClosing] = useState(false);
  const [people, setPeople] = useState(false);
  const closed = r.session.state === 'closed';
  const talk = sessionTalk(r);
  const conv = useConversation(talk);
  const company = r.route?.companies[0] ?? r.ack?.assigned[0]?.company ?? null;
  const holder = r.participants.find((p) => p.kind === 'holder') ?? null;
  const titleOf = (by: string) => r.participants.find((p) => p.key === by)?.title_fa ?? (by.startsWith('player:') ? playerName(by) : undefined);
  const speak = (t: string) => void pane.current?.send(t);
  const failed = (e: unknown, fallback: string) => toast({ tone: 'error', text: errText(e, fallback) });
  const runFix = (f: NonNullable<typeof r.blockers[number]['fix']>) => fix.mutateAsync(f);
  const hide = () => act.hide.mutate(undefined, { onSuccess: () => { toast({ tone: 'info', text: 'جلسه از فهرست رفت. چیزی پاک نشد؛ از «بایگانی» برمیگردد.' }); router.push('/s'); }, onError: (e) => failed(e, 'پنهان نشد.') });
  const target = to && r.participants.some((p) => p.key === to) ? to : to === 'all' ? 'all' : '';

  const [details, setDetails] = useState(false);
  const [wide, setWide] = useState(false);
  const askClose = () => { setDetails(false); setClosing(true); };
  const ready = r.session.badge === 'ready' && !closed;

  // The talk is the body: the order's system steps sit in it as small grey lines at their time, and what was delivered as compact cards at its end.
  const timeline = r.steps.map((s, i) => ({ key: `step-${s.at}-${i}`, at: s.at, node: <StepLine s={s} /> }));
  const tail = r.outputs.length ? (
    <div className="flex flex-col items-start gap-1.5" aria-label="نتیجه‌های رسیده">
      {r.outputs.map((o) => <OutputChip key={o.ref} o={o} />)}
    </div>
  ) : null;

  return (
    <div className="mx-auto flex w-full max-w-[58rem] flex-col gap-3">
      <header className="flex flex-col gap-1.5">
        <Link href="/s" className="self-start text-caption text-muted hover:text-ink">جلسه‌ها</Link>
        <div className="flex items-start gap-2">
          <h1 className={cx('min-w-0 flex-1 text-h3 font-semibold leading-8 text-ink', !wide && 'line-clamp-2')}><PlainText text={r.text_fa} /></h1>
          {r.text_fa.length > 60 ? <button type="button" aria-expanded={wide} onClick={() => setWide(!wide)} className="flex-none pt-1 text-[12px] text-muted hover:text-ink">{wide ? 'کمتر' : 'بیشتر'}</button> : null}
        </div>
        <div className="flex items-center gap-2">
          <BadgePill badge={r.session.badge} />
          <span className="min-w-0 flex-1 truncate text-[13px] text-sec" title={plain(r.session.reason_fa)}><PlainText text={r.session.reason_fa} /></span>
          {ready ? <Button size="sm" variant="primary" icon="seal" onClick={() => setClosing(true)}>تأیید و بستن</Button> : null}
          {closed ? <Button size="sm" variant="primary" icon="refresh" loading={act.reopen.isPending} onClick={() => act.reopen.mutate(undefined, { onError: (e) => failed(e, 'باز نشد.') })}>دوباره باز کن</Button> : null}
          <Button size="sm" icon="more" aria-haspopup="dialog" onClick={() => setDetails(true)}>جزئیات</Button>
        </div>
      </header>

      {r.turn && !closed ? <OpenTurn r={r} onReply={(text) => act.reply.mutate(text, { onSuccess: () => toast({ tone: 'ok', text: 'جوابت رفت.' }), onError: (e) => failed(e, 'جوابت نرفت؛ دوباره بزن.') })} busy={act.reply.isPending} /> : null}

      {r.blockers.length && !closed ? (
        <Card className="flex flex-col gap-3 p-4 ring-1 ring-[var(--hq-neg-line)]" aria-label="گیرها">
          <SectionTitle title="کجا گیر کرده" note="هر گیر با دکمه‌ی رفعش؛ یک ضربه کافی است" />
          <ul className="flex flex-col gap-2">{r.blockers.map((b, i) => <BlockerRow key={`${b.kind}-${i}`} b={b} company={company} run={runFix} />)}</ul>
        </Card>
      ) : null}

      <Room r={r} closed={closed} to={target} onTo={setTo} />
      {talk ? (
        <ConversationPane
          conversationRef={talk} face={holder?.key ?? 'secretary'} to={target || null} titleOf={titleOf} readOnly={closed || !!conv.data?.closed_at} onApi={bindPane}
          talkHeight="h-[calc(100dvh-20rem)]" timeline={timeline} tail={tail} placeholder="به مسئول بگو چه بکند، یا از همین‌جا بسپار، استخدام کن، گروه و خط تولید راه بینداز…"
          emptyTitle="هنوز حرفی زده نشده" emptyBody="هر چه بگویی همین‌جا به مسئول فرمان میرسد؛ هر کاری که از دل گفتگو بیرون بیاید فقط با کارتی که تو میزنی انجام میشود." />
      ) : (
        <Card className="p-5"><Empty icon="messages" title="گفتگوی این جلسه هنوز باز نشده" action={<Button icon="messages" loading={act.talk.isPending} onClick={() => act.talk.mutate(undefined, { onError: (e) => failed(e, 'باز نشد.') })}>گفتگو را شروع کن</Button>} /></Card>
      )}

      {/* ⟨1.13⟩ §31.2: a «new company» order — the kit's form, preview and seal, right in its session. */}
      {r.kit ? <KitCard refId={refId} kit={r.kit} /> : null}

      {/* ⟨1.15⟩ §33.7 and §33.10: the parallel parts with their merge, and the workspace on the company's own server. */}
      <SplitParts r={r as OrderParallel} />
      <WorkspaceCard r={r as OrderParallel} />

      <Sheet open={details} onOpenChange={setDetails} title="جزئیات جلسه" description="همه‌ی چیزهایی که کنار گفتگو لازم میشوند" width={520}>
        <div className="flex flex-col gap-4">
          <Brief r={r} />
          <Card className="flex flex-col gap-2 p-4" aria-label="وضعیت و روش کار">
            <div className="flex flex-wrap items-center gap-2"><BadgePill badge={r.session.badge} /><OrderStatePill state={r.state} />{closed && r.session.closed_at ? <span className="text-[12px] text-muted">بسته شد {jDateTime(r.session.closed_at)}</span> : null}</div>
            {closed ? (
              <Pill tone="neutral" icon="time">روش کار: {PACE_FA[r.pace ?? 'auto']}</Pill>
            ) : (
              <Segmented<Pace>
                label="روش کار"
                value={r.pace ?? 'auto'}
                onChange={(v) => act.pace.mutate(v, { onSuccess: () => toast({ tone: 'ok', text: v === 'step' ? 'از این به بعد قدم‌به‌قدم با تو.' : 'از این به بعد خودش تا آخر میرود.' }), onError: (e) => failed(e, 'عوض نشد؛ دوباره بزن.') })}
                options={[{ value: 'step', label: PACE_FA.step }, { value: 'auto', label: PACE_FA.auto }]}
              />
            )}
          </Card>
          <Participants r={r} closed={closed} onAddPerson={() => setPeople(true)} />
          <Tasks r={r} closed={closed} />
          <Plan r={r} />
          <Results r={r} closed={closed} />
          <FilesCard r={r} />
          <Card className="flex flex-col gap-2 p-4" aria-label="بستن و پنهان کردن">
            <SectionTitle title="پایان جلسه" />
            <div className="flex flex-wrap items-center gap-2">
              {closed ? (
                <Button variant="primary" icon="refresh" loading={act.reopen.isPending} onClick={() => act.reopen.mutate(undefined, { onSuccess: () => setDetails(false), onError: (e) => failed(e, 'باز نشد.') })}>دوباره باز کن</Button>
              ) : (
                <Button variant="primary" icon="seal" onClick={askClose}>تأیید و بستن</Button>
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
      </Sheet>
      <PersonSheet open={people} onOpenChange={setPeople} r={r} />
      <CloseSheet open={closing} onOpenChange={setClosing} r={r} onAsk={(t) => { setClosing(false); speak(t); }} onClosed={() => { setClosing(false); toast({ tone: 'ok', text: 'جلسه بسته و بایگانی شد.' }); }} />
    </div>
  );
}

/** A system step, small and grey and centred on one line, in the talk at its time. */
function StepLine({ s }: { s: SessionReport['steps'][number] }) {
  return (
    <div className="mx-auto flex max-w-full items-center justify-center gap-1.5 px-2 py-0.5 text-[11px] leading-5 text-muted" data-step title={`${s.who_fa}: ${plain(s.what_fa)}`}>
      <span className="fig flex-none">{jTime(s.at)}</span>
      <span className="min-w-0 truncate">{s.who_fa}: <FaText text={s.what_fa} /></span>
    </div>
  );
}

/** A delivered output, a compact card in the talk. */
function OutputChip({ o }: { o: SessionReport['outputs'][number] }) {
  return (
    <Link href={`/outputs?ref=${o.ref}&tab=all`} data-output className="flex max-w-full items-center gap-2 rounded-[12px] border border-div bg-tile px-3 py-2 text-[13px] hover:bg-hover">
      <Icon name={o.kind === 'reel' ? 'video' : o.kind === 'post' || o.kind === 'story' ? 'image' : 'deliverable'} size={16} className="flex-none text-silver-ink" />
      <span className="min-w-0 truncate"><PlainText text={o.title_fa} /></span>
      <span className="flex-none text-[11px] text-muted">{OUTPUT_KIND_FA[o.kind as OutputKind] ?? 'خروجی'}</span>
    </Link>
  );
}

// ================================================================================================ the brief ==
/** «چه شد · حالا چه · از تو چه», stacked, in the details sheet. */
function Brief({ r }: { r: Full }) {
  const rows = [['چه شد', r.brief.done_fa, 'seal', 'text-pos'], ['حالا چه', r.brief.now_fa, 'time', 'text-warn'], ['از تو چه', r.brief.need_fa, 'owner', 'text-gold-ink']] as const;
  return (
    <section className="tahrir flex flex-col gap-2" aria-label="خلاصه‌ی جلسه">
      {rows.map(([t, v, icon, tint]) => (
        <section key={t} className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3">
          <h3 className={cx('flex items-center gap-1.5 text-[13px] font-semibold', tint)}><Icon name={icon} size={15} />{t}</h3>
          {v ? <PlainPara text={v} className="text-[13px] leading-6 text-ink" /> : <p className="text-[13px] text-muted">—</p>}
        </section>
      ))}
    </section>
  );
}

// ============================================================================================ the open question ==
function OpenTurn({ r, onReply, busy }: { r: Full; onReply: (t: string) => void; busy: boolean }) {
  const [text, setText] = useState('');
  const t = r.turn!;
  return (
    <Card as="section" className="flex flex-col gap-3 p-5 ring-1 ring-[var(--hq-gold-ink)]" aria-label="نوبت تو">
      <div className="flex items-center gap-2"><Pill tone="gold" live>نوبت تو</Pill><span className="text-[13px] text-sec">{t.who_fa} میپرسد</span></div>
      <PlainPara text={t.question_fa} className="text-[15px] font-semibold leading-7" />
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { onReply(text.trim()); setText(''); } }}>
        <input value={text} onChange={(e) => setText(e.target.value)} dir="auto" aria-label="جواب تو" placeholder="جوابت را بنویس…" className={cx(field, 'h-11 min-w-0 flex-[1_1_16rem]')} />
        <Button type="submit" variant="primary" icon="send" disabled={!text.trim()} loading={busy}>جواب بده</Button>
      </form>
    </Card>
  );
}

// ====================================================================================== who is in the room ==
function Room({ r, closed, to, onTo }: { r: Full; closed: boolean; to: string; onTo: (k: string) => void }) {
  if (closed) return null;
  const others = r.participants.filter((p) => p.kind !== 'holder');
  if (!others.length) return null;
  return (
    <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5" role="radiogroup" aria-label="به چه کسی میگویی">
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
    <Sheet open={open} onOpenChange={onOpenChange} title="کی را بیاورم؟" description="همکار هلدینگ یا مدیر یک شرکت" width={420}>
      <div className="flex flex-col gap-4">
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
    </Sheet>
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
    <Card className="flex flex-col gap-3 p-5" aria-label="کارها">
      <SectionTitle title="کارها" note={live.length ? `${done} از ${live.length} انجام شد` : 'کارهای این جلسه، قدم به قدم'} />
      {live.length ? (
        <ul className="flex flex-col gap-1">
          {live.map((t) => (
            <li key={t.id} className="flex items-center gap-2.5 rounded-[10px] px-1 py-1" data-state={t.state}>
              <input type="checkbox" checked={t.state === 'done'} disabled={closed} aria-label={`${t.title_fa}: ${STATE_FA[t.state]}`} className="size-5 flex-none accent-[var(--hq-gold-ink)]"
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
                <Link key={a.code} href={`/employees/${a.code}`} className="inline-flex h-8 items-center gap-1.5 rounded-full bg-tile px-3 text-[12px] hover:bg-hover"><CompanyMark code={a.company} height={12} mono />{a.title_fa}<span className="text-muted">· {name(a.company)}</span></Link>
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
                <span className="text-[11px] text-muted">{OUTPUT_KIND_FA[o.kind as OutputKind] ?? 'خروجی'}</span>
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
function CloseSheet({ open, onOpenChange, r, onAsk, onClosed }: { open: boolean; onOpenChange: (v: boolean) => void; r: Full; onAsk: (text: string) => void; onClosed: () => void }) {
  const toast = useToast();
  const act = useSessionActions(r.ref);
  const [note, setNote] = useState('');
  const [sure, setSure] = useState(false);
  const left = r.tasks.filter((t) => t.state === 'todo' || t.state === 'doing').length;
  const close = (verdict: 'ok' | 'cancel') => act.close.mutate({ verdict, note: note.trim() || undefined }, { onSuccess: onClosed, onError: (e) => toast({ tone: 'error', text: errText(e, 'بسته نشد؛ دوباره بزن.') }) });
  return (
    <Sheet open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) setSure(false); }} title="تأیید و بستن جلسه" description="بعد از بستن، جلسه بایگانی میشود و هر وقت خواستی دوباره بازش میکنی" width={460}
      footer={(
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon="seal" loading={act.close.isPending && act.close.variables?.verdict === 'ok'} onClick={() => close('ok')}>تأیید و ببند</Button>
          {sure ? <Button variant="danger" icon="reject" loading={act.close.isPending && act.close.variables?.verdict === 'cancel'} onClick={() => close('cancel')}>بله، لغو کن</Button> : <Button variant="ghost" onClick={() => setSure(true)}>لغو فرمان</Button>}
        </div>
      )}>
      <div className="flex flex-col gap-5">
        <section className="flex flex-col gap-2" aria-label="پیش از بستن">
          <h3 className="text-[13px] font-semibold text-sec">پیش از بستن، اگر کار تکرارشدنی است</h3>
          <p className="text-[13px] leading-6 text-sec">یک کارگروه یا یک خط تولید راه بینداز تا این کار بعد از بسته شدن جلسه هم ادامه پیدا کند؛ مسئول فرمان کارتش را همین‌جا در گفتگو میگذارد و تو اجرا میکنی.</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" icon="companies" onClick={() => onAsk('برای این کار یک کارگروه راه بینداز')}>کارگروه راه بینداز</Button>
            <Button size="sm" icon="task" onClick={() => onAsk('برای این کار یک خط تولید راه بینداز')}>خط تولید راه بینداز</Button>
          </div>
        </section>
        {left ? <p className="rounded-[10px] bg-warn-soft px-3 py-2 text-[13px] leading-6">{left} کار هنوز مانده. با بستن جلسه، کارهای باز لغو میشوند و فقط کارگروه و خط تولید و قانون‌هایی که ساخته‌ای میمانند.</p> : null}
        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] text-sec">یادداشت (اختیاری)</span>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} dir="auto" aria-label="یادداشت بستن" className={cx(field, 'py-2 leading-6')} />
        </label>
      </div>
    </Sheet>
  );
}

export type { Participant };
