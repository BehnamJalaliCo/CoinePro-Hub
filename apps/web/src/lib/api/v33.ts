'use client';

// ⟨1.15⟩ Contract §33 (prompt 24): money and the Grok-like working style — usage in the advisor's words, crypto payments read and
// reconciled, revenue analytics, a small CRM, affiliate follow-up, a decision's money impact, parallel parts of an order, the company's
// journey, personas and the message test, and the workspace on a company's own server. Every shape here is the hub's own
// (`apps/api/openapi/hq-api.v1.json`, regenerated 2026-11-05): a money amount the hub keeps as a Decimal reaches the panel as a string
// (`Dec`) and is read with `dec()`. Every request body carries only the fields of its model (the hub refuses any other key). Each route
// group is feature-gated like §29–§32: a hub that answers 404/405/501 shows a calm «after the hub update» state. Money is only ever read
// here; nothing moves a payment.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { bodyTarget, stepUp } from '@/lib/auth';
import { ApiError } from './client';
import { handled } from './observe';
import { call } from './v13';
import { ifMatch } from './v15';
import { notServed } from './v28';

const enc = encodeURIComponent;
export async function served<T>(p: Promise<T>): Promise<T | null> {
  try { return await p; } catch (e) { if (notServed(e)) return null; throw e; }
}
/** A page of the hub: `{items, next_cursor}`. */
export type Page<T> = { items: T[]; next_cursor?: string | null };
/** A Decimal as the hub writes it in JSON (a string such as "2050.00"). */
export type Dec = string;
/** A Decimal (or a number) as a number; null stays null. */
export const dec = (v: Dec | number | null | undefined): number | null => (v == null || v === '' ? null : Number(v));
/** The same, with 0 for null (for sums). */
export const dec0 = (v: Dec | number | null | undefined): number => dec(v) ?? 0;

async function withStepUp<T>(action: string, target: () => Promise<string>, run: (h?: Record<string, string>) => Promise<T>): Promise<T> {
  try { return await run(); } catch (e) {
    if (!(e instanceof ApiError && e.status === 403 && e.code === 'step_up_required')) throw e;
    handled(e);
    return run({ 'X-Step-Up': await stepUp(action, await target()) });
  }
}
const inval = (qc: ReturnType<typeof useQueryClient>) => () => qc.invalidateQueries({ queryKey: ['g33'] });
const qs = (o: Record<string, string | number | null | undefined>) => {
  const p = Object.entries(o).filter(([, v]) => v != null && v !== '').map(([k, v]) => `${k}=${enc(String(v))}`);
  return p.length ? `?${p.join('&')}` : '';
};

// ======================================================================================== §33.1 usage reports ==
export type UsageDomainRow = { domain: string; tokens: number; usd_equiv: number; share: number };
export type UsageCompanyRow = { company: string; tokens: number; usd_equiv: number; share: number };
export type UsageAnomalyKind = 'tech_domain_largest' | 'spike' | 'voice_high' | 'failed_calls';
export type UsagePack = {
  period: 'day' | 'week'; from: string; to: string;
  by_domain: UsageDomainRow[]; by_company: UsageCompanyRow[];
  top_runs: Array<{ ref: string; role: string | null; tokens: number }>;
  voice_usd: number; lines: { runs: number; tokens: number }; ads_spend_usd: number;
  vs_prev: { tokens_pct: number | null; usd_pct: number | null }; anomalies: Array<{ kind: UsageAnomalyKind; note: string }>;
};
export type UsageText = { lines_fa: string[]; saving_fa: string };
/** `words`: «model» when the advisor wrote the lines, «code» when the model gave nothing usable and code wrote them from the pack. */
export type UsageReport = { ref: string; period: 'day' | 'week'; from: string; to: string; pack: UsagePack; text: UsageText | null; words?: 'model' | 'code'; at: string };
export const useUsageReports = (period: 'day' | 'week' | null) =>
  useQuery({ queryKey: ['g33', 'usage', period], staleTime: 30_000, queryFn: async () => (await served(call<Page<UsageReport>>('GET', `/usage/reports${qs({ period, limit: 20 })}`)))?.items ?? null });
export function useMakeUsageReport() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (period: 'day' | 'week') => call<UsageReport>('POST', '/usage/reports', { period }), onSettled: inval(qc) });
}

