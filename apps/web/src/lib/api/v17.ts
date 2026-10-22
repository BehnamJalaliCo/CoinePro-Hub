'use client';

// Contract v1.5 §20 (prompt 11): governance. The meeting room run by code, the versioned charter and company addenda, the four-layer
// knowledge base, the three cards and the live scorecard, OKRs, decision outcome reviews at 30/60/90 days, the authority matrix, the risk
// register, the change calendar and the batch seal. The server builds it in prompt 11; until the OpenAPI file is regenerated, the types
// live here, written from the contract (nullable exactly as written). Money is a decimal string (§1); tokens are integers; rates are 0..1.

import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { bodyTarget, stepUp } from '@/lib/auth';
import { ApiError, type Schemas } from './client';
import { call, type Actor } from './v13';
import { ifMatch, qs } from './v15';

type Page<T> = { items: T[]; next_cursor: string | null };
/** §20 names a cursor only where it says "Page"; the other lists are read either bare or paged. */
const items = <T>(x: T[] | Page<T>): T[] => (Array.isArray(x) ? x : x.items);
const enc = encodeURIComponent;
export type Source = { kind: string; ref: string; note: string };

// ------------------------------------------------------------------- meetings (§20.1) --
export type MeetingTypeKey = 'board' | 'company' | 'standup' | 'war_room' | 'postmortem' | 'strategy';
export type OwnerPresence = 'live' | 'summary' | 'audio';
export type MeetingType = {
  key: MeetingTypeKey; title_fa: string;
  schedule: string | null; // RRULE in the owner's time zone; null = opened by an event (war_room, postmortem)
  members: { roles: string[]; companies: 'all' | 'concerned' };
  max_rounds: number; max_speakers: number; // 1..3, 2..8 (per agenda item)
  budget_tokens: number | null; // null = no meeting cap (war_room only)
  turn_cap_tokens: number; owner_presence: OwnerPresence; enabled: boolean; version: number;
};
export type MeetingState = 'scheduled' | 'prep' | 'live' | 'closing' | 'ended' | 'cancelled';
export type ItemState = 'waiting' | 'round_1' | 'round_2' | 'done' | 'skipped';
export type MeetingItem = {
  id: string; n: number; title_fa: string; brief_md: string; sources: Source[]; time_box_min: number; speakers: Actor[];
  round: number; state: ItemState;
};
export type Participant = { actor: Actor; role_fa: string; speaker: boolean; devil: boolean };
export type Draft = { id: string; meeting: string; item: string; text_md: string; proposer: Actor; votes: { support: number; oppose: number; abstain: number }; decision: string | null };
export type Meeting = {
  id: string; ref: string; type: MeetingTypeKey; company: string; // the holding's company for board and strategy
  title_fa: string; starts_at: string; state: MeetingState;
  mode: 'discussion' | 'written'; // written: not enough of the daily cap left; statements only
  budget: { cap: number | null; estimate: number; reserved: number; used: number }; // cap null: a war room has no meeting cap (assumed, as budget_tokens)
  trimmed_fa: string | null; items: MeetingItem[]; participants: Participant[]; owner_presence: OwnerPresence;
  minutes: { deliverable: string; summary_md: string } | null;
  incident: string | null; // the incident ref (I-…) a war room or post-mortem belongs to
  version: number; created_at: string;
  drafts?: Draft[]; // §20.1 defines Draft without a route; read from GET /meetings/{ref} when the server sends them
};
export type ClaimStatus = 'sourced' | 'unsourced' | 'challenged' | 'withdrawn';
export type Claim = { id: string; text_fa: string; source: { kind: string; ref: string } | null; status: ClaimStatus };
export type Vote = 'support' | 'oppose' | 'abstain';
export type Turn = {
  id: string; meeting: string; item: string; n: number; round: number; speaker: Actor; kind: 'statement' | 'challenge' | 'vote' | 'owner';
  statement_md: string; claims: Claim[]; draft_md: string | null; stance: { draft: string; vote: Vote; reason_fa: string } | null;
  run_id: string | null; tokens: number; at: string;
};
/** The advisor's; visible to the owner only. */
export type Whisper = { id: string; meeting: string; item: string; text_md: string; sources: Source[]; at: string };
/** A page of turns; for the owner the page also carries the whispers (§20.1 "whispers are included for the owner only"). */
export type TurnsPage = Page<Turn> & { whispers?: Whisper[] };
export type MeetingFilter = { type?: MeetingTypeKey | null; company?: string | null; state?: MeetingState | null; from?: string | null; to?: string | null };
export type MeetingIn = { type: MeetingTypeKey; company?: string; starts_at: string; items?: Array<{ title_fa: string; brief_md?: string; time_box_min?: number }> };
/** PATCH before or during a meeting: the items in their new order (each may be skipped), a lower cap, the owner's presence. */
export type MeetingPatch = { items?: Array<{ id: string; n: number; skip?: boolean }>; budget_cap?: number; owner_presence?: OwnerPresence };
export type MeetingControl = { action: 'next_round' | 'skip_item' | 'end' | 'raise_budget'; tokens?: number };

