'use client';

// ⟨1.11⟩ Contract §29 (prompt 21): the owner sees the business. Every order answered (its report, its blockers and their one-tap fixes),
// the holding's secretary (one line before an order goes), long voice through the hub's STT in chunks, the owner's rules, the council v2
// (a plan with «اجرا کن», each player's role, the fact pack), each company's readiness for a working group, the working groups, the
// connections, the owner's home (three cards, the morning, the groups' KPIs, the orders, only critical items) and each employee's state.
// Until the OpenAPI file is regenerated the shapes live here, written from §29; the same conventions as the typed client.
// The hub deploys §29 after the panel: a route that answers 404/405/501 is «not served yet» and every screen says so calmly.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { stepUp } from '@/lib/auth';
import { ApiError, isMock, type Problem } from './client';
import { handled, observed } from './observe';
import { call } from './v13';
import type { Finding } from './v14';
import type { Notification } from './v21';
import { notServed, type Council } from './v28';

const enc = encodeURIComponent;
type Actor = { kind: string; code: string; display_fa?: string | null };

/** [p]'s value, or null when the hub does not serve the route yet (404/405/501, kept out of «خطاخوان»). */
async function served<T>(p: Promise<T>): Promise<T | null> {
  try { return await p; } catch (e) { if (notServed(e)) return null; throw e; }
}
/** A list the hub may send bare or as a page. */
const listOf = <T,>(x: T[] | { items?: T[] } | null | undefined): T[] => (Array.isArray(x) ? x : x?.items ?? []);

// ============================================================================================ §29.1 domains ==
export type Domain = 'business' | 'media' | 'revenue' | 'product' | 'tech' | 'security' | 'infra';
export const TECH_DOMAINS: Domain[] = ['tech', 'infra', 'security'];
export const DOMAIN_FA: Record<Domain, string> = {
  business: 'کسب‌وکار', media: 'رسانه', revenue: 'درآمد', product: 'محصول', tech: 'فنی', security: 'امنیت', infra: 'زیرساخت',
};
export type CriticalReason = 'data_leak' | 'product_down' | 'money' | 'legal';
export const CRITICAL_FA: Record<CriticalReason, string> = { data_leak: 'نشت داده', product_down: 'محصول از دسترس خارج شد', money: 'پول', legal: 'حقوقی' };
/** What §29.1 adds to every finding, notification and card. */
export type Routed = { domain?: Domain | null; owner_visible?: boolean | null; routed_to?: string | null; critical_reason?: CriticalReason | null };
export type Notification29 = Notification & Routed;
export type Finding29 = Finding & Routed;

// =============================================================================================== fixes ==
/** A one-tap fix: of a blocker (§29.2), a readiness check (§29.9) or a stuck employee (§29.14). Extra fields (e.g. `tokens`) travel with it. */
export type Fix = { action: string; label_fa: string; target: string | null; tokens?: number | null; [k: string]: unknown };

/** Where a fix is done inside the panel instead of on the hub: a guide to open, a card to seal, the release switches. */
export type LocalFix = { kind: 'guide'; connection: string; company: string | null } | { kind: 'go'; href: string };
const DECISION_REF = /^D-\d+$/;
/** Fixes the panel does itself (the hub's route is not the place for them): §29.2's `connection.guide`, a card to seal, a lock to open. */
export function localFix(f: Fix, company?: string | null): LocalFix | null {
  const t = f.target?.trim() ?? '';
  if (f.action === 'connection.guide') {
    // The target names the kind, alone or after its company («TY/instagram»).
    const [a, b] = t.includes('/') ? t.split('/', 2) : [company ?? null, t];
    return { kind: 'guide', connection: (b ?? '').trim(), company: a ? a.trim() : company ?? null };
  }
  if ((f.action === 'series.seal' || f.action === 'card.seal') && DECISION_REF.test(t)) return { kind: 'go', href: `/cartable?ref=${t}` };
  if (f.action === 'lock.open') return { kind: 'go', href: company ? `/companies/${enc(company)}` : '/control' };
  if (f.action === 'series.propose' && !t) return { kind: 'go', href: '/media/series' };
  return null;
}

