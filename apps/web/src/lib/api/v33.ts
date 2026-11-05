'use client';

// ⟨1.15⟩ Contract §33 (prompt 24): money and the Grok-like working style — usage in the advisor's words, crypto payments read and
// reconciled, revenue analytics, a small CRM, affiliate follow-up, a decision's money impact, parallel parts of an order, the company's
// journey, personas and the message test, and the workspace on a company's own server. Until the OpenAPI file is regenerated the shapes
// live here, written from §33. Where §33 leaves a shape open (a list's envelope, the pipeline's fields, the order report's parts) the
// reader accepts the likely forms and the assumption is noted next to the type. Every route group is feature-gated like §29–§32: a hub
// that answers 404/405/501 shows a calm «after the hub update» state. Money is only ever read here; nothing moves a payment.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { stepUp } from '@/lib/auth';
import { ApiError } from './client';
import { handled } from './observe';
import { call } from './v13';
import { notServed } from './v28';

const enc = encodeURIComponent;
export async function served<T>(p: Promise<T>): Promise<T | null> {
  try { return await p; } catch (e) { if (notServed(e)) return null; throw e; }
}
/** A list from an array, `{items}` or `{days}`-less envelope. */
export const listOf = <T,>(x: T[] | { items?: T[] } | null | undefined): T[] => (Array.isArray(x) ? x : x?.items ?? []);
async function withStepUp<T>(action: string, target: string, run: (h?: Record<string, string>) => Promise<T>): Promise<T> {
  try { return await run(); } catch (e) {
    if (!(e instanceof ApiError && e.status === 403 && e.code === 'step_up_required')) throw e;
    handled(e);
    return run({ 'X-Step-Up': await stepUp(action, target) });
  }
}
const inval = (qc: ReturnType<typeof useQueryClient>) => () => qc.invalidateQueries({ queryKey: ['g33'] });
const qs = (o: Record<string, string | number | null | undefined>) => {
  const p = Object.entries(o).filter(([, v]) => v != null && v !== '').map(([k, v]) => `${k}=${enc(String(v))}`);
  return p.length ? `?${p.join('&')}` : '';
};
const num = (v: unknown): number => (typeof v === 'number' ? v : Number(v) || 0);

// ======================================================================================== §33.1 usage reports ==
export type UsagePack = {
  period: 'day' | 'week'; from: string; to: string;
  by_domain: Array<{ domain: string; tokens: number; usd_equiv: number; share: number }>;
  by_company: Array<{ company: string; tokens: number; usd_equiv: number; share: number }>;
  top_runs: Array<{ ref: string; role: string; tokens: number }>;
  voice_usd: number; lines: { runs: number; tokens: number }; ads_spend_usd: number;
  vs_prev: { tokens_pct: number | null; usd_pct: number | null }; anomalies: Array<{ kind: string; note: string }>;
};
export type UsageReport = { ref: string; period: 'day' | 'week'; from: string; to: string; pack: UsagePack; text: { lines_fa: string[]; saving_fa: string }; at: string };
export const useUsageReports = (period: 'day' | 'week' | null) =>
  useQuery({ queryKey: ['g33', 'usage', period], staleTime: 30_000, queryFn: async () => { const r = await served(call<UsageReport[] | { items: UsageReport[] }>('GET', `/usage/reports${qs({ period })}`)); return r ? listOf(r) : null; } });
export function useMakeUsageReport() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (period: 'day' | 'week') => call<UsageReport>('POST', '/usage/reports', { period }), onSettled: inval(qc) });
}

