'use client';

// ⟨1.14⟩ Contract §32 (prompt 23): the owner talks with the holding, by text or by voice. Until the OpenAPI file is regenerated the shapes live
// here, written from §32. Every route group is feature-gated like §29–§31: a hub that answers 404/405/501 shows a calm «after the hub
// update» state. The key of a voice engine only ever travels in `PUT /voice/providers/{provider}/secret` (behind the passkey); it never
// enters a conversation, a query key or a log.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { stepUp } from '@/lib/auth';
import { ApiError, isMock } from './client';
import { handled } from './observe';
import { call, type MediaRef } from './v13';
import { ifMatch } from './v15';
import { notServed } from './v28';

const enc = encodeURIComponent;
async function served<T>(p: Promise<T>): Promise<T | null> {
  try { return await p; } catch (e) { if (notServed(e)) return null; throw e; }
}
const listOf = <T,>(x: T[] | { items?: T[] } | null | undefined): T[] => (Array.isArray(x) ? x : x?.items ?? []);
const list = <T,>(path: string) => async () => { const r = await served(call<T[] | { items: T[] }>('GET', path)); return r ? listOf(r) : null; };
async function withStepUp<T>(action: string, target: string, run: (h?: Record<string, string>) => Promise<T>): Promise<T> {
  try { return await run(); } catch (e) {
    if (!(e instanceof ApiError && e.status === 403 && e.code === 'step_up_required')) throw e;
    handled(e);
    return run({ 'X-Step-Up': await stepUp(action, target) });
  }
}

// ============================================================================================= §32.1 personas ==
export type PersonaKey = 'secretary' | 'overseer' | 'assistant' | 'advisor' | 'manager';
export type Persona = {
  key: PersonaKey; role: string; title_fa: string; company: string | null;
  voice: { engine: string; voice: string; rate: number }; brain: { task_class: string; effort: string }; tools: string[]; face?: string | null; consult_only: boolean;
};
export type Mode = 'consult' | 'work';
export type CardKind = 'order' | 'ask' | 'hire' | 'decision' | 'planner' | 'rule' | 'automation' | 'minutes' | 'invite' | 'delegate' | 'budget' | 'group' | 'line' | 'playbook';
export type CardState = 'offered' | 'done' | 'dismissed' | 'failed';
export type TalkCard = { id: string; turn: string; kind: CardKind; title_fa: string; body_fa: string; payload: Record<string, unknown>; state: CardState; made: string[]; reason_fa: string | null };
export type Conversation = {
  ref: string; order_ref?: string | null; closed_at?: string | null; title_fa: string; persona: string; present: string[]; mode: Mode; started_at: string; last_turn_at: string | null; turns: number; summary_fa: string | null;
  cost: { tokens: number; usd_equiv: number; voice_usd: number }; open_cards: number;
};
export type TurnSource = 'typed' | 'hold' | 'handsfree';
export type TurnState = 'streaming' | 'done' | 'stopped' | 'failed';
export type Turn = {
  id: string; conversation: string; n: number; by: string; source: TurnSource | null; text: string; say_fa: string | null; show_md: string | null; cards: TalkCard[];
  audio: Array<{ seq: number; file_id: string; seconds: number; engine: string }>; tokens: { input: number; output: number; cache_read: number; cache_write: number } | null;
  voice: { engine: string; seconds: number; audio_tokens: number; usd: number } | null; state: TurnState; files?: MediaRef[]; reason_fa: string | null; at: string;
};
/** The page of a conversation: the conversation itself and its turns (assumed flat, like the list rows, with the turns beside). */
export type ConversationPage = Conversation & { turns_page?: Turn[]; items?: Turn[]; next?: string | null };
export const MODE_FA: Record<Mode, string> = { consult: 'مشورت', work: 'جلسه‌ی کاری' };
export const CARD_FA: Record<CardKind, { fa: string; icon: 'task' | 'advisor' | 'hire' | 'decision' | 'planner' | 'seal' | 'refresh' | 'report' | 'agent' | 'delegate' | 'treasury' | 'companies'; run: string }> = {
  order: { fa: 'فرمان', icon: 'task', run: 'فرمان را بفرست' },
  ask: { fa: 'پرسش عمیق', icon: 'advisor', run: 'بپرس' },
  hire: { fa: 'استخدام', icon: 'hire', run: 'پیشنهاد را بفرست' },
  decision: { fa: 'تصمیم', icon: 'decision', run: 'کارت تصمیم بساز' },
  planner: { fa: 'برنامه', icon: 'planner', run: 'در برنامه بگذار' },
  rule: { fa: 'قانون', icon: 'seal', run: 'قانون را ثبت کن' },
  automation: { fa: 'اتوماسیون', icon: 'refresh', run: 'بساز' },
  minutes: { fa: 'صورت‌جلسه', icon: 'report', run: 'اجرا کن' },
  invite: { fa: 'دعوت', icon: 'agent', run: 'بیاورش' },
  // ⟨1.17⟩ §35.4 cards in a session
  delegate: { fa: 'سپردن کار', icon: 'delegate', run: 'بسپار' },
  budget: { fa: 'بودجه', icon: 'treasury', run: 'بودجه بده' },
  group: { fa: 'کارگروه', icon: 'companies', run: 'به کارگروه ببر' },
  line: { fa: 'خط تولید', icon: 'task', run: 'راه بینداز' },
  // ⟨1.22⟩ §40.2 the working group a session made; with a `draft` it is the holder's rewrite of the draft.
  playbook: { fa: 'کارگروه از این جلسه', icon: 'companies', run: 'بازنویسی را بپذیر' },
};

