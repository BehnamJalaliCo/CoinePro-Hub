'use client';

// ⟨1.17⟩ Contract §34 and §35 (prompt 25): every order is a session the owner talks in; the home is his office with the canvas of companies
// and the links between them. Until the OpenAPI file is regenerated the shapes live here, written from §34/§35. A route that answers
// 404/405/501 is «not served yet» (the hub deploys after the panel): the hooks answer null and the pages fall back to what they had.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { call } from './v13';
import type { Schemas } from './client';
import { orderReport, type OrderReport, type OrderOut29, type Notification29, type Suggestion } from './v29';
import { notServed } from './v28';
import type { Turn } from './v32';

const enc = encodeURIComponent;
async function served<T>(p: Promise<T>): Promise<T | null> {
  try { return await p; } catch (e) { if (notServed(e)) return null; throw e; }
}
const listOf = <T,>(x: T[] | { items?: T[] } | null | undefined): T[] => (Array.isArray(x) ? x : x?.items ?? []);

// ============================================================================================= §35.2 shapes ==
export type Badge = 'your_turn' | 'ready' | 'stuck' | 'moving' | 'closed';
export type Pace = 'auto' | 'step';
export type ParticipantKind = 'holder' | 'person' | 'player';
export type Participant = { key: string; kind: ParticipantKind; title_fa: string; company: string | null };
export type TaskState = 'todo' | 'doing' | 'done' | 'dropped';
export type SessionTask = { id: string; n: number; title_fa: string; state: TaskState; by: 'owner' | 'agent'; who_fa: string | null; work_ref: string | null };
export type SessionBrief = { done_fa: string; now_fa: string; need_fa: string };
export type SessionCard = {
  ref: string; conversation_ref: string; title_fa: string;
  holder: { code: string; title_fa: string; company: string; company_fa: string } | null;
  badge: Badge; reason_fa: string; brief: SessionBrief; pace: Pace; participants: Participant[];
  tasks: { done: number; total: number }; opened_at: string; last_at: string; closed_at: string | null; hidden: boolean;
};
/** What §35.2 adds to `OrderReport`. */
export type SessionExtras = {
  session: { state: 'open' | 'closed'; badge: Badge; reason_fa: string; closed_at: string | null; hidden: boolean };
  brief: SessionBrief; tasks: SessionTask[]; participants: Participant[];
  pace?: Pace; talk_ref?: string | null; conversation_ref?: string | null;
  turn?: { question_fa: string; at: string; by: { kind: string; code: string; display_fa?: string | null }; who_fa: string } | null;
};
export type SessionReport = OrderReport & Partial<SessionExtras>;

export const BADGE: Record<Badge, { fa: string; tone: 'gold' | 'pos' | 'neg' | 'lapis' | 'silver'; rank: number; live?: boolean }> = {
  your_turn: { fa: 'نوبت تو', tone: 'gold', rank: 0, live: true },
  ready: { fa: 'آماده‌ی تأیید', tone: 'pos', rank: 1 },
  stuck: { fa: 'گیر کرده', tone: 'neg', rank: 2 },
  moving: { fa: 'در جریان', tone: 'lapis', rank: 3 },
  closed: { fa: 'بسته شد', tone: 'silver', rank: 4 },
};
export const PACE_FA: Record<Pace, string> = { auto: 'خودکار', step: 'با من' };
export const PLAYERS: Array<{ key: 'gpt' | 'gemini' | 'deepseek'; fa: string }> = [{ key: 'gpt', fa: 'جی‌پی‌تی' }, { key: 'gemini', fa: 'جمنای' }, { key: 'deepseek', fa: 'دیپ‌سیک' }];
export const LINK_KIND: Record<LinkKind, string> = { serves: 'خدمت میدهد', publishes: 'منتشر میکند', feeds: 'خوراک میدهد', sells: 'میفروشد', supports: 'پشتیبانی میکند' };

/** Newest first within a badge, the owner's turn first of all (§35.3). */
export const bySessionOrder = (a: SessionCard, b: SessionCard) => BADGE[a.badge].rank - BADGE[b.badge].rank || Date.parse(b.last_at) - Date.parse(a.last_at);

