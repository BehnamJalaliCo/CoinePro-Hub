'use client';

// ⟨1.14⟩ Contract §32 «گفتگو»: the owner talks with the holding secretary, the overseer, the personal assistant, the advisor or any manager,
// by typing, by holding a button, or hands-free. The answer streams in (text, then the spoken sentences in order); work comes out only
// through cards he taps. The voice engine's key is given in the chat's own sheet, never as a message.

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Avatar, Orb } from '@/components/brand/avatar';
import { Icon } from '@/components/icon';
import { Waveform } from '@/components/media/composer';
import { Button, IconButton } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, FilterChip, Pill, Segmented, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaText } from '@/components/v29/text';
import { errText, field } from '@/components/v31/kit';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { useRoles } from '@/lib/api/v14';
import {
  MODE_FA, looksLikeKey, postTurn, readTurnEvents, stopTurn, turnsOf, useConversation, useConversations, useEngines, usePersonas, useTalkActions,
  type Conversation, type Mode, type Persona, type TalkCard, type Turn, type TurnEvent, type TurnSource,
} from '@/lib/api/v32';
import { ago, cx } from '@/lib/format';
import { LONG_VOICE_ERROR, recognizer, useLongVoice } from '@/lib/long-voice';
import { useAudioQueue } from '@/lib/talk-audio';
import { useHandsFree } from '@/lib/talk-handsfree';
import { TalkCardView } from './cards';
import { EngineLights, KeyDialog, MeterChip, MeterPanel, VoicesPanel, personaFa } from './engines';

const FACES = ['secretary', 'overseer', 'assistant', 'advisor'] as const;
const FACE_FA: Record<string, string> = { secretary: 'منشی هلدینگ', overseer: 'ناظر کل', assistant: 'دستیار شخصی', advisor: 'مشاور کل' };

/** The mark of a persona: the same medallions as the rest of the app, the secretary with the command mark. */
function Face({ k, size = 44, state = 'idle' }: { k: string; size?: number; state?: 'idle' | 'working' | 'sleeping' }) {
  if (k === 'advisor') return <Orb size={size} state={state === 'working' ? 'speaking' : 'rest'} label={FACE_FA.advisor} />;
  if (k === 'overseer') return <Avatar kind="overseer" size={size} state={state} label={FACE_FA.overseer} />;
  if (k === 'assistant') return <Avatar kind="assistant" size={size} state={state} label={FACE_FA.assistant} />;
  if (k === 'secretary') {
    return <span role="img" aria-label={FACE_FA.secretary} className="flex flex-none items-center justify-center rounded-full bg-gold-soft text-gold-ink" style={{ width: size, height: size, boxShadow: 'inset 0 0 0 2px var(--hq-gold-ink)' }}><Icon name="command" size={Math.round(size * 0.5)} /></span>;
  }
  return <Avatar kind="manager" size={size} state={state} label="مدیر" />;
}

// What the page keeps about the turn that is being answered right now.
type Live = { owner: string; id: string | null; answer: string; cards: TalkCard[]; error: string | null; streaming: boolean };