export const usePersonas = () => useQuery({ queryKey: ['talk', 'personas'], staleTime: 60_000, queryFn: list<Persona>('/talk/personas') });
export function useSavePersona() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { key: string; voice?: string; engine?: string; effort?: string }) => call<Persona>('PUT', `/talk/personas/${enc(v.key)}`, { voice: v.voice, engine: v.engine, effort: v.effort }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['talk', 'personas'] }),
  });
}

// ====================================================================================== conversations and turns ==
export const useConversations = (f: { q?: string; persona?: string } = {}) => useQuery({
  queryKey: ['talk', 'conversations', f.q ?? '', f.persona ?? ''], staleTime: 10_000,
  queryFn: list<Conversation>(`/talk/conversations?${new URLSearchParams({ ...(f.q ? { q: f.q } : {}), ...(f.persona ? { persona: f.persona } : {}) })}`),
});
export const turnsOf = (c: ConversationPage | null | undefined): Turn[] => c?.turns_page ?? c?.items ?? [];
export const useConversation = (ref: string | null) => useQuery({
  queryKey: ['talk', 'conversation', ref], enabled: !!ref, staleTime: 5_000,
  queryFn: () => served(call<ConversationPage>('GET', `/talk/conversations/${enc(ref!)}`)),
});
export function useTalkActions() {
  const qc = useQueryClient();
  const settle = () => Promise.all([qc.invalidateQueries({ queryKey: ['talk'] })]);
  return {
    create: useMutation({ mutationFn: (b: { persona: string; role?: string; company?: string; mode?: Mode }) => call<Conversation>('POST', '/talk/conversations', b), onSettled: settle }),
    patch: useMutation({ mutationFn: (v: { ref: string; mode?: Mode; title_fa?: string }) => call<Conversation>('PATCH', `/talk/conversations/${enc(v.ref)}`, { mode: v.mode, title_fa: v.title_fa }), onSettled: settle }),
    invite: useMutation({ mutationFn: (v: { ref: string; role: string; company: string }) => call<Conversation>('POST', `/talk/conversations/${enc(v.ref)}/invite`, { role: v.role, company: v.company }), onSettled: settle }),
    minutes: useMutation({ mutationFn: (ref: string) => call<{ turn?: Turn; card?: TalkCard }>('POST', `/talk/conversations/${enc(ref)}/minutes`, {}), onSettled: settle }),
    run: useMutation({ mutationFn: (v: { id: string; payload?: Record<string, unknown> }) => call<{ made: string[] }>('POST', `/talk/cards/${enc(v.id)}/run`, v.payload ? { payload: v.payload } : {}), onSettled: () => Promise.all([settle(), qc.invalidateQueries({ queryKey: ['orders'] }), qc.invalidateQueries({ queryKey: ['decisions'] })]) }),
    dismiss: useMutation({ mutationFn: (id: string) => call<TalkCard>('POST', `/talk/cards/${enc(id)}/dismiss`, {}), onSettled: settle }),
  };
}
export const postTurn = (ref: string, b: { text: string; source: TurnSource; client_id: string; to?: string; file_ids?: string[] }) =>
  call<{ turn: Turn; events: string }>('POST', `/talk/conversations/${enc(ref)}/turns`, b, { 'Idempotency-Key': b.client_id });
export const stopTurn = (id: string) => call<void>('POST', `/talk/turns/${enc(id)}/stop`, {});

// ====================================================================================== the turn's stream (SSE) ==
export type TurnEvent =
  | { type: 'text'; delta: string }
  | { type: 'say'; text: string }
  | { type: 'audio'; seq: number; file_id: string; seconds: number; engine: string }
  | { type: 'card'; card: TalkCard }
  | { type: 'invite'; role: string; company: string | null }
  | { type: 'meter'; voice_usd?: number | null; talk_usd_equiv?: number | null }
  | { type: 'done'; turn?: Turn }
  | { type: 'error'; code: string; reason_fa: string };

