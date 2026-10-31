// Contract §27 ⟨1.9⟩, the Android app's core/data/Players.kt: who plays an order (the router, Claude, or a substitute seat of §21.13) and
// the council of models. Pure: the owner's choice and the wire fields, a player's availability from `GET /substitutes`, the players a voice
// order names, and applying the owner's choice to the works a voice order made.

import { call } from '@/lib/api/v13';
import { ifMatch } from '@/lib/api/v15';
import type { OrderOut } from '@/lib/api/v13';
import type { Substitute } from '@/lib/api/v18';

export type PlayerKey = 'auto' | 'claude' | 'gpt' | 'gemini' | 'deepseek' | 'council';
/** One choice of «با کدام مدل؟». [player] and [mode] are what goes on the wire; [provider] picks the logo (null: the router's glyph). */
export type PlayerOption = { key: PlayerKey; fa: string; provider: string | null; player: 'auto' | 'claude' | 'gpt' | 'gemini' | 'deepseek'; mode: 'single' | 'council'; substitute: boolean };
export const PLAYER_OPTIONS: PlayerOption[] = [
  { key: 'auto', fa: 'خودکار', provider: null, player: 'auto', mode: 'single', substitute: false },
  { key: 'claude', fa: 'Claude', provider: 'anthropic', player: 'claude', mode: 'single', substitute: false },
  { key: 'gpt', fa: 'GPT', provider: 'openai', player: 'gpt', mode: 'single', substitute: true },
  { key: 'gemini', fa: 'Gemini', provider: 'google', player: 'gemini', mode: 'single', substitute: true },
  { key: 'deepseek', fa: 'DeepSeek', provider: 'deepseek', player: 'deepseek', mode: 'single', substitute: true },
  { key: 'council', fa: 'شورای مدل‌ها', provider: null, player: 'auto', mode: 'council', substitute: false },
];
export const optionOf = (key: PlayerKey) => PLAYER_OPTIONS.find((o) => o.key === key) ?? PLAYER_OPTIONS[0]!;
/** The option a work carries; an unknown player (a newer hub) reads as the router's. */
export const optionOfWork = (player?: string | null, mode?: string | null): PlayerOption =>
  mode === 'council' ? optionOf('council') : PLAYER_OPTIONS.find((o) => o.key === player && o.key !== 'council') ?? PLAYER_OPTIONS[0]!;

/** Whether a player can take an order now, and if not why, in the owner's words; chosen anyway, the run waits up to 30 minutes for it. */
export type Availability = { ok: boolean; stateFa?: string; reasonFa?: string };
/**
 * A player's availability from `GET /substitutes` (§21.13): the router and Claude always play. A substitute plays when it is `ready` and
 * signed in where its seats run (the CLI's sign-in for a player with a runner, the signed-in browser profile otherwise). Signed out,
 * `limited`, `off` or `error` greys it with the reason. Unknown (taken as available) while the list loads.
 */
export function availabilityOf(o: PlayerOption, subs: Substitute[] | null | undefined): Availability {
  if (!o.substitute || !subs) return { ok: true };
  const s = subs.find((x) => x.player === o.key);
  if (!s) return { ok: false, stateFa: 'تعریف نشده', reasonFa: 'این بازیکن روی هاب وصل نشده است.' };
  if (s.status === 'limited') return { ok: false, stateFa: 'محدود', reasonFa: s.status_reason ?? 'سقف امروزش پر شده؛ تا ریست صبر میکند.' };
  if (s.status === 'off') return { ok: false, stateFa: 'خاموش', reasonFa: s.status_reason ?? 'خاموش است.' };
  if (s.status === 'error') return { ok: false, stateFa: 'خطا', reasonFa: s.status_reason ?? 'آخرین فراخوانی‌اش خطا داد.' };
  const signedIn = (s.runner != null && s.login?.state === 'signed_in') || s.web?.state === 'signed_in';
  return signedIn ? { ok: true } : { ok: false, stateFa: 'خارج', reasonFa: s.status_reason ?? 'از حسابش خارج است؛ ورود دوباره با مالک است.' };
}

/** The players a council would seat now (§27.2): Claude, then every substitute that is available. */
export const councilSeats = (subs: Substitute[] | null | undefined): PlayerOption[] =>
  [optionOf('claude'), ...(['gpt', 'gemini', 'deepseek'] as const).map(optionOf).filter((o) => !!subs && availabilityOf(o, subs).ok)];