const LIVE: MeetingState[] = ['live', 'closing'];
export const useMeetings = (f: MeetingFilter = {}) =>
  useQuery({
    queryKey: ['meetings', 'list', f.type ?? '', f.company ?? '', f.state ?? '', f.from ?? '', f.to ?? ''],
    queryFn: async () => items(await call<Meeting[] | Page<Meeting>>('GET', `/meetings${qs({ type: f.type, company: f.company, state: f.state, from: f.from, to: f.to, limit: 100 })}`)),
    placeholderData: keepPreviousData, refetchInterval: 60_000,
  });
export const useMeeting = (ref: string) =>
  useQuery({ queryKey: ['meetings', 'one', ref], queryFn: () => call<Meeting>('GET', `/meetings/${enc(ref)}`), refetchInterval: (q) => (q.state.data && LIVE.includes(q.state.data.state) ? 5_000 : false) });
export const useTurns = (ref: string, live: boolean) =>
  useQuery({ queryKey: ['meetings', 'turns', ref], queryFn: () => call<TurnsPage>('GET', `/meetings/${enc(ref)}/turns${qs({ limit: 200 })}`), refetchInterval: live ? 4_000 : false });
export function useMeetingAction() {
  const qc = useQueryClient();
  const done = () => Promise.all([qc.invalidateQueries({ queryKey: ['meetings'] }), qc.invalidateQueries({ queryKey: ['decisions'] }), qc.invalidateQueries({ queryKey: ['planner'] })]);
  return {
    // Same speaker rule, budget and daily share as a scheduled one. One key per press, so a retry is the same meeting.
    create: useMutation({ mutationFn: (v: { body: MeetingIn; key: string }) => call<Meeting>('POST', '/meetings', v.body, { 'Idempotency-Key': v.key }), onSuccess: done }),
    patch: useMutation({ mutationFn: (v: { m: Meeting; patch: MeetingPatch }) => call<Meeting>('PATCH', `/meetings/${enc(v.m.ref)}`, v.patch, ifMatch(v.m.version)), onSuccess: done }),
    // The owner jumps the queue; `409 meeting_not_live` otherwise. The key is required: one per text, kept across retries.
    speak: useMutation({ mutationFn: (v: { ref: string; text?: string; file_id?: string | null; key: string }) => call<Turn>('POST', `/meetings/${enc(v.ref)}/speak`, { ...(v.text ? { text: v.text } : {}), ...(v.file_id ? { file_id: v.file_id } : {}) }, { 'Idempotency-Key': v.key }), onSuccess: done }),
    // Only the owner raises a budget.
    control: useMutation({ mutationFn: (v: { ref: string; body: MeetingControl }) => call<Meeting>('POST', `/meetings/${enc(v.ref)}/control`, v.body), onSuccess: done }),
  };
}
export const useMeetingSettings = () =>
  useQuery({ queryKey: ['meetings', 'settings'], queryFn: async () => { const x = await call<MeetingType[] | Page<MeetingType> | { types: MeetingType[] }>('GET', '/meetings/settings'); return Array.isArray(x) ? x : 'types' in x ? x.types : x.items; }, staleTime: 60_000 });