/** One SSE message as a typed event; null for a type this app does not know (the stream may carry more over time). */
export function turnEventOf(name: string | null, data: string): TurnEvent | null {
  let o: Record<string, unknown> = {};
  try { const j: unknown = JSON.parse(data); o = j && typeof j === 'object' ? (j as Record<string, unknown>) : { delta: j }; } catch { o = { delta: data }; }
  const d = (o.data && typeof o.data === 'object' ? o.data : o) as Record<string, unknown>;
  const type = (name && name !== 'message' ? name : (o.type as string | undefined)) ?? '';
  switch (type) {
    case 'text': return { type, delta: String(d.delta ?? d.text ?? '') };
    case 'say': return { type, text: String(d.text ?? d.say_fa ?? '') };
    case 'audio': return { type, seq: Number(d.seq ?? 0), file_id: String(d.file_id ?? ''), seconds: Number(d.seconds ?? 0), engine: String(d.engine ?? '') };
    case 'card': return { type, card: (d.card ?? d) as TalkCard };
    case 'invite': return { type, role: String(d.role ?? ''), company: (d.company as string | null) ?? null };
    case 'meter': return { type, voice_usd: d.voice_usd as number | undefined, talk_usd_equiv: d.talk_usd_equiv as number | undefined };
    case 'done': return { type, turn: d.turn as Turn | undefined };
    case 'error': return { type, code: String(d.code ?? 'error'), reason_fa: String(d.reason_fa ?? 'پاسخ کامل نشد.') };
    default: return null;
  }
}

// Same path as the typed client, so next.config's alias swaps the fixtures out of production builds.
const raw = isMock ? async (r: Request) => (await import('@/lib/api/mock-v21')).handle(r) : (r: Request) => globalThis.fetch(r);

/**
 * Reads `GET /talk/turns/{id}/events` until the turn is done or fails or [signal] aborts. One reader, no reconnect: a turn that cannot be
 * followed any more is fetched again as a stored turn by the caller. Resolves with how it ended.
 */
export async function readTurnEvents(id: string, onEvent: (e: TurnEvent) => void, signal: AbortSignal): Promise<'done' | 'error' | 'aborted' | 'ended'> {
  try {
    const res = await raw(new Request(new URL(`/api/v1/talk/turns/${enc(id)}/events`, window.location.origin), { headers: { Accept: 'text/event-stream' }, credentials: 'same-origin', cache: 'no-store', signal }));
    if (!res.ok || !res.body) { onEvent({ type: 'error', code: String(res.status), reason_fa: 'به جریان پاسخ وصل نشدم؛ پاسخ ذخیره میشود و بعداً در گفتگو میبینی.' }); return 'error'; }
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let rest = '';
    let ev: string | null = null;
    let data: string[] = [];
    let end: 'done' | 'error' | 'ended' = 'ended';
    const emit = () => {
      if (!data.length && !ev) return;
      const e = turnEventOf(ev, data.join('\n'));
      ev = null; data = [];
      if (!e) return;
      onEvent(e);
      if (e.type === 'done') end = 'done'; else if (e.type === 'error') end = 'error';
    };
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      const lines = (rest + value).split(/\r\n|\n|\r/);
      rest = lines.pop() ?? '';
      for (const l of lines) {
        if (!l) { emit(); continue; }
        if (l.startsWith(':')) continue;
        const i = l.indexOf(':');
        const k = i < 0 ? l : l.slice(0, i);
        const v = i < 0 ? '' : l.slice(i + 1).replace(/^ /, '');
        if (k === 'event') ev = v; else if (k === 'data') data.push(v);
      }
      if (end !== 'ended') { void reader.cancel().catch(() => undefined); break; }
    }
    emit();
    return end;
  } catch {
    return signal.aborted ? 'aborted' : 'ended';
  }
}

// ============================================================================================== §32.5 engines ==
export type EngineState = 'missing' | 'checking' | 'ok' | 'failing' | 'capped';
export type EnginePrice = { text_in_per_m: number; audio_out_per_m: number; audio_tokens_per_s: number; valid_until: string | null; next: { from: string; text_in_per_m: number; audio_out_per_m: number } | null; source_url: string; as_of: string };
export type VoiceEngine = {
  key: string; title_fa: string; provider: 'google' | 'local'; model: string; languages: number; rank_fa: string; key_pattern: string | null; state: EngineState; reason_fa: string | null;
  checked_at: string | null; price: EnginePrice; voices: Array<{ name: string; gender_fa: string; sample_file: string | null }>;
};
export const ENGINE_LIGHT: Record<EngineState, { fa: string; dot: string }> = {
  ok: { fa: 'کار میکند', dot: 'bg-pos' },
  checking: { fa: 'در حال بررسی', dot: 'bg-gold' },
  missing: { fa: 'کلید ندارد', dot: 'bg-neg' },
  failing: { fa: 'خطا دارد', dot: 'bg-neg' },
  capped: { fa: 'به سقف رسید', dot: 'bg-warn' },
};
export const useEngines = () => useQuery({ queryKey: ['voice', 'engines'], staleTime: 20_000, refetchInterval: (q) => (q.state.data?.some((e) => e.state === 'checking') ? 1_500 : false), queryFn: list<VoiceEngine>('/voice/engines') });