// ======================================================================================= §33.2 crypto payments ==
export type Network = 'bsc_usdt' | 'trc20_usdt';
export type PaySourceState = 'not_configured' | 'ok' | 'error';
/** `PayPaymentSource`: `adapter` is the hub's own («ledger_v1» or «chain-read»); `server` is the runner's server of a ledger source. */
export type PaymentSource = {
  id: string; company: string; kind: 'ledger' | 'chain'; adapter: string; network?: Network | null; address?: string | null; server?: string | null;
  enabled?: boolean; state: PaySourceState; last_read_at?: string | null; last_error_fa?: string | null;
};
/** `PayPaymentSourceIn`, and nothing else. A chain source: `network` and a public `address`; a ledger source: at most `server`. */
export type PaySourceIn = { kind: 'ledger' | 'chain'; network?: Network | null; address?: string | null; server?: string | null; enabled: boolean };
/** `PayReadResult`: a chain read counts the transfers and pages it read; a ledger read is `queued` on the company's runner. */
export type PayReadResult = { source: PaymentSource; queued?: boolean; payments?: number; transfers?: number; pages?: number };
export type PayStatus = 'matched' | 'ledger_only' | 'chain_only' | 'amount_mismatch' | 'pending_chain';
export type Payment = {
  id: string; company: string; source: string; ext_id: string; customer?: string | null; plan?: string | null; amount_usdt?: Dec | null; network?: Network | null; tx_hash?: string | null;
  paid_at: string; period_start?: string | null; period_end?: string | null; status: PayStatus; checked_at: string; chain_amount?: Dec | null; note_fa?: string | null;
};
export type Reconcile = { company: string; day: string; ledger_count: number; chain_count: number; matched: number; ledger_only: number; chain_only: number; amount_mismatch: number; pending_chain?: number; note_fa: string };
export const PAY_STATUS: Record<PayStatus, { fa: string; tone: 'pos' | 'neg' | 'warn' | 'lapis' | 'silver'; hint: string }> = {
  matched: { fa: 'جور است', tone: 'pos', hint: 'پرداخت در دفتر شرکت و روی شبکه هست.' },
  ledger_only: { fa: 'فقط در دفتر', tone: 'neg', hint: 'تأیید شده ولی پولی روی شبکه پیدا نشد.' },
  chain_only: { fa: 'فقط روی شبکه', tone: 'warn', hint: 'پول رسیده ولی مشتری‌ای برایش نیست.' },
  amount_mismatch: { fa: 'مبلغ کم‌تر', tone: 'warn', hint: 'مبلغ رسیده از قیمت طرح کم‌تر است.' },
  pending_chain: { fa: 'منتظر تأیید شبکه', tone: 'silver', hint: 'هنوز به تعداد لازم تأیید نشده.' },
};
export const SOURCE_STATE: Record<PaySourceState, { fa: string; tone: 'pos' | 'neg' | 'silver' }> = { ok: { fa: 'سالم', tone: 'pos' }, error: { fa: 'خطا', tone: 'neg' }, not_configured: { fa: 'تنظیم نشده', tone: 'silver' } };
export const NETWORK_FA: Record<Network, string> = { bsc_usdt: 'شبکه‌ی بایننس', trc20_usdt: 'شبکه‌ی ترون' };
/** The hub's own check of a public address (`apps/api/seed/payments/chain.yaml`), so a wrong one is caught before the passkey. */
export const ADDRESS_RE: Record<Network, RegExp> = { bsc_usdt: /^0x[0-9a-fA-F]{40}$/, trc20_usdt: /^T[1-9A-HJ-NP-Za-km-z]{33}$/ };
export const useSources = (c: string) =>
  useQuery({ queryKey: ['g33', 'sources', c], staleTime: 15_000, queryFn: () => served(call<PaymentSource[]>('GET', `/companies/${enc(c)}/payment-sources`)) });
export type PayFilter = { status: PayStatus | null; from: string; to: string };
/** `?status&from&to` (days, YYYY-MM-DD), newest first; one page of up to 100. */
export const usePayments = (c: string, f: PayFilter) =>
  useQuery({ queryKey: ['g33', 'payments', c, f], staleTime: 15_000, queryFn: async () => (await served(call<Page<Payment>>('GET', `/companies/${enc(c)}/payments${qs({ status: f.status, from: f.from, to: f.to, limit: 100 })}`)))?.items ?? null });