export function useSaveMeetingSettings() {
  const qc = useQueryClient();
  return useMutation({
    // The whole list, sealed on the SHA-256 of the exact body (§20.11 `meetings.settings`).
    mutationFn: async (types: MeetingType[]) => {
      const body = { types };
      return call<MeetingType[] | { types: MeetingType[] }>('PUT', '/meetings/settings', body, { 'X-Step-Up': await stepUp('meetings.settings', await bodyTarget(JSON.stringify(body))) });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['meetings'] }),
  });
}

// ---------------------------------------------------------------- charter (§20.2) --
export type RedLine = { key: string; text_fa: string; check: 'rule' | 'sample'; patterns: string[] | null };
export type CharterStatus = 'proposed' | 'sealed' | 'superseded';
export type Charter = {
  scope: string; // "holding" or a company code
  version: number; status: CharterStatus;
  body_md: string; // holding ≤ 6000 characters, an addendum ≤ 3000
  red_lines: RedLine[];
  body_sha256: string; // sha256 of the canonical JSON {body_md, red_lines}: the seal binds the red lines too
  created_by: Actor; created_at: string; sealed_by: Actor | null; sealed_at: string | null;
};
export type CharterVersionRef = Pick<Charter, 'version' | 'status' | 'created_by' | 'created_at' | 'sealed_at'>;
/** One scope of GET /charter: its sealed version, a proposed one waiting for the seal, and the version list. */
export type CharterScope = { scope: string; sealed: Charter | null; proposed: Charter | null; versions: CharterVersionRef[] };
export type CharterDiff = { scope: string; version: number; against: number; diff: string };
export const CHARTER_MAX = { holding: 6000, addendum: 3000 };
export const charterMax = (scope: string) => (scope === 'holding' ? CHARTER_MAX.holding : CHARTER_MAX.addendum);

export const useCharter = () =>
  useQuery({ queryKey: ['charter'], queryFn: async () => { const x = await call<CharterScope[] | Page<CharterScope> | { scopes: CharterScope[] }>('GET', '/charter'); return Array.isArray(x) ? x : 'scopes' in x ? x.scopes : x.items; } });
export const useCharterVersions = (scope: string | null) =>
  useQuery({ queryKey: ['charter', 'versions', scope], queryFn: async () => items(await call<Charter[] | Page<Charter>>('GET', `/charter/${enc(scope!)}/versions`)), enabled: !!scope });
export const useCharterVersion = (scope: string | null, v: number | null) =>
  useQuery({ queryKey: ['charter', 'version', scope, v], queryFn: () => call<Charter>('GET', `/charter/${enc(scope!)}/versions/${v}`), enabled: !!scope && v != null });
export const useCharterDiff = (scope: string | null, v: number | null, against: number | null) =>
  useQuery({ queryKey: ['charter', 'diff', scope, v, against], queryFn: () => call<CharterDiff>('GET', `/charter/${enc(scope!)}/versions/${v}/diff${qs({ against })}`), enabled: !!scope && v != null && against != null && v !== against });
export function useCharterAction() {
  const qc = useQueryClient();
  const done = () => Promise.all([qc.invalidateQueries({ queryKey: ['charter'] }), qc.invalidateQueries({ queryKey: ['decisions'] })]);
  return {
    // A new `proposed` version; nothing reaches an agent until it is sealed.
    propose: useMutation({ mutationFn: (v: { scope: string; body_md: string; red_lines: RedLine[] }) => call<Charter>('PUT', `/charter/${enc(v.scope)}`, { body_md: v.body_md, red_lines: v.red_lines }), onSuccess: done }),
    // Sealed on the version's body_sha256, which the server recomputes: a token for one text cannot seal another (or weaker red lines).
    seal: useMutation({ mutationFn: async (c: Charter) => call<Charter>('POST', `/charter/${enc(c.scope)}/versions/${c.version}/seal`, {}, { 'X-Step-Up': await stepUp('charter.seal', c.body_sha256) }), onSuccess: done }),
  };
}