export function Talk() {
  const qc = useQueryClient();
  const toast = useToast();
  const act = useTalkActions();
  const personas = usePersonas();
  const engines = useEngines();
  const convs = useConversations();
  const companies = useCompanies();
  const [ref, setRef] = useState<string | null>(null);
  const [face, setFace] = useState<string>('secretary');
  const conv = useConversation(ref);
  const [live, setLive] = useState<Live | null>(null);
  const [text, setText] = useState('');
  const [keyOpen, setKeyOpen] = useState<{ n: number; key: string } | null>(null);
  const [meterOpen, setMeterOpen] = useState(false);
  const [voicesOpen, setVoicesOpen] = useState(false);
  const [listOpen, setListOpen] = useState(false);
  const [plus, setPlus] = useState(false);
  const [pulse, setPulse] = useState(0);
  const [handsFree, setHandsFree] = useState(false);
  const audio = useAudioQueue();
  const abort = useRef<AbortController | null>(null);
  const liveId = useRef<string | null>(null);
  const bottom = useRef<HTMLDivElement | null>(null);

  const c = conv.data ?? null;
  const turns = turnsOf(c);
  const mode: Mode = c?.mode ?? 'consult';
  const busy = !!live?.streaming;
  const personaOf = (key: string) => personas.data?.find((p) => p.key === key || key.startsWith(`${p.role}@`)) ?? null;

  useEffect(() => { bottom.current?.scrollIntoView({ block: 'end' }); }, [turns.length, live?.answer, live?.cards.length]);

  /** Barge-in: what is playing stops, what is waiting is not played, and the generation ends (so unspoken sentences are not billed). */
  const interrupt = useCallback(() => {
    audio.stop();
    const id = liveId.current;
    if (id) { liveId.current = null; void stopTurn(id).catch(() => undefined); }
  }, [audio]);

  const openKey = (k = '') => setKeyOpen((o) => ({ n: (o?.n ?? 0) + 1, key: k }));

  const ensureConversation = async (persona: string): Promise<string> => {
    if (ref) return ref;
    const created = await act.create.mutateAsync({ persona });
    setRef(created.ref);
    return created.ref;
  };

  const send = useCallback(async (raw: string, source: TurnSource = 'typed') => {
    const t = raw.trim();
    if (!t) return;
    // A key-shaped string is never a message: it moves into the key sheet (the server also scrubs one that slips through).
    if (looksLikeKey(t, engines.data)) { setText(''); openKey(t); return; }
    try {
      interrupt();
      const cv = ref ?? (await act.create.mutateAsync({ persona: face })).ref;
      if (!ref) setRef(cv);
      setText('');
      setLive({ owner: t, id: null, answer: '', cards: [], error: null, streaming: true });
      const { turn } = await postTurn(cv, { text: t, source, client_id: crypto.randomUUID() });
      liveId.current = turn.id;
      setLive((l) => l && { ...l, id: turn.id });
      abort.current?.abort();
      const ctl = new AbortController();
      abort.current = ctl;
      const onEvent = (e: TurnEvent) => {
        if (e.type === 'text') setLive((l) => l && { ...l, answer: l.answer + e.delta });
        else if (e.type === 'audio') audio.push({ seq: e.seq, file_id: e.file_id });
        else if (e.type === 'card') setLive((l) => l && { ...l, cards: [...l.cards, e.card] });
        else if (e.type === 'meter') { setPulse((n) => n + 1); void qc.invalidateQueries({ queryKey: ['voice', 'meter'] }); }
        else if (e.type === 'invite' && e.company) act.invite.mutate({ ref: cv, role: e.role, company: e.company });
        else if (e.type === 'error') setLive((l) => l && { ...l, error: e.reason_fa });
      };
      const end = await readTurnEvents(turn.id, onEvent, ctl.signal);
      if (liveId.current === turn.id) liveId.current = null;
      if (end === 'aborted') return;
      await Promise.all([qc.refetchQueries({ queryKey: ['talk', 'conversation', cv] }), qc.invalidateQueries({ queryKey: ['talk', 'conversations'] }), qc.invalidateQueries({ queryKey: ['voice'] })]);
      setLive((l) => (l?.id === turn.id ? (end === 'error' ? { ...l, streaming: false } : null) : l));
    } catch (e) {
      setLive(null);
      toast({ tone: 'error', text: errText(e, 'گفته‌ات فرستاده نشد؛ دوباره بزن.') });
    }
  }, [act.create, act.invite, audio, engines.data, face, interrupt, qc, ref, toast]);

  // Hold to talk: the phone's recogniser first; long speech goes to the hub's transcription (purpose «talk»).
  const lv = useLongVoice({
    purpose: 'talk',
    onText: (r) => void send(r.text, 'hold'),
    onError: (f, d) => toast({ tone: f === 'empty' ? 'info' : 'error', text: d ?? LONG_VOICE_ERROR[f] }),
  });
  const holding = lv.phase === 'listening' || lv.phase === 'asking';
  useHandsFree({
    enabled: handsFree,
    onSpeech: interrupt,
    onUtterance: (t) => void send(t, 'handsfree'),
    onFatal: (why) => { setHandsFree(false); toast({ tone: 'error', text: why === 'not-allowed' || why === 'service-not-allowed' ? LONG_VOICE_ERROR.denied : 'گوش دادن بی‌دست متوقف شد؛ دوباره روشنش کن.' }); },
  });
  useEffect(() => () => { abort.current?.abort(); }, []);

  const open = (r: string | null, persona?: string) => {
    abort.current?.abort(); audio.stop(); liveId.current = null; setLive(null);
    setRef(r); if (persona) setFace(persona.includes('@') ? 'manager' : persona);
  };
  const pick = (k: string) => {
    const mine = (convs.data ?? []).find((x) => x.persona === k);
    setFace(k);
    if (mine) open(mine.ref, k); else open(null, k);
  };
  const setMode = (m: Mode) => { if (ref) act.patch.mutate({ ref, mode: m }, { onError: (e) => toast({ tone: 'error', text: errText(e, 'حالت عوض نشد.') }) }); };
  const minutes = () => ref && act.minutes.mutate(ref, { onSuccess: () => toast({ tone: 'ok', text: 'صورت‌جلسه آماده شد؛ کارتش پایین گفتگو است.' }), onError: (e) => toast({ tone: 'error', text: errText(e, 'صورت‌جلسه ساخته نشد.') }) });
  const recSupported = typeof window !== 'undefined' && !!recognizer();
  const present = c?.present ?? [];
  const nameOf = (code: string) => companies.data?.find((x) => x.code === code)?.name_fa ?? code;
  const presentFa = (p: string) => (p.includes('@') ? `${p.startsWith('ceo') ? 'مدیرعامل' : p.split('@')[0]} ${nameOf(p.split('@')[1]!)}` : personaFa(p));

  return (
    <div className="flex flex-col gap-4">
      {/* The header of the talk screen: the engines' light, the meter, the key, the voices. */}
      <Card as="section" className="flex flex-col gap-3 p-4" aria-label="وضعیت صدا">
        <div className="flex flex-wrap items-center gap-2">
          <div className="min-w-0 flex-1"><EngineLights engines={engines.data} onKey={() => openKey()} /></div>
          <MeterChip onOpen={() => setMeterOpen(true)} pulse={pulse} />
          <IconButton icon="lock" label="کلید صدا" onClick={() => openKey()} />
          <IconButton icon="mic" label="صدای چهره‌ها" onClick={() => setVoicesOpen(true)} />
          <IconButton icon="messages" label="گفتگوها" onClick={() => setListOpen(true)} className="lg:hidden" />
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="hidden lg:block" aria-label="گفتگوها"><ConversationList current={ref} onPick={(x) => open(x.ref, x.persona)} onNew={() => open(null, face)} /></aside>

        <div className="flex min-w-0 flex-col gap-3">
          {/* The faces */}
          <div className="no-scrollbar flex items-start gap-3 overflow-x-auto pb-1" role="radiogroup" aria-label="با چه کسی حرف میزنی">
            {FACES.map((k) => {
              const on = (c ? c.persona === k : face === k) || (!!c && c.present.includes(k) && c.persona === k);
              const talking = busy && on;
              return (
                <button key={k} type="button" role="radio" aria-checked={on} onClick={() => pick(k)} className={cx('flex w-[84px] flex-none flex-col items-center gap-1.5 rounded-[14px] p-2 text-[12px]', on ? 'bg-gold-soft font-semibold text-ink' : 'text-sec hover:bg-hover')}>
                  <Face k={k} state={talking ? 'working' : 'idle'} />
                  <span className="text-center leading-4">{FACE_FA[k]}</span>
                </button>
              );
            })}
            {present.filter((p) => p.includes('@')).map((p) => (
              <span key={p} className="flex w-[84px] flex-none flex-col items-center gap-1.5 rounded-[14px] bg-gold-soft p-2 text-[12px] font-semibold text-ink" aria-label={`حاضر: ${presentFa(p)}`}>
                <Face k="manager" state={busy ? 'working' : 'idle'} />
                <span className="text-center leading-4">{presentFa(p)}</span>
              </span>
            ))}
            <button type="button" onClick={() => setPlus(true)} aria-label="مدیر یک شرکت را بیاور" className="flex w-[84px] flex-none flex-col items-center gap-1.5 rounded-[14px] p-2 text-[12px] text-sec hover:bg-hover">
              <span className="flex size-11 items-center justify-center rounded-full border border-dashed border-strong text-gold-ink"><Icon name="add" size={22} /></span>
              <span className="text-center leading-4">مدیر شرکت</span>
            </button>
          </div>

          {/* Mode, end of a working session, minutes */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="w-56 max-w-full"><Segmented<Mode> label="حالت گفتگو" value={mode} onChange={setMode} options={[{ value: 'consult', label: MODE_FA.consult }, { value: 'work', label: MODE_FA.work }]} /></div>
            {mode === 'work' && ref ? <Button size="sm" icon="stop" disabled={busy} onClick={() => void send('پایان جلسه')}>پایان جلسه</Button> : null}
            {ref ? <Button size="sm" icon="report" loading={act.minutes.isPending} disabled={busy || !turns.length} onClick={minutes}>صورت‌جلسه کن</Button> : null}
            {c ? <span className="ms-auto text-[12px] text-muted"><FaText text={c.ref} /></span> : null}
          </div>

          {/* The conversation */}
          <Card as="section" className="flex min-h-[320px] flex-col gap-3 p-4 lg:max-h-[calc(100dvh-22rem)] lg:overflow-y-auto" aria-label="گفتگو" aria-live="polite">
            {ref && conv.isLoading ? <Skeleton className="h-40 rounded-[14px]" /> : null}
            {!ref && !live ? <Empty icon="messages" title={`با ${FACE_FA[face] ?? 'مدیر'} حرف بزن`} body="بنویس یا دکمه‌ی میکروفون را نگه دار و بگو. کاری که از دل گفتگو بیرون میآید، فقط با کارتی که تو میزنی اجرا میشود." /> : null}
            {turns.map((t) => <TurnView key={t.id} t={t} persona={personaOf(t.by)} />)}
            {live ? (
              <>
                <OwnerBubble text={live.owner} />
                <div className="flex gap-2.5" aria-label="پاسخ در حال نوشته شدن">
                  <Face k={c?.persona.includes('@') ? 'manager' : (c?.persona ?? face)} size={32} state={live.streaming ? 'working' : 'idle'} />
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

          {/* The composer */}
          <Card as="section" className="flex flex-col gap-2.5 p-3" aria-label="نوشتن">
            {holding ? (
              <div className="flex items-center gap-3 rounded-[10px] bg-tile px-3 py-2" role="status" aria-label="در حال شنیدن">
                <Waveform levels={lv.levels} className="h-8 min-w-0 flex-1" />
                <span className="fig text-[12px] text-sec">{Math.floor(lv.elapsed)}s</span>
                {lv.live ? <span className="min-w-0 max-w-[50%] truncate text-[12px] text-sec"><FaText text={lv.live} /></span> : null}
                <button type="button" onClick={lv.cancel} className="text-[12px] text-muted hover:text-ink">لغو</button>
              </div>
            ) : null}
            <div className="flex items-end gap-2">
              <textarea
                value={text} rows={2} dir="auto" aria-label="پیام" placeholder="بنویس یا نگه‌دار و بگو…" autoComplete="off" spellCheck={false}
                onChange={(e) => { const v = e.target.value; if (looksLikeKey(v, engines.data)) { setText(''); openKey(v.trim()); } else setText(v); }}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(text); } }}
                className={cx(field, 'min-h-[3rem] flex-1 resize-none py-2.5 leading-6')} />
              <button type="button" aria-label="نگه‌دار و بگو" aria-pressed={holding} disabled={!recSupported && typeof MediaRecorder === 'undefined'}
                onPointerDown={(e) => { e.preventDefault(); (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId); interrupt(); void lv.start(); }}
                onPointerUp={() => lv.finish()} onPointerCancel={() => lv.cancel()}
                onKeyDown={(e) => { if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) { e.preventDefault(); if (holding) lv.finish(); else { interrupt(); void lv.start(); } } }}
                className={cx('flex size-12 flex-none touch-none select-none items-center justify-center rounded-full', holding ? 'bg-neg text-white' : 'bg-gold text-on-gold hover:bg-gold-bright disabled:bg-disabled-fill disabled:text-disabled')}>
                <Icon name="mic" size={22} />
              </button>
              <Button variant="primary" icon="send" disabled={!text.trim() || busy} onClick={() => void send(text)} aria-label="بفرست">بفرست</Button>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-[12px] text-muted">
              <Switch checked={handsFree} onChange={setHandsFree} label="بی‌دست (خودش گوش میدهد)" disabled={!recSupported} />
              <span>{recSupported ? 'دکمه‌ی طلایی را نگه دار، بگو و رها کن.' : 'این مرورگر گفتار را نمیشناسد؛ بنویس.'}</span>
            </div>
          </Card>
        </div>
      </div>

      <Sheet open={listOpen} onOpenChange={setListOpen} title="گفتگوها" width={420}>
        <ConversationList current={ref} onPick={(x) => { open(x.ref, x.persona); setListOpen(false); }} onNew={() => { open(null, face); setListOpen(false); }} />
      </Sheet>
      <PlusSheet open={plus} onOpenChange={setPlus} onDone={(r) => { setPlus(false); if (r) { setRef(r); setFace('manager'); } }} current={ref} />
      {keyOpen ? <KeyDialog key={keyOpen.n} open onOpenChange={(v) => { if (!v) setKeyOpen(null); }} initialKey={keyOpen.key} /> : null}
      <MeterPanel open={meterOpen} onOpenChange={setMeterOpen} />
      <VoicesPanel open={voicesOpen} onOpenChange={setVoicesOpen} />
    </div>
  );
}

