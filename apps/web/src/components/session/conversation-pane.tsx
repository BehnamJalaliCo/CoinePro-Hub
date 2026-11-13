'use client';

// The conversation itself, taken out of «گفتگو» (components/v32/talk.tsx) so the session page speaks with the same composer, voice,
// hands-free listening, streamed answer and cards: the answer streams in (text, then the spoken sentences in order); work comes out only
// through cards he taps. The pane is bound to one conversation (`conversationRef`); on «گفتگو» it is made on the first word (`ensure`),
// in a session it is the order's own talk, and `to` aims a word at one participant or at everyone (§35.4).

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { Avatar, Orb } from '@/components/brand/avatar';
import { Icon } from '@/components/icon';
import { AttachmentTray, MessageMedia, RICH_ACCEPT, useAttachments } from '@/components/media/attachments';
import { Waveform } from '@/components/media/composer';
import { Button, IconButton } from '@/components/ui/button';
import { CopyButton } from '@/components/ui/copy-button';
import { Md } from '@/components/ui/md';
import { Card, Empty, Pill, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaText } from '@/components/v29/text';
import { errText, field } from '@/components/v31/kit';
import { KeyDialog, personaFa } from '@/components/v32/engines';
import { TalkCardView } from '@/components/v32/cards';
import {
  looksLikeKey, postTurn, readTurnEvents, stopTurn, turnsOf, useConversation, useEngines, usePersonas, useTalkActions,
  type Persona, type TalkCard, type Turn, type TurnEvent, type TurnSource,
} from '@/lib/api/v32';
import type { MediaRef } from '@/lib/api/v13';
import { PLAYERS } from '@/lib/api/v34';
import { SystemGroup } from './system-group';
import { Ltr } from '@/components/look/text';
import { prefersReducedMotion } from '@/components/live/motion';
import { cx, jTime } from '@/lib/format';
import { LONG_VOICE_ERROR, recognizer, useLongVoice } from '@/lib/long-voice';
import { useAudioQueue } from '@/lib/talk-audio';
import { useHandsFree } from '@/lib/talk-handsfree';

export const FACE_FA: Record<string, string> = { secretary: 'منشی هلدینگ', overseer: 'ناظر کل', assistant: 'دستیار شخصی', advisor: 'مشاور کل' };

/** The name of a model seat: «player:gpt» → «جی‌پی‌تی». */
export const playerName = (key: string) => PLAYERS.find((p) => `player:${p.key}` === key || p.key === key)?.fa ?? key.replace(/^player:/, '');

/** The mark of a persona: the same medallions as the rest of the app, the secretary with the command mark, a model with the model mark. */
export function Face({ k, size = 44, state = 'idle' }: { k: string; size?: number; state?: 'idle' | 'working' | 'sleeping' }) {
  if (k === 'advisor') return <Orb size={size} state={state === 'working' ? 'speaking' : 'rest'} label={FACE_FA.advisor} />;
  if (k === 'overseer') return <Avatar kind="overseer" size={size} state={state} label={FACE_FA.overseer} />;
  if (k === 'assistant') return <Avatar kind="assistant" size={size} state={state} label={FACE_FA.assistant} />;
  if (k === 'secretary') {
    return <span role="img" aria-label={FACE_FA.secretary} className="flex flex-none items-center justify-center rounded-full bg-gold-soft text-gold-ink" style={{ width: size, height: size, boxShadow: 'inset 0 0 0 2px var(--hq-gold-ink)' }}><Icon name="command" size={Math.round(size * 0.5)} /></span>;
  }
  if (k.startsWith('player:')) {
    return <span role="img" aria-label={playerName(k)} className="flex flex-none items-center justify-center rounded-full bg-lapis-soft text-lapis" style={{ width: size, height: size }}><Icon name="model" size={Math.round(size * 0.5)} /></span>;
  }
  return <Avatar kind="manager" size={size} state={state} label="مدیر" />;
}

// What the pane keeps about the turn that is being answered right now.
type Live = { owner: string; files: MediaRef[]; id: string | null; answer: string; cards: TalkCard[]; error: string | null; streaming: boolean };

