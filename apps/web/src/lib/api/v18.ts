'use client';

// Contract v1.5 §21 (prompt 12): the owner's management tools. The premium advisor (decision memos, the devil's advocate, proactive
// notes, the weekly review), "ask the hub", spoken briefings and the CEOs' weekly letters, department ranks and the monthly HR round,
// the real diff on a deploy card, waste, ROI, a new connection, quick notes and cartable reminders, refuted claims on the health board,
// the digital CEO (prediction only), and §21.13's substitute players (GPT, Gemini, DeepSeek) with their seats, sign-ins and creatives.
// The server builds it in prompt 12; until the OpenAPI file is regenerated, the types live here, written from the contract (nullable
// exactly as written). Money is a decimal string (§1); tokens are integers; rates and confidences are 0..1.

import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { bodyTarget, stepUp } from '@/lib/auth';
import { ApiError, type Schemas } from './client';
import { handled } from './observe';
import { call, type Actor } from './v13';
import { ifMatch, qs, type Connection } from './v15';
import type { Conflict } from './v17';

type Page<T> = { items: T[]; next_cursor: string | null };
/** §21 names a cursor only on some lists; the others are read either bare or paged. */
const items = <T>(x: T[] | Page<T>): T[] => (Array.isArray(x) ? x : x.items);
const enc = encodeURIComponent;
/** A GET that answers 404 when the thing does not exist yet (a memo, the current review, the latest briefing): null, not an error. */
async function orNull<T>(p: Promise<T>): Promise<T | null> {
  try { return await p; } catch (e) { if (e instanceof ApiError && e.status === 404) { handled(e); return null; } throw e; }
}

export type FileRef = { id: string; name: string; mime: string; size: number; sha256: string };
export type Usage = { tokens: number; usd: string };
export type Level3 = 'low' | 'medium' | 'high';
export type Player = 'gpt' | 'gemini' | 'deepseek';

// ------------------------------------------------------------- premium advisor (§21.1) --
export type MemoMode = 'standard' | 'devil';
export type MemoState = 'writing' | 'ready' | 'failed' | 'stale';
export type Recommendation = 'approve' | 'reject' | 'return' | 'ask';
/** A substitute's independent opinion on the same masked facts pack (§21.13 seats `advisor_second_opinion`, `third_opinion`). */
export type Opinion = { player: Player; model: string; recommendation: Recommendation; confidence: number; summary_fa: string; differences: string[]; agrees: boolean };
export type DecisionMemo = {
  id: string; ref: string; decision: string; decision_version: number; mode: MemoMode; state: MemoState; trigger: 'owner' | 'auto';
  summary_fa: string; recommendation: Recommendation; confidence: number;
  options: Array<{ title_fa: string; pros_md: string; cons_md: string }>;
  against_md: string; // the strongest case against; never empty
  risks: Array<{ title_fa: string; likelihood: Level3; impact: Level3; mitigation_fa: string }>;
  questions: string[]; // what the owner should ask the proposer
  citations: Array<{ kind: string; ref: string }>; usage: Usage;
  second_opinion: Opinion | null;
  third_opinion?: Opinion | null; // §21.13 `third_opinion`, the shape of second_opinion
  created_at: string;
};
export type TriggerKind = 'budget' | 'quota' | 'compliance' | 'incident' | 'revenue' | 'waiting_decisions' | 'finding' | 'okr';
export type AdvisorTrigger = {
  id: string; key: string; kind: TriggerKind; company: string | null; fired_at: string; facts: Record<string, unknown>;
  message_ref: string | null; state: 'sent' | 'deferred' | 'capped';
};
/** What a message of thread A carries in `meta` (§21.1, §21.3). */
export type AdvisorMeta = { mode?: 'devil'; proactive?: { kind: TriggerKind; key: string }; review?: string };

/** The latest memo of a card in one mode; null while none was asked for. Polls while the advisor writes. */
export const useDecisionMemo = (ref: string, mode: MemoMode) =>
  useQuery({
    queryKey: ['memos', 'decision', ref, mode],
    queryFn: () => orNull(call<DecisionMemo>('GET', `/decisions/${enc(ref)}/memo${qs({ mode })}`)),
    refetchInterval: (q) => (q.state.data?.state === 'writing' ? 2_500 : false),
  });