// ===================================================================================================== the bubbles ==
function Bubble({ children, own }: { children: React.ReactNode; own?: boolean }) {
  return <div className={cx('max-w-[46rem] rounded-[14px] px-3.5 py-2.5 text-[14px] leading-7', own ? 'self-start bg-gold-soft text-ink' : 'bg-tile text-ink')}>{children}</div>;
}
const OwnerBubble = ({ text }: { text: string }) => <div className="flex justify-start" data-by="owner"><Bubble own><span dir="auto" className="whitespace-pre-wrap"><FaText text={text} /></span></Bubble></div>;

function TurnView({ t, persona }: { t: Turn; persona: Persona | null }) {
  if (t.by === 'owner') return <OwnerBubble text={t.text} />;
  const body = t.show_md ?? t.say_fa ?? t.text;
  return (
    <div className="flex gap-2.5" data-by={t.by} data-state={t.state}>
      <Face k={t.by.includes('@') ? 'manager' : t.by} size={32} />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <span className="text-[11px] font-semibold text-muted">{persona?.title_fa ?? personaFa(t.by)}</span>
        {body ? <Bubble><Md text={body} /></Bubble> : null}
        {t.state === 'stopped' ? <span className="text-[12px] text-muted">قطع شد.</span> : null}
        {t.state === 'failed' ? <p className="rounded-[10px] bg-warn-soft px-3 py-2 text-[13px] leading-6"><FaText text={t.reason_fa ?? 'جواب کامل نشد؛ دوباره بپرس.'} /></p> : null}
        {t.cards.map((cd) => <TalkCardView key={cd.id} card={cd} />)}
      </div>
    </div>
  );
}