/** A system line (a step of the order): consecutive ones between two real turns fold into one quiet row. */
export type SysLine = { who: string; text: string };

/** What a page can ask of the pane from outside: say a word for the owner, or put words in his composer for him to finish. */
export type PaneApi = {
  send: (text: string) => Promise<void>; draft: (text: string) => void;
  /** ⟨1.0.3⟩ §57.7 the holder's chip: the composer is brought into view and takes the focus, what is typed there kept. */
  focus: () => void;
};

/** ⟨1.0.1⟩ [session]: the session's look (C2.2): the owner's words carry a thin gold edge, the holder's a silver mark; nothing is filled gold. */
export function Bubble({ children, own, session }: { children: React.ReactNode; own?: boolean; session?: boolean }) {
  const tone = session ? (own ? 'hq-edge self-start bg-raised text-ink' : 'bg-tile text-ink') : own ? 'self-start bg-gold-soft text-ink' : 'bg-tile text-ink';
  return <div className={cx('max-w-[46rem] rounded-[14px] px-3.5 py-2.5 text-[14px] leading-7', tone)}>{children}</div>;
}
/**
 * ⟨1.0.1⟩ In a session «کپی» and the time do not sit under every bubble: they come with the pointer over the turn, or once the turn has
 * the focus (a tap on it), as one small bar at its corner.
 */
function TurnTools({ target, at }: { target: RefObject<HTMLElement | null>; at?: string | null }) {
  return (
    <span data-turn-tools className="pointer-events-none absolute -top-3 end-2 z-[1] flex items-center gap-0.5 rounded-full bg-raised px-1.5 opacity-0 shadow-[0_2px_10px_rgba(0,0,0,.28)] ring-1 ring-div transition-opacity group-focus-within/turn:pointer-events-auto group-focus-within/turn:opacity-100 group-hover/turn:pointer-events-auto group-hover/turn:opacity-100">
      {at ? <Ltr className="px-1 text-[11px] text-muted">{jTime(at)}</Ltr> : null}
      <CopyButton target={target} className="self-center" />
    </span>
  );
}
// ⟨1.18⟩ §36.2 the owner's files sit in his bubble: pictures as thumbnails, the rest as rows with a download. The word «فایل» that stands in
// for an empty text is not shown when files are there.
export const FILE_WORD = 'فایل';
export function OwnerBubble({ text, files, session, at }: { text: string; files?: MediaRef[]; session?: boolean; at?: string | null }) {
  const has = !!files?.length;
  const body = useRef<HTMLSpanElement | null>(null);
  const showText = !(has && text === FILE_WORD);
  return (
    <div className={cx('flex flex-col items-start gap-0.5', session && 'group/turn relative rounded-[14px]')} data-by="owner" tabIndex={session ? 0 : undefined}>
      <Bubble own session={session}>
        <div className="flex flex-col gap-2">
          {has ? <div aria-label="فایل‌های فرستاده‌شده"><MessageMedia items={files!} /></div> : null}
          {showText ? <span ref={body} dir="auto" className="whitespace-pre-wrap"><FaText text={text} /></span> : null}
        </div>
      </Bubble>
      {showText ? (session ? <TurnTools target={body} at={at} /> : <CopyButton target={body} />) : null}
    </div>
  );
}

