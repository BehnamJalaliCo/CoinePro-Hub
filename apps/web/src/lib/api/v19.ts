'use client';

// Contract v1.6 §22 (prompt 13): the media studio and the legal counsel. Departments defined by mandate and identity, roles written on
// demand by a department's manager, each company's media pipeline (script → direction → motion graphics as code → voice → sandboxed
// render → checks → publishing only through the official Telegram and Instagram APIs, under a series the owner seals once), the hub's own
// open-source voice chosen by the owner's ear, and the holding's legal counsel (cases LC-…, thread L, every outgoing email sealed).
// The server builds it in prompt 13; until the OpenAPI file is regenerated, the types live here, written from the contract (nullable
// exactly as written). Where §22 leaves a shape open, the reading here is marked "assumed" and listed for §22.7.

import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { bodyTarget, stepUp } from '@/lib/auth';
import { ApiError, type Schemas } from './client';
import { call, type Actor } from './v13';
import { ifMatch, qs } from './v15';
import type { EvalRun } from './v14';
import type { FileRef } from './v18';

type Page<T> = { items: T[]; next_cursor: string | null };
const items = <T>(x: T[] | Page<T>): T[] => (Array.isArray(x) ? x : x.items);
const enc = encodeURIComponent;
async function orNull<T>(p: Promise<T>): Promise<T | null> {
  try { return await p; } catch (e) { if (e instanceof ApiError && e.status === 404) return null; throw e; }
}

export type ModelCeiling = 'claude-haiku-5-5' | 'claude-sonnet-5-5' | 'claude-opus-5-5';
export const MODEL_ORDER: ModelCeiling[] = ['claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5'];

// ------------------------------------------------- department mandate and identity (§22.1) --
export type Mandate = {
  from_fa: string; to_fa: string; // «مبدأ و مقصد»: what it starts from, what it must reach
  outputs_fa: string[]; boundaries_fa: string[];
  tool_ceiling: string[]; model_ceiling: ModelCeiling;
};
export type TeamRole = { role: string; title_fa: string; why_fa: string; first: boolean }; // a starting suggestion, never a limit
export type Department19 = Schemas['Department'] & { mandate?: Mandate | null; identity_md?: string | null; team?: TeamRole[] };
export type MandateIn = { mandate: Mandate; identity_md: string };

/** The same query as the base departments hook (one cache entry), read with the §22.1 fields. */
export const useDepartments19 = (code: string) =>
  useQuery({ queryKey: ['companies', code, 'departments'], queryFn: () => call<Department19[]>('GET', `/companies/${enc(code)}/departments`), enabled: !!code });
export function useMandateAction() {
  const qc = useQueryClient();
  return useMutation({
    // Sealed on the SHA-256 of the exact body (`department.mandate`), with the department's version.
    mutationFn: async (v: { company: string; d: Department19; body: MandateIn }) => {
      const text = JSON.stringify(v.body);
      return call<Department19>('PUT', `/companies/${enc(v.company)}/departments/${enc(v.d.code)}/mandate`, v.body, { ...ifMatch(v.d.version), 'X-Step-Up': await stepUp('department.mandate', await bodyTarget(text)) });
    },
    onSuccess: (_d, v) => qc.invalidateQueries({ queryKey: ['companies', v.company, 'departments'] }),
  });
}

// ------------------------------------------------------------- roles on demand (§22.5) --
export type RoleDraftState = 'drafting' | 'in_review' | 'eval' | 'proposed' | 'active' | 'rejected' | 'retired';
export type RoleChecks = { injection: boolean; secrets: boolean; conflicts: boolean; policy: boolean; ceiling: boolean };
export type EvalCase = { id: string; input_md: string; rubric_md: string; weight: number };
export type RoleDraft = {
  id: string; ref: string; company: string; department: string; role: string; title_fa: string; title_en: string; why_md: string;
  charter_md: string; tools: string[]; model: string; effort: string;
  limits: { steps_per_run: number; tokens_per_step: number; tokens_per_run: number };
  eval: { suite: string; cases: EvalCase[] }; // at least 3 cases written with the draft
  state: RoleDraftState;
  review: { by: Actor; verdict: 'pass' | 'changes' | 'reject'; checks: RoleChecks; sha256: string } | null;
  eval_run: EvalRun | null; approver: Actor | null; decision_ref: string | null; version: number; created_at: string; activated_at: string | null;
  // assumed: who asked and what, what the manager compared, the rule-based originality check, hires on it, when it was retired
  brief_md?: string | null; requested_by?: Actor | null; written_by?: Actor | null; compared?: string[];
  originality?: { ok: boolean; closest: string | null; note_fa: string | null } | null; hires?: number; retired_at?: string | null; state_note_fa?: string | null;
};
export const useRoleDrafts = (f: { company?: string | null; department?: string | null; state?: RoleDraftState | null } = {}) =>
  useQuery({
    queryKey: ['roles', 'drafts', f.company ?? '', f.department ?? '', f.state ?? ''],
    queryFn: async () => items(await call<RoleDraft[] | Page<RoleDraft>>('GET', `/roles/drafts${qs({ company: f.company, department: f.department, state: f.state })}`)),
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.some((d) => ['drafting', 'in_review', 'eval'].includes(d.state)) ? 5_000 : false),
  });
