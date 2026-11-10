/**
 * ⟨1.0.1⟩ Part C, the look (contract §55): what the redesigned screens read and send. The command sheet's order (one path: the
 * existing `POST /orders`, with the company the owner picked by its mark) and its «کارمند ۲۴ ساعته» routine from one sentence
 * (`POST /routines {sentence_fa, company}`, part A's route), the limits block of the treasury (`GET /treasury/limits`: the Claude
 * accounts as rings and today's meter), and the small readers the home and the notifications share. The shapes are the hub's own
 * (`apps/api/openapi/hq-api.v1.json`), typed here by hand.
 *
 * A hub before §55 does not have these routes: a read that answers 404/405 is null and its block is not shown (the older card stays);
 * a write that answers so hides its action from then on; a field it does not send is its default.
 */
import { useSyncExternalStore } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from './client';
import { call } from './v13';
import { notServed } from './v28';
import { sendOrder29, type OrderOut29 } from './v29';
import { served } from './v33';
import type { Pace } from './v34';
import type { SessionRoutine } from './v47';

// ============================================================================================ what an older hub lacks ==
export type Feature55 = 'routine';
const absent = new Set<Feature55>();
const listeners = new Set<() => void>();
function markAbsent(f: Feature55) {
  if (absent.has(f)) return;
  absent.add(f);
  for (const l of listeners) l();
}
const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };
/** A write route answered 404/405 (the hub is older): its entry is hidden from now on in this tab. */
export const useAbsent55 = (f: Feature55) => useSyncExternalStore(subscribe, () => absent.has(f), () => false);

// ==================================================================================================== C2.1 the command ==
export type CommandCompany = { code: string; name_fa: string };
/** The templates only fill the starting text; the path is the same one path. `{co}`: the picked companies, or nothing. */
export const TEMPLATES = [
  { key: 'reel', label: 'ریلز اینستاگرام', make: 'یک ریلز اینستاگرام بساز: ' },
  { key: 'motion', label: 'موشن‌گرافی', make: 'یک موشن‌گرافی بساز: ' },
] as const;
export type TemplateKey = (typeof TEMPLATES)[number]['key'];
/** «تریدیار», «تریدیار و پرو-چارت», «تریدیار، پرو-چارت و کوینه‌پرو اف‌ایکس». */
export const namesFa = (names: string[]): string => (names.length <= 1 ? names[0] ?? '' : `${names.slice(0, -1).join('، ')} و ${names[names.length - 1]}`);
/** «برای {شرکت} یک ریلز اینستاگرام بساز: »; with no company picked the holding decides, and the text names none. */
export const templateText = (key: TemplateKey, names: string[]): string => {
  const t = TEMPLATES.find((x) => x.key === key)!;
  return names.length ? `برای ${namesFa(names)} ${t.make}` : t.make;
};

/**
 * «باز کن»: the existing new-order call. One company: the order carries it (`company`). Several: the hub takes one company per
 * order, so the text names them all and the order goes to the holding, which spreads it. None: the holding decides.
 * A hub that does not know `company` on an order yet refuses the field (422): the order then goes with the company named in its text.
 */
export async function sendCommand(v: { text: string; companies: CommandCompany[]; pace: Pace }): Promise<OrderOut29> {
  const text = v.text.trim();
  const names = v.companies.map((c) => c.name_fa);
  const named = (t: string) => (names.length && !names.every((n) => t.includes(n)) ? `برای ${namesFa(names)}: ${t}` : t);
  if (v.companies.length !== 1) return sendOrder29({ text: named(text), source: 'text', pace: v.pace });
  try {
    return await call<OrderOut29>('POST', '/orders', { text, source: 'text', file_id: null, company: v.companies[0]!.code, pace: v.pace });
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 422 || !(e.fields?.company || e.fields?.pace)) throw e;
  }
  return sendOrder29({ text: named(text), source: 'text', pace: v.pace });
}

/** `POST /routines {sentence_fa, company}`: a «کارمند ۲۴ ساعته» from one sentence, on at once (no card, no passkey).
 *  `422`: the sentence is no routine, and `message_fa` says why. A hub before part A: the entry is hidden. */
export function useMakeCompanyRoutine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { sentence_fa: string; company: string | null; key: string }) => {
      try {
        return await call<SessionRoutine>('POST', '/routines', { sentence_fa: v.sentence_fa, ...(v.company ? { company: v.company } : {}) }, { 'Idempotency-Key': v.key });
      } catch (e) {
        if (notServed(e)) { markAbsent('routine'); return null; }
        throw e;
      }
    },
    onSuccess: () => { for (const k of ['orders', 'g31', 'routines']) void qc.invalidateQueries({ queryKey: [k] }); },
  });
}