export const useReconcile = (c: string, from: string, to: string) =>
  useQuery({ queryKey: ['g33', 'reconcile', c, from, to], staleTime: 15_000, queryFn: () => served(call<Reconcile[]>('GET', `/companies/${enc(c)}/reconcile${qs({ from, to })}`)) });
export function useSourceActions(c: string) {
  const qc = useQueryClient();
  const settle = inval(qc);
  return {
    /** Adding or changing a source is sealed on `payment.source`; the target is the SHA-256 of the exact body sent. */
    save: useMutation({
      mutationFn: (b: PaySourceIn) => {
        const body: PaySourceIn = b.kind === 'chain'
          ? { kind: 'chain', network: b.network ?? null, address: b.address ?? null, enabled: b.enabled }
          : { kind: 'ledger', server: b.server || null, enabled: b.enabled };
        return withStepUp('payment.source', () => bodyTarget(JSON.stringify(body)), (h) => call<PaymentSource>('POST', `/companies/${enc(c)}/payment-sources`, body, h));
      },
      onSettled: settle,
    }),
    /** «بخوان»: an owner's explicit read (`Idempotency-Key`, set by `call` on every POST); a chain answering badly is a 502 in Persian. */
    read: useMutation({ mutationFn: (id: string) => call<PayReadResult>('POST', `/payment-sources/${enc(id)}/read`), onSettled: settle }),
  };
}

// =========================================================================================== §33.3 revenue board ==
export type RevenueMonth = { month: string; mrr_usdt: Dec; new_customers: number; churned: number; active: number; arpu_usdt: Dec | null };
export type RevenueBoard = {
  company: string | null; period?: 'month'; months: RevenueMonth[]; churn_rate: number | null; ltv_usdt: Dec | null; cac_usdt: Dec | null; payback_months: number | null;
  /** `retained`: percent still paying, month by month from the start (100 first). */
  cohorts: Array<{ start_month: string; size: number; retained: number[] }>;
  forecast: Array<{ month: string; mrr_usdt: Dec; low: Dec; high: Dec }>; forecast_basis_fa: string;
  roi: { revenue_usdt: Dec; cost_usd: { tokens: Dec; voice: Dec; ads: Dec; servers?: Dec | null }; ratio: number | null };
  cost_per_output: Array<{ kind: 'line_run' | 'deliverable' | 'order'; count: number; usd_each: Dec | null }>;
};
export const OUTPUT_COST_FA: Record<RevenueBoard['cost_per_output'][number]['kind'], string> = { line_run: 'هر اجرای خط تولید', deliverable: 'هر خروجی', order: 'هر فرمان' };
export const useRevenueBoard = (company: string | null) => useQuery({ queryKey: ['g33', 'board', company], staleTime: 30_000, queryFn: () => served(call<RevenueBoard>('GET', `/revenue/board${qs({ company })}`)) });
/** `by_source` (additive on `GET /revenue/summary`): per company, the referral commission and the customers' payments of the period;
 *  `store_payments` counts in-app purchases, which carry no amount and are counted, not summed. */
export type RevenueBySource = { company: string; affiliate_usdt: Dec; payments_usdt: Dec; store_payments?: number; total_usdt: Dec };
export const useRevenueBySource = (period: string, company: string | null) =>
  useQuery({
    queryKey: ['g33', 'by-source', period, company], staleTime: 30_000,
    queryFn: async (): Promise<RevenueBySource[] | null> => (await served(call<{ by_source?: RevenueBySource[] }>('GET', `/revenue/summary${qs({ period, company })}`)))?.by_source ?? null,
  });