export function TurnView({ t, persona, title, session }: { t: Turn; persona: Persona | null; title?: string; session?: boolean }) {
  const bodyRef = useRef<HTMLDivElement | null>(null);
  if (t.by === 'owner') return <OwnerBubble text={t.text} files={t.files} session={session} at={t.at} />;
  const body = t.show_md ?? t.say_fa ?? t.text;
  return (
    <div className={cx('flex gap-2.5', session && 'group/turn relative rounded-[14px]')} data-by={t.by} data-state={t.state} tabIndex={session ? 0 : undefined}>
      <Face k={t.by.includes('@') && !t.by.startsWith('player:') ? 'manager' : t.by} size={session ? 28 : 32} />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <span className="text-[11px] font-semibold text-muted">{title ?? persona?.title_fa ?? (t.by.startsWith('player:') ? playerName(t.by) : personaFa(t.by))}</span>
        {body ? <><Bubble session={session}><div ref={bodyRef}><Md text={body} /></div></Bubble>{session ? <TurnTools target={bodyRef} at={t.at} /> : <CopyButton target={bodyRef} />}</> : null}
        {t.state === 'stopped' ? <span className="text-[12px] text-muted">قطع شد.</span> : null}
        {t.state === 'failed' ? <p className="rounded-[10px] bg-warn-soft px-3 py-2 text-[13px] leading-6"><FaText text={t.reason_fa ?? 'جواب کامل نشد؛ دوباره بپرس.'} /></p> : null}
        {t.cards.map((cd) => <TalkCardView key={cd.id} card={cd} />)}
      </div>
    </div>
  );
}

export type PaneProps = {
  /** The conversation to show; null before the first word on «گفتگو». */
  conversationRef: string | null;
  /** The persona it opens with (a new conversation, the live bubble's face). */
  face: string;
  /** Makes the conversation on the first word when there is none; the page then hands the ref back through [conversationRef]. */
  ensure?: () => Promise<string>;
  /** Aims the owner's words: a participant's key, or «all». The holder answers when empty. */
  to?: string | null;
  /** The plain name of a speaker in this conversation (a session's participants). */
  titleOf?: (by: string) => string | undefined;
  /** A closed session: the talk is read-only. */
  readOnly?: boolean;
  onBusy?: (busy: boolean) => void;
  /** The voice meter moved (a spoken answer was billed). */
  onMeter?: () => void;
  /** Hands the page what it may ask of the pane (and null when the pane goes away). */
  onApi?: (api: PaneApi | null) => void;
  emptyTitle?: string;
  emptyBody?: string;
  /** Height classes of the scrolling talk (it scrolls inside, the composer stays under it). */
  talkHeight?: string;
  placeholder?: string;
  /** Small things that belong in the timeline at their time (a session's system steps): shown between the turns by `at`. */
  timeline?: Array<{ key: string; at: string; node: ReactNode; sys?: SysLine }>;
  /** What is shown after the last turn and before the live answer (a session's delivered outputs). */
  tail?: ReactNode;
  /** What sits just above the composer (a session's live work panel). */
  above?: ReactNode;
  /** ⟨1.0.1⟩ `session`: the session's look (C2.2); `talk` (the default) is «گفتگو» as it was. */
  variant?: 'talk' | 'session';
  /** The pane fills its flex column: the talk takes what is left and scrolls inside, the composer keeps its place under it. */
  fill?: boolean;
  /** The page carries its one full gold elsewhere (a decision bar, a knot's action): the send button is then quiet. */
  quietSend?: boolean;
  /** Whether the talk has scrolled away from its start (the page's header then folds to one line, M18). */
  onScrolled?: (scrolled: boolean) => void;
  /**
   * While the session's holder waits for the owner's answer: what he types (with no file) is that answer and goes through the
   * session's own reply, which says whether the hub took it. Typing still works; it is not a second, parallel turn.
   */
  answer?: (text: string) => Promise<boolean>;
};

/** The composer's textarea grows to this many lines, then scrolls. */
const MAX_LINES = 6;
const LINE_PX = 24;
/** How near the end counts as «at the end» (px). */
const END_SLACK = 80;