// ============================================================================================ §35.3 routes ==
export type SessionFilter = 'open' | 'closed' | 'all';
/** `GET /sessions?state=…`; null on a hub before §35. */
export const useSessions = (state: SessionFilter = 'open', limit = 100) => useQuery({
  queryKey: ['orders', 'sessions', state, limit], staleTime: 10_000,
  queryFn: async () => { const r = await served(call<SessionCard[] | { items: SessionCard[] }>('GET', `/sessions?state=${state}&limit=${limit}`)); return r ? listOf(r) : null; },
});

/** The session's whole record: the order's report with §35.2's additions. */
export const useOrderSession = (ref: string) => useQuery({
  queryKey: ['orders', 'report', ref], queryFn: () => orderReport(ref) as Promise<SessionReport | null>, staleTime: 8_000,
  refetchInterval: (q) => (q.state.data && q.state.data.session?.state !== 'closed' ? 15_000 : false),
});

/** The turns of a session's conversation come from §32; this is only the key a session page reads them by. */
export const sessionTalk = (r: SessionReport | null | undefined): string | null => r?.conversation_ref ?? r?.talk_ref ?? null;

export function useSessionActions(ref: string) {
  const qc = useQueryClient();
  const settle = () => Promise.all(['orders', 'office', 'home', 'talk'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  const o = `/orders/${enc(ref)}`;
  return {
    talk: useMutation({ mutationFn: () => call<{ conversation_ref: string }>('POST', `/orders/${enc(ref)}/talk`, {}), onSettled: settle }),
    addParticipant: useMutation({ mutationFn: (b: { kind: 'person' | 'player'; key: string }) => call<SessionReport>('POST', `/orders/${enc(ref)}/participants`, b), onSettled: settle }),
    removeParticipant: useMutation({ mutationFn: (key: string) => call<SessionReport>('DELETE', `/orders/${enc(ref)}/participants/${enc(key)}`), onSettled: settle }),
    addTask: useMutation({ mutationFn: (title_fa: string) => call<SessionTask>('POST', `/orders/${enc(ref)}/tasks`, { title_fa }), onSettled: settle }),
    patchTask: useMutation({
      mutationFn: (v: { id: string; title_fa?: string; state?: TaskState; n?: number }) => call<SessionTask>('PATCH', `/orders/${enc(ref)}/tasks/${enc(v.id)}`, { title_fa: v.title_fa, state: v.state, n: v.n }),
      // The tick shows at once; the hub's answer settles it.
      onMutate: (v) => {
        qc.setQueryData<SessionReport | null>(['orders', 'report', ref], (r) => (r?.tasks ? { ...r, tasks: r.tasks.map((t) => (t.id === v.id ? { ...t, ...(v.state ? { state: v.state } : {}), ...(v.title_fa ? { title_fa: v.title_fa } : {}) } : t)) } : r));
      },
      onSettled: settle,
    }),
    close: useMutation({ mutationFn: (v: { verdict: 'ok' | 'cancel'; note?: string }) => call<SessionReport>('POST', `/orders/${enc(ref)}/close`, v.note ? v : { verdict: v.verdict }, { 'Idempotency-Key': crypto.randomUUID() }), onSettled: settle }),
    reopen: useMutation({ mutationFn: () => call<SessionReport>('POST', `/orders/${enc(ref)}/reopen`, {}), onSettled: settle }),
    hide: useMutation({ mutationFn: () => call<SessionReport>('POST', `/orders/${enc(ref)}/hide`, {}), onSettled: settle }),
    unhide: useMutation({ mutationFn: () => call<SessionReport>('POST', `/orders/${enc(ref)}/unhide`, {}), onSettled: settle }),
    reply: useMutation({ mutationFn: (text: string) => call<SessionReport>('POST', `/orders/${enc(ref)}/reply`, { text }), onSettled: settle }),
    // §35.3 the owner switches «با من / خودکار» at any time
    pace: useMutation({ mutationFn: (pace: Pace) => call<SessionReport>('POST', `/orders/${enc(ref)}/pace`, { pace }), onSettled: settle }),
    path: o,
  };
}

/** A new order: it opens its session at once (`talk_ref` is always set from §35.1, `ref` is the session's key). */
export type OrderOut35 = OrderOut29 & { talk_ref?: string | null; pace?: Pace };
export const asSessionOut = (o: OrderOut29): OrderOut35 => o as OrderOut35;

// ======================================================================================= §35.4 the card kinds ==
export const SESSION_CARD_KINDS = ['delegate', 'budget', 'group', 'line'] as const;
/** The turn's `to`: a participant's key, or everyone (the holder then sums up). */
export type TurnTo = string | 'all';
export type TurnWithTo = Turn;

// ============================================================================================ §35.5 the office ==
export type OfficeMoney = { revenue_month_usd: number | null; spend_month_usd: number; budget_month_usd: number | null; line_fa: string };
export type Office = {
  sessions: SessionCard[]; approvals: Array<Schemas['Decision']>; approvals_total: number; money: OfficeMoney; critical: Notification29[]; suggestions: Suggestion[]; canvas: Canvas;
};
/** `GET /office`; null on a hub before §35 (the page then shows the older home). */
export const useOffice = () => useQuery({ queryKey: ['office'], staleTime: 15_000, queryFn: () => served(call<Office>('GET', '/office')) });

// ============================================================================================== §35.6 the canvas ==
export type LinkKind = 'serves' | 'publishes' | 'feeds' | 'sells' | 'supports';
export type CanvasNode = { code: string; name_fa: string; kind: 'holding' | 'company'; x: number | null; y: number | null; line_fa: string; open_sessions: number };
export type CompanyLink = { id: string; from: string; to: string; kind: LinkKind; purpose_fa: string; state: 'on' | 'off'; open_works: number; updated_at: string };
export type Canvas = { nodes: CanvasNode[]; links: CompanyLink[] };

export const useLinks = () => useQuery({ queryKey: ['links'], staleTime: 15_000, queryFn: () => served(call<Canvas>('GET', '/links')) });
export function useCanvasActions() {
  const qc = useQueryClient();
  const settle = () => Promise.all(['office', 'links'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    create: useMutation({ mutationFn: (b: { from: string; to: string; kind: LinkKind; purpose_fa: string }) => call<CompanyLink>('POST', '/links', b), onSettled: settle }),
    patch: useMutation({ mutationFn: (v: { id: string; kind?: LinkKind; purpose_fa?: string; state?: 'on' | 'off' }) => call<CompanyLink>('PATCH', `/links/${enc(v.id)}`, { kind: v.kind, purpose_fa: v.purpose_fa, state: v.state }), onSettled: settle }),
    place: useMutation({
      mutationFn: (v: { code: string; x: number; y: number }) => call<CanvasNode>('PUT', `/canvas/nodes/${enc(v.code)}`, { x: v.x, y: v.y }),
      // The node stays where the owner dropped it while the hub confirms.
      onMutate: (v) => {
        qc.setQueryData<Office | null>(['office'], (o) => (o ? { ...o, canvas: { ...o.canvas, nodes: o.canvas.nodes.map((n) => (n.code === v.code ? { ...n, x: v.x, y: v.y } : n)) } } : o));
      },
      onSettled: settle,
    }),
  };
}

/** Where a node with no stored place goes: evenly on a circle round the centre (the holding), the first at the top. Coordinates in 0..1. */
export function layoutNodes(nodes: CanvasNode[]): Array<CanvasNode & { px: number; py: number }> {
  const others = nodes.filter((n) => n.kind !== 'holding');
  const free = others.filter((n) => n.x == null || n.y == null);
  return nodes.map((n) => {
    if (n.kind === 'holding' && (n.x == null || n.y == null)) return { ...n, px: 0.5, py: 0.5 };
    if (n.x != null && n.y != null) return { ...n, px: n.x, py: n.y };
    const i = free.findIndex((f) => f.code === n.code);
    const a = (-Math.PI / 2) + (2 * Math.PI * i) / Math.max(1, free.length);
    return { ...n, px: 0.5 + 0.36 * Math.cos(a), py: 0.5 + 0.36 * Math.sin(a) };
  });
}