export const useRoleDraft = (ref: string | null) =>
  useQuery({ queryKey: ['roles', 'draft', ref], queryFn: () => call<RoleDraft>('GET', `/roles/drafts/${enc(ref!)}`), enabled: !!ref });
export function useRoleDraftAction() {
  const qc = useQueryClient();
  const done = () => Promise.all(['roles', 'stories', 'decisions', 'inbox'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    // Owner: «یه تدوینگر پادکست میخوام»; the department's manager is woken to write it.
    ask: useMutation({ mutationFn: (v: { company: string; department: string; brief_md: string; key: string }) => call<RoleDraft>('POST', '/roles/drafts', { company: v.company, department: v.department, brief_md: v.brief_md }, { 'Idempotency-Key': v.key }), onSuccess: done }),
    // Stops new hires on it; employees on it keep running until moved or dismissed.
    retire: useMutation({ mutationFn: (ref: string) => call<RoleDraft>('POST', `/roles/drafts/${enc(ref)}/retire`, {}), onSuccess: done }),
  };
}

// --------------------------------------------------------------- the media studio (§22.2) --
export type MediaKind = 'reel' | 'story' | 'post' | 'carousel';
export type Channel = 'telegram' | 'instagram';
export type MediaPlacement = 'telegram_post' | 'telegram_story' | 'instagram_reel' | 'instagram_story' | 'instagram_post';
export type Aspect = '9:16' | '4:5' | '1:1' | '16:9';
export type CheckKey = 'brand' | 'red_lines' | 'risk_warning' | 'facts' | 'rights' | 'platform' | 'qc';
export const CHECKS: CheckKey[] = ['brand', 'red_lines', 'risk_warning', 'facts', 'rights', 'platform', 'qc'];
export type SeriesTarget = { channel: Channel; account: string; placement: MediaPlacement };
export type SeriesFormat = {
  aspect: Aspect; duration_s: number | null; voice: { voice_id: string } | null; captions: boolean; music: 'none' | 'library';
  overlay: { cta_fa: string | null; mark: boolean };
};
export type SeriesStatus = 'draft' | 'proposed' | 'sealed' | 'paused' | 'retired';
export type Series = {
  id: string; ref: string; company: string; title_fa: string; kind: MediaKind; targets: SeriesTarget[];
  schedule: string; // RRULE in the owner's time zone
  topics: { pool: string[]; rule_fa: string | null } | null; format: SeriesFormat; checks: CheckKey[];
  auto_publish: boolean; max_per_day: number; status: SeriesStatus; digest: string; version: number; sealed_at: string | null;
  // assumed: who proposed it and its card, the next runs (server-computed from the RRULE), today's count, when it last changed
  proposed_by?: Actor | null; decision_ref?: string | null; next_at?: string[]; today?: { made: number; published: number } | null;
  items_total?: number; created_at?: string; updated_at?: string; status_note_fa?: string | null;
};
export type SeriesIn = Pick<Series, 'company' | 'title_fa' | 'kind' | 'targets' | 'schedule' | 'topics' | 'format' | 'checks' | 'auto_publish' | 'max_per_day'>;

export type ItemState = 'scripting' | 'directing' | 'composing' | 'voicing' | 'rendering' | 'checking' | 'review' | 'scheduled' | 'published' | 'waiting_owner' | 'held' | 'failed' | 'rejected';
export type Source = { kind: string; ref?: string | null; url?: string | null; note: string };
export type Shot = { n: number; duration_s: number; visual_fa: string; text_on_screen_fa: string | null; voice_fa: string | null };
export type CheckResult = { key: CheckKey; result: 'pass' | 'fail' | 'n/a'; note_fa: string | null };
export type PublishRow = { channel: Channel; placement: MediaPlacement; at: string | null; external_id: string | null; url: string | null; error: string | null };
export type MediaFile = FileRef & { width?: number; height?: number; duration_s?: number }; // §17.1 metadata, as files carry it
export type MediaItem = {
  id: string; ref: string; company: string; series: string | null; kind: MediaKind | 'design'; title_fa: string; state: ItemState;
  script: { text_fa: string; sources: Source[]; by: Actor } | null;
  direction: { shots: Shot[]; by: Actor } | null;
  composition: { format: 'html' | 'lottie'; sha256: string; by: Actor } | null;
  assets: MediaFile[]; voice: MediaFile | null; render: MediaFile | null; captions: MediaFile | null;
  checks: CheckResult[]; qc: { by: Actor; verdict: 'pass' | 'changes' | 'reject'; note_md: string } | null;
  publish: PublishRow[]; decision_ref: string | null; ai_generated: true; cost: { tokens: number; usd: string };
  created_at: string; updated_at: string; version: number;
  // assumed: the brief of a one-off or design item, the series topic, the design's deliverable, why it is held or failed, renders of a carousel
  brief_md?: string | null; topic_fa?: string | null; deliverable_ref?: string | null; state_note_fa?: string | null; pages?: MediaFile[];
};
export type Voice = {
  id: string; engine: string; name_fa: string; licence: string; licence_commercial: boolean;
  rtf: number | null; mem_mb: number | null; owner_score: number | null; status: 'candidate' | 'active' | 'retired';
  // assumed: whose voice it speaks in, the bake-off clips, a note when it cannot be measured yet
  speaker?: 'model' | 'owner'; clones?: boolean; samples?: VoiceSample[]; note_fa?: string | null; measured_at?: string | null; version?: number;
};
export type VoiceSample = { script: string; title_fa: string; text_fa: string; file: MediaFile };
export type VoiceReference = { file: MediaFile; duration_s: number; created_at: string; state: 'processing' | 'ready' | 'rejected'; reason_fa: string | null };
/** A publishing account's own limit and today's use (assumed `GET /media/limits`). */
export type PlatformLimit = { account: string; channel: Channel; company: string; per_24h: number | null; used_24h: number; resets_at: string | null; note_fa: string | null };

const ITEM_LIVE: ItemState[] = ['scripting', 'directing', 'composing', 'voicing', 'rendering', 'checking'];
export const useSeriesList = (f: { company?: string | null; status?: SeriesStatus | null } = {}) =>
  useQuery({ queryKey: ['media', 'series', f.company ?? '', f.status ?? ''], queryFn: async () => items(await call<Series[] | Page<Series>>('GET', `/media/series${qs({ company: f.company, status: f.status })}`)), placeholderData: keepPreviousData });
export function useSeriesAction() {
  const qc = useQueryClient();
  const done = () => Promise.all(['media', 'decisions', 'inbox'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    // Creates a `draft`; nothing runs until it is sealed.
    create: useMutation({ mutationFn: (v: { body: SeriesIn; key: string }) => call<Series>('POST', '/media/series', v.body, { 'Idempotency-Key': v.key }), onSuccess: done }),
    // A sealed series edited goes back to `proposed`: its seal no longer covers it.
    update: useMutation({ mutationFn: (v: { s: Series; body: SeriesIn }) => call<Series>('PUT', `/media/series/${enc(v.s.ref)}`, v.body, ifMatch(v.s.version)), onSuccess: done }),
    // 🔏 `media.series` on the series digest: the seal covers exactly this version.
    seal: useMutation({ mutationFn: async (s: Series) => call<Series>('POST', `/media/series/${enc(s.ref)}/seal`, { digest: s.digest }, { 'X-Step-Up': await stepUp('media.series', s.digest) }), onSuccess: done }),
    pause: useMutation({ mutationFn: (ref: string) => call<Series>('POST', `/media/series/${enc(ref)}/pause`, {}), onSuccess: done }),
    retire: useMutation({ mutationFn: (ref: string) => call<Series>('POST', `/media/series/${enc(ref)}/retire`, {}), onSuccess: done }),
  };
}
export const useMediaItems = (f: { company?: string | null; series?: string | null; state?: ItemState | null } = {}) =>
  useInfiniteQuery({
    queryKey: ['media', 'items', f.company ?? '', f.series ?? '', f.state ?? ''],
    queryFn: ({ pageParam }) => call<Page<MediaItem>>('GET', `/media/items${qs({ company: f.company, series: f.series, state: f.state, limit: 100, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.pages.some((p) => p.items.some((x) => ITEM_LIVE.includes(x.state))) ? 15_000 : false),
  });
export const useMediaItem = (ref: string | null) =>
  useQuery({ queryKey: ['media', 'item', ref], queryFn: () => call<MediaItem>('GET', `/media/items/${enc(ref!)}`), enabled: !!ref });
export function useMediaItemAction() {
  const qc = useQueryClient();
  const done = () => Promise.all(['media', 'decisions', 'inbox'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    // A one-off always ends as a card; `design` is a UI mockup for the CTO and is never published.
    create: useMutation({ mutationFn: (v: { body: { company: string; kind: MediaKind | 'design'; brief_md: string; series?: string }; key: string }) => call<MediaItem>('POST', '/media/items', v.body, { 'Idempotency-Key': v.key }), onSuccess: done }),
    // 🔏 `media.unpublish` on the ref; deleted through the same API where the platform allows it.
    unpublish: useMutation({ mutationFn: async (ref: string) => call<MediaItem>('POST', `/media/items/${enc(ref)}/unpublish`, {}, { 'X-Step-Up': await stepUp('media.unpublish', ref) }), onSuccess: done }),
  };
}
export const usePlatformLimits = () =>
  useQuery({ queryKey: ['media', 'limits'], queryFn: async () => items(await call<PlatformLimit[] | Page<PlatformLimit>>('GET', '/media/limits')), refetchInterval: 120_000 });

export const useVoices = () => useQuery({ queryKey: ['media', 'voices'], queryFn: async () => items(await call<Voice[] | Page<Voice>>('GET', '/media/voices')) });
/** The owner's own recorded reference; null while none was recorded (assumed `GET /media/voices/reference`, 404 when none). */
export const useVoiceReference = () =>
  useQuery({ queryKey: ['media', 'voices', 'reference'], queryFn: () => orNull(call<VoiceReference>('GET', '/media/voices/reference')), refetchInterval: (q) => (q.state.data?.state === 'processing' ? 4_000 : false) });
export function useVoiceAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['media', 'voices'] });
  return {
    // The owner's blind listening score, 1..10.
    score: useMutation({ mutationFn: (v: { id: string; score: number }) => call<Voice>('POST', `/media/voices/${enc(v.id)}/score`, { score: v.score }), onSuccess: done }),
    // Owner only; 1–3 minutes of clean speech, stored like any owner file and never sent anywhere.
    reference: useMutation({ mutationFn: (fileId: string) => call<VoiceReference>('POST', '/media/voices/reference', { file_id: fileId }), onSuccess: done }),
    // Assumed: the owner's explicit choice, 🔏 `voice.activate` on the voice id; a non-commercial licence must be acknowledged in the body.
    activate: useMutation({
      mutationFn: async (v: Voice) => call<Voice>('POST', `/media/voices/${enc(v.id)}/activate`, v.licence_commercial ? {} : { accept_non_commercial: true }, { 'X-Step-Up': await stepUp('voice.activate', v.id) }),
      onSuccess: done,
    }),
  };
}

// --------------------------------------------------------------- the legal counsel (§22.4) --
export type CaseKind = 'platform_restriction' | 'account_appeal' | 'takedown' | 'partner_dispute' | 'policy_review' | 'contract_review' | 'compliance' | 'other';
export type CaseStatus = 'open' | 'waiting_reply' | 'waiting_owner' | 'resolved' | 'closed';
export type TimelineEntry = { at: string; kind: 'note' | 'email_out' | 'email_in' | 'form' | 'decision'; ref: string | null; summary_fa: string };
export type LegalCase = {
  id: string; ref: string; company: string; title_fa: string; kind: CaseKind;
  counterpart: { name: string; channel: 'email' | 'form' | 'portal' | 'other'; address: string | null };
  status: CaseStatus; timeline: TimelineEntry[]; deadlines: Array<{ at: string; what_fa: string }>;
  opened_by: Actor; created_at: string; updated_at: string; version: number;
  // assumed: the brief it was opened with; on GET one, the emails (the full thread)
  brief_md?: string | null; emails?: CaseEmail[];
};
export type EmailDraft = { case: string; from: string; to: string[]; cc: string[]; subject: string; body_md: string; attachments: FileRef[]; lang: 'fa' | 'en'; digest: string };
/** One message of a case's thread (assumed): an outgoing draft is its `email_send` card until sealed; incoming replies are masked. */
export type CaseEmail = EmailDraft & {
  id: string; direction: 'out' | 'in'; state: 'waiting_seal' | 'sent' | 'received' | 'superseded' | 'rejected';
  decision_ref: string | null; message_id: string | null; at: string;
};
export const useCases = (f: { company?: string | null; status?: CaseStatus | null } = {}) =>
  useInfiniteQuery({
    queryKey: ['legal', 'cases', f.company ?? '', f.status ?? ''],
    queryFn: ({ pageParam }) => call<Page<LegalCase>>('GET', `/legal/cases${qs({ company: f.company, status: f.status, limit: 50, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
  });
export const useCase = (ref: string | null) =>
  useQuery({ queryKey: ['legal', 'case', ref], queryFn: () => call<LegalCase>('GET', `/legal/cases/${enc(ref!)}`), enabled: !!ref });
export function useCaseAction() {
  const qc = useQueryClient();
  const done = () => Promise.all(['legal', 'threads', 'decisions', 'inbox'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    open: useMutation({ mutationFn: (v: { body: { company: string; title_fa: string; kind: CaseKind; brief_md: string; file_ids?: string[] }; key: string }) => call<LegalCase>('POST', '/legal/cases', v.body, { 'Idempotency-Key': v.key }), onSuccess: done }),
    close: useMutation({ mutationFn: (ref: string) => call<LegalCase>('POST', `/legal/cases/${enc(ref)}/close`, {}), onSuccess: done }),
  };
}

// ------------------------------------------------------------- kinds and codes (§22.6, §14) --
/** The decision kinds of §22, and how each is sealed. */
export const MEDIA_KINDS = ['media_series', 'media_publish', 'email_send', 'role_new'] as const;
/** `email_send` is sealed on the exact message: the step-up target is the message digest, not the card's ref (§22.6). */
export function sealTarget(d: { kind: string; ref: string; payload?: unknown }): string {
  if (d.kind === 'email_send') {
    const digest = (d.payload as Partial<EmailDraft> | null)?.digest;
    if (digest) return digest;
  }
  return d.ref;
}

const CODE_FA: Record<string, string> = {
  series_not_sealed: 'این برنامه‌ی انتشار مُهر نشده؛ چیزی خودکار منتشر نمیشود و آیتم کارت میشود.',
  platform_limit: 'سقف انتشار خود پلتفرم برای این حساب پر شده',
  held: 'ناظر کل این را نگه داشته؛ تا تصمیم تو کاری روی آن انجام نمیشود.',
  account_not_configured: 'این حساب هنوز کلید ندارد؛ با make account-secret روی سرور واردش کن.',
  version_conflict: 'همین حالا عوض شده؛ دوباره نگاه کن و بعد ذخیره کن.',
  precondition_required: 'نسخه همراه درخواست نیامد؛ صفحه را تازه کن.',
  decision_not_pending: 'این کارت دیگر منتظر تصمیم نیست.',
  company_locked: 'کلید توقف این شرکت روشن است؛ هیچ انتشاری انجام نمیشود.',
  policy_denied: 'سیاست این کار را اجازه نمیدهد.',
  not_ready: 'این کار روی این نسخه‌ی سرور هنوز آماده نیست.',
};
/** The Persian sentence for a failed §22 call; the server's own sentence for everything else. */
export function faError(e: unknown): string {
  if (!(e instanceof ApiError)) return e instanceof Error ? e.message : 'انجام نشد.';
  const base = CODE_FA[e.code] ?? e.messageFa;
  if ((e.code === 'platform_limit' || e.code === 'rate_limited') && e.retryAfter) {
    return `${base}؛ ${e.retryAfter < 5400 ? `${Math.ceil(e.retryAfter / 60)} دقیقه‌ی` : `${Math.round(e.retryAfter / 3600)} ساعت`} دیگر.`;
  }
  if (e.code === 'validation_failed' && e.fields && Object.keys(e.fields).length) return `${e.messageFa} (${Object.keys(e.fields).join('، ')})`;
  return base;
}