export const useMemos = (decision?: string | null) =>
  useInfiniteQuery({
    queryKey: ['memos', 'list', decision ?? ''],
    queryFn: ({ pageParam }) => call<Page<DecisionMemo>>('GET', `/advisor/memos${qs({ decision, limit: 30, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor,
  });
export function useRequestMemo() {
  const qc = useQueryClient();
  return useMutation({
    // Idempotent per decision, mode and card version: asking twice returns the same DM-…; a decided card is `409 decision_not_pending`.
    mutationFn: (v: { ref: string; mode: MemoMode }) => call<DecisionMemo>('POST', `/decisions/${enc(v.ref)}/memo`, { mode: v.mode }),
    onSuccess: (m) => { qc.setQueryData(['memos', 'decision', m.decision, m.mode], m); void qc.invalidateQueries({ queryKey: ['memos', 'list'] }); void qc.invalidateQueries({ queryKey: ['decisions'] }); },
  });
}
export const useAdvisorTriggers = (f: { since?: string | null; kind?: TriggerKind | null } = {}) =>
  useQuery({ queryKey: ['advisor', 'triggers', f.since ?? '', f.kind ?? ''], queryFn: async () => items(await call<AdvisorTrigger[] | Page<AdvisorTrigger>>('GET', `/advisor/triggers${qs({ since: f.since, kind: f.kind })}`)), refetchInterval: 120_000 });

// --------------------------------------------------------------- ask the hub (§21.2) --
export const ASK_MAX = 500;
export type AskState = 'queued' | 'searching' | 'answering' | 'done' | 'failed';
export type CitationKind = 'resolution' | 'decision' | 'deliverable' | 'work' | 'message' | 'doc' | 'code';
export type AskCitation = { kind: CitationKind; ref?: string; repo?: string; path?: string; lines?: [number, number]; commit?: string; snippet: string };
export type Ask = {
  id: string; ref: string; q: string; scope: { companies?: string[]; kinds?: string[] } | null; state: AskState;
  found: number; // 0 = nothing retrieved, and no model ran
  answer_md: string | null; citations: AskCitation[]; not_indexed: string[]; usage: Usage; created_at: string; finished_at: string | null;
};
const ASK_LIVE: AskState[] = ['queued', 'searching', 'answering'];
export const useAsks = () =>
  useInfiniteQuery({
    queryKey: ['ask', 'list'],
    queryFn: ({ pageParam }) => call<Page<Ask>>('GET', `/ask${qs({ limit: 20, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor,
  });
export const useAsk = (ref: string | null) =>
  useQuery({ queryKey: ['ask', 'one', ref], queryFn: () => call<Ask>('GET', `/ask/${enc(ref!)}`), enabled: !!ref, refetchInterval: (q) => (q.state.data && ASK_LIVE.includes(q.state.data.state) ? 1_500 : false) });
export function useAskHub() {
  const qc = useQueryClient();
  return useMutation({
    // Owner only. One key per question, kept across a retry of the same press.
    mutationFn: (v: { q: string; scope?: Ask['scope']; key: string }) => call<Ask>('POST', '/ask', { q: v.q, ...(v.scope ? { scope: v.scope } : {}) }, { 'Idempotency-Key': v.key }),
    onSuccess: (a) => { qc.setQueryData(['ask', 'one', a.ref], a); void qc.invalidateQueries({ queryKey: ['ask', 'list'] }); },
  });
}

// --------------------------------------------------------- weekly review (§21.3) --
export type AgendaKind = 'decision' | 'risk' | 'okr' | 'finding' | 'budget' | 'revenue' | 'outcome_review' | 'note';
export type AgendaItem = { n: number; kind: AgendaKind; ref: string; company: string | null; title_fa: string; why_fa: string; status: 'open' | 'done' | 'deferred'; owner_note: string | null };
export type WeeklyReview = {
  id: string; ref: string; week: string; // the week's Saturday, YYYY-MM-DD, owner TZ
  state: 'ready' | 'in_progress' | 'done' | 'skipped';
  agenda: AgendaItem[]; // ≤ 12, in the kind order above
  brief_message_ref: string | null; minutes_ref: string | null;
  started_at: string | null; finished_at: string | null; duration_s: number | null; version: number;
};
export const useWeeklyReviews = () => useQuery({ queryKey: ['reviews', 'list'], queryFn: async () => items(await call<WeeklyReview[] | Page<WeeklyReview>>('GET', '/reviews/weekly')) });
export const useCurrentReview = () => useQuery({ queryKey: ['reviews', 'current'], queryFn: () => orNull(call<WeeklyReview>('GET', '/reviews/weekly/current')), refetchInterval: 120_000 });
export function useReviewAction() {
  const qc = useQueryClient();
  const done = () => Promise.all([qc.invalidateQueries({ queryKey: ['reviews'] }), qc.invalidateQueries({ queryKey: ['deliverables'] })]);
  return {
    start: useMutation({ mutationFn: (ref: string) => call<WeeklyReview>('POST', `/reviews/weekly/${enc(ref)}/start`, {}), onSuccess: done }),
    // Writes the minutes as a deliverable O-… by HQ-ADV.
    finish: useMutation({ mutationFn: (ref: string) => call<WeeklyReview>('POST', `/reviews/weekly/${enc(ref)}/finish`, {}), onSuccess: done }),
    item: useMutation({
      mutationFn: (v: { r: WeeklyReview; n: number; status: AgendaItem['status']; owner_note?: string | null }) =>
        call<WeeklyReview>('PATCH', `/reviews/weekly/${enc(v.r.ref)}/items/${v.n}`, { status: v.status, ...(v.owner_note != null ? { owner_note: v.owner_note } : {}) }, ifMatch(v.r.version)),
      onSuccess: done,
    }),
  };
}

// ------------------------------------------------- briefings and CEO letters (§21.4) --
export type BriefingKind = 'morning' | 'ceo_letter';
export type AudioState = 'pending' | 'ready' | 'off' | 'failed';
export type Briefing = {
  id: string; ref: string; kind: BriefingKind; company: string; period: { from: string; to: string };
  deliverable_ref: string; text_md: string;
  audio: FileRef | null; audio_state: AudioState;
  voice: { engine: 'piper'; version: string; voice: string; license: string } | null; created_at: string;
};
export const useBriefings = (f: { kind?: BriefingKind | null; company?: string | null }) =>
  useInfiniteQuery({
    queryKey: ['briefings', 'list', f.kind ?? '', f.company ?? ''],
    queryFn: ({ pageParam }) => call<Page<Briefing>>('GET', `/briefings${qs({ kind: f.kind, company: f.company, limit: 30, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
  });
export const useLatestBriefing = (kind: BriefingKind, company?: string | null) =>
  useQuery({ queryKey: ['briefings', 'latest', kind, company ?? ''], queryFn: () => orNull(call<Briefing>('GET', `/briefings/latest${qs({ kind, company })}`)), refetchInterval: (q) => (q.state.data?.audio_state === 'pending' ? 10_000 : false) });
export const useBriefing = (ref: string | null) => useQuery({ queryKey: ['briefings', 'one', ref], queryFn: () => call<Briefing>('GET', `/briefings/${enc(ref!)}`), enabled: !!ref });

// --------------------------------------------- department rank, HR round (§21.5) --
export type DepartmentRank = {
  period: 'week' | 'month'; key: string; company: string; department: string; score: number;
  parts: { people: number; delivery: number; efficiency: number; owner: number | null }; // 0..100 each; owner null = no ratings, its weight spread
  employees: number; rank_company: number; rank_holding: number | null; trend: number[]; computed_at: string;
};
export type HrFlag = 'promote_candidate' | 'coach' | 'demote_candidate' | 'dismiss_candidate' | 'probation_end';
export type HrEmployee = {
  code: string; title_fa: string; score: number; score_prev: number | null; stars: number | null; efficiency: number | null; owner_avg: number | null;
  failed_share: number; findings_open: number; refuted_claims: number; probation_until: string | null; flags: HrFlag[];
};
export type HrRound = {
  id: string; ref: string; company: string; month: string; // Jalali, "1405-08"
  state: 'drafting' | 'proposed' | 'done'; evaluator: Actor; due_at: string; employees: HrEmployee[];
  deliverable_ref: string | null; decisions: string[]; teachings: string[];
};
/** `evaluation` payload v2 (§21.5). */
export type EvaluationPayload = {
  employee: string; recommendation: 'promote' | 'demote' | 'dismiss' | 'confirm';
  change: { model?: string; effort?: string; title_fa?: string; quota_estimate_month?: number } | null;
  transfer_to?: string | null; round: string; evidence: Array<{ kind: string; ref: string; note?: string }>; unflagged?: boolean; override_reason?: string | null;
};
export const useDepartmentRanks = (f: { period: 'week' | 'month'; company?: string | null; key?: string | null }) =>
  useQuery({ queryKey: ['rankings', f.period, f.company ?? '', f.key ?? ''], queryFn: async () => items(await call<DepartmentRank[] | Page<DepartmentRank>>('GET', `/rankings/departments${qs({ period: f.period, company: f.company, key: f.key })}`)), placeholderData: keepPreviousData });
export const useHrRounds = (f: { company?: string | null; month?: string | null }) =>
  useQuery({ queryKey: ['hr', 'rounds', f.company ?? '', f.month ?? ''], queryFn: async () => items(await call<HrRound[] | Page<HrRound>>('GET', `/hr/rounds${qs({ company: f.company, month: f.month })}`)) });
export const useHrRound = (ref: string | null) => useQuery({ queryKey: ['hr', 'one', ref], queryFn: () => call<HrRound>('GET', `/hr/rounds/${enc(ref!)}`), enabled: !!ref });

// ----------------------------------------------------- the deploy card's diff (§21.6) --
export type DiffFile = {
  path: string; status: 'added' | 'modified' | 'removed' | 'renamed'; additions: number; deletions: number; binary: boolean;
  patch: string | null; truncated: boolean; secret_masked: boolean;
};
export type DeployDiff = {
  base_sha: string; head_sha: string; total_files: number; total_additions: number; total_deletions: number; truncated: boolean; fetched_at: string; files: DiffFile[];
};
/** A substitute's second review of the change (§21.13 seat `code_review`); the CTO or QC verifies each finding. */
export type ReviewFinding = { path: string; line: number; severity: 'low' | 'medium' | 'high' | 'critical'; title_fa: string; detail_md: string; verified?: boolean | null };
export type DeployPayload = {
  repo: string; pr_url: string; head_sha: string; diff_stat: string; ci: { status: string; url?: string | null }; tests: { passed: number; failed: number }; rollout: string;
  window: { from: string; to: string } | null; calendar_conflicts: Conflict[] | null;
  diff: DeployDiff | null; diff_unavailable: 'no_access' | 'too_large' | 'fetch_failed' | null;
  second_review?: { player: Player; model: string; findings: ReviewFinding[]; verified: boolean | number } | null;
};
/** One file's full patch, ≤ 2000 lines, masked the same way (assumed to answer in the shape of a `files[]` row). */
export const useDecisionDiffFile = (ref: string, path: string | null) =>
  useQuery({ queryKey: ['decisions', 'diff', ref, path], queryFn: () => call<DiffFile>('GET', `/decisions/${enc(ref)}/diff${qs({ file: path })}`), enabled: !!path, staleTime: 300_000 });

// --------------------------------------------------- waste, ROI, connection (§21.7) --
export type WasteCategory = 'failed_runs' | 'cancelled_work' | 'no_progress_runs' | 'retry_loops' | 'router_errors' | 'duplicate_calls' | 'cache_miss' | 'over_model';
export type WasteItem = { category: WasteCategory; tokens: number; usd: string; count: number; top: Array<{ employee?: string; run_id?: string; work_ref?: string; tokens: number }> };
export type WasteDay = {
  day: string; company: string | null; // null = the holding total
  total_tokens: number; total_usd: string; waste_tokens: number; waste_usd: string; share: number;
  vs_7d: number; // read as the relative change of waste against the trailing 7-day average (+0.2 = 20% more)
  items: WasteItem[];
};
export const useWasteDay = (day: string | null, company?: string | null) =>
  useQuery({ queryKey: ['treasury', 'waste', 'day', day ?? '', company ?? ''], queryFn: () => call<WasteDay>('GET', `/treasury/waste${qs({ day, company })}`), placeholderData: keepPreviousData });
export const useWasteRange = (from: string, to: string, company?: string | null) =>
  useQuery({ queryKey: ['treasury', 'waste', 'range', from, to, company ?? ''], queryFn: async () => items(await call<WasteDay[] | Page<WasteDay>>('GET', `/treasury/waste${qs({ from, to, company })}`)), placeholderData: keepPreviousData });
export type RoiBy = 'employee' | 'department' | 'company';
export type RoiRow = {
  by: RoiBy; key: string; company: string; period: 'week' | 'month'; period_key: string;
  cost_usd: string; accepted: number; avg_rating: number | null; value_points: number; cost_per_accepted_usd: string | null;
  attributed: { rescued?: number; resolved_conversations?: number };
  revenue_usd: string | null; net_usd: string | null; roi: number | null; // companies only (§19.1); never invented for a person
  trend: number[];
};
export const useRoi = (f: { by: RoiBy; period: 'week' | 'month'; key?: string | null; company?: string | null }) =>
  useQuery({ queryKey: ['treasury', 'roi', f.by, f.period, f.key ?? '', f.company ?? ''], queryFn: async () => items(await call<RoiRow[] | Page<RoiRow>>('GET', `/treasury/roi${qs({ by: f.by, period: f.period, key: f.key, company: f.company })}`)), placeholderData: keepPreviousData });

/** What POST /connections takes. `pricing` per model in USD per million tokens, `limits` per minute and per day (assumed shapes). */
export type ConnectionIn = {
  key: string; provider: string; kind: 'subscription' | 'api_key'; display_name: string; base_url?: string;
  models: string[]; default_model?: string;
  pricing: Record<string, { input_per_mtok: string; output_per_mtok: string }>;
  limits: { rpm?: number; tpm?: number; daily_usd?: string };
  fallback_priority?: number;
};
/** A connection with the §21.7 statuses: `pending_secret` → `verifying` (assumed) → `ready` or `error`. */
export type Connection18 = Omit<Connection, 'status' | 'kind'> & { status: string; kind: string };
export const ROUTER_PROVIDERS = ['anthropic', 'openai', 'google', 'deepseek', 'mistral', 'openai_compatible'] as const;
export function useCreateConnection() {
  const qc = useQueryClient();
  return useMutation({
    // Sealed on the SHA-256 of the exact body; the key is required: one per wizard, kept across a retry of the same body.
    mutationFn: async (v: { body: ConnectionIn; key: string }) => {
      const text = JSON.stringify(v.body);
      return call<Connection18>('POST', '/connections', v.body, { 'X-Step-Up': await stepUp('connection.create', await bodyTarget(text)), 'Idempotency-Key': v.key });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['treasury'] }),
  });
}
/** Is a base URL one the egress guard would take: https and not a private, loopback or link-local address. */
export function publicHttps(u: string): boolean {
  let x: URL;
  try { x = new URL(u); } catch { return false; }
  if (x.protocol !== 'https:') return false;
  const h = x.hostname;
  return !(h === 'localhost' || /^(10|127)\./.test(h) || /^192\.168\./.test(h) || /^172\.(1[6-9]|2\d|3[01])\./.test(h) || /^169\.254\./.test(h) || h.endsWith('.internal') || h.endsWith('.local') || /^\[?(::1|f[cd])/i.test(h));
}

// ------------------------------------------------ quick notes, reminders (§21.8) --
export type NoteStatus = 'open' | 'promoted' | 'archived';
export type OwnerNote = {
  id: string; ref: string; text_md: string; source: 'text' | 'voice'; file_id: string | null; tags: string[]; status: NoteStatus;
  promoted_to: { kind: 'work' | 'order' | 'errand'; ref: string } | null; created_at: string; updated_at: string; version: number;
};
/** POST /notes/{ref}/promote: `{to, …}`; read here as `company` (required for work) and an optional `title`. */
export type PromoteIn = { to: 'work' | 'order' | 'errand'; company?: string; title?: string };
export type ReminderKind = 'half' | 'before_expiry' | 'age_24h' | 'age_72h' | 'age_7d';
export type Reminder = { at: string; kind: ReminderKind };
export type DceoBrief = { verdict: 'approve' | 'reject' | 'return'; confidence: number; method: 'baseline' | 'model'; correct: boolean | null };
/** What §21 adds to a decision card. */
export type Decision18 = Omit<Schemas['Decision'], 'digital_ceo_prediction'> & {
  memos?: Array<{ ref: string; mode: MemoMode; state: MemoState }>;
  waiting_h?: number | null; reminders?: Reminder[];
  digital_ceo_prediction?: DceoBrief | null; // null while the card is pending (reveal "after")
};
export const useNotes = (f: { status?: NoteStatus | null; q?: string }) =>
  useInfiniteQuery({
    queryKey: ['notes', f.status ?? '', f.q ?? ''],
    queryFn: ({ pageParam }) => call<Page<OwnerNote>>('GET', `/notes${qs({ status: f.status, q: f.q?.trim(), limit: 50, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
  });
export function useNoteAction() {
  const qc = useQueryClient();
  const done = () => Promise.all(['notes', 'reviews', 'work', 'orders', 'errands', 'planner'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    create: useMutation({ mutationFn: (v: { text_md: string; source: 'text' | 'voice'; file_id?: string | null; tags?: string[]; key: string }) => call<OwnerNote>('POST', '/notes', { text_md: v.text_md, source: v.source, ...(v.file_id ? { file_id: v.file_id } : {}), ...(v.tags?.length ? { tags: v.tags } : {}) }, { 'Idempotency-Key': v.key }), onSuccess: done }),
    // No delete: archiving is the end of a note.
    patch: useMutation({ mutationFn: (v: { n: OwnerNote; patch: { text_md?: string; tags?: string[]; status?: 'archived' } }) => call<OwnerNote>('PATCH', `/notes/${enc(v.n.ref)}`, v.patch, ifMatch(v.n.version)), onSuccess: done }),
    promote: useMutation({ mutationFn: (v: { ref: string; body: PromoteIn }) => call<OwnerNote>('POST', `/notes/${enc(v.ref)}/promote`, v.body), onSuccess: done }),
  };
}

// --------------------------------------------- claims and the health board (§21.9) --
export type ClaimVerdict = 'confirmed' | 'refuted' | 'unverifiable';
export type CheckedClaim = {
  id: string; ref: string; company: string; deliverable: string; employee: string; claim_md: string; verdict: ClaimVerdict;
  checked_by: Actor; protocol: string | null; evidence: Array<{ kind: string; ref: string; note: string }>; at: string;
};
export type HealthFlag = 'truth' | 'reliability' | 'loops';
export type AgentHealth = {
  employee: string; company: string; period: '7d' | '30d'; runs: number; failed_share: number; refused_share: number; retry_loops: number;
  owner_returns: number; claims_checked: number; refuted: number; refuted_share: number | null; cost_usd: string; flags: HealthFlag[];
};
export const useClaims = (f: { company?: string | null; employee?: string | null; verdict?: ClaimVerdict | null }) =>
  useInfiniteQuery({
    queryKey: ['claims', f.company ?? '', f.employee ?? '', f.verdict ?? ''],
    queryFn: ({ pageParam }) => call<Page<CheckedClaim>>('GET', `/claims${qs({ company: f.company, employee: f.employee, verdict: f.verdict, limit: 30, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
  });
export const useRunsHealth = (f: { company?: string | null; period: '7d' | '30d' }) =>
  useInfiniteQuery({
    queryKey: ['runs-health', f.company ?? '', f.period],
    queryFn: ({ pageParam }) => call<Page<AgentHealth>>('GET', `/runs/health${qs({ company: f.company, period: f.period, limit: 100, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData, refetchInterval: 120_000,
  });

// ---------------------------------------------------- the digital CEO (§21.10) --
export type Verdict3 = 'approve' | 'reject' | 'return';
export type Prediction = {
  decision: string; made_at: string; method: 'baseline' | 'model'; verdict: Verdict3; confidence: number;
  rationale_fa: string | null; principles: string[]; sealed_hash: string; seen_before: boolean;
  actual: Verdict3 | null; correct: boolean | null;
  kind?: string; title?: string; // assumed: the card's kind and title, for reading the list
};
export type Principle = {
  id: string; ref: string; text_fa: string; sources: Array<{ kind: string; ref: string }>; status: 'proposed' | 'active' | 'retired';
  edited_by_owner: boolean; version: number; updated_at: string;
};
export type DceoWindow = '30d' | '90d' | 'all';
export type DceoStats = {
  window: DceoWindow; n: number; accuracy: number | null; baseline_accuracy: number | null; model_accuracy: number | null; brier: number | null;
  by_kind: Record<string, { n: number; accuracy: number }>; calibration: Array<{ bucket: string; n: number; hit_rate: number }>;
};
export type DceoSettings = { enabled: boolean; reveal: 'after' | 'before'; model_predictions: boolean; max_model_per_day: number };
/** GET /digital-ceo: the three windows and the setting (assumed body `{stats: [...], settings}`; `hidden` = clean predictions so far). */
export type DceoView = { stats: DceoStats[]; settings: DceoSettings; hidden?: number };
export const useDigitalCeo = () => useQuery({ queryKey: ['dceo', 'view'], queryFn: () => call<DceoView>('GET', '/digital-ceo') });
export const usePredictions = (f: { correct?: boolean | null; kind?: string | null }) =>
  useInfiniteQuery({
    queryKey: ['dceo', 'predictions', String(f.correct ?? ''), f.kind ?? ''],
    queryFn: ({ pageParam }) => call<Page<Prediction>>('GET', `/digital-ceo/predictions${qs({ correct: f.correct, kind: f.kind, limit: 50, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
  });
export const usePrinciples = () => useQuery({ queryKey: ['dceo', 'principles'], queryFn: async () => items(await call<Principle[] | Page<Principle>>('GET', '/digital-ceo/principles')) });
export function usePrincipleAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['dceo'] });
  return {
    add: useMutation({ mutationFn: (text_fa: string) => call<Principle>('POST', '/digital-ceo/principles', { text_fa }), onSuccess: done }),
    // An edit or a retirement is a new version.
    edit: useMutation({ mutationFn: (v: { p: Principle; text_fa?: string; status?: 'active' | 'retired' }) => call<Principle>('PUT', `/digital-ceo/principles/${enc(v.p.ref)}`, { text_fa: v.text_fa ?? v.p.text_fa, status: v.status ?? (v.p.status === 'retired' ? 'retired' : 'active') }, ifMatch(v.p.version)), onSuccess: done }),
    accept: useMutation({ mutationFn: (ref: string) => call<Principle>('POST', `/digital-ceo/principles/${enc(ref)}/accept`, {}), onSuccess: done }),
  };
}

// ------------------------------------------------------- owner settings (§21.12) --
export type ManagementSettings = {
  advisor: { auto_memo: { enabled: boolean; max_per_day: number }; proactive_per_day: number };
  weekly_review: { enabled: boolean; day: string; at: string };
  audio_briefings: { morning: boolean; ceo_letters: boolean };
  ceo_weekly_letter: { enabled: boolean; day: string; at: string };
  reminders: { enabled: boolean; fraction: number; before_expiry_h: number; ages_h: number[] };
  digital_ceo: DceoSettings;
  substitutes: { behind_ratio: number; creative_default_image: 'gpt' | 'gemini' };
};
export type OwnerSettings18 = Schemas['OwnerSettings'] & Partial<ManagementSettings>;
export type SettingsPatch = { [K in keyof ManagementSettings]?: Partial<ManagementSettings[K]> };
/** The same query as the base settings hook (one cache entry), read with the §21.12 fields. */
export const useSettings18 = () => useQuery({ queryKey: ['owner-settings'], queryFn: () => call<OwnerSettings18>('GET', '/owner/settings') });
export function useSaveSettings18() {
  const qc = useQueryClient();
  return useMutation({
    // A partial body; fields left out keep their value.
    mutationFn: (v: { version: number; patch: SettingsPatch }) => call<OwnerSettings18>('PUT', '/owner/settings', v.patch, ifMatch(v.version)),
    onSuccess: (s) => { qc.setQueryData(['owner-settings'], s); void qc.invalidateQueries({ queryKey: ['dceo'] }); },
  });
}

// ---------------------------------------------------- substitute players (§21.13) --
export type Cap = 'cli' | 'web' | 'api' | 'off';
export type SeatKey = 'advisor_second_opinion' | 'code_review' | 'overseer_cross_check' | 'assistant_errand' | 'content_draft' | 'long_read' | 'quick_search' | 'third_opinion' | 'creative';
export type Seat = {
  seat: SeatKey; via: 'cli' | 'web'; model: string; enabled: boolean; per_day: number; used_today: number;
  per_day_video?: number; used_today_video?: number; // `creative` only: its video cap beside the image cap (assumed)
};
export type SeatIn = Pick<Seat, 'seat' | 'via' | 'model' | 'enabled' | 'per_day'> & { per_day_video?: number };
export type Substitute = {
  player: Player; connection: string; runner: 'codex_cli' | 'gemini_cli' | null; // DeepSeek has no CLI: web only
  login: { state: 'signed_out' | 'signing_in' | 'signed_in' | 'expired'; plan_fa: string; since: string | null; last_ok_at: string | null };
  status: 'ready' | 'limited' | 'off' | 'error'; limited_until: string | null; status_reason: string | null;
  models: Array<{ id: string; label: string; tier: 'strong' | 'light'; available: boolean }>;
  capabilities: { text: Cap; image: Cap; video: Cap };
  web: { account: string; state: 'signed_in' | 'expired' | 'signed_out'; last_ok_at: string | null; recipe_version: string; last_failure: string | null };
  seats: Seat[];
  month: { key: string; calls: number; skipped: number; input_tokens: number; output_tokens: number; estimated: boolean; equiv_usd: string; price_usd: string; value_ratio: number | null };
  version: number;
};
export type SubstituteLogin = {
  id: string; connection: string; method: 'device_code' | 'auth_code'; verification_url: string; user_code: string | null; expires_at: string;
  state: 'waiting' | 'done' | 'expired' | 'failed'; status_reason: string | null;
};
export type Placement = 'telegram_post' | 'telegram_story' | 'instagram_post' | 'instagram_story' | 'banner' | 'other';
export type Aspect = '1:1' | '4:5' | '9:16' | '16:9';
export type Overlay = { title_fa: string; body_fa: string | null; cta_fa: string | null; mark: boolean };
export type CreativeState = 'queued' | 'generating' | 'review' | 'accepted' | 'rejected' | 'failed';
export type Creative = {
  id: string; ref: string; company: string; kind: 'image' | 'video'; brief_md: string; prompt_md: string;
  placement: Placement; aspect: Aspect; duration_s: number | null;
  overlay: Overlay | null; // Persian text set by the hub, never generated
  composed: FileRef | null; player: 'gpt' | 'gemini'; model: string; path: 'web' | 'cli' | 'api'; state: CreativeState;
  requested_by: Actor; work_ref: string | null; errand_ref: string | null; files: FileRef[]; review_md: string | null;
  source: { player: Player; model: string; at: string } | null; ai_generated: true; created_at: string; updated_at: string; version: number;
};
export type CreativeIn = { company: string; kind: 'image' | 'video'; brief_md: string; placement: Placement; overlay?: Overlay; duration_s?: number; player?: 'gpt' | 'gemini' };

export const useSubstitutes = () =>
  useQuery({ queryKey: ['substitutes'], queryFn: async () => items(await call<Substitute[] | Page<Substitute>>('GET', '/substitutes')), refetchInterval: 60_000 });
export function useSubstituteAction() {
  const qc = useQueryClient();
  const done = () => Promise.all([qc.invalidateQueries({ queryKey: ['substitutes'] }), qc.invalidateQueries({ queryKey: ['treasury'] })]);
  return {
    // Sealed on the SHA-256 of the exact body (the seat list), with the player's version.
    seats: useMutation({
      mutationFn: async (v: { s: Substitute; seats: SeatIn[] }) => call<Substitute>('PUT', `/substitutes/${v.s.player}/seats`, v.seats, { ...ifMatch(v.s.version), 'X-Step-Up': await stepUp('substitute.seats', await bodyTarget(JSON.stringify(v.seats))) }),
      onSuccess: done,
    }),
    // Wipes the signed-in browser profile; signing in again is the owner's terminal (`make <player>-web-login`).
    webLogout: useMutation({ mutationFn: async (player: Player) => call<Substitute>('POST', `/substitutes/${player}/web/logout`, {}, { 'X-Step-Up': await stepUp('substitute.web_logout', player) }), onSuccess: done }),
    // The CLI's own headless sign-in; `409 not_ready` when the CLI has none (the app shows the terminal command).
    login: useMutation({ mutationFn: async (connectionId: string) => call<SubstituteLogin>('POST', `/connections/${enc(connectionId)}/login`, {}, { 'X-Step-Up': await stepUp('connection.login', connectionId) }), onSuccess: done }),
    // Write-only; covered by the start's step-up, while `waiting`, at most 10 minutes.
    code: useMutation({ mutationFn: (v: { connectionId: string; loginId: string; code: string }) => call<SubstituteLogin>('POST', `/connections/${enc(v.connectionId)}/login/${enc(v.loginId)}/code`, { code: v.code }), onSuccess: done }),
    // Removes the stored sign-in (step-up action assumed `connection.logout`, target = id).
    logout: useMutation({ mutationFn: async (connectionId: string) => call<unknown>('POST', `/connections/${enc(connectionId)}/logout`, {}, { 'X-Step-Up': await stepUp('connection.logout', connectionId) }), onSuccess: done }),
  };
}
export const useSubstituteLogin = (connectionId: string | null, loginId: string | null) =>
  useQuery({
    queryKey: ['substitutes', 'login', connectionId, loginId],
    queryFn: () => call<SubstituteLogin>('GET', `/connections/${enc(connectionId!)}/login/${enc(loginId!)}`),
    enabled: !!connectionId && !!loginId, refetchInterval: (q) => (!q.state.data || q.state.data.state === 'waiting' ? 2_000 : false),
  });
const CREATIVE_LIVE: CreativeState[] = ['queued', 'generating'];
export const useCreatives = (f: { company?: string | null; state?: CreativeState | null; kind?: 'image' | 'video' | null }) =>
  useInfiniteQuery({
    queryKey: ['creatives', 'list', f.company ?? '', f.state ?? '', f.kind ?? ''],
    queryFn: ({ pageParam }) => call<Page<Creative>>('GET', `/creatives${qs({ company: f.company, state: f.state, kind: f.kind, limit: 30, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.pages.some((p) => p.items.some((c) => CREATIVE_LIVE.includes(c.state))) ? 3_000 : false),
  });
export const useCreative = (ref: string | null) =>
  useQuery({ queryKey: ['creatives', 'one', ref], queryFn: () => call<Creative>('GET', `/creatives/${enc(ref!)}`), enabled: !!ref, refetchInterval: (q) => (q.state.data && CREATIVE_LIVE.includes(q.state.data.state) ? 2_500 : false) });
export function useCreativeAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['creatives'] });
  return {
    create: useMutation({ mutationFn: (v: { body: CreativeIn; key: string }) => call<Creative>('POST', '/creatives', v.body, { 'Idempotency-Key': v.key }), onSuccess: done }),
    accept: useMutation({ mutationFn: (v: { ref: string; note?: string }) => call<Creative>('POST', `/creatives/${enc(v.ref)}/accept`, v.note ? { note: v.note } : {}), onSuccess: done }),
    reject: useMutation({ mutationFn: (v: { ref: string; note?: string }) => call<Creative>('POST', `/creatives/${enc(v.ref)}/reject`, v.note ? { note: v.note } : {}), onSuccess: done }),
  };
}

// ------------------------------------------------------------- codes (§21.12, §14) --
const CODE_FA: Record<string, string> = {
  decision_not_pending: 'این کارت دیگر منتظر تصمیم نیست؛ یادداشت فقط برای کارت منتظر نوشته میشود.',
  not_ready: 'این کار روی این نسخه‌ی سرور هنوز آماده نیست.',
  channel_not_configured: 'این بازیکن خارج شده یا خاموش است؛ جایگاهش رد میشود و کار با مدل خود Claude ادامه دارد.',
  envelope_exceeded: 'تغییر مدل در پاکت ماهانه‌ی شرکت جا نمیشود؛ هیچ چیز عوض نشد.',
  version_conflict: 'همین حالا عوض شده؛ دوباره نگاه کن و بعد ذخیره کن.',
  policy_denied: 'سیاست این کار را اجازه نمیدهد.',
};
/** The Persian sentence for a failed §21 call; the server's own sentence for everything else. */
export function faError(e: unknown): string {
  if (!(e instanceof ApiError)) return e instanceof Error ? e.message : 'انجام نشد.';
  const base = CODE_FA[e.code] ?? e.messageFa;
  if (e.code === 'rate_limited' && e.retryAfter) return `${e.messageFa}؛ ${e.retryAfter < 90 ? `${e.retryAfter} ثانیه‌ی` : `${Math.ceil(e.retryAfter / 60)} دقیقه‌ی`} دیگر.`;
  return base;
}