// ================================================================================================= §33.4 sales ==
export type LeadSource = 'support' | 'telegram' | 'site' | 'payment' | 'referral' | 'manual';
export const LEAD_SOURCE_FA: Record<LeadSource, string> = { support: 'پشتیبانی', telegram: 'تلگرام', site: 'سایت', payment: 'پرداخت', referral: 'معرفی', manual: 'دستی' };
export type Actor = { kind: 'owner' | 'agent' | 'service' | 'system'; code: string; display_fa?: string | null };
export type Lead = {
  ref: string; company: string; source: LeadSource; name_fa: string | null; contact: string; stage: string; value_usdt: Dec | null; next_at: string | null; next_fa: string | null;
  assignee: Actor | null; lost_reason_fa: string | null; events: Array<{ at: string; kind: string; note_fa: string }>; created_at: string; updated_at: string; version: number;
};
/** `LeadIn`: a lead by hand. `contact` is a pseudonym (8–128 of A-Z a-z 0-9 _ : . -); without one the hub makes one. */
export type LeadIn = { name_fa?: string | null; contact?: string | null; source?: 'site' | 'referral' | 'manual' | 'support' | 'telegram'; value_usdt?: number | null; next_at?: string | null; next_fa?: string | null; note_fa?: string | null; assignee?: Actor | null };
/** `LeadPatch`: only what changes; `If-Match` is the lead's version. */
export type LeadPatch = { stage?: string | null; lost_reason_fa?: string | null; name_fa?: string | null; value_usdt?: number | null; next_at?: string | null; next_fa?: string | null; note_fa?: string | null; assignee?: Actor | null };
export const CONTACT_RE = /^[A-Za-z0-9_:.-]{8,128}$/;
/** `LeadDraft`: the follow-up text, checked by the outbound guard and never sent. */
export type LeadDraft = { lead: string; draft_fa: string; guard_ok: boolean; blocked_reasons: string[]; sent?: false };
export type PipelineStage = { stage: string; title_fa: string; kind: 'open' | 'won' | 'lost'; count: number; value_usdt: Dec; median_days: number | null };
/** `win_rate`: won ÷ (won + lost), 0..1. */
export type Pipeline = { company: string; stages: PipelineStage[]; total: number; open_count: number; won_count: number; lost_count: number; open_value_usdt: Dec; win_rate: number | null };
export const STAGE_FA: Record<string, string> = { new: 'تازه', contacted: 'تماس گرفته شد', qualified: 'جدی', trial: 'آزمایشی', paid: 'پرداخت کرد', lost: 'از دست رفت' };
/** The pipeline's own title wins (stages are the company's data); the default stages have a Persian name here. */
export const stageFa = (k: string, t?: string | null) => t || STAGE_FA[k] || k;
export const useLeads = (c: string) =>
  useQuery({ queryKey: ['g33', 'leads', c], staleTime: 15_000, queryFn: async () => (await served(call<Page<Lead>>('GET', `/companies/${enc(c)}/leads${qs({ limit: 200 })}`)))?.items ?? null });
export const usePipeline = (c: string) => useQuery({ queryKey: ['g33', 'pipeline', c], staleTime: 15_000, queryFn: () => served(call<Pipeline>('GET', `/companies/${enc(c)}/pipeline`)) });
export const useLead = (ref: string | null) => useQuery({ queryKey: ['g33', 'lead', ref], enabled: !!ref, staleTime: 10_000, queryFn: () => call<Lead>('GET', `/leads/${enc(ref!)}`) });
export function useLeadActions(c: string) {
  const qc = useQueryClient();
  const settle = inval(qc);
  return {
    add: useMutation({ mutationFn: (b: LeadIn) => call<Lead>('POST', `/companies/${enc(c)}/leads`, b), onSettled: settle }),
    /** `PATCH /leads/{ref}` with `If-Match: <version>`; a lead changed meanwhile is a 409. */
    edit: useMutation({ mutationFn: (v: { ref: string; version: number; body: LeadPatch }) => call<Lead>('PATCH', `/leads/${enc(v.ref)}`, v.body, ifMatch(v.version)), onSettled: settle }),
    draft: useMutation({ mutationFn: (ref: string) => call<LeadDraft>('POST', `/leads/${enc(ref)}/draft`) }),
  };
}

// ============================================================================================ §33.5 affiliate gaps ==
/** One account and month: the commission due against what arrived. `waiting` until the exchange's settlement day (or while a day is
 *  incomplete), `ok` within the line, `open` above it (a follow-up work for the finance manager), `closed` once the gap was paid. */
export type GapState = 'waiting' | 'ok' | 'open' | 'closed';
export type AffiliateGap = {
  account: string; company: string; exchange: string; month: string; due_usdt: Dec; received_usdt: Dec; gap_usdt: Dec; gap_pct: number;
  settles_on: string; state: GapState; draft_fa: string | null; work_ref: string | null;
};
export const useAffiliateGaps = (company: string | null) =>
  useQuery({ queryKey: ['g33', 'gaps', company], staleTime: 30_000, queryFn: () => served(call<AffiliateGap[]>('GET', `/revenue/affiliate-gaps${qs({ company })}`)) });