// ======================================================================================= §33.2 crypto payments ==
export type PaySourceState = 'not_configured' | 'ok' | 'error';
export type PaymentSource = { id: string; company: string; kind: 'ledger' | 'chain'; adapter: string; network: 'bsc_usdt' | 'trc20_usdt' | null; address: string | null; state: PaySourceState; last_read_at: string | null; last_error_fa: string | null };
export type PayStatus = 'matched' | 'ledger_only' | 'chain_only' | 'amount_mismatch' | 'pending_chain';
export type Payment = {
  id: string; company: string; source: string; ext_id: string; customer: string; plan: string | null; amount_usdt: number | null; network: 'bsc_usdt' | 'trc20_usdt' | null; tx_hash: string | null; paid_at: string;
  period_start: string | null; period_end: string | null; status: PayStatus; checked_at: string | null;
};
export type Reconcile = { company: string; day: string; ledger_count: number; chain_count: number; matched: number; ledger_only: number; chain_only: number; amount_mismatch: number; note_fa: string | null };
export const PAY_STATUS: Record<PayStatus, { fa: string; tone: 'pos' | 'neg' | 'warn' | 'lapis' | 'silver'; hint: string }> = {
  matched: { fa: 'تطبیق خورد', tone: 'pos', hint: 'پرداخت در دفتر شرکت و روی زنجیره هست.' },
  ledger_only: { fa: 'فقط در دفتر', tone: 'neg', hint: 'تأیید شده ولی پولی روی زنجیره پیدا نشد.' },
  chain_only: { fa: 'فقط روی زنجیره', tone: 'warn', hint: 'پول رسیده ولی مشتری‌ای برایش نیست.' },
  amount_mismatch: { fa: 'مبلغ کم‌تر', tone: 'warn', hint: 'مبلغ روی زنجیره از قیمت طرح کم‌تر است.' },
  pending_chain: { fa: 'منتظر تأیید زنجیره', tone: 'silver', hint: 'هنوز به تعداد لازم تأیید نشده.' },
};
export const SOURCE_STATE: Record<PaySourceState, { fa: string; tone: 'pos' | 'neg' | 'silver' }> = { ok: { fa: 'سالم', tone: 'pos' }, error: { fa: 'خطا', tone: 'neg' }, not_configured: { fa: 'تنظیم نشده', tone: 'silver' } };
export const NETWORK_FA: Record<string, string> = { bsc_usdt: 'BSC (BEP20)', trc20_usdt: 'TRON (TRC20)' };
export const useSources = (c: string) => useQuery({ queryKey: ['g33', 'sources', c], staleTime: 15_000, queryFn: async () => { const r = await served(call<PaymentSource[] | { items: PaymentSource[] }>('GET', `/companies/${enc(c)}/payment-sources`)); return r ? listOf(r) : null; } });
export type PayFilter = { status: PayStatus | null; from: string; to: string };
export const usePayments = (c: string, f: PayFilter) =>
  useQuery({ queryKey: ['g33', 'payments', c, f], staleTime: 15_000, queryFn: async () => { const r = await served(call<Payment[] | { items: Payment[] }>('GET', `/companies/${enc(c)}/payments${qs({ status: f.status, from: f.from, to: f.to })}`)); return r ? listOf(r) : null; } });
export const useReconcile = (c: string, from: string, to: string) =>
  useQuery({ queryKey: ['g33', 'reconcile', c, from, to], staleTime: 15_000, queryFn: async () => { const r = await served(call<Reconcile[] | { items?: Reconcile[]; days?: Reconcile[] }>('GET', `/companies/${enc(c)}/reconcile${qs({ from, to })}`)); return r ? (Array.isArray(r) ? r : r.days ?? r.items ?? []) : null; } });
export type SourceBody = { id?: string; kind: 'ledger' | 'chain'; adapter: string; network: 'bsc_usdt' | 'trc20_usdt' | null; address: string | null };
export function useSourceActions(c: string) {
  const qc = useQueryClient();
  const settle = inval(qc);
  return {
    /** Adding or changing a source is sealed on `payment.source` (target: the source's id, or the company for a new one). */
    save: useMutation({ mutationFn: (b: SourceBody) => withStepUp('payment.source', b.id ?? c, (h) => call<PaymentSource>('POST', `/companies/${enc(c)}/payment-sources`, b, h)), onSettled: settle }),
    /** «بخوان»: an owner's explicit read; an upstream refusal comes back as 502 with a Persian message. */
    read: useMutation({ mutationFn: (id: string) => call<PaymentSource>('POST', `/payment-sources/${enc(id)}/read`, {}), onSettled: settle }),
  };
}