// --------------------------------------------------------------- knowledge (§20.3) --
export type Layer = 'holding' | 'company' | 'department' | 'employee';
export type KnowledgeKind = 'principle' | 'policy' | 'fact' | 'faq' | 'playbook' | 'support';
export type KnowledgeStatus = 'draft' | 'in_review' | 'approved' | 'expired' | 'retired';
export type KnowledgeEntry = {
  id: string; ref: string; layer: Layer; company: string; department: string | null; kind: KnowledgeKind; title_fa: string; body_md: string;
  sources: Source[]; // at least one
  valid_until: string; // a date
  status: KnowledgeStatus;
  review: { by: Actor; at: string; verdict: 'pass' | 'changes' | 'reject'; checks: { injection: boolean; secrets: boolean; conflicts: boolean; policy: boolean }; notes_md: string } | null;
  approved_by: Actor | null; version: number; created_by: Actor; created_at: string; updated_at: string;
};
export type KnowledgeIn = { layer: Exclude<Layer, 'employee'>; company: string; department?: string | null; kind: Exclude<KnowledgeKind, 'support'>; title_fa: string; body_md: string; sources: Source[]; valid_until: string };
export type KnowledgeFilter = { layer?: Layer | null; company?: string | null; department?: string | null; kind?: KnowledgeKind | null; status?: KnowledgeStatus | null; q?: string; include_expired?: boolean };
/** Longest validity by kind, in days (support articles follow §19). */
export const VALID_DAYS: Record<Exclude<KnowledgeKind, 'support'>, number> = { fact: 90, faq: 180, playbook: 365, policy: 365, principle: 730 };