/** A fix that the hub may want sealed: tried as it is, then once more behind the passkey when the hub answers `step_up_required`. */
async function withStepUp<T>(action: string, target: string, run: (headers?: Record<string, string>) => Promise<T>): Promise<T> {
  try { return await run(); } catch (e) {
    if (!(e instanceof ApiError && e.status === 403 && e.code === 'step_up_required')) throw e;
    handled(e);
    return run({ 'X-Step-Up': await stepUp(action, target) });
  }
}
const fixBody = (f: Fix) => {
  const { label_fa: _label, ...rest } = f;
  return rest;
};

// ===================================================================================== §29.2 the order report ==
export type OrderState = 'received' | 'planned' | 'in_progress' | 'waiting' | 'blocked' | 'delivered' | 'failed' | 'cancelled';
export const ORDER_STATE: Record<OrderState, { fa: string; tone: 'neutral' | 'gold' | 'pos' | 'neg' | 'warn' | 'lapis' | 'silver'; live?: boolean }> = {
  received: { fa: 'رسید', tone: 'lapis' }, planned: { fa: 'برنامه دارد', tone: 'lapis' }, in_progress: { fa: 'در جریان', tone: 'gold', live: true },
  waiting: { fa: 'منتظر', tone: 'warn' }, blocked: { fa: 'گیر کرده', tone: 'neg' }, delivered: { fa: 'تحویل شد', tone: 'pos' },
  failed: { fa: 'ناموفق', tone: 'neg' }, cancelled: { fa: 'لغو شد', tone: 'silver' },
};
export const ENDED_ORDER: ReadonlySet<string> = new Set(['delivered', 'failed', 'cancelled']);
export type OutputKind = 'post' | 'reel' | 'story' | 'article' | 'report' | 'plan' | 'code' | 'answer' | 'other';
export const OUTPUT_KIND_FA: Record<OutputKind, string> = {
  post: 'پست', reel: 'ریلز', story: 'استوری', article: 'مقاله', report: 'گزارش', plan: 'برنامه', code: 'تغییر نرم‌افزار', answer: 'پاسخ', other: 'خروجی',
};
export type BlockerKind = 'no_employee' | 'hiring_closed' | 'locked' | 'series_unsealed' | 'budget' | 'player_down' | 'connection_missing' | 'no_progress' | 'talk_loop';
export const BLOCKER_ICON: Record<BlockerKind, 'agent' | 'lock' | 'send' | 'treasury' | 'model' | 'globe' | 'time' | 'refresh'> = {
  no_employee: 'agent', hiring_closed: 'agent', locked: 'lock', series_unsealed: 'send', budget: 'treasury', player_down: 'model',
  connection_missing: 'globe', no_progress: 'time', talk_loop: 'refresh',
};
export type Blocker = { kind: BlockerKind; title_fa: string; detail_fa: string; since: string; fix: Fix | null };
export type OrderRouteFields = { companies: string[]; department: string | null; collaborators: string[]; output_kind: OutputKind; budget_tokens: number; mode: 'single' | 'council'; player: string };
export type OrderReport = {
  ref: string; text_fa: string; at: string; state: OrderState;
  ack: { at: string; by: Actor; plan_fa: string; assigned: Array<{ company: string; code: string; title_fa: string }>; due_at: string | null } | null;
  route: OrderRouteFields | null;
  steps: Array<{ at: string; who_fa: string; what_fa: string }>;
  blockers: Blocker[]; outputs: Array<{ ref: string; title_fa: string; kind: string }>;
  summary: { done_fa: string; left_fa: string; need_fa: string } | null; updated_at: string;
};

export async function orderReport(ref: string): Promise<OrderReport | null> {
  try { return await call<OrderReport>('GET', `/orders/${enc(ref)}/report`); } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 405 || e.status === 501)) { handled(e); return null; }
    throw e;
  }
}
/** The report, live: the stream's `order.report` reads it again (`order.` refreshes `orders`); while it moves, a quiet look every 20 s. */
export const useOrderReport = (ref: string) =>
  useQuery({
    queryKey: ['orders', 'report', ref], queryFn: () => orderReport(ref), staleTime: 10_000,
    refetchInterval: (q) => (q.state.data && !ENDED_ORDER.has(q.state.data.state) ? 20_000 : false),
  });