// =========================================================================================== §33.3 revenue board ==
export type RevenueMonth = { month: string; mrr_usdt: number; new_customers: number; churned: number; active: number; arpu_usdt: number };
export type RevenueBoard = {
  company: string | null; period: 'month'; months: RevenueMonth[]; churn_rate: number | null; ltv_usdt: number | null; cac_usdt: number | null; payback_months: number | null;
  cohorts: Array<{ start_month: string; size: number; retained: number[] }>;
  forecast: Array<{ month: string; mrr_usdt: number; low: number; high: number }>; forecast_basis_fa: string | null;
  roi: { revenue_usdt: number; cost_usd: { tokens: number; voice: number; ads: number; servers: number | null }; ratio: number | null };
  cost_per_output: Array<{ kind: 'line_run' | 'deliverable' | 'order'; count: number; usd_each: number }>;
};
export const OUTPUT_COST_FA: Record<string, string> = { line_run: 'هر اجرای خط تولید', deliverable: 'هر خروجی', order: 'هر فرمان' };
export const useRevenueBoard = (company: string | null) => useQuery({ queryKey: ['g33', 'board', company], staleTime: 30_000, queryFn: () => served(call<RevenueBoard>('GET', `/revenue/board${qs({ company })}`)) });
/** `by_source` (additive on `GET /revenue/summary`): assumed `[{source: "affiliate"|"payments", usdt}]` or a `{source: usdt}` map. */
export type RevenueBySource = Array<{ source: string; usdt: number }>;
export const SOURCE_FA: Record<string, string> = { affiliate: 'کمیسیون رفرال', payments: 'پرداخت مشتریان', payment: 'پرداخت مشتریان' };
export const useRevenueBySource = (period: string, company: string | null) =>
  useQuery({
    queryKey: ['g33', 'by-source', period, company], staleTime: 30_000,
    queryFn: async (): Promise<RevenueBySource | null> => {
      const r = await served(call<{ by_source?: unknown }>('GET', `/revenue/summary${qs({ period, company })}`));
      const b = r?.by_source;
      if (!b) return null;
      if (Array.isArray(b)) return b.map((x: { source: string; usdt?: unknown; total_usdt?: unknown }) => ({ source: x.source, usdt: num(x.usdt ?? x.total_usdt) }));
      return Object.entries(b as Record<string, unknown>).map(([source, v]) => ({ source, usdt: num(v) }));
    },
  });

