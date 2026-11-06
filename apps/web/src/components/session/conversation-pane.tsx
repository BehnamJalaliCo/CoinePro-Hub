'use client';

// The conversation itself, taken out of «گفتگو» (components/v32/talk.tsx) so the session page speaks with the same composer, voice,
// hands-free listening, streamed answer and cards: the answer streams in (text, then the spoken sentences in order); work comes out only
// through cards he taps. The pane is bound to one conversation (`conversationRef`); on «گفتگو» it is made on the first word (`ensure`),
// in a session it is the order's own talk, and `to` aims a word at one participant or at everyone (§35.4).

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
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
import { cx } from '@/lib/format';
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

/** What a page can ask of the pane from outside. */
export type PaneApi = { send: (text: string) => Promise<void> };

export function Bubble({ children, own }: { children: React.ReactNode; own?: boolean }) {
  return <div className={cx('max-w-[46rem] rounded-[14px] px-3.5 py-2.5 text-[14px] leading-7', own ? 'self-start bg-gold-soft text-ink' : 'bg-tile text-ink')}>{children}</div>;
}
// ⟨1.18⟩ §36.2 the owner's files sit in his bubble: pictures as thumbnails, the rest as rows with a download. The word «فایل» that stands in
// for an empty text is not shown when files are there.
export const FILE_WORD = 'فایل';
export function OwnerBubble({ text, files }: { text: string; files?: MediaRef[] }) {
  const has = !!files?.length;
  const body = useRef<HTMLSpanElement | null>(null);
  const showText = !(has && text === FILE_WORD);
  return (
    <div className="flex flex-col items-start gap-0.5" data-by="owner">
      <Bubble own>
        <div className="flex flex-col gap-2">
          {has ? <div aria-label="فایل‌های فرستاده‌شده"><MessageMedia items={files!} /></div> : null}
          {showText ? <span ref={body} dir="auto" className="whitespace-pre-wrap"><FaText text={text} /></span> : null}
        </div>
      </Bubble>
      {showText ? <CopyButton target={body} /> : null}
    </div>
  );
}