/** Whether [text] is the shape of a provider's key (any `key_pattern` of the engines): such text never goes out as a message. */
export function looksLikeKey(text: string, engines: VoiceEngine[] | null | undefined): VoiceEngine['provider'] | null {
  const tokens = text.trim().split(/\s+/).filter((t) => t.length >= 16 && t.length <= 200);
  for (const e of engines ?? []) {
    if (!e.key_pattern) continue;
    let re: RegExp;
    try { re = new RegExp(e.key_pattern); } catch { continue; } // a pattern the browser cannot read: the server still scans
    if (tokens.some((t) => re.test(t))) return e.provider;
  }
  return null;
}

export function useVoiceActions() {
  const qc = useQueryClient();
  const settle = () => Promise.all([qc.invalidateQueries({ queryKey: ['voice'] }), qc.invalidateQueries({ queryKey: ['owner-settings'] })]);
  return {
    // Write-only: the key goes to the secret store and never comes back. First key: the step-up is on the provider.
    setSecret: useMutation({ mutationFn: (v: { provider: string; secret: string }) => withStepUp('voice.secret', v.provider, (h) => call<{ state: EngineState }>('PUT', `/voice/providers/${enc(v.provider)}/secret`, { secret: v.secret }, h)), onSettled: settle }),
    removeSecret: useMutation({ mutationFn: (provider: string) => withStepUp('voice.secret', provider, (h) => call<void>('DELETE', `/voice/providers/${enc(provider)}/secret`, undefined, h)), onSettled: settle }),
    check: useMutation({ mutationFn: (key: string) => call<VoiceEngine>('POST', `/voice/engines/${enc(key)}/check`, {}), onSettled: settle }),
    price: useMutation({ mutationFn: (v: { key: string; price: Partial<Pick<EnginePrice, 'text_in_per_m' | 'audio_out_per_m' | 'audio_tokens_per_s' | 'valid_until'>> & { next?: EnginePrice['next'] } }) => call<VoiceEngine>('PUT', `/voice/engines/${enc(v.key)}/price`, v.price), onSettled: settle }),
    sample: useMutation({ mutationFn: (v: { engine: string; voice: string; text?: string }) => call<{ file_id: string; seconds: number }>('POST', '/voice/sample', v), onSettled: () => qc.invalidateQueries({ queryKey: ['voice', 'meter'] }) }),
  };
}

// =============================================================================================== §32.6 the meter ==
export type VoiceMeter = {
  period: 'today' | 'month'; voice_usd: number; cap_usd: number | null; projected_usd: number;
  by_engine: Array<{ engine: string; usd: number; seconds: number; audio_tokens: number }>; by_persona: Array<{ persona: string; usd: number; seconds: number }>;
  talk_tokens: number; talk_usd_equiv: number; price_note_fa: string | null; updated_at: string;
};
export const useMeter = (period: 'today' | 'month') => useQuery({ queryKey: ['voice', 'meter', period], staleTime: 10_000, queryFn: () => served(call<VoiceMeter>('GET', `/voice/meter?period=${period}`)) });
/** The owner's cap: `owner.settings.voice.month_cap_usd` (null removes it). Nothing else raises it. */
export function useSaveCap() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { version: number; month_cap_usd: number | null }) => call<unknown>('PUT', '/owner/settings', { voice: { month_cap_usd: v.month_cap_usd } }, ifMatch(v.version)),
    onSettled: () => Promise.all([qc.invalidateQueries({ queryKey: ['voice'] }), qc.invalidateQueries({ queryKey: ['owner-settings'] })]),
  });
}
/** A price that changes within 14 days: the warning the app shows beside the meter. */
export function priceWarning(e: VoiceEngine, now = Date.now()): { days: number; from: string; text_in_per_m: number; audio_out_per_m: number } | null {
  const n = e.price.next;
  if (!n) return null;
  const days = Math.ceil((Date.parse(n.from) - now) / 86_400_000);
  return days >= 0 && days <= 14 ? { days, ...n } : null;
}

/** The unit of a dollar sum on the meter: cents show when small, so a few sentences are not «$0.00». */
export const dollars = (v: number | null | undefined) => (v == null ? '—' : `$${v.toLocaleString('en-US', { minimumFractionDigits: v !== 0 && Math.abs(v) < 1 ? 3 : 2, maximumFractionDigits: v !== 0 && Math.abs(v) < 1 ? 3 : 2 })}`);