// ================================================================================================= §33.4 sales ==
export type LeadSource = 'support' | 'telegram' | 'site' | 'payment' | 'referral' | 'manual';
export const LEAD_SOURCE_FA: Record<LeadSource, string> = { support: 'پشتیبانی', telegram: 'تلگرام', site: 'سایت', payment: 'پرداخت', referral: 'معرفی', manual: 'دستی' };
export type Lead = {
  ref: string; company: string; source: LeadSource; name_fa: string | null; contact: string; stage: string; value_usdt: number | null; next_at: string | null; next_fa: string | null;
  assignee: { kind: string; code: string; display_fa?: string | null } | null; lost_reason_fa: string | null; events: Array<{ at: string; kind: string; note_fa: string }>; created_at: string; updated_at: string;
};
/** Assumed: `stages` in order, each with its count, value and median days; `win_rate` as 0..1 (a value over 1 is read as a percent). */
export type Pipeline = { stages: Array<{ key: string; title_fa?: string | null; count: number; value_usdt: number; median_days: number | null }>; win_rate: number | null };
export const STAGE_FA: Record<string, string> = { new: 'تازه', contacted: 'تماس گرفته شد', qualified: 'واجد شرایط', trial: 'آزمایشی', paid: 'پرداخت کرد', lost: 'از دست رفت' };
export const stageFa = (k: string, t?: string | null) => t || STAGE_FA[k] || k;
export const useLeads = (c: string) => useQuery({ queryKey: ['g33', 'leads', c], staleTime: 15_000, queryFn: async () => { const r = await served(call<Lead[] | { items: Lead[] }>('GET', `/companies/${enc(c)}/leads`)); return r ? listOf(r) : null; } });
export const usePipeline = (c: string) => useQuery({ queryKey: ['g33', 'pipeline', c], staleTime: 15_000, queryFn: () => served(call<Pipeline>('GET', `/companies/${enc(c)}/pipeline`)) });
export const useLead = (ref: string | null) => useQuery({ queryKey: ['g33', 'lead', ref], enabled: !!ref, staleTime: 10_000, queryFn: () => call<Lead>('GET', `/leads/${enc(ref!)}`) });
export type LeadBody = { name_fa?: string | null; contact?: string; source?: LeadSource; stage?: string; value_usdt?: number | null; next_at?: string | null; next_fa?: string | null; lost_reason_fa?: string | null };
export function useLeadActions(c: string) {
  const qc = useQueryClient();
  const settle = inval(qc);
  return {
    add: useMutation({ mutationFn: (b: LeadBody & { contact: string }) => call<Lead>('POST', `/companies/${enc(c)}/leads`, b), onSettled: settle }),
    edit: useMutation({ mutationFn: (v: { ref: string; body: LeadBody }) => call<Lead>('PATCH', `/leads/${enc(v.ref)}`, v.body), onSettled: settle }),
    /** The draft, never sent. Assumed answer: `{text_fa}` (also read as `draft_fa` or `text`). */
    draft: useMutation({ mutationFn: async (ref: string) => { const r = await call<{ text_fa?: string; draft_fa?: string; text?: string }>('POST', `/leads/${enc(ref)}/draft`, {}); return r.text_fa ?? r.draft_fa ?? r.text ?? ''; } }),
  };
}

// ============================================================================================ §33.5 affiliate gaps ==
/** Assumed row: one account and month with the commission due against what arrived; `state` open until the gap is paid. */
export type AffiliateGap = { account: string; company: string; month: string; due_usdt: number; received_usdt: number; gap_pct: number; state: 'open' | 'closed' | 'in_window'; draft_fa: string | null; planner: string | null };
export const useAffiliateGaps = (company: string | null) =>
  useQuery({ queryKey: ['g33', 'gaps', company], staleTime: 30_000, queryFn: async () => { const r = await served(call<AffiliateGap[] | { items: AffiliateGap[] }>('GET', `/revenue/affiliate-gaps${qs({ company })}`)); return r ? listOf(r) : null; } });

// ================================================================================================= §33.6 impact ==
export type Impact = { revenue_usdt: number | null; cost_usd: number | null; horizon_days: number; basis_fa: string; kind: 'measured' | 'estimate' };
export const impactOf = (d: unknown): Impact | null => ((d as { impact?: Impact | null } | null)?.impact ?? null);
/** One number to sort by: revenue minus cost (a cost-only card is negative); a card without impact sorts last. */
export const impactScore = (i: Impact | null): number => (i ? (i.revenue_usdt ?? 0) - (i.cost_usd ?? 0) : Number.NEGATIVE_INFINITY);

// ======================================================================================= §33.7 / §33.10 order report ==
/** Assumed additive fields of §29.2's report: the parts of a split work, the merge, and the on-server workspace. */
export type SplitPart = { ref: string; title_fa: string; role_fa: string | null; state: 'queued' | 'running' | 'done' | 'failed'; progress_pct: number | null; summary_fa: string | null; outputs: Array<{ ref: string; title_fa: string }>; failed_fa: string | null };
export type SplitMerge = { state: 'waiting' | 'running' | 'done' | 'failed'; by_fa: string | null; text_fa: string | null };
export type WorkspaceInfo = { mode: 'on_server' | 'hub'; server_fa: string | null; state: 'preparing' | 'working' | 'awaiting_seal' | 'done' | 'stopped' | 'failed'; progress_pct: number | null; note_fa: string | null; folder: string | null };
export type OrderParallel = { parts?: SplitPart[] | null; merge?: SplitMerge | null; workspace?: WorkspaceInfo | null };
export const PART_STATE: Record<SplitPart['state'], { fa: string; tone: 'silver' | 'lapis' | 'pos' | 'neg' }> = { queued: { fa: 'در صف', tone: 'silver' }, running: { fa: 'در حال کار', tone: 'lapis' }, done: { fa: 'تمام شد', tone: 'pos' }, failed: { fa: 'نشد', tone: 'neg' } };
export const WORKSPACE_STATE: Record<WorkspaceInfo['state'], { fa: string; tone: 'silver' | 'lapis' | 'warn' | 'pos' | 'neg' }> = {
  preparing: { fa: 'در حال آماده شدن', tone: 'silver' }, working: { fa: 'در حال کار', tone: 'lapis' }, awaiting_seal: { fa: 'منتظر مُهر تو', tone: 'warn' }, done: { fa: 'تحویل شد', tone: 'pos' }, stopped: { fa: 'متوقف شد', tone: 'silver' }, failed: { fa: 'نشد', tone: 'neg' },
};