// ================================================================================================ the conversations ==
function ConversationList({ current, onPick, onNew }: { current: string | null; onPick: (c: Conversation) => void; onNew: () => void }) {
  const [q, setQ] = useState('');
  const [term, setTerm] = useState('');
  useEffect(() => { const h = setTimeout(() => setTerm(q.trim()), 250); return () => clearTimeout(h); }, [q]);
  const list = useConversations({ q: term });
  return (
    <Card as="section" className="flex flex-col gap-3 p-3" aria-label="فهرست گفتگوها">
      <div className="flex items-center gap-2">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="جست‌وجو در گفتگوها" aria-label="جست‌وجو در گفتگوها" dir="auto" className={cx(field, 'h-10 min-w-0 flex-1')} />
        <IconButton icon="add" label="گفتگوی تازه" onClick={onNew} />
      </div>
      {list.isLoading ? <Skeleton className="h-24 rounded-[12px]" /> : list.data === null ? <p className="text-[13px] text-muted">گفتگو بعد از به‌روزرسانی ستاد میاید.</p> : !list.data?.length ? (
        <p className="py-4 text-center text-[13px] text-muted">{term ? 'چیزی پیدا نشد.' : 'هنوز گفتگویی نیست.'}</p>
      ) : (
        <ul className="flex flex-col gap-1" aria-label="گفتگوها">
          {list.data.map((c) => (
            <li key={c.ref}>
              <button type="button" onClick={() => onPick(c)} aria-current={c.ref === current ? 'true' : undefined} className={cx('flex w-full flex-col gap-0.5 rounded-[10px] px-3 py-2 text-start', c.ref === current ? 'bg-gold-soft' : 'hover:bg-hover')}>
                <span className="flex items-center gap-2 text-[13px] font-semibold text-ink"><span className="min-w-0 flex-1 truncate"><FaText text={c.title_fa} /></span>{c.open_cards ? <Pill tone="gold">{c.open_cards}</Pill> : null}</span>
                <span className="flex gap-2 text-[11px] text-muted"><span>{personaFa(c.persona.includes('@') ? 'manager' : c.persona)}</span><span>{c.last_turn_at ? ago(c.last_turn_at) : 'تازه'}</span></span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ============================================================================================= the «+» (company → role) ==
function PlusSheet({ open, onOpenChange, onDone, current }: { open: boolean; onOpenChange: (v: boolean) => void; onDone: (ref: string | null) => void; current: string | null }) {
  const companies = useCompanies();
  const roles = useRoles();
  const act = useTalkActions();
  const toast = useToast();
  const [co, setCo] = useState<string | null>(null);
  const list = useMemo(() => (companies.data ?? []).filter((c) => c.kind !== 'holding' && c.code !== 'HQ'), [companies.data]);
  const rs = (roles.data ?? []).filter((r) => r.scope === 'company' && (r.kind === 'ceo' || r.kind === 'manager') && (!r.company || r.company === co));
  const go = (role: string) => {
    if (!co) return;
    const done = (ref: string) => { setCo(null); onDone(ref); };
    const fail = (e: unknown) => toast({ tone: 'error', text: errText(e, e instanceof ApiError ? 'این مدیر نیامد.' : 'نشد؛ دوباره بزن.') });
    if (current) act.invite.mutate({ ref: current, role, company: co }, { onSuccess: (r) => done(r.ref), onError: fail });
    else act.create.mutate({ persona: 'manager', role, company: co }, { onSuccess: (r) => done(r.ref), onError: fail });
  };
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="مدیر یک شرکت را بیاور" description="اول شرکت، بعد نقش؛ فقط به اطلاعات همان شرکت دسترسی دارد" width={420}>
      <div className="flex flex-col gap-4">
        <fieldset className="flex flex-col gap-2"><legend className="pb-1 text-[12px] text-sec">شرکت</legend>
          <div className="flex flex-wrap gap-1.5">{list.map((c) => <FilterChip key={c.code} selected={co === c.code} onClick={() => setCo(c.code)}>{c.name_fa}</FilterChip>)}</div>
        </fieldset>
        {co ? (
          <fieldset className="flex flex-col gap-2"><legend className="pb-1 text-[12px] text-sec">نقش</legend>
            <div className="flex flex-wrap gap-1.5">{rs.map((r) => <FilterChip key={r.role} onClick={() => go(r.role)}>{r.title_fa}</FilterChip>)}</div>
          </fieldset>
        ) : null}
      </div>
    </Sheet>
  );
}