// ================================================================================================= §33.6 impact ==
export type Impact = { revenue_usdt?: number | null; cost_usd?: number | null; horizon_days: number; basis_fa: string; kind: 'measured' | 'estimate' };
export const impactOf = (d: unknown): Impact | null => ((d as { impact?: Impact | null } | null)?.impact ?? null);
/** The hub's own sort key (`domain/impact.py` `score`): the size of the impact per 30 days, revenue and cost together. */
export const impactScore = (i: Impact | null): number =>
  (i ? ((Math.abs(i.revenue_usdt ?? 0) + Math.abs(i.cost_usd ?? 0)) * 30) / Math.max(i.horizon_days || 1, 1) : Number.NEGATIVE_INFINITY);

// ======================================================================================= §33.7 / §33.10 order report ==
/** One part of a split work: an ordinary child work. `state` is the plain reading of the child's `status`. */
export type SplitPart = {
  n: number; ref: string; title_fa: string; role: string; assignee?: string | null; who_fa?: string | null; status: string; state: 'working' | 'delivered' | 'failed';
  progress_pct?: number | null; output_ref?: string | null; output_title_fa?: string | null; failed_fa?: string | null; tokens_used?: number; budget_tokens?: number | null;
};
/** The parts of one work side by side, and the one merge the parent's assignee writes when every part is done. */
export type WorkSplit = { work_ref: string; state: 'running' | 'merging' | 'done' | 'failed' | 'cancelled'; proposed_by: string; parts: SplitPart[]; merge_queued_at?: string | null; created_at: string };
export type WorkspaceState = 'starting' | 'working' | 'awaiting_seal' | 'idle' | 'delivered' | 'stopped' | 'failed';
/** A work's persistent folder on its company's own server (§33.10). */
export type WorkspaceProgress = {
  work_ref: string; server: string; where_fa: string; path: string; state: WorkspaceState; turns: number; session_ref?: string | null;
  last_step_fa?: string | null; note_fa?: string | null; updated_at: string; closed_at?: string | null; remove_after?: string | null;
};
export type WorkStopped = { work_ref: string; workspace?: WorkspaceState | null; jobs_stopped?: number };
/** What §33 adds to the order report (§29.2), both additive. */
export type OrderParallel = { parts?: WorkSplit[]; workspaces?: WorkspaceProgress[] };
export const PART_STATE: Record<SplitPart['state'], { fa: string; tone: 'lapis' | 'pos' | 'neg' }> = { working: { fa: 'در حال کار', tone: 'lapis' }, delivered: { fa: 'تحویل شد', tone: 'pos' }, failed: { fa: 'نشد', tone: 'neg' } };
export const SPLIT_STATE: Record<WorkSplit['state'], { fa: string; tone: 'lapis' | 'gold' | 'pos' | 'neg' | 'silver' }> = {
  running: { fa: 'بخش‌ها در حال کار', tone: 'lapis' }, merging: { fa: 'در حال جمع‌بندی', tone: 'gold' }, done: { fa: 'جمع‌بندی نوشته شد', tone: 'pos' }, failed: { fa: 'نشد', tone: 'neg' }, cancelled: { fa: 'لغو شد', tone: 'silver' },
};
export const WORKSPACE_STATE: Record<WorkspaceState, { fa: string; tone: 'silver' | 'lapis' | 'warn' | 'pos' | 'neg' }> = {
  starting: { fa: 'در حال آماده شدن', tone: 'silver' }, working: { fa: 'در حال کار', tone: 'lapis' }, awaiting_seal: { fa: 'منتظر مُهر تو', tone: 'warn' }, idle: { fa: 'منتظر نوبت بعد', tone: 'silver' },
  delivered: { fa: 'تحویل شد', tone: 'pos' }, stopped: { fa: 'متوقف شد', tone: 'silver' }, failed: { fa: 'نشد', tone: 'neg' },
};
export const WORKSPACE_LIVE: ReadonlySet<WorkspaceState> = new Set(['starting', 'working', 'awaiting_seal', 'idle']);
/** `GET /work/{id}/split` (the work's UUID): the parts of a split work; null for a work that was never split (404). */
export const useWorkSplit = (id: string | null) =>
  useQuery({ queryKey: ['g33', 'split', id], enabled: !!id, staleTime: 15_000, queryFn: () => served(call<WorkSplit>('GET', `/work/${enc(id!)}/split`)) });