// ============================================================================================== §33.8 the journey ==
export type JourneyStage = { key: string; title_fa: string; reached_at: string | null; evidence: { kind: string; ref: string } | null };
export type Journey = { company: string; stages: JourneyStage[]; current: string | null; next_fa: string | null; days_in_stage: number | null };
export const useJourney = (c: string) => useQuery({ queryKey: ['g33', 'journey', c], staleTime: 30_000, queryFn: () => served(call<Journey>('GET', `/companies/${enc(c)}/journey`)) });
export const useJourneys = () => useQuery({ queryKey: ['g33', 'journeys'], staleTime: 30_000, queryFn: async () => { const r = await served(call<Journey[] | { items: Journey[] }>('GET', '/journeys')); return r ? listOf(r) : null; } });

// ==================================================================================== §33.9 personas and the test ==
export type PersonaRow = { id: string; company: string; name_fa: string; summary_fa: string; pains_fa: string[]; objections_fa: string[]; channel_fa: string; source: 'owner' | 'kb_suggested'; version: number };
export type PersonaDraft = Omit<PersonaRow, 'id' | 'company' | 'version'>;
export type PersonaTest = { text: string; results: Array<{ persona: string; score: number; would_act: boolean; objection_fa: string | null; fix_fa: string | null }>; at: string };
export const usePersonas = (c: string) => useQuery({ queryKey: ['g33', 'personas', c], staleTime: 20_000, queryFn: async () => { const r = await served(call<PersonaRow[] | { items: PersonaRow[] }>('GET', `/companies/${enc(c)}/personas`)); return r ? listOf(r) : null; } });
export function usePersonaActions(c: string) {
  const qc = useQueryClient();
  const settle = inval(qc);
  return {
    /** Keeping a suggestion, or adding by hand: `POST …/personas`. */
    add: useMutation({ mutationFn: (b: PersonaDraft) => call<PersonaRow>('POST', `/companies/${enc(c)}/personas`, b), onSettled: settle }),
    /** `PATCH /personas/{id}`: the fields only (the hub refuses any other key). */
    edit: useMutation({
      mutationFn: (b: PersonaDraft & { id: string; version: number }) =>
        call<PersonaRow>('PATCH', `/personas/${enc(b.id)}`, { name_fa: b.name_fa, summary_fa: b.summary_fa, pains_fa: b.pains_fa, objections_fa: b.objections_fa, channel_fa: b.channel_fa }),
      onSettled: settle,
    }),
    remove: useMutation({ mutationFn: (id: string) => call<void>('DELETE', `/personas/${enc(id)}`), onSettled: settle }),
    /** Proposes up to four from the knowledge base; nothing is saved until the owner keeps one. Assumed answer: an array or `{items}` of drafts. */
    suggest: useMutation({ mutationFn: async () => listOf(await call<PersonaDraft[] | { items: PersonaDraft[] }>('POST', `/companies/${enc(c)}/personas/suggest`, {})) }),
    test: useMutation({ mutationFn: (text: string) => call<PersonaTest>('POST', `/companies/${enc(c)}/personas/test`, { text }) }),
  };
}