export function ConversationPane({ conversationRef: ref, face, ensure, to, titleOf, readOnly, onBusy, onMeter, onApi, emptyTitle, emptyBody, talkHeight = 'max-h-[calc(100dvh-22rem)]', placeholder, timeline, tail, above, variant = 'talk', fill, quietSend, onScrolled, answer }: PaneProps) {
  const session = variant === 'session';
  const qc = useQueryClient();
  const toast = useToast();
  const act = useTalkActions();
  const personas = usePersonas();
  const engines = useEngines();
  const conv = useConversation(ref);
  const [live, setLive] = useState<Live | null>(null);
  const [text, setText] = useState('');
  const [keyOpen, setKeyOpen] = useState<{ n: number; key: string } | null>(null);
  const [handsFree, setHandsFree] = useState(false);
  const [drag, setDrag] = useState(false);
  const files = useAttachments(10, true);
  const pick = useRef<HTMLInputElement | null>(null);
  const filesRef = useRef(files);
  const sending = useRef(false); // a word on its way to the hub: Enter twice is one word
  const answerRef = useRef(answer); // read when a word is sent: the page's own callback may be new on every render
  useEffect(() => { filesRef.current = files; answerRef.current = answer; });
  const audio = useAudioQueue();
  const abort = useRef<AbortController | null>(null);
  const liveId = useRef<string | null>(null);
  const scroller = useRef<HTMLDivElement | null>(null);
  const inner = useRef<HTMLDivElement | null>(null);
  const area = useRef<HTMLTextAreaElement | null>(null);
  // The talk opens at its last turn and stays there while he is at the end; once he scrolls up it leaves him be and offers «↓».
  const pinned = useRef(true);
  // ⟨2026-11-11⟩ «↓» is a smooth scroll: until it reaches the end, its own scroll events do not let go of the end.
  const jumping = useRef(false);
  /** Holds (or lets go of) the end. While held, the browser's scroll anchoring is off: a live line replaced at the end of a working
   *  session (the tail keeps its last three) moved the view up a line each time, and «↓» stopped short of the end. */
  const pin = useCallback((on: boolean) => {
    pinned.current = on;
    if (scroller.current) scroller.current.style.overflowAnchor = on ? 'none' : '';
  }, []);
  // `left`: how many turns there were when he scrolled away from the end (null while he is at the end), per conversation.
  const [leave, setLeave] = useState<{ ref: string | null; at: number } | null>(null);

  const c = conv.data ?? null;
  const turns = turnsOf(c);
  const busy = !!live?.streaming;
  const turnsLen = useRef(0);
  useEffect(() => { turnsLen.current = turns.length; });
  const personaOf = (key: string) => personas.data?.find((p) => p.key === key || key.startsWith(`${p.role}@`)) ?? null;

  useEffect(() => { onBusy?.(busy); }, [busy, onBusy]);
  const toEnd = useCallback((smooth = false) => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
  }, []);
  useLayoutEffect(() => { pin(true); }, [ref, pin]);
  useLayoutEffect(() => { if (pinned.current) toEnd(); }, [toEnd, turns.length, live?.answer, live?.cards.length, timeline?.length]);
  // Pictures, cards and the streamed answer grow the talk after it was placed: stay at the end if he is there.
  useEffect(() => {
    const el = inner.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => { if (pinned.current) toEnd(); });
    ro.observe(el);
    // ⟨1.0.1⟩ the frame itself too: a bar that comes above the composer makes it shorter, and the end must stay in sight
    if (scroller.current) ro.observe(scroller.current);
    // ⟨2026-11-11⟩ and any change in it (a live line in place of another, a running step's seconds): the end stays the end
    const mo = typeof MutationObserver === 'undefined' ? null : new MutationObserver(() => { if (pinned.current) toEnd(); });
    mo?.observe(el, { childList: true, subtree: true, characterData: true });
    return () => { ro.disconnect(); mo?.disconnect(); };
  }, [toEnd]);
  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
    onScrolled?.(el.scrollTop > 24);
    if (jumping.current) {
      if (gap > 1) return;
      jumping.current = false;
    }
    const near = gap < END_SLACK;
    pin(near);
    setLeave((l) => (near ? (l ? null : l) : l && l.ref === ref ? l : { ref, at: turnsLen.current }));
  };
  const atEnd = !leave || leave.ref !== ref;
  const unseen = atEnd ? 0 : Math.max(0, turns.length - leave.at);

  // The composer grows with the text to six lines and then scrolls.
  useLayoutEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = 'auto';
    const max = MAX_LINES * LINE_PX + 22;
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
    el.style.overflowY = el.scrollHeight > max ? 'auto' : 'hidden';
  }, [text, readOnly]);

  const items = (() => {
    const all = [
      ...turns.map((t, i) => ({ key: t.id, at: Date.parse(t.at), i, node: <TurnView t={t} persona={personaOf(t.by)} title={titleOf?.(t.by)} session={session} />, sys: undefined as (SysLine & { iso: string }) | undefined })),
      ...(timeline ?? []).map((x, i) => ({ key: x.key, at: Date.parse(x.at), i: turns.length + i, node: x.node, sys: x.sys ? { ...x.sys, iso: x.at } : undefined })),
    ].sort((a, b) => (Number.isNaN(a.at) || Number.isNaN(b.at) ? a.i - b.i : a.at - b.at || a.i - b.i));
    // Consecutive system lines between two real turns fold into one row (a lone one stays as it is).
    const out: Array<{ key: string; node: ReactNode }> = [];
    for (let k = 0; k < all.length; k++) {
      const x = all[k]!;
      if (!x.sys) { out.push({ key: x.key, node: x.node }); continue; }
      const run = [x];
      while (all[k + 1]?.sys) run.push(all[++k]!);
      out.push(run.length === 1 ? { key: x.key, node: x.node } : { key: `sys-${x.key}`, node: <SystemGroup lines={run.map((r) => ({ at: r.sys!.iso, who: r.sys!.who, text: r.sys!.text }))} /> });
    }
    return out;
  })();

  /** Barge-in: what is playing stops, what is waiting is not played, and the generation ends (so unspoken sentences are not billed). */
  const interrupt = useCallback(() => {
    audio.stop();
    const id = liveId.current;
    if (id) { liveId.current = null; void stopTurn(id).catch(() => undefined); }
  }, [audio]);

  const openKey = (k = '') => setKeyOpen((o) => ({ n: (o?.n ?? 0) + 1, key: k }));

  // `withFiles`: what the owner has attached goes with this word (his own composer); a word the page speaks for him carries none.
  const send = useCallback(async (raw: string, source: TurnSource = 'typed', withFiles = false) => {
    const att = withFiles ? filesRef.current : null;
    const ids = att?.ids ?? [];
    if (att?.uploading || sending.current) return;
    if (att?.items.some((x) => x.state === 'failed')) {
      toast({ tone: 'error', text: 'یک فایل بالا نرفت؛ آن را بردار یا دوباره بفرست.' });
      return;
    }
    const t = raw.trim() || (ids.length ? FILE_WORD : '');
    if (!t || readOnly) return;
    // A key-shaped string is never a message: it moves into the key sheet (the server also scrubs one that slips through).
    if (looksLikeKey(t, engines.data)) { setText(''); openKey(t); return; }
    // An open question of the session's holder: his typed words are its answer (the hub puts them in the talk as his turn).
    const answerNow = answerRef.current;
    if (answerNow && source === 'typed' && !ids.length) {
      sending.current = true;
      pin(true);
      setText('');
      try { if (!(await answerNow(t))) setText(t); } finally { sending.current = false; }
      return;
    }
    let taken = false; // the hub took the word (a turn exists)
    sending.current = true;
    try {
      interrupt();
      pin(true); // what he says, and the answer to it, are seen
      const cv = ref ?? (ensure ? await ensure() : null);
      if (!cv) return;
      setText('');
      setLive({ owner: t, files: (att?.items ?? []).flatMap((x) => (x.ref ? [x.ref] : [])), id: null, answer: '', cards: [], error: null, streaming: true });
      const { turn } = await postTurn(cv, { text: t, source, client_id: crypto.randomUUID(), ...(to ? { to } : {}), ...(ids.length ? { file_ids: ids } : {}) });
      taken = true;
      sending.current = false;
      if (ids.length) att?.clear();
      liveId.current = turn.id;
      setLive((l) => l && { ...l, id: turn.id });
      abort.current?.abort();
      const ctl = new AbortController();
      abort.current = ctl;
      const onEvent = (e: TurnEvent) => {
        if (e.type === 'text') setLive((l) => l && { ...l, answer: l.answer + e.delta });
        else if (e.type === 'audio') audio.push({ seq: e.seq, file_id: e.file_id });
        else if (e.type === 'card') setLive((l) => l && { ...l, cards: [...l.cards, e.card] });
        else if (e.type === 'meter') { onMeter?.(); void qc.invalidateQueries({ queryKey: ['voice', 'meter'] }); }
        else if (e.type === 'invite' && e.company) act.invite.mutate({ ref: cv, role: e.role, company: e.company });
        else if (e.type === 'error') setLive((l) => l && { ...l, error: e.reason_fa });
      };
      const end = await readTurnEvents(turn.id, onEvent, ctl.signal);
      if (liveId.current === turn.id) liveId.current = null;
      if (end === 'aborted') return;
      void qc.invalidateQueries({ queryKey: ['orders'] }); // a session moves with its talk; the answer does not wait for that
      await Promise.all([qc.refetchQueries({ queryKey: ['talk', 'conversation', cv] }), qc.invalidateQueries({ queryKey: ['talk', 'conversations'] }), qc.invalidateQueries({ queryKey: ['voice'] })]);
      setLive((l) => (l?.id === turn.id ? (end === 'error' ? { ...l, streaming: false } : null) : l));
      // «نظر همه»: the others answer one after the other and the holder sums up; look again a little later.
      if (to === 'all') for (const ms of [2500, 6000]) setTimeout(() => void qc.invalidateQueries({ queryKey: ['talk', 'conversation', cv] }), ms);
    } catch (e) {
      setLive(null);
      // the word was not taken: it goes back into the composer (never over something typed meanwhile)
      if (!taken && source === 'typed' && raw.trim()) setText((cur) => cur || raw);
      toast({ tone: 'error', text: errText(e, 'گفته‌ات فرستاده نشد؛ دوباره بزن.') });
    } finally {
      sending.current = false;
    }
  }, [act.invite, audio, engines.data, ensure, interrupt, onMeter, pin, qc, readOnly, ref, to, toast]);

  // The page may speak for the owner («پایان جلسه», a suggestion's words…).
  const sendRef = useRef(send);
  useEffect(() => { sendRef.current = send; });
  useEffect(() => {
    onApi?.({
      send: (t) => sendRef.current(t),
      draft: (t) => { setText(t); requestAnimationFrame(() => { const el = area.current; if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } }); },
      focus: () => {
        const el = area.current;
        if (!el) return;
        el.scrollIntoView({ block: 'nearest', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
        el.focus({ preventScroll: true });
        el.setSelectionRange(el.value.length, el.value.length);
      },
    });
    return () => onApi?.(null);
  }, [onApi]);

  // Hold to talk: the phone's recogniser first; long speech goes to the hub's transcription (purpose «talk»).
  const lv = useLongVoice({
    purpose: 'talk',
    onText: (r) => void send(r.text, 'hold', true),
    onError: (f, d) => toast({ tone: f === 'empty' ? 'info' : 'error', text: d ?? LONG_VOICE_ERROR[f] }),
  });
  const holding = lv.phase === 'listening' || lv.phase === 'asking';
  useHandsFree({
    enabled: handsFree && !readOnly,
    onSpeech: interrupt,
    onUtterance: (t) => void send(t, 'handsfree', true),
    onFatal: (why) => { setHandsFree(false); toast({ tone: 'error', text: why === 'not-allowed' || why === 'service-not-allowed' ? LONG_VOICE_ERROR.denied : 'گوش دادن بی‌دست متوقف شد؛ دوباره روشنش کن.' }); },
  });
  useEffect(() => () => { abort.current?.abort(); }, []);

  const recSupported = typeof window !== 'undefined' && !!recognizer();
  const liveFace = c?.persona.includes('@') ? 'manager' : (c?.persona ?? face);

  const hasText = !!text.trim() || files.items.length > 0;
  return (
    <>
      <div className={cx('relative', fill && 'flex min-h-0 flex-1 flex-col')}>
        <Card as="section" className={cx('p-0', fill && 'flex min-h-0 flex-1 flex-col')} aria-label="گفتگو" aria-live="polite">
          <div ref={scroller} onScroll={onScroll} data-testid="talk-scroll" className={cx('overflow-y-auto overscroll-contain p-4', fill ? 'min-h-0 flex-1' : cx('min-h-[320px]', talkHeight))}>
            <div ref={inner} className="flex flex-col gap-3">
              {ref && conv.isLoading ? <Skeleton className="h-40 rounded-[14px]" /> : null}
              {!ref && !live ? <Empty icon="messages" title={emptyTitle ?? `با ${FACE_FA[face] ?? 'مدیر'} حرف بزن`} body={emptyBody ?? 'بنویس یا دکمه‌ی میکروفون را نگه دار و بگو. کاری که از دل گفتگو بیرون میآید، فقط با کارتی که تو میزنی اجرا میشود.'} /> : null}
              {ref && !conv.isLoading && !items.length && !live && !tail ? <Empty icon="messages" title={emptyTitle ?? 'هنوز حرفی زده نشده'} body={emptyBody} /> : null}
              {items.map((x) => <div key={x.key} className="flex flex-col">{x.node}</div>)}
              {tail}
              {live ? (
                <>
                  <OwnerBubble text={live.owner} files={live.files} session={session} />
                  <div className="flex gap-2.5" aria-label="پاسخ در حال نوشته شدن">
                    <Face k={to && to !== 'all' && to.startsWith('player:') ? to : liveFace} size={session ? 28 : 32} state={live.streaming ? 'working' : 'idle'} />
                    <div className="flex min-w-0 flex-1 flex-col gap-2">
                      {live.answer ? <Bubble session={session}><Md text={live.answer} /></Bubble> : live.streaming ? <Bubble session={session}><span className="text-[13px] text-muted" role="status">دارم فکر میکنم…</span></Bubble> : null}
                      {live.cards.map((cd) => <TalkCardView key={cd.id} card={cd} />)}
                      {live.error ? <p className="rounded-[10px] bg-warn-soft px-3 py-2 text-[13px] leading-6" role="alert"><FaText text={live.error} /></p> : null}
                      {live.streaming ? <div><Button size="sm" icon="stop" onClick={() => { interrupt(); }}>ساکت شو</Button></div> : null}
                    </div>
                  </div>
                </>
              ) : null}
              {audio.playing ? <span className="self-start"><Pill tone="silver" icon="mic">در حال گفتن</Pill></span> : null}
            </div>
          </div>
        </Card>
        {!atEnd ? (
          <button type="button" aria-label={unseen ? `برو به آخر گفتگو، ${unseen} نوبت تازه` : 'برو به آخر گفتگو'} onClick={() => { jumping.current = true; pin(true); toEnd(true); window.setTimeout(() => { jumping.current = false; }, 1500); }}
            className="absolute bottom-3 left-3 flex h-10 min-w-10 items-center justify-center gap-1 rounded-full border border-strong bg-page px-2.5 text-[18px] leading-none text-ink shadow-[0_6px_20px_rgba(0,0,0,.3)] hover:bg-hover">
{unseen ? <span className="fig rounded-full bg-raised px-1.5 text-[11px] font-semibold leading-5 text-ink shadow-[inset_0_0_0_1px_var(--hq-silver-line)]">{unseen}</span> : null}
            <span aria-hidden>↓</span>
          </button>
        ) : null}
      </div>

      {above}

      {readOnly ? (
        <Card as="section" className="flex-none p-3 text-[13px] text-sec" aria-label="نوشتن">این جلسه بسته شده و فقط خواندنی است؛ برای ادامه، دوباره بازش کن.</Card>
      ) : (
        <Card as="section" className={cx('flex flex-none flex-col gap-2 p-3 transition-colors', drag && 'bg-raised ring-1 ring-[var(--hq-silver-line)]')} aria-label="نوشتن"
          onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDrag(true); } }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); void files.add(e.dataTransfer.files); }}>
          <AttachmentTray items={files.items} onRemove={files.remove} onRetry={files.retry} />
          {holding ? (
            <div className="flex items-center gap-3 rounded-[10px] bg-tile px-3 py-2" role="status" aria-label="در حال شنیدن">
              <Waveform levels={lv.levels} className="h-8 min-w-0 flex-1" />
              <span className="fig text-[12px] text-sec">{Math.floor(lv.elapsed)}s</span>
              {lv.live ? <span className="min-w-0 max-w-[50%] truncate text-[12px] text-sec"><FaText text={lv.live} /></span> : null}
              <button type="button" onClick={lv.cancel} className="text-[12px] text-muted hover:text-ink">لغو</button>
            </div>
          ) : null}
          {/* The text takes the whole width; the actions are one compact row under it. */}
          <textarea
            ref={area} value={text} rows={1} dir="auto" aria-label="پیام" placeholder={placeholder ?? 'بنویس یا نگه‌دار و بگو…'} autoComplete="off" spellCheck={false}
            onPaste={(e) => { const fs = [...e.clipboardData.files]; if (fs.length) { e.preventDefault(); void files.add(fs); } }}
            onChange={(e) => { const v = e.target.value; if (looksLikeKey(v, engines.data)) { setText(''); openKey(v.trim()); } else setText(v); }}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(text, 'typed', true); } }}
            style={{ minHeight: 48, maxHeight: MAX_LINES * LINE_PX + 22 }}
            className={cx(field, 'block w-full min-w-0 resize-none py-[11px] leading-6')} />
          <div className="flex items-center gap-2">
            <input ref={pick} type="file" multiple hidden accept={RICH_ACCEPT} aria-label="فایل برای فرستادن" onChange={(e) => { if (e.target.files) void files.add(e.target.files); e.target.value = ''; }} />
            <IconButton icon="attach" label="فایل بفرست: عکس، فیلم، صدا، PDF، فونت، متن یا ZIP" size={40} onClick={() => pick.current?.click()} />
            <span className="flex items-center gap-2 text-[12px] text-muted">
              <Switch checked={handsFree} onChange={setHandsFree} label="بی‌دست (خودش گوش میدهد)" disabled={!recSupported} />
              <span aria-hidden>بی‌دست</span>
            </span>
            {files.uploading ? <span role="status" className="min-w-0 truncate text-[12px] text-muted">صبر کن فایل‌ها بالا بروند…</span> : null}
            <span className="flex-1" />
            {hasText && !holding ? (
              <button type="button" aria-label="بفرست" disabled={files.uploading || busy} onClick={() => void send(text, 'typed', true)}
                className={cx('flex size-10 flex-none items-center justify-center rounded-full disabled:bg-disabled-fill disabled:text-disabled', quietSend ? 'bg-[var(--hq-silver-soft)] text-ink hover:bg-[var(--hq-silver-soft-hover)]' : 'bg-gold text-on-gold hover:bg-gold-bright')}>
                <Icon name="send" size={20} mirror />
              </button>
            ) : (
              <button type="button" aria-label="نگه‌دار و بگو" title="نگه دار، بگو و رها کن." aria-pressed={holding} disabled={!recSupported && typeof MediaRecorder === 'undefined'}
                onPointerDown={(e) => { e.preventDefault(); (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId); interrupt(); void lv.start(); }}
                onPointerUp={() => lv.finish()} onPointerCancel={() => lv.cancel()}
                onKeyDown={(e) => { if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) { e.preventDefault(); if (holding) lv.finish(); else { interrupt(); void lv.start(); } } }}
                className={cx('flex size-10 flex-none touch-none select-none items-center justify-center rounded-full', holding ? 'bg-neg text-white' : 'bg-[var(--hq-silver-soft)] text-silver-ink hover:bg-[var(--hq-silver-soft-hover)] disabled:bg-disabled-fill disabled:text-disabled')}>
                <Icon name="mic" size={20} />
              </button>
            )}
          </div>
        </Card>
      )}
      {keyOpen ? <KeyDialog key={keyOpen.n} open onOpenChange={(v) => { if (!v) setKeyOpen(null); }} initialKey={keyOpen.key} /> : null}
    </>
  );
}