/** The API addresses a work by its UUID; the report names it by ref (`W-000312`), so the ref is resolved through the list's search. */
async function workId(ref: string): Promise<string> {
  const hit = (await call<Page<{ id: string; ref: string }>>('GET', `/work${qs({ q: ref, limit: 5 })}`)).items.find((w) => w.ref === ref);
  if (!hit) throw new ApiError(404, { code: 'not_found', message_fa: 'این کار پیدا نشد.' });
  return hit.id;
}
/** «توقف»: the workspace's turn on the company server is cancelled; the work stays open (`POST /work/{id}/stop`). */
export function useStopWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (ref: string) => call<WorkStopped>('POST', `/work/${enc(await workId(ref))}/stop`),
    onSettled: () => { void qc.invalidateQueries({ queryKey: ['orders'] }); void qc.invalidateQueries({ queryKey: ['g33'] }); },
  });
}

// ============================================================================================== §33.8 the journey ==
export type JourneyStage = { key: string; title_fa: string; reached_at?: string | null; evidence?: { kind: string; ref?: string | null } | null };
/** `current`: the latest stage reached (the first stage when none is); `next_fa`: one line about the next, written when a stage changes. */
export type Journey = { company: string; stages: JourneyStage[]; current: string; next_fa?: string | null; days_in_stage: number };
export type JourneyEvent = { at: string; company: string; stage: string; title_fa: string };
export type JourneyBoard = { journeys: Journey[]; timeline: JourneyEvent[] };
export const useJourney = (c: string) => useQuery({ queryKey: ['g33', 'journey', c], staleTime: 30_000, queryFn: () => served(call<Journey>('GET', `/companies/${enc(c)}/journey`)) });
export const useJourneys = () => useQuery({ queryKey: ['g33', 'journeys'], staleTime: 30_000, queryFn: () => served(call<JourneyBoard>('GET', '/journeys')) });

// ==================================================================================== §33.9 personas and the test ==
export type PersonaRow = { id: string; company: string; name_fa: string; summary_fa: string; pains_fa: string[]; objections_fa: string[]; channel_fa: string; source: string; version: number };
/** A suggestion from the knowledge base (`PersonaSuggestion.personas`): nothing is saved until the owner keeps it. */
export type PersonaDraft = { name_fa: string; summary_fa: string; pains_fa: string[]; objections_fa: string[]; channel_fa: string };
export type PersonaSuggestion = { company: string; basis_fa: string; personas: PersonaDraft[] };
/** `PersonaIn`: at most 8 pains and 8 objections. */
export type PersonaIn = PersonaDraft & { source: 'owner' | 'kb_suggested' };
export type PersonaPatch = Partial<PersonaDraft>;
export type PersonaTest = {
  id: string; text: string; at: string; average: number; lowest: number;
  results: Array<{ persona: string; name_fa: string; score: number; would_act: boolean; objection_fa?: string | null; fix_fa?: string | null }>;
};
export const PERSONA_LIST_MAX = 8;
export const usePersonas = (c: string) => useQuery({ queryKey: ['g33', 'personas', c], staleTime: 20_000, queryFn: () => served(call<PersonaRow[]>('GET', `/companies/${enc(c)}/personas`)) });
export function usePersonaActions(c: string) {
  const qc = useQueryClient();
  const settle = inval(qc);
  return {
    /** Keeping a suggestion (`source: kb_suggested`), or adding by hand. */
    add: useMutation({ mutationFn: (b: PersonaIn) => call<PersonaRow>('POST', `/companies/${enc(c)}/personas`, b), onSettled: settle }),
    /** `PATCH /personas/{id}`: the fields only (the hub refuses any other key); a kept suggestion becomes the owner's own. */
    edit: useMutation({ mutationFn: (v: { id: string; body: PersonaPatch }) => call<PersonaRow>('PATCH', `/personas/${enc(v.id)}`, v.body), onSettled: settle }),
    remove: useMutation({ mutationFn: (id: string) => call<void>('DELETE', `/personas/${enc(id)}`), onSettled: settle }),
    suggest: useMutation({ mutationFn: () => call<PersonaSuggestion>('POST', `/companies/${enc(c)}/personas/suggest`) }),
    test: useMutation({ mutationFn: (text: string) => call<PersonaTest>('POST', `/companies/${enc(c)}/personas/test`, { text }) }),
  };
}