/** `POST /orders/{ref}/fix {action, target}` (and `tokens` for `budget.add`); sealed when the hub asks for it. */
export function useOrderFix(ref: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (f: Fix) => withStepUp(f.action, f.target ?? ref, (h) => call<OrderReport | { ok?: boolean } | undefined>('POST', `/orders/${enc(ref)}/fix`, fixBody(f), h)),
    onSettled: () => Promise.all(['orders', 'home', 'work', 'employees'].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}

/** The owner's orders with ⟨1.11⟩ `state` and `summary` (`GET /orders`). */
export type OrderItem = { ref: string; text: string; text_fa?: string | null; source: 'voice' | 'text'; created_at: string; state?: OrderState | null; summary?: string | { done_fa?: string } | null; summary_fa?: string | null };
export const orderSummaryFa = (o: Pick<OrderItem, 'summary' | 'summary_fa'>): string | null =>
  (typeof o.summary === 'string' ? o.summary : o.summary?.done_fa) || o.summary_fa || null;
export const useOrderItems = () => useQuery({ queryKey: ['orders', 'items'], queryFn: async () => listOf(await call<OrderItem[] | { items: OrderItem[] }>('GET', '/orders')), staleTime: 15_000 });

// ===================================================================================== §29.4 the secretary ==
export type Route = OrderRouteFields & { count: number | null; preview_fa: string; confidence: number; why_fa: string };
/** One line before an order goes; null on a hub without the secretary (the order then goes as before). */
export const previewOrder = (text: string, source: 'voice' | 'text') => served(call<Route>('POST', '/orders/preview', { text, source }));
export type OrderOut29 = { ref: string; summary_fa: string; routes: Array<{ company: string; to: string; kind: 'work' | 'code' | 'meeting' | 'question'; work_ref?: string; session_ref?: string; decision_ref?: string }> };
/** `POST /orders {text, source, file_id?, route?}`: with the (possibly edited) preview the hub follows it exactly. */
export const sendOrder29 = (b: { text: string; source: 'voice' | 'text'; file_id?: string | null; route?: Omit<Route, 'preview_fa' | 'confidence' | 'why_fa'> | null }) =>
  call<OrderOut29>('POST', '/orders', { text: b.text, source: b.source, file_id: b.file_id ?? null, ...(b.route ? { route: b.route } : {}) });

/** «400 هزار», «1.2 میلیون»: a budget in plain words (the owner reads «واحد مصرف», never tokens). Latin digits. */
export function unitsFa(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  const a = Math.abs(n);
  if (a >= 1_000_000) return `${(n / 1_000_000).toFixed(a >= 10_000_000 ? 0 : 1).replace(/\.0$/, '')} میلیون`;
  if (a >= 1_000) return `${Math.round(n / 1_000)} هزار`;
  return String(Math.round(n));
}

// ===================================================================================== §29.5 long voice ==
export type SttPurpose = 'order' | 'rule' | 'message' | 'note';
export type SttResult = { text: string; duration_s: number; chunks: number; segments?: Array<{ start_s: number; end_s: number; text: string }> };
const mockHandle = isMock ? async (r: Request) => (await import('@/lib/api/mock-v21')).handle(r) : undefined;
const send = observed(mockHandle ?? ((r: Request) => globalThis.fetch(r)));

/** `POST /transcribe/sessions {purpose}` → its id; null on a hub without sessions. */
export const openSttSession = async (purpose: SttPurpose) => (await served(call<{ id: string }>('POST', '/transcribe/sessions', { purpose })))?.id ?? null;
/** `PUT /transcribe/sessions/{id}/chunks/{n}`: one piece of raw audio (≤ 90 s), idempotent per n. */
export async function putSttChunk(id: string, n: number, audio: Blob, signal?: AbortSignal): Promise<void> {
  const h = new Headers({ 'X-HQ-Client': 'web', Accept: 'application/json', 'Content-Type': audio.type || 'audio/webm' });
  // In the demo the fixtures read JSON; the bytes stay in the page.
  const body: BodyInit = isMock ? JSON.stringify({ size: audio.size, type: audio.type }) : audio;
  let res: Response;
  try {
    res = await send(new Request(new URL(`/api/v1/transcribe/sessions/${enc(id)}/chunks/${n}`, window.location.origin), { method: 'PUT', headers: h, body, credentials: 'same-origin', signal }));
  } catch (e) {
    throw signal?.aborted ? e : new ApiError(0, undefined);
  }
  if (!res.ok) {
    let p: Partial<Problem> | undefined;
    try { p = (await res.json()) as Partial<Problem>; } catch { /* not JSON */ }
    throw new ApiError(res.status, { ...p, request_id: p?.request_id ?? res.headers.get('X-Request-Id') });
  }
}
export const finishSttSession = (id: string) => call<SttResult>('POST', `/transcribe/sessions/${enc(id)}/finish`, {});

// ===================================================================================== §29.3 the owner's rules ==
export type AppliesTo = 'all' | 'overseer' | { roles: string[] } | { companies: string[] };
export type Rule = {
  id?: string; ref: string; text_md: string; text?: string | null; source: 'voice' | 'text'; file_id?: string | null; applies_to: AppliesTo;
  status: 'proposed' | 'sealed' | 'retired'; version: number; sealed_at: string | null; created_at: string;
  counts?: { applied?: number | null; runs?: number | null; violations?: number | null; fixed?: number | null } | null;
  first_report_at?: string | null;
};
/** «همه‌ی نقش‌ها», «ناظر کل», the roles or the companies by name. */
export function appliesFa(a: AppliesTo | null | undefined, names?: (code: string) => string): string {
  if (!a || a === 'all') return 'همه‌ی نقش‌ها';
  if (a === 'overseer') return 'ناظر کل';
  if ('companies' in a) return a.companies.map((c) => names?.(c) ?? c).join('، ');
  return a.roles.map(roleFa).join('، ');
}
const ROLE_FA: Record<string, string> = {
  ceo: 'مدیرعامل‌ها', cto: 'مدیرهای فنی', sre: 'مهندس‌های پایداری', media_director: 'مدیرهای رسانه', content_lead: 'مدیرهای محتوا', writer: 'نویسنده‌ها',
  scriptwriter: 'سناریست‌ها', visual_designer: 'طراح‌ها', motion_designer: 'طراح‌های موشن', publisher: 'مسئول‌های انتشار', analyst: 'تحلیلگرها',
};
export const roleFa = (r: string) => ROLE_FA[r] ?? r;

export const useRules = () =>
  useQuery({
    queryKey: ['rules'], staleTime: 15_000,
    // A hub before §29.3 keeps the same records as the overseer's standing orders.
    queryFn: async () => {
      const r = await served(call<Rule[] | { items: Rule[] }>('GET', '/rules'));
      if (r) return listOf(r);
      return listOf(await call<Rule[] | { items: Rule[] }>('GET', '/oversight/orders'));
    },
  });
export function useRuleActions() {
  const qc = useQueryClient();
  const done = () => Promise.all(['rules', 'oversight', 'home'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    /** `POST /rules {text, source, file_id?}` → a proposed rule in one clear imperative. */
    create: useMutation({
      mutationFn: async (b: { text: string; source: 'voice' | 'text'; file_id?: string | null }) =>
        (await served(call<Rule>('POST', '/rules', { text: b.text, source: b.source, file_id: b.file_id ?? null })))
        ?? call<Rule>('POST', '/oversight/orders', { text_md: b.text, source: b.source, file_id: b.file_id ?? null, applies_to: 'all' }),
      onSettled: done,
    }),
    /** One tap, sealed with the passkey (🔏 the standing order's own seal). */
    seal: useMutation({ mutationFn: async (ref: string) => call<Rule>('POST', `/oversight/orders/${enc(ref)}/seal`, {}, { 'X-Step-Up': await stepUp('oversight.order', ref) }), onSettled: done }),
    /** `PUT /rules/{ref}`: a new version, sealed. */
    edit: useMutation({ mutationFn: async (v: { ref: string; text: string }) => call<Rule>('PUT', `/rules/${enc(v.ref)}`, { text: v.text }, { 'X-Step-Up': await stepUp('rule.seal', v.ref) }), onSettled: done }),
    retire: useMutation({
      mutationFn: async (ref: string) => (await served(call<Rule>('POST', `/rules/${enc(ref)}/retire`, {}))) ?? call<Rule>('POST', `/oversight/orders/${enc(ref)}/retire`, {}),
      onSettled: done,
    }),
  };
}

// ===================================================================================== §29.8 the council v2 ==
export type FactPack = {
  company: string; at: string; figures: Array<{ key: string; title_fa: string; value: number | string; source: string; at: string }>;
  recent_posts?: Array<{ title_fa?: string | null; at?: string | null; kind?: string | null; reach?: number | null }> | null; notes_fa?: string | null;
};
export type Council29 = Council & { round?: 1 | 2 | 3 | null; roles?: Record<string, string> | null; fact_pack_ref?: string | null; fact_pack?: FactPack | null; plan_md?: string | null };
const COUNCIL_ROLE_FA: Record<string, string> = {
  captain: 'کاپیتان', researcher: 'پژوهشگر با منبع', numbers: 'عدد و منطق', devil: 'مخالف خلاق', devils_advocate: 'مخالف خلاق', critic: 'مخالف خلاق',
};
export const councilRoleFa = (r: string) => COUNCIL_ROLE_FA[r] ?? r;
export const ROUND_FA: Record<1 | 2 | 3, string> = { 1: 'دور ۱ از ۳: پیشنهادها', 2: 'دور ۲ از ۳: نقد پیشنهادها', 3: 'دور ۳ از ۳: برنامه‌ی کاپیتان' };
/** Where a figure came from, in words. */
export const sourceFa = (s: string) => CONNECTION_FA[s as ConnectionKind] ?? SOURCE_FA[s] ?? s;
const SOURCE_FA: Record<string, string> = { hub: 'داده‌ی ستاد', revenue: 'درآمد', treasury: 'خزانه', support: 'پشتیبانی', manual: 'ثبت دستی', council: 'شورای مشاوران', group: 'کارگروه', advisor: 'مشاور کل' };

// ===================================================================================== §29.9 readiness ==
export type Check = { key: string; ok: boolean; title_fa: string; detail_fa: string; fix: Fix | null };
export type Readiness = { company: string; group: string; ready: boolean; checks: Check[] };
export const useReadiness = (code: string | null, group: string) =>
  useQuery({
    queryKey: ['groups', 'readiness', code, group], enabled: !!code, staleTime: 20_000,
    queryFn: () => served(call<Readiness>('GET', `/companies/${enc(code!)}/readiness?group=${enc(group)}`)),
  });
/**
 * A failed check's fix on the hub. §29.9 names the actions but no route; the panel asks `POST /companies/{code}/readiness/fix
 * {group, action, target}` (the order report's own shape), sealed when the hub asks. null: the hub does not do it yet.
 */
export function useReadinessFix(code: string, group: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (f: Fix) => served(withStepUp(f.action, f.target ?? code, (h) => call<Readiness | undefined>('POST', `/companies/${enc(code)}/readiness/fix`, { group, ...fixBody(f) }, h))),
    onSettled: () => Promise.all(['groups', 'employees', 'connections', 'home'].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}

// ===================================================================================== §29.11 working groups ==
export type Routine = { key: string; title_fa: string; seat: string; schedule: string; brief_md: string; max_tokens: number; state: 'on' | 'paused' };
export type Group = {
  key: string; title_fa: string; purpose_fa: string; seats: Array<{ seat: string; role: string; title_fa: string; count: number }>; routines: Routine[];
  kpis: Array<{ key: string; title_fa: string; unit: string; source: string }>; connections: string[]; eligible: 'has_channel' | 'all'; state: 'on' | 'off';
  members?: Membership[] | null;
};
export type Membership = { group: string; company: string; state: 'on' | 'paused'; joined_at: string; seats: Array<{ seat: string; employee: string | null }> };
export type RoutineRun = { id: string; group: string; company: string; routine: string; at: string; work_ref: string | null; state: 'queued' | 'done' | 'failed' | 'skipped'; note_fa: string };
export const RUN_STATE: Record<RoutineRun['state'], { fa: string; tone: 'neutral' | 'pos' | 'neg' | 'silver' }> = {
  queued: { fa: 'در صف', tone: 'neutral' }, done: { fa: 'انجام شد', tone: 'pos' }, failed: { fa: 'ناموفق', tone: 'neg' }, skipped: { fa: 'رد شد', tone: 'silver' },
};
export type Experiment = { id: string; group: string; company: string; week: string; hypothesis_fa: string; metric: string; target: number | string; result: number | string | null; kept: boolean | null };
export type KpiPoint = { day: string; value: number | null };
export type KpiSeries = { company: string; key: string; title_fa?: string | null; unit?: string | null; series: KpiPoint[] };

export const useGroups = () => useQuery({ queryKey: ['groups', 'list'], staleTime: 30_000, queryFn: async () => { const r = await served(call<Group[] | { items: Group[] }>('GET', '/groups')); return r ? listOf(r) : null; } });
export const useGroup = (key: string) => useQuery({ queryKey: ['groups', 'one', key], staleTime: 30_000, queryFn: () => served(call<Group>('GET', `/groups/${enc(key)}`)) });
export const useGroupMembers = (key: string) =>
  useQuery({ queryKey: ['groups', 'members', key], staleTime: 20_000, queryFn: async () => listOf(await call<Membership[] | { items: Membership[] }>('GET', `/groups/${enc(key)}/members`)) });
export const useGroupRuns = (key: string, company: string | null) =>
  useQuery({ queryKey: ['groups', 'runs', key, company], staleTime: 20_000, queryFn: async () => listOf(await call<RoutineRun[] | { items: RoutineRun[] }>('GET', `/groups/${enc(key)}/runs${company ? `?company=${enc(company)}` : ''}`)) });
export const useExperiments = (key: string, company: string | null) =>
  useQuery({ queryKey: ['groups', 'experiments', key, company], staleTime: 30_000, queryFn: async () => listOf(await call<Experiment[] | { items: Experiment[] }>('GET', `/groups/${enc(key)}/experiments${company ? `?company=${enc(company)}` : ''}`)) });

/**
 * A group's KPI series per company, whichever way the hub writes them: series (`[{company, key, series: [{day, value}]}]`) or the daily
 * rows of `growth.metrics_daily` (`[{company, day, key, value}]`), grouped here. A missing day stays missing, never zero.
 */
export function parseKpis(x: unknown): KpiSeries[] {
  const rows = listOf(x as unknown[] | { items?: unknown[] });
  const out = new Map<string, KpiSeries>();
  for (const r0 of rows) {
    const r = r0 as Record<string, unknown>;
    const company = String(r.company ?? r.code ?? '');
    const key = String(r.key ?? r.kpi ?? '');
    const k = `${company}|${key}`;
    const s = out.get(k) ?? { company, key, title_fa: (r.title_fa as string | null) ?? null, unit: (r.unit as string | null) ?? null, series: [] };
    const pts = (r.series ?? r.days ?? r.values) as Array<{ day?: string; at?: string; value: number | null }> | undefined;
    if (Array.isArray(pts)) s.series.push(...pts.map((p) => ({ day: String(p.day ?? p.at ?? '').slice(0, 10), value: p.value == null ? null : Number(p.value) })));
    else if (r.day != null) s.series.push({ day: String(r.day).slice(0, 10), value: r.value == null ? null : Number(r.value) });
    out.set(k, s);
  }
  for (const s of out.values()) s.series.sort((a, b) => a.day.localeCompare(b.day));
  return [...out.values()];
}
export const useGroupKpis = (key: string, company: string | null, days = 30) =>
  useQuery({ queryKey: ['groups', 'kpis', key, company, days], staleTime: 60_000, queryFn: async () => parseKpis(await call<unknown>('GET', `/groups/${enc(key)}/kpis?days=${days}${company ? `&company=${enc(company)}` : ''}`)) });

export function useGroupActions(key: string) {
  const qc = useQueryClient();
  const done = () => Promise.all(['groups', 'home'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    member: useMutation({ mutationFn: (v: { company: string; state: 'on' | 'paused' }) => call<Membership>('PUT', `/groups/${enc(key)}/members/${enc(v.company)}`, { state: v.state }), onSettled: done }),
    routine: useMutation({ mutationFn: (v: { routine: string; state: 'on' | 'paused' }) => call<Routine>('PUT', `/groups/${enc(key)}/routines/${enc(v.routine)}`, { state: v.state }), onSettled: done }),
  };
}

// ===================================================================================== §29.12 connections ==
export type ConnectionKind = 'search_console' | 'ga4' | 'instagram' | 'telegram' | 'youtube' | 'x' | 'pagespeed' | 'trends' | 'bing' | 'play_console';
/** §29.12's order of work. */
export const CONNECTION_KINDS: ConnectionKind[] = ['search_console', 'ga4', 'instagram', 'telegram', 'youtube', 'x', 'pagespeed', 'trends', 'bing', 'play_console'];
export const CONNECTION_FA: Record<ConnectionKind, string> = {
  search_console: 'جست‌وجوی گوگل (سئو)', ga4: 'آمار بازدید سایت', instagram: 'اینستاگرام', telegram: 'تلگرام', youtube: 'یوتیوب', x: 'ایکس',
  pagespeed: 'سرعت صفحه‌ها', trends: 'روند جست‌وجو', bing: 'جست‌وجوی بینگ', play_console: 'گوگل‌پلی',
};
export const CONNECTION_ICON: Record<ConnectionKind, 'search' | 'chart' | 'image' | 'send' | 'video' | 'messages' | 'time' | 'globe' | 'deliverable'> = {
  search_console: 'search', ga4: 'chart', instagram: 'image', telegram: 'send', youtube: 'video', x: 'messages', pagespeed: 'time', trends: 'chart', bing: 'globe', play_console: 'deliverable',
};
export type Connection = {
  company: string; kind: ConnectionKind; label_fa: string; state: 'not_connected' | 'connected' | 'error'; config: Record<string, unknown>;
  secret: 'set' | 'missing'; last_read_at: string | null; last_error_fa: string | null; daily: Array<{ day: string; key: string; value: number }>;
};
export const CONNECTION_STATE: Record<Connection['state'], { fa: string; tone: 'neutral' | 'pos' | 'neg' }> = {
  not_connected: { fa: 'وصل نیست', tone: 'neutral' }, connected: { fa: 'وصل است', tone: 'pos' }, error: { fa: 'خطا دارد', tone: 'neg' },
};
/** A one-page guide (`GET /connections/guides/{kind}`): its words, and the settings it asks for (never the secret's value). */
export type ConnectionGuide = {
  kind: string; title_fa: string; body_md?: string | null; steps_md?: string | null; md?: string | null;
  config?: Array<{ key: string; label_fa: string; placeholder?: string | null; hint_fa?: string | null }> | null;
  secret_fa?: string | null; secret?: boolean | null;
};
export const guideText = (g: ConnectionGuide) => g.body_md ?? g.steps_md ?? g.md ?? '';

export const useCompanyConnections = (code: string | null) =>
  useQuery({
    queryKey: ['connections', code], enabled: !!code, staleTime: 20_000,
    queryFn: async () => { const r = await served(call<Connection[] | { items: Connection[] }>('GET', `/companies/${enc(code!)}/connections`)); return r ? listOf(r) : null; },
  });
export const useConnectionGuide = (kind: string | null) =>
  useQuery({ queryKey: ['connections', 'guide', kind], enabled: !!kind, staleTime: 300_000, queryFn: () => served(call<ConnectionGuide>('GET', `/connections/guides/${enc(kind!)}`)) });
export function useConnectionActions(code: string, kind: string) {
  const qc = useQueryClient();
  const done = () => Promise.all(['connections', 'groups', 'home'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  const target = `${code}/${kind}`;
  return {
    /** Settings that are not secret; sealed when they widen what is read (the hub says so). */
    config: useMutation({ mutationFn: (config: Record<string, unknown>) => withStepUp('connection.config', target, (h) => call<Connection>('PUT', `/companies/${enc(code)}/connections/${enc(kind)}`, { config }, h)), onSettled: done }),
    /** Write-only (🔏): the secret goes to the hub's vault and never comes back; the answer says only «set». */
    secret: useMutation({ mutationFn: async (secret: string) => call<Connection | undefined>('PUT', `/companies/${enc(code)}/connections/${enc(kind)}/secret`, { secret }, { 'X-Step-Up': await stepUp('connection.secret', target) }), onSettled: done }),
    test: useMutation({ mutationFn: () => call<{ ok?: boolean; message_fa?: string | null } & Partial<Connection>>('POST', `/companies/${enc(code)}/connections/${enc(kind)}/test`, {}), onSettled: done }),
  };
}

// ===================================================================================== §29.13 the owner's home ==
export type Suggestion = {
  id: string; kind: 'effective' | 'good'; company: string; title_fa: string; why_fa: string; impact_fa: string; cost_fa: string;
  source: 'council' | 'group' | 'advisor'; state: 'new' | 'run' | 'later' | 'no'; reason_fa: string | null; order_ref: string | null; created_at: string;
};
export type Progress = { id: string; company: string; title_fa: string; before: { value: number; at: string }; after: { value: number; at: string }; kpi: string; source: string; work_ref: string | null };
export type HomeGroup = { key: string; title_fa: string; companies: Array<{ code: string; name_fa: string; kpi: { key: string; title_fa: string; unit: string; series: KpiPoint[] } | null }> };
export type Home = {
  cards: { effective: Suggestion | null; good: Suggestion | null; progress: Progress | null };
  morning: string[]; groups: HomeGroup[]; orders: Array<{ ref: string; text_fa: string; state: OrderState; summary_fa: string | null }>;
  critical: Notification29[];
};
/** `GET /home`; null on a hub before §29.13. */
export const useHome = () => useQuery({ queryKey: ['home'], staleTime: 20_000, queryFn: () => served(call<Home>('GET', '/home')) });
export function useSuggestionAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; action: 'run' | 'later' | 'no'; reason_fa?: string | null }) =>
      call<Suggestion>('POST', `/home/suggestions/${enc(v.id)}`, { action: v.action, ...(v.reason_fa ? { reason_fa: v.reason_fa } : {}) }),
    onSettled: () => Promise.all(['home', 'orders'].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}

// ===================================================================================== §29.14 employee state ==
export type EmployeeState = 'idle' | 'thinking' | 'working' | 'waiting' | 'stuck' | 'done';
export type Stuck = { reason_fa: string; fix: Fix | null };
export const EMPLOYEE_STATE: Record<EmployeeState, { fa: string; tone: 'neutral' | 'gold' | 'pos' | 'neg' | 'warn' | 'lapis' | 'silver'; live?: boolean; ring: string }> = {
  idle: { fa: 'بیکار', tone: 'silver', ring: 'sleeping' }, thinking: { fa: 'در فکر', tone: 'lapis', live: true, ring: 'working' },
  working: { fa: 'در کار', tone: 'gold', live: true, ring: 'working' }, waiting: { fa: 'منتظر', tone: 'warn', ring: 'waiting' },
  stuck: { fa: 'گیر کرده', tone: 'neg', ring: 'error' }, done: { fa: 'تمام', tone: 'pos', ring: 'idle' },
};
/** An employee's §29.14 state; an older hub's activity read the same way (working → در کار, asleep → بیکار). */
export function stateOf(e: { state?: string | null; activity?: string | null }): EmployeeState {
  if (e.state && e.state in EMPLOYEE_STATE) return e.state as EmployeeState;
  const a = e.activity ?? '';
  return a === 'working' ? 'working' : a === 'waiting' ? 'waiting' : a === 'error' ? 'stuck' : 'idle';
}
export const stuckOf = (e: { stuck?: Stuck | null }): Stuck | null => e.stuck ?? null;
/**
 * A stuck employee's fix (§29.14): on its order when the fix names one (`order`, or a target that is an order's ref), through the order
 * report's own route; anything else has no route of its own in §29 yet (null: the button says so).
 */
export function useEmployeeFix() {
  const qc = useQueryClient();
  return async (f: Fix): Promise<unknown> => {
    const ref = typeof f.order === 'string' ? f.order : /^F-\d+$/.test(f.target ?? '') ? f.target! : null;
    if (!ref) return null;
    try {
      return await withStepUp(f.action, f.target ?? ref, (h) => call<unknown>('POST', `/orders/${enc(ref)}/fix`, fixBody(f), h));
    } finally {
      await Promise.all(['orders', 'home', 'employees'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
    }
  };
}

// ===================================================================================== «شرکت ← فنی» ==
async function techList<T>(path: '/oversight/findings' | '/notifications', code: string): Promise<T[]> {
  // One call per domain (the contract writes them as alternatives), merged; a row without a domain (an older hub) is the company's too.
  const parts = await Promise.all(TECH_DOMAINS.map((d) => call<{ items: T[] } | T[]>('GET', `${path}?scope=all&domain=${d}&company=${enc(code)}&limit=100`)));
  const seen = new Set<string>();
  const out: T[] = [];
  for (const x of parts.flatMap((p) => listOf(p))) {
    const r = x as T & Routed & { id?: string; ref?: string; company?: string };
    const k = r.ref ?? r.id ?? JSON.stringify(r);
    if (seen.has(k) || (r.company && r.company !== code) || (r.domain && !TECH_DOMAINS.includes(r.domain))) continue;
    seen.add(k);
    out.push(x);
  }
  return out;
}
export const useTechFindings = (code: string) => useQuery({ queryKey: ['oversight', 'tech', code], staleTime: 30_000, queryFn: () => techList<Finding29>('/oversight/findings', code) });
export const useTechNotifications = (code: string) => useQuery({ queryKey: ['notifications', 'tech', code], staleTime: 30_000, queryFn: () => techList<Notification29>('/notifications', code) });