export const useKnowledge = (f: KnowledgeFilter) =>
  useInfiniteQuery({
    queryKey: ['knowledge', 'list', f.layer ?? '', f.company ?? '', f.department ?? '', f.kind ?? '', f.status ?? '', f.q ?? '', !!f.include_expired],
    queryFn: ({ pageParam }) => call<Page<KnowledgeEntry>>('GET', `/knowledge${qs({ layer: f.layer, company: f.company, department: f.department, kind: f.kind, status: f.status, q: f.q?.trim(), include_expired: f.include_expired || null, limit: 50, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
  });
export const useKnowledgeEntry = (ref: string | null) => useQuery({ queryKey: ['knowledge', 'one', ref], queryFn: () => call<KnowledgeEntry>('GET', `/knowledge/${enc(ref!)}`), enabled: !!ref });
export const useKnowledgeVersions = (ref: string | null) =>
  useQuery({ queryKey: ['knowledge', 'versions', ref], queryFn: async () => items(await call<KnowledgeEntry[] | Page<KnowledgeEntry>>('GET', `/knowledge/${enc(ref!)}/versions`)), enabled: !!ref });
export function useKnowledgeAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['knowledge'] });
  return {
    // What the owner writes is approved by that act.
    create: useMutation({ mutationFn: (b: KnowledgeIn) => call<KnowledgeEntry>('POST', '/knowledge', b), onSuccess: done }),
    update: useMutation({ mutationFn: (v: { ref: string; body: KnowledgeIn }) => call<KnowledgeEntry>('PUT', `/knowledge/${enc(v.ref)}`, v.body), onSuccess: done }),
    retire: useMutation({ mutationFn: (ref: string) => call<KnowledgeEntry>('POST', `/knowledge/${enc(ref)}/retire`, {}), onSuccess: done }),
  };
}

// ------------------------------------------------------ the three cards, scorecard (§20.4) --
export type CardKey = 'stability' | 'growth' | 'safety_cost';
export const CARDS: CardKey[] = ['stability', 'growth', 'safety_cost'];
export type Kpi = {
  id: string; company: string; key: string; card: CardKey; name_fa: string; unit: string; direction: 'up' | 'down';
  source: { kind: 'query'; query: string } | { kind: 'manual' }; freshness_hours: number; target: number | null;
  scorecard: boolean; aggregate: 'sum' | 'avg' | 'min' | 'max'; status: 'active' | 'paused'; version: number;
};
export type KpiValue = { kpi: string; at: string; value: number; source_ref: Source };
export type KpiState = 'ok' | 'stale' | 'no_source';
export type CardKpi = {
  key: string; name_fa: string; unit: string; value: number | null; at: string | null; source_ref: Source | null; target: number | null;
  trend: Array<number | null>; // 30 values, oldest first; a day without a value is null, never zero
  state: KpiState;
};
export type Card = { company: string; card: CardKey; kpis: CardKpi[] };
/** One row of the scorecard: the company's `scorecard` KPIs, each with its card (assumed shape, §20.4 "one row per company"). */
export type ScorecardRow = { company: string; kpis: Array<CardKpi & { card?: CardKey; direction?: 'up' | 'down' }> };
/** The definitions of one company; the set carries the version its PUT matches with If-Match (assumed). */
export type KpiSet = { company: string; version: number; kpis: Kpi[] };
export type KpiPatch = Pick<Kpi, 'key' | 'target' | 'scorecard' | 'status' | 'freshness_hours'>;

/** `company` null = the holding (the server's default). */
export const useCards = (company: string | null) =>
  useQuery({ queryKey: ['cards', company ?? ''], queryFn: async () => items(await call<Card[] | Page<Card>>('GET', `/cards${qs({ company })}`)), placeholderData: keepPreviousData, refetchInterval: 300_000 });
export const useScorecards = (q: string) =>
  useInfiniteQuery({
    queryKey: ['scorecards', q],
    queryFn: ({ pageParam }) => call<Page<ScorecardRow>>('GET', `/scorecards${qs({ q: q.trim(), limit: 50, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
  });
export const useKpis = (company: string | null) =>
  useQuery({ queryKey: ['kpis', company], queryFn: () => call<KpiSet>('GET', `/kpis/${enc(company!)}`), enabled: !!company });
export const useKpiValues = (company: string | null, key: string | null, from: string, to: string) =>
  useQuery({ queryKey: ['kpis', 'values', company, key, from, to], queryFn: async () => items(await call<KpiValue[] | Page<KpiValue>>('GET', `/kpis/${enc(company!)}/${enc(key!)}/values${qs({ from, to })}`)), enabled: !!company && !!key });
export function useKpiAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { set: KpiSet; kpis: KpiPatch[] }) => call<KpiSet>('PUT', `/kpis/${enc(v.set.company)}`, { kpis: v.kpis }, ifMatch(v.set.version)),
    onSuccess: () => Promise.all(['kpis', 'cards', 'scorecards'].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}

// --------------------------------------------------------------------- OKR (§20.5) --
export type ObjectiveStatus = 'draft' | 'proposed' | 'active' | 'closed';
export type Checkin = { at: string; by: Actor; confidence: number; note_md: string; evidence: Source[] };
export type KeyResult = {
  id: string; ref: string; objective: string; title_fa: string; kpi: string | null; metric_fa: string | null;
  start: number; target: number; current: number | null; progress: number; confidence: number; weight: number; checkins: Checkin[];
};
export type Objective = {
  id: string; ref: string; company: string; quarter: string; // Jalali, "1405-Q3"
  title_fa: string; why_md: string; owner: Actor; status: ObjectiveStatus; decision: string | null; key_results: KeyResult[];
};
export const useOkr = (f: { company?: string | null; quarter?: string | null; status?: ObjectiveStatus | null }) =>
  useQuery({ queryKey: ['okr', 'list', f.company ?? '', f.quarter ?? '', f.status ?? ''], queryFn: async () => items(await call<Objective[] | Page<Objective>>('GET', `/okr${qs({ company: f.company, quarter: f.quarter, status: f.status })}`)), placeholderData: keepPreviousData });
export const useObjective = (ref: string | null) => useQuery({ queryKey: ['okr', 'one', ref], queryFn: () => call<Objective>('GET', `/okr/${enc(ref!)}`), enabled: !!ref });
/** Weighted progress of an objective, 0..1. */
export const okrProgress = (o: Objective) => {
  const w = o.key_results.reduce((a, k) => a + k.weight, 0);
  return w ? o.key_results.reduce((a, k) => a + k.progress * k.weight, 0) / w : 0;
};

// ---------------------------------------------------------- decision outcomes (§20.6) --
export type Expected = { metric_fa: string; kpi: string | null; baseline: number; target: number; by_days: 30 | 60 | 90 };
export type Decision = Schemas['Decision'] & { expected?: Expected | null; warnings?: string[]; approver?: Actor | null };
export type Verdict = 'pending' | 'met' | 'partly' | 'missed' | 'unmeasurable';
export type OutcomeReview = {
  id: string; ref: string; decision: string; company: string; day: 30 | 60 | 90; due_at: string; expected: Expected;
  measured: { value: number; at: string; source_ref: Source } | null; verdict: Verdict; proposer: Actor;
  proposer_note_md: string | null; overseer_note_md: string | null; status: 'due' | 'answered' | 'verified';
};
export type OutcomeFilter = { company?: string | null; verdict?: Verdict | null; due?: boolean; decision?: string | null };
export const useOutcomes = (f: OutcomeFilter) =>
  useInfiniteQuery({
    queryKey: ['outcomes', f.company ?? '', f.verdict ?? '', !!f.due, f.decision ?? ''],
    queryFn: ({ pageParam }) => call<Page<OutcomeReview>>('GET', `/outcomes${qs({ company: f.company, verdict: f.verdict, due: f.due || null, decision: f.decision, limit: 100, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
  });
/** Prediction accuracy (§1.16) from the verdicts: met 1, partly ½, missed 0; pending and unmeasurable are not counted. */
export function accuracy(rs: OutcomeReview[]): number | null {
  const scored = rs.filter((r) => r.verdict === 'met' || r.verdict === 'partly' || r.verdict === 'missed');
  return scored.length ? scored.reduce((a, r) => a + (r.verdict === 'met' ? 1 : r.verdict === 'partly' ? 0.5 : 0), 0) / scored.length : null;
}

// ---------------------------------------------------------------- authority (§20.7) --
export type Weekday = 'SA' | 'SU' | 'MO' | 'TU' | 'WE' | 'TH' | 'FR';
export type Limit = { tokens_month?: number; usd?: number; count_day?: number; count_hour?: number; days?: Weekday[]; items?: number };
export type AuthorityRule = {
  key: string; title_fa: string; action: string; actor: string; scope: 'own_company' | 'holding';
  limit: Limit | null; bounds: { min: number; max: number } | null; step_up: boolean; class: 'A0' | 'A1' | 'A2' | 'A3' | 'A4';
  locked: boolean; note_fa: string; version: number;
};
/** One changed row of PUT /authority (assumed body `{rules: [...]}`): unlocked rows only, inside `bounds`. */
export type AuthorityChange = { key: string; actor?: string; limit: Limit | null; version: number };
export const useAuthority = () =>
  useQuery({ queryKey: ['authority'], queryFn: async () => { const x = await call<AuthorityRule[] | Page<AuthorityRule> | { rules: AuthorityRule[] }>('GET', '/authority'); return Array.isArray(x) ? x : 'rules' in x ? x.rules : x.items; } });
export function useAuthorityAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (rules: AuthorityChange[]) => {
      const body = { rules };
      return call<unknown>('PUT', '/authority', body, { 'X-Step-Up': await stepUp('authority.update', await bodyTarget(JSON.stringify(body))) });
    },
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: ['authority'] }), qc.invalidateQueries({ queryKey: ['decisions', 'batchable'] })]),
  });
}
/** The numeric field a row's limit carries, if any (a row is bounded on that one number). */
export const LIMIT_KEYS = ['tokens_month', 'usd', 'count_day', 'count_hour', 'items'] as const;
export const limitNumber = (l: Limit | null): { key: (typeof LIMIT_KEYS)[number]; value: number } | null => {
  if (!l) return null;
  for (const k of LIMIT_KEYS) { const v = l[k]; if (typeof v === 'number') return { key: k, value: v }; }
  return null;
};

// -------------------------------------------------------------------- risks (§20.8) --
export type RiskCategory = 'product' | 'security' | 'data' | 'money' | 'people' | 'vendor' | 'ops' | 'reputation';
export type RiskStatus = 'open' | 'mitigating' | 'accepted' | 'closed';
export type Risk = {
  id: string; ref: string; company: string; title_fa: string; body_md: string; category: RiskCategory;
  likelihood: number; impact: number; score: number; // score = likelihood × impact
  owner: Actor; mitigation_md: string | null; status: RiskStatus; review_at: string; accepted: { decision: string; until: string } | null;
  links: { finding?: string; incident?: string; decision?: string; work?: string }; history: Array<{ at: string; by: Actor; change: string; note: string }>; version: number;
};
/** The 5 × 5 counts; `counts[likelihood − 1][impact − 1]` (assumed shape). */
export type RiskMatrix = { company: string | null; counts: number[][] };
export type RiskIn = { company: string; title_fa: string; body_md: string; category: RiskCategory; likelihood: number; impact: number; owner?: string; mitigation_md?: string | null; review_at?: string };
export type RiskPatch = Partial<Pick<Risk, 'title_fa' | 'body_md' | 'category' | 'likelihood' | 'impact' | 'mitigation_md' | 'status' | 'review_at'>>;
export type RiskFilter = { company?: string | null; status?: RiskStatus | null; category?: RiskCategory | null; min_score?: number | null };
/** Longest review interval by score: ≥ 15 → 14 days, ≥ 8 → 30, else 90. */
export const reviewDays = (score: number) => (score >= 15 ? 14 : score >= 8 ? 30 : 90);

export const useRisks = (f: RiskFilter) =>
  useInfiniteQuery({
    queryKey: ['risks', 'list', f.company ?? '', f.status ?? '', f.category ?? '', f.min_score ?? ''],
    queryFn: ({ pageParam }) => call<Page<Risk>>('GET', `/risks${qs({ company: f.company, status: f.status, category: f.category, min_score: f.min_score, limit: 100, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
  });
export const useRiskMatrix = (company: string | null) => useQuery({ queryKey: ['risks', 'matrix', company ?? ''], queryFn: () => call<RiskMatrix>('GET', `/risks/matrix${qs({ company })}`), placeholderData: keepPreviousData });
export function useRiskAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['risks'] });
  return {
    create: useMutation({ mutationFn: (b: RiskIn) => call<Risk>('POST', '/risks', b), onSuccess: done }),
    patch: useMutation({ mutationFn: (v: { r: Risk; patch: RiskPatch }) => call<Risk>('PATCH', `/risks/${enc(v.r.ref)}`, v.patch, ifMatch(v.r.version)), onSuccess: done }),
  };
}

// ----------------------------------------------------------------- calendar (§20.9) --
export type CalendarKind = 'deploy' | 'campaign' | 'event' | 'maintenance' | 'meeting' | 'freeze' | 'holiday';
export type CalendarEvent = {
  id: string; ref: string; company: string | null; kind: CalendarKind; title_fa: string; starts_at: string; ends_at: string;
  source: { decision?: string; work?: string; meeting?: string; order?: string }; status: 'planned' | 'done' | 'cancelled';
  risk: 'low' | 'medium' | 'high'; created_by: Actor;
  version?: number; // §20.9 lists no version, but its PATCH takes If-Match (§1); sent when the server gives one
};
export type Conflict = { a: string; b: string; rule: string; severity: 'medium' | 'high'; note_fa: string };
export type CalendarView = { events: CalendarEvent[]; conflicts: Conflict[] };
export type CalendarIn = { company: string | null; kind: Exclude<CalendarKind, 'meeting' | 'holiday' | 'deploy'>; title_fa: string; starts_at: string; ends_at: string; risk: CalendarEvent['risk'] };
export const useCalendar = (f: { company?: string | null; from: string; to: string; kind?: CalendarKind | null }) =>
  useQuery({
    queryKey: ['calendar', f.company ?? '', f.from, f.to, f.kind ?? ''],
    queryFn: () => call<CalendarView>('GET', `/calendar${qs({ company: f.company, from: f.from, to: f.to, kind: f.kind })}`), placeholderData: keepPreviousData,
  });
export function useCalendarAction() {
  const qc = useQueryClient();
  const done = () => Promise.all([qc.invalidateQueries({ queryKey: ['calendar'] }), qc.invalidateQueries({ queryKey: ['planner'] })]);
  return {
    create: useMutation({ mutationFn: (b: CalendarIn) => call<CalendarEvent>('POST', '/calendar', b), onSuccess: done }),
    patch: useMutation({
      mutationFn: (v: { e: CalendarEvent; patch: Partial<Pick<CalendarEvent, 'status' | 'starts_at' | 'ends_at' | 'title_fa' | 'risk'>> }) =>
        call<CalendarEvent>('PATCH', `/calendar/${enc(v.e.ref)}`, v.patch, v.e.version != null ? ifMatch(v.e.version) : {}),
      onSuccess: done,
    }),
  };
}

// --------------------------------------------------------------- batch seal (§20.10) --
export type Batchable = {
  ref: string; version: number; kind: string; company: string; title: string; quota_estimate: { tokens: number; usd: string }; proposer: Actor;
  risk?: string; created_at?: string; expires_at?: string | null;
};
export type BatchItem = { ref: string; version: number };
export type BatchOut = { batch: string; items: Array<{ ref: string; resolution: string | null }> };
export const BATCH_KINDS = new Set(['proposal', 'meeting_resolution', 'knowledge_entry']);
export const useBatchable = () =>
  useQuery({ queryKey: ['decisions', 'batchable'], queryFn: async () => items(await call<Batchable[] | Page<Batchable>>('GET', '/decisions/batchable')), refetchInterval: 60_000 });
/** The exact set the passkey is bound to: `[{ref, version}]` sorted by ref, canonical JSON (keys sorted, no spaces). */
export const batchItems = (xs: BatchItem[]): BatchItem[] => [...xs].sort((a, b) => (a.ref < b.ref ? -1 : a.ref > b.ref ? 1 : 0)).map((x) => ({ ref: x.ref, version: x.version }));
export const batchTarget = (xs: BatchItem[]) => bodyTarget(JSON.stringify(batchItems(xs)));
export function useBatchSeal() {
  const qc = useQueryClient();
  return useMutation({
    // All or nothing. The key is required (a decision action): one per press, kept across a retry of the same set.
    mutationFn: async (v: { items: BatchItem[]; key: string }) => {
      const set = batchItems(v.items);
      const token = await stepUp('decision.batch', await batchTarget(set));
      return call<BatchOut>('POST', '/decisions/batch/approve', { items: set }, { 'X-Step-Up': token, 'Idempotency-Key': v.key });
    },
    onSuccess: () => Promise.all(['decisions', 'inbox', 'away', 'resolutions', 'meetings', 'knowledge', 'outcomes'].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}
/** `422 batch_not_eligible`: which card and why, from `fields.items`. */
export function batchReasons(e: unknown): Array<{ ref: string; reason: string }> {
  if (!(e instanceof ApiError) || e.code !== 'batch_not_eligible') return [];
  const xs = (e.fields as unknown as { items?: unknown } | null | undefined)?.items;
  return Array.isArray(xs) ? xs.filter((x): x is { ref: string; reason: string } => !!x && typeof (x as { ref?: unknown }).ref === 'string').map((x) => ({ ref: x.ref, reason: String(x.reason ?? '') })) : [];
}

// ----------------------------------------------------------------- codes (§20.11, §14) --
const CODE_FA: Record<string, string> = {
  meeting_not_live: 'جلسه الان زنده نیست؛ ورود تو فقط در جلسه‌ی زنده ممکن است.',
  knowledge_expired: 'این ورودی دانشنامه منقضی شده و به‌عنوان منبع پذیرفته نمیشود.',
  batch_not_eligible: 'یکی از کارت‌ها عوض شده یا دیگر برای مُهر گروهی شایسته نیست؛ هیچ کارتی مُهر نشد.',
  decision_not_pending: 'این کارت دیگر منتظر مُهر نیست؛ نسخه‌ی پایه عوض شده و کارت تازه میاید.',
  version_conflict: 'همین حالا عوض شده؛ دوباره نگاه کن و بعد ذخیره کن.',
};
/** The Persian sentence for a failed §20 call; the server's own sentence for everything else. */
export function faError(e: unknown): string {
  if (!(e instanceof ApiError)) return e instanceof Error ? e.message : 'انجام نشد.';
  return CODE_FA[e.code] ?? e.messageFa;
}