// ============================================================================================== C3.6 the limits (§55.3) ==
export type AccountState = 'working' | 'ready' | 'full' | 'off';
/** `utilization`: the share of its window that is used, 0..1 (the hub writes a decimal; a string or a number), null when unknown. */
export type ClaudeAccount = {
  key: string; name_fa: string; state: AccountState; utilization?: number | string | null; window_fa?: string | null;
  resets_at?: string | null; observed_at?: string | null;
};
export type MeterState = 'calm' | 'warm' | 'near' | 'full';
/** Today's agent spend against the daily cap. `share`: spent / cap (it may pass 1). */
export type TodayMeter = { spent?: number; cap?: number; share?: number | string; state?: MeterState; resets_at: string; note_fa?: string };
export type Limits = { accounts?: ClaudeAccount[]; waiting?: boolean; today: TodayMeter };

/** A decimal of the hub's as a number; null when it is missing or not a number. */
export const num = (v: number | string | null | undefined): number | null => {
  if (v == null || v === '') return null;
  const n = typeof v === 'string' ? Number(v) : v;
  return Number.isFinite(n) ? n : null;
};

/** `GET /treasury/limits`; null on a hub before §55 (the block is hidden and the older quota card stays). Read again every minute. */
export const useLimits = () => useQuery({
  queryKey: ['treasury', 'limits'], staleTime: 30_000, refetchInterval: 60_000,
  queryFn: () => served(call<Limits>('GET', '/treasury/limits')),
});

/** «۲ ساعت و ۱۰ دقیقه دیگر», «۴۰ دقیقه دیگر», «کمتر از یک دقیقه دیگر»; null once the moment has passed. A count in a sentence. */
export function inFa(iso: string | null | undefined, now = Date.now()): string | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - now;
  if (!Number.isFinite(ms) || ms <= 0) return null;
  const m = Math.round(ms / 60_000);
  if (m < 1) return 'کمتر از یک دقیقه دیگر';
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (!h) return `${m} دقیقه دیگر`;
  if (h >= 24) { const d = Math.floor(h / 24); const hh = h % 24; return hh ? `${d} روز و ${hh} ساعت دیگر` : `${d} روز دیگر`; }
  return r ? `${h} ساعت و ${r} دقیقه دیگر` : `${h} ساعت دیگر`;
}
/** The earliest reset among the accounts that are full: when the queue moves again. */
export const queueOpensAt = (l: Limits): string | null => {
  const full = (l.accounts ?? []).filter((a) => a.state === 'full' && a.resets_at).map((a) => a.resets_at!) ;
  return full.length ? full.sort()[0]! : null;
};

// ============================================================================================ C3.1 the pulse's series ==
/** A 24-hour series for each figure of the office pulse, oldest first, when the hub's live summary carries one. */
export type PulseSeries = { working?: number[] | null; sessions?: number[] | null; waiting?: number[] | null; until?: string | null };
export const pulseSeries = (summary: unknown): PulseSeries | null => {
  const s = (summary && typeof summary === 'object' ? (summary as { series?: unknown }).series : null);
  return s && typeof s === 'object' ? (s as PulseSeries) : null;
};

// ======================================================================================= C2.2 / C3 the ready answers ==
export const DECIDE_YOURSELF_FA = 'خودت تصمیم بگیر و ادامه بده';
const QUOTED = /«([^«»]{1,80})»/g;
/**
 * The two or three answers a question offers by itself: the hub's quick replies when the report carries them; else, for a question
 * that names two or three options with «یا», those options (the quoted ones first: «الف»، «ب» یا «پ»). Nothing for an open question.
 */
export function readyAnswers(question: string | null | undefined, quick?: Array<string | { label_fa?: string; text?: string }> | null): string[] {
  const given = (quick ?? []).map((q) => (typeof q === 'string' ? q : q.label_fa ?? q.text ?? '')).map((x) => x.trim()).filter(Boolean);
  if (given.length) return given.slice(0, 3);
  const q = (question ?? '').trim();
  if (!q || !/\sیا\s/.test(q)) return [];
  const quoted = [...q.matchAll(QUOTED)].map((m) => m[1]!.trim()).filter(Boolean);
  if (quoted.length >= 2 && quoted.length <= 3) return quoted;
  // «امروز منتشر کنم یا فردا صبح؟» → the clause around «یا», cut at the sentence marks before it.
  const tail = q.replace(/[؟?.!]+\s*$/, '').split(/[:؛\n]|[؟?.!]\s/).pop() ?? '';
  const parts = tail.split(/\s+یا\s+|،\s*/).map((x) => x.trim()).filter(Boolean);
  return parts.length >= 2 && parts.length <= 3 && parts.every((p) => p.length <= 48) ? parts : [];
}