export function TurnView({ t, persona, title }: { t: Turn; persona: Persona | null; title?: string }) {
  const bodyRef = useRef<HTMLDivElement | null>(null);
  if (t.by === 'owner') return <OwnerBubble text={t.text} files={t.files} />;
  const body = t.show_md ?? t.say_fa ?? t.text;
  return (
    <div className="flex gap-2.5" data-by={t.by} data-state={t.state}>
      <Face k={t.by.includes('@') && !t.by.startsWith('player:') ? 'manager' : t.by} size={32} />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <span className="text-[11px] font-semibold text-muted">{title ?? persona?.title_fa ?? (t.by.startsWith('player:') ? playerName(t.by) : personaFa(t.by))}</span>
        {body ? <><Bubble><div ref={bodyRef}><Md text={body} /></div></Bubble><CopyButton target={bodyRef} /></> : null}
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
  /** Height of the scrolling talk on wide screens. */
  talkHeight?: string;
  placeholder?: string;
};

export function ConversationPane({ conversationRef: ref, face, ensure, to, titleOf, readOnly, onBusy, onMeter, onApi, emptyTitle, emptyBody, talkHeight = 'lg:max-h-[calc(100dvh-22rem)]', placeholder }: PaneProps) {
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
  useEffect(() => { filesRef.current = files; });
  const audio = useAudioQueue();
  const abort = useRef<AbortController | null>(null);
  const liveId = useRef<string | null>(null);
  const bottom = useRef<HTMLDivElement | null>(null);

  const c = conv.data ?? null;
  const turns = turnsOf(c);
  const busy = !!live?.streaming;
  const personaOf = (key: string) => personas.data?.find((p) => p.key === key || key.startsWith(`${p.role}@`)) ?? null;

  useEffect(() => { onBusy?.(busy); }, [busy, onBusy]);
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'end' }); }, [turns.length, live?.answer, live?.cards.length]);

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
    if (att?.uploading) return;
    const t = raw.trim() || (ids.length ? FILE_WORD : '');
    if (!t || readOnly) return;
    // A key-shaped string is never a message: it moves into the key sheet (the server also scrubs one that slips through).
    if (looksLikeKey(t, engines.data)) { setText(''); openKey(t); return; }
    try {
      interrupt();
      const cv = ref ?? (ensure ? await ensure() : null);
      if (!cv) return;
      setText('');
      setLive({ owner: t, files: (att?.items ?? []).flatMap((x) => (x.ref ? [x.ref] : [])), id: null, answer: '', cards: [], error: null, streaming: true });
      const { turn } = await postTurn(cv, { text: t, source, client_id: crypto.randomUUID(), ...(to ? { to } : {}), ...(ids.length ? { file_ids: ids } : {}) });
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
      toast({ tone: 'error', text: errText(e, 'گفته‌ات فرستاده نشد؛ دوباره بزن.') });
    }
  }, [act.invite, audio, engines.data, ensure, interrupt, onMeter, qc, readOnly, ref, to, toast]);

  // The page may speak for the owner («پایان جلسه», a suggestion's words…).
  const sendRef = useRef(send);
  useEffect(() => { sendRef.current = send; });
  useEffect(() => {
    onApi?.({ send: (t) => sendRef.current(t) });
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

  return (
    <>
      <Card as="section" className={cx('flex min-h-[320px] flex-col gap-3 p-4 lg:overflow-y-auto', talkHeight)} aria-label="گفتگو" aria-live="polite">
        {ref && conv.isLoading ? <Skeleton className="h-40 rounded-[14px]" /> : null}
        {!ref && !live ? <Empty icon="messages" title={emptyTitle ?? `با ${FACE_FA[face] ?? 'مدیر'} حرف بزن`} body={emptyBody ?? 'بنویس یا دکمه‌ی میکروفون را نگه دار و بگو. کاری که از دل گفتگو بیرون میآید، فقط با کارتی که تو میزنی اجرا میشود.'} /> : null}
        {turns.map((t) => <TurnView key={t.id} t={t} persona={personaOf(t.by)} title={titleOf?.(t.by)} />)}
        {live ? (
          <>
            <OwnerBubble text={live.owner} files={live.files} />
            <div className="flex gap-2.5" aria-label="پاسخ در حال نوشته شدن">
              <Face k={to && to !== 'all' && to.startsWith('player:') ? to : liveFace} size={32} state={live.streaming ? 'working' : 'idle'} />
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                {live.answer ? <Bubble><Md text={live.answer} /></Bubble> : live.streaming ? <Bubble><span className="text-[13px] text-muted" role="status">دارم فکر میکنم…</span></Bubble> : null}
                {live.cards.map((cd) => <TalkCardView key={cd.id} card={cd} />)}
                {live.error ? <p className="rounded-[10px] bg-warn-soft px-3 py-2 text-[13px] leading-6" role="alert"><FaText text={live.error} /></p> : null}
                {live.streaming ? <div><Button size="sm" icon="stop" onClick={() => { interrupt(); }}>ساکت شو</Button></div> : null}
              </div>
            </div>
          </>
        ) : null}
        {audio.playing ? <span className="self-start"><Pill tone="gold" live icon="mic">در حال گفتن</Pill></span> : null}
        <div ref={bottom} />
      </Card>

      {readOnly ? (
        <Card as="section" className="p-3 text-[13px] text-sec" aria-label="نوشتن">این جلسه بسته شده و فقط خواندنی است؛ برای ادامه، دوباره بازش کن.</Card>
      ) : (
        <Card as="section" className={cx('flex flex-col gap-2.5 p-3 transition-colors', drag && 'bg-gold-soft ring-1 ring-[var(--hq-gold-ink)]')} aria-label="نوشتن"
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
          <div className="flex items-end gap-2">
            <input ref={pick} type="file" multiple hidden accept={RICH_ACCEPT} aria-label="فایل برای فرستادن" onChange={(e) => { if (e.target.files) void files.add(e.target.files); e.target.value = ''; }} />
            <IconButton icon="attach" label="فایل بفرست: عکس، فیلم، صدا، PDF، فونت، متن یا ZIP" size={48} onClick={() => pick.current?.click()} />
            <textarea
              value={text} rows={2} dir="auto" aria-label="پیام" placeholder={placeholder ?? 'بنویس یا نگه‌دار و بگو…'} autoComplete="off" spellCheck={false}
              onPaste={(e) => { const fs = [...e.clipboardData.files]; if (fs.length) { e.preventDefault(); void files.add(fs); } }}
              onChange={(e) => { const v = e.target.value; if (looksLikeKey(v, engines.data)) { setText(''); openKey(v.trim()); } else setText(v); }}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(text, 'typed', true); } }}
              className={cx(field, 'min-h-[3rem] flex-1 resize-none py-2.5 leading-6')} />
            <button type="button" aria-label="نگه‌دار و بگو" aria-pressed={holding} disabled={!recSupported && typeof MediaRecorder === 'undefined'}
              onPointerDown={(e) => { e.preventDefault(); (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId); interrupt(); void lv.start(); }}
              onPointerUp={() => lv.finish()} onPointerCancel={() => lv.cancel()}
              onKeyDown={(e) => { if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) { e.preventDefault(); if (holding) lv.finish(); else { interrupt(); void lv.start(); } } }}
              className={cx('flex size-12 flex-none touch-none select-none items-center justify-center rounded-full', holding ? 'bg-neg text-white' : 'bg-gold text-on-gold hover:bg-gold-bright disabled:bg-disabled-fill disabled:text-disabled')}>
              <Icon name="mic" size={22} />
            </button>
            <Button variant="primary" icon="send" disabled={(!text.trim() && !files.ids.length) || files.uploading || busy} onClick={() => void send(text, 'typed', true)} aria-label="بفرست">بفرست</Button>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-[12px] text-muted">
            <Switch checked={handsFree} onChange={setHandsFree} label="بی‌دست (خودش گوش میدهد)" disabled={!recSupported} />
            {files.uploading ? <span role="status">صبر کن فایل‌ها بالا بروند…</span> : null}
            <span>{recSupported ? 'دکمه‌ی طلایی را نگه دار، بگو و رها کن.' : 'این مرورگر گفتار را نمیشناسد؛ بنویس.'}</span>
          </div>
        </Card>
      )}
      {keyOpen ? <KeyDialog key={keyOpen.n} open onOpenChange={(v) => { if (!v) setKeyOpen(null); }} initialKey={keyOpen.key} /> : null}
    </>
  );
}