const fa = (n: number) => n.toLocaleString('fa-IR');
/** What the chosen option means, in one sentence. */
export function optionNoteFa(o: PlayerOption, a: Availability, seats: number): string {
  if (o.key === 'auto') return 'مسیریاب مدل برای هر قدم خودش انتخاب میکند، مثل همیشه.';
  if (o.key === 'claude') return 'همه‌ی فراخوانی‌های مدل این کار با مدل‌های Claude.';
  if (o.key === 'council') return `همان شرح، جدا از هم، به Claude و هر بازیکن آماده (الان ${fa(seats)} بازیکن) میرود؛ Claude جمع‌بندی مینویسد: کجا هم‌نظرند، کجا نه و چرا، و پیشنهاد. یک پاکت بودجه برای همه.`;
  if (!a.ok) return `${o.fa} الان ${a.stateFa}: ${a.reasonFa} کار تا ۳۰ دقیقه منتظرش میماند و بعد خودکار میشود؛ اعلانش میاید.`;
  return `هر فراخوانی مدل این کار به ${o.fa} میرود، در سقف روزانه‌ی جایگاهش و با همان پوشاندن داده‌ها.`;
}

// ---------------------------------------------------------------------------------------------------------------- voice --
/** What a voice order named: the option and the words that named it («با جمنای»). */
export type Recognised = { option: PlayerOption; phrase: string };

/** Persian as the phone and the hub write it: Arabic ي/ك as ی/ک, the tatweel gone, one space. */
export const normaliseFa = (s: string) => s.replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/ـ/g, '').replace(/[ \t\n]+/g, ' ').trim();

/** A gap inside a word as it may be written: a half-space, a space or nothing. */
const G = '[‌ ]?';
const COUNCIL_WORDS = [
  new RegExp(`شورای?${G}مدل${G}ها`), /شورای مدل/, /(^| )شورا($| |[،,.؟!:؛])/, new RegExp(`همه${G}ی?${G}مدل${G}ها`), /با هم مشارکت کن/,
  /با هم (بسازن|بنویسن|انجام بدن|کار کنن)/, /\bcouncil\b/i,
];
const PLAYER_WORDS: Array<[PlayerKey, RegExp]> = [
  ['gpt', new RegExp(`(چت${G})?جی${G}پی${G}تی|chat${G}gpt|\\bgpt\\b`, 'i')],
  ['gemini', /جمنای|جمینای|جیمنای|جیمینای|جمینی|جمنی|\bgemini\b/i],
  ['deepseek', new RegExp(`دیپ${G}سیک|\\bdeep${G}seek\\b`, 'i')],
  ['claude', /کلود|کلاد|\bclaude\b/i],
];

/**
 * The player a voice order names (§27.1: «با جی‌پی‌تی / با جمنای / با دیپ‌سیک / شورا»): the council when the order asks the models
 * together, otherwise the first player named (with «با» before it when said so). Null when the order names none: the router plays.
 */
export function recogniseOption(text: string): Recognised | null {
  const t = normaliseFa(text);
  if (!t) return null;
  for (const re of COUNCIL_WORDS) {
    const m = re.exec(t);
    if (m) return { option: optionOf('council'), phrase: m[0].replace(/^[ ،,.؟!:؛]+|[ ،,.؟!:؛]+$/g, '') };
  }
  let best: { key: PlayerKey; index: number; value: string } | null = null;
  for (const [key, re] of PLAYER_WORDS) {
    const m = re.exec(t);
    if (m && (!best || m.index < best.index)) best = { key, index: m.index, value: m[0] };
  }
  if (!best) return null;
  const before = t.slice(0, best.index).trimEnd();
  const phrase = before.endsWith(' با') || before === 'با' ? `با ${best.value}` : best.value;
  return { option: optionOf(best.key), phrase: phrase.trim() };
}

/**
 * A voice order goes as words (`POST /orders`): the hub reads «با جمنای» from them. When the owner's choice differs from what the hub set
 * on a work the order made, that work is changed to it (`PATCH /work/{id}` with `player` and `mode`, §27.1). Returns how many changed;
 * a work that cannot be read or changed is left as the hub made it.
 */
export async function applyPlayer(order: OrderOut, o: PlayerOption): Promise<number> {
  let changed = 0;
  for (const r of order.routes) {
    if (r.kind !== 'work' || !r.work_ref) continue;
    try {
      const w = await call<{ id: string; version: number; player?: string | null; mode?: string | null }>('GET', `/work/${encodeURIComponent(r.work_ref)}`);
      if ((w.player ?? 'auto') === o.player && (w.mode ?? 'single') === o.mode) continue;
      await call<unknown>('PATCH', `/work/${encodeURIComponent(w.id)}`, { player: o.player, mode: o.mode }, ifMatch(w.version));
      changed++;
    } catch { /* left as the hub made it */ }
  }
  return changed;
}
