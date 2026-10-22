'use client';

// Contract v1.5 §19 (prompt 10): the revenue radar, the funnel and referral rescue, the support desk the owner teaches, the shadow test,
// templates, lifecycle rules and NPS, the feedback inbox and intake from outside. The server builds it in prompt 10; until the OpenAPI
// file is regenerated, the types live here, written from the contract. Money and USDT are decimal strings (§1); rates are 0..1.

import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { bodyTarget, stepUp } from '@/lib/auth';
import { ApiError } from './client';
import { call } from './v13';
import { ifMatch, qs } from './v15';

type Page<T> = { items: T[]; next_cursor: string | null };
/** §19 names a cursor only on conversations, rescue cases and feedback; the other lists are read either bare or paged. */
const items = <T>(x: T[] | Page<T>): T[] => (Array.isArray(x) ? x : x.items);
const enc = encodeURIComponent;

// ------------------------------------------------------------ revenue radar (§19.1) --
export type RevenuePeriod = 'day' | 'week' | 'month';
export type RevenueAccount = {
  id: string; company: string; exchange: string; adapter: string; service_account: string; // a §18.13 service account
  title_fa: string; status: 'not_configured' | 'ok' | 'error'; last_pull_at: string | null; last_error: string | null; version: number;
};
export type RevenueDay = {
  company: string; account: string; day: string; // the exchange's settlement day (lbank: T+1, UTC+8)
  commission_usdt: string; by_coin: Array<{ coin: string; amount: string; usdt: string; price_source: string }>; fees_usdt: string | null; volume_usdt: string | null;
  new_invitees: number; active_traders: number | null; deposits_usdt: string | null;
  complete: boolean; pulled_at: string; source: { adapter: string; endpoints: string[] };
};
export type RevenueAlert = { kind: 'drop' | 'pull_failed' | 'incomplete'; company: string; account: string | null; note_fa: string };
export type RevenueSummary = {
  period: RevenuePeriod; from: string; to: string; total_usdt: string; prev_total_usdt: string | null;
  by_company: Array<{ company: string; usdt: string; token_cost_usd: string; net_usd: string; share: number }>;
  by_account: Array<{ account: string; company: string; usdt: string }>; trend: Array<{ day: string; usdt: string }>;
  alerts: RevenueAlert[];
};
export type RevenueAccountIn = { company: string; exchange: string; adapter: string; service_account: string; title_fa: string };

export const useRevenueSummary = (period: RevenuePeriod, company?: string | null) =>
  useQuery({ queryKey: ['revenue', 'summary', period, company ?? ''], queryFn: () => call<RevenueSummary>('GET', `/revenue/summary${qs({ period, company })}`), placeholderData: keepPreviousData, refetchInterval: 300_000 });
/** Unpaged, at most 400 rows. */
export const useRevenueDays = (f: { from: string; to: string; company?: string | null; account?: string | null }) =>
  useQuery({ queryKey: ['revenue', 'days', f.from, f.to, f.company ?? '', f.account ?? ''], queryFn: async () => items(await call<RevenueDay[] | Page<RevenueDay>>('GET', `/revenue/days${qs(f)}`)) });
export const useRevenueAccounts = () => useQuery({ queryKey: ['revenue', 'accounts'], queryFn: async () => items(await call<RevenueAccount[] | Page<RevenueAccount>>('GET', '/revenue/accounts')) });
export function useRevenueAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['revenue'] });
  return {
    // Adds or changes the account of `exchange` + `company`, sealed on the exact body. The key and secret never pass here (`make account-secret`).
    save: useMutation({ mutationFn: async (body: RevenueAccountIn) => call<RevenueAccount>('POST', '/revenue/accounts', body, { 'X-Step-Up': await stepUp('revenue.account', await bodyTarget(JSON.stringify(body))) }), onSuccess: done }),
    // ≤ 31 days, rate-limited like the schedule. The key is required: a retry of the same press sends the same key.
    pull: useMutation({ mutationFn: (v: { id: string; key: string; from?: string; to?: string }) => call<unknown>('POST', `/revenue/accounts/${enc(v.id)}/pull${qs({ from: v.from, to: v.to })}`, {}, { 'Idempotency-Key': v.key }), onSuccess: done }),
  };
}

// ------------------------------------------------------- funnel and rescue (§19.2) --
export type FunnelStageKey = 'visit' | 'signup' | 'referral_verified' | 'min_balance' | 'vip_active';
export type Funnel = {
  company: string; period: 'week' | 'month'; from: string; to: string;
  // A stage with no source is `connected: false, count: null`; a rate is never estimated.
  stages: Array<{ key: FunnelStageKey; label_fa: string; count: number | null; connected: boolean; source: 'affiliate' | 'product_events' | 'support' | 'analytics' | null }>;
  conversions: Array<{ from: string; to: string; rate: number | null }>; leaks: Array<{ stage: string; note_fa: string; rate: number; median_rate: number }>;
};
export type RescueState = 'open' | 'contacted' | 'rescued' | 'lost' | 'opted_out';
export type RescueCase = {
  id: string; ref: string; company: string; source: 'support' | 'product'; conversation: string | null; exchange: string;
  subject: string; state: RescueState; // subject: a keyed pseudonym, never the handle or the exchange UID
  steps: Array<{ at: string; kind: 'check' | 'message' | 'follow_up' | 'note'; template: string | null; result_fa: string }>;
  opened_at: string; rescued_at: string | null; closed_at: string | null;
};
export const useFunnel = (company: string | null, period: 'week' | 'month') =>
  useQuery({ queryKey: ['growth', 'funnel', company, period], queryFn: () => call<Funnel>('GET', `/growth/funnel${qs({ company, period })}`), enabled: !!company, placeholderData: keepPreviousData });
export const useRescueCases = (f: { company?: string | null; state?: RescueState | null }) =>
  useInfiniteQuery({
    queryKey: ['growth', 'rescue', f.company ?? '', f.state ?? ''],
    queryFn: ({ pageParam }) => call<Page<RescueCase>>('GET', `/growth/rescue${qs({ company: f.company, state: f.state, limit: 50, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
  });
export const useRescueCase = (ref: string | null) => useQuery({ queryKey: ['growth', 'rescue', 'one', ref], queryFn: () => call<RescueCase>('GET', `/growth/rescue/${enc(ref!)}`), enabled: !!ref });

// ------------------------------------------------------------ support desk (§19.3) --
export type ChannelKind = 'telegram_business' | 'telegram_bot' | 'chatwoot' | 'product_bot' | 'mystery';
export type ChannelState = 'not_configured' | 'shadow' | 'live' | 'paused';
export type AutoSend = 'kb_verbatim' | 'kb_grounded' | 'off';
export type SupportChannel = {
  company: string; kind: ChannelKind; state: ChannelState; live_since: string | null; paused_reason: string | null;
  auto_send: AutoSend; // what may leave without the owner
  version?: number; // §19.3 lists no version, but its PATCH takes If-Match (§1); sent when the server gives one
};
export type ConversationState = 'open' | 'waiting_owner' | 'answered' | 'closed';
export type HandoffReason = 'no_kb' | 'low_confidence' | 'blocked' | 'asked_for_human' | 'complaint' | 'security';
export type Conversation = {
  id: string; ref: string; company: string; channel: ChannelKind; customer: { display_name: string | null; handle_masked: string; lang: string };
  state: ConversationState; opened_at: string; last_message_at: string; handoff: { reason: HandoffReason; at: string } | null;
  tags: string[]; rescue: string | null; csat: number | null; mystery: boolean;
};
export type GuardCode = 'asks_secret' | 'unknown_link' | 'unknown_code' | 'profit_promise' | 'customer_data' | 'internal_data' | 'too_long' | 'red_line';
export type SupportMessage = {
  id: string; conversation: string; at: string; direction: 'in' | 'out'; author: 'customer' | 'agent' | 'owner' | 'rule';
  body: string; // masked: secrets, cards and seed phrases are never stored raw
  status: 'draft' | 'queued' | 'sent' | 'blocked' | 'failed'; kb_refs: string[]; confidence: number | null;
  checks: { guard: 'pass' | 'fail'; grounded: 'pass' | 'fail' | null }; blocked_reasons: string[];
};
export type ConversationDetail = Conversation & { messages: SupportMessage[] };
export type QueueItem = { conversation: string; kind: 'handoff' | 'low_confidence' | 'blocked' | 'shadow_disagreement'; since: string; draft: SupportMessage | null; company: string };
export type ConversationFilter = { company?: string | null; state?: ConversationState | null; channel?: ChannelKind | null; q?: string };

export const useChannels = (company?: string | null) => useQuery({ queryKey: ['support', 'channels', company ?? ''], queryFn: async () => items(await call<SupportChannel[] | Page<SupportChannel>>('GET', `/support/channels${qs({ company })}`)) });
/** Widening needs a passkey: to `kb_grounded`, or a paused channel that already went live back to `live`. Narrowing needs none. */
export const widens = (c: SupportChannel, p: { auto_send?: AutoSend; state?: 'live' }) => (p.auto_send === 'kb_grounded' && c.auto_send !== 'kb_grounded') || (p.state === 'live' && c.state !== 'live');
export function useChannelAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['support'] });
  return {
    // Stopping is always safe: no step-up.
    pause: useMutation({ mutationFn: (c: SupportChannel) => call<SupportChannel>('POST', `/support/channels/${enc(c.company)}/${c.kind}/pause`, {}), onSuccess: done }),
    patch: useMutation({
      mutationFn: async (v: { c: SupportChannel; patch: { auto_send?: AutoSend; state?: 'live' } }) => {
        const h: Record<string, string> = v.c.version != null ? ifMatch(v.c.version) : {};
        if (widens(v.c, v.patch)) h['X-Step-Up'] = await stepUp('support.channel', `${v.c.company}/${v.c.kind}@${v.patch.auto_send ?? v.c.auto_send}`);
        return call<SupportChannel>('PATCH', `/support/channels/${enc(v.c.company)}/${v.c.kind}`, v.patch, h);
      },
      onSuccess: done,
    }),
  };
}
export const useConversations = (f: ConversationFilter) =>
  useInfiniteQuery({
    queryKey: ['support', 'conversations', f.company ?? '', f.state ?? '', f.channel ?? '', f.q ?? ''],
    queryFn: ({ pageParam }) => call<Page<Conversation>>('GET', `/support/conversations${qs({ company: f.company, state: f.state, channel: f.channel, q: f.q?.trim(), limit: 30, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData, refetchInterval: 30_000,
  });
export const useConversation = (ref: string) => useQuery({ queryKey: ['support', 'conversation', ref], queryFn: () => call<ConversationDetail>('GET', `/support/conversations/${enc(ref)}`), refetchInterval: 15_000 });
export const useQueue = () => useQuery({ queryKey: ['support', 'queue'], queryFn: async () => items(await call<QueueItem[] | Page<QueueItem>>('GET', '/support/queue')), refetchInterval: 30_000 });
export type TeachOut = { message: SupportMessage | null; article: KbArticle };
export function useConversationAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['support'] });
  return {
    // Sent as the owner through the outbound guard: `422 send_blocked` with its reasons. The key is the caller's, one per text.
    reply: useMutation({ mutationFn: (v: { ref: string; body: string; key: string }) => call<SupportMessage>('POST', `/support/conversations/${enc(v.ref)}/reply`, { body: v.body }, { 'Idempotency-Key': v.key }), onSuccess: done }),
    // Sends the answer (when the conversation waits) and opens a KB proposal from it.
    teach: useMutation({
      mutationFn: (v: { ref: string; message_id?: string | null; answer_md: string; generalise: boolean; key: string }) =>
        call<TeachOut>('POST', `/support/conversations/${enc(v.ref)}/teach`, { ...(v.message_id ? { message_id: v.message_id } : {}), answer_md: v.answer_md, generalise: v.generalise }, { 'Idempotency-Key': v.key }),
      onSuccess: done,
    }),
    close: useMutation({ mutationFn: (ref: string) => call<Conversation>('POST', `/support/conversations/${enc(ref)}/close`, {}), onSuccess: done }),
  };
}

// ---------------------------------------------- knowledge, shadow test, go-live (§19.4) --
export type KbKind = 'faq' | 'policy' | 'procedure' | 'referral' | 'official_link' | 'safety';
export type KbStatus = 'proposed' | 'approved' | 'expired' | 'retired';
export type KbArticle = {
  id: string; ref: string; company: string; version: number; kind: KbKind;
  key: string | null; // policy keys, e.g. "vip.min_balance"
  question_fa: string; variants: string[]; answer_md: string; variables: Array<{ name: string; source: 'customer' | 'policy' }>;
  links: Array<{ url: string; label_fa: string }>; codes: Array<{ exchange: string; code: string }>; // referral / official_link only
  status: KbStatus; source: { kind: 'owner_answer' | 'owner' | 'doc' | 'agent'; ref: string | null };
  approved_at: string | null; expires_at: string; uses_30d: number; sha256: string;
};
export type KbArticleIn = {
  company: string; kind: KbKind; question_fa: string; answer_md: string; variants?: string[]; key?: string | null;
  variables?: KbArticle['variables']; links?: KbArticle['links']; codes?: KbArticle['codes']; ref?: string;
};
export type ShadowReport = {
  company: string; suite: string; run_id: string; at: string; total: number; correct: number; partial: number; wrong: number;
  safety_failures: number; wrong_codes: number; pass: boolean; threshold: number; disagreements: Array<{ case: string; verdict: string; note_fa: string }>;
};
export const useKb = (f: { company?: string | null; kind?: KbKind | null; status?: KbStatus | null; q?: string }) =>
  useQuery({
    queryKey: ['support', 'kb', f.company ?? '', f.kind ?? '', f.status ?? '', f.q ?? ''],
    queryFn: async () => items(await call<KbArticle[] | Page<KbArticle>>('GET', `/support/kb${qs({ company: f.company, kind: f.kind, status: f.status, q: f.q?.trim() })}`)),
    placeholderData: keepPreviousData,
  });
export function useKbAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['support'] });
  return {
    propose: useMutation({ mutationFn: (b: KbArticleIn) => call<KbArticle>('POST', '/support/kb', b), onSuccess: done }),
    // An approved article changes what may leave without the owner: sealed on `ref@version`.
    approve: useMutation({ mutationFn: async (a: KbArticle) => call<KbArticle>('POST', `/support/kb/${enc(a.ref)}/approve`, {}, { 'X-Step-Up': await stepUp('support.kb', `${a.ref}@${a.version}`) }), onSuccess: done }),
    retire: useMutation({ mutationFn: (ref: string) => call<KbArticle>('POST', `/support/kb/${enc(ref)}/retire`, {}), onSuccess: done }),
  };
}
/** The latest report of each company. */
export const useShadow = () => useQuery({ queryKey: ['support', 'shadow'], queryFn: async () => items(await call<ShadowReport[] | Page<ShadowReport>>('GET', '/support/shadow')) });
export function useShadowAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['support'] });
  return {
    // A chat export (Telegram Desktop JSON or a CSV of question and answer), already uploaded through /files, builds the private suite.
    history: useMutation({ mutationFn: (b: { company: string; file_id: string }) => call<{ suite?: string; cases?: number }>('POST', '/support/history', b), onSuccess: done }),
    // An academy eval run of the support charter on the suite (§18.6).
    run: useMutation({ mutationFn: (company: string) => call<{ run_id?: string }>('POST', `/support/shadow/${enc(company)}/run`, {}), onSuccess: done }),
  };
}

// ------------------------------------------- templates, lifecycle rules, NPS (§19.5) --
export type TemplatePurpose = 'welcome' | 'reactivation' | 'rescue' | 'nps' | 'holding_reply' | 'safety' | 'csat';
export type Template = {
  id: string; ref: string; company: string; version: number; purpose: TemplatePurpose; body_fa: string; variables: string[];
  status: 'proposed' | 'sealed' | 'retired'; sealed_at: string | null; sha256: string;
};
export type RuleKind = 'welcome' | 'reactivation' | 'rescue' | 'nps' | 'csat';
export type LifecycleRule = {
  id: string; ref: string; company: string; version: number; kind: RuleKind;
  trigger: { event?: 'signup' | 'referral_failed' | 'conversation_closed'; after_hours?: number; inactive_days?: number; rrule?: string };
  template: string; channel: ChannelKind; // template: "TM-0007@2"
  limits: { per_customer_days: number; daily_cap: number; quiet_hours: [string, string]; max_follow_ups: number };
  status: 'proposed' | 'active' | 'paused'; decision_ref: string | null; sent_30d: number; opt_outs_30d: number;
};
export type NpsWave = {
  ref: string; company: string; quarter: string; sample: number; sent: number; responses: number; score: number | null; // -100..100
  promoters: number; passives: number; detractors: number; opens_at: string; closes_at: string; comments_to_feedback: number;
};
export type TemplateIn = { company: string; purpose: TemplatePurpose; body_fa: string; variables: string[]; ref?: string };
export type LifecycleRuleIn = Pick<LifecycleRule, 'company' | 'kind' | 'trigger' | 'template' | 'channel' | 'limits'> & { ref?: string };

export const useTemplates = (company?: string | null) => useQuery({ queryKey: ['growth', 'templates', company ?? ''], queryFn: async () => items(await call<Template[] | Page<Template>>('GET', `/growth/templates${qs({ company })}`)) });
export const useRules = (company?: string | null) => useQuery({ queryKey: ['growth', 'rules', company ?? ''], queryFn: async () => items(await call<LifecycleRule[] | Page<LifecycleRule>>('GET', `/growth/rules${qs({ company })}`)) });
export const useNps = (company?: string | null) => useQuery({ queryKey: ['growth', 'nps', company ?? ''], queryFn: async () => items(await call<NpsWave[] | Page<NpsWave>>('GET', `/growth/nps${qs({ company })}`)) });
export function useGrowthAction() {
  const qc = useQueryClient();
  const done = () => Promise.all([qc.invalidateQueries({ queryKey: ['growth'] }), qc.invalidateQueries({ queryKey: ['decisions'] })]);
  return {
    proposeTemplate: useMutation({ mutationFn: (b: TemplateIn) => call<Template>('POST', '/growth/templates', b), onSuccess: done }),
    // Bound to the exact body: a seal token for one company's text cannot seal the same text elsewhere.
    sealTemplate: useMutation({ mutationFn: async (t: Template) => call<Template>('POST', `/growth/templates/${enc(t.ref)}/seal`, {}, { 'X-Step-Up': await stepUp('growth.template', `${t.ref}@${t.version}:${t.sha256}`) }), onSuccess: done }),
    createRule: useMutation({ mutationFn: (b: LifecycleRuleIn) => call<LifecycleRule>('POST', '/growth/rules', b), onSuccess: done }),
    // Sealing is the owner's A3 approval in advance; the rule's template version must be sealed (`409 template_not_sealed`).
    sealRule: useMutation({ mutationFn: async (r: LifecycleRule) => call<LifecycleRule>('POST', `/growth/rules/${enc(r.ref)}/seal`, {}, { 'X-Step-Up': await stepUp('growth.rule', `${r.ref}@${r.version}`) }), onSuccess: done }),
    pauseRule: useMutation({ mutationFn: (ref: string) => call<LifecycleRule>('POST', `/growth/rules/${enc(ref)}/pause`, {}), onSuccess: done }),
    resumeRule: useMutation({ mutationFn: async (r: LifecycleRule) => call<LifecycleRule>('POST', `/growth/rules/${enc(r.ref)}/resume`, {}, { 'X-Step-Up': await stepUp('growth.rule', `${r.ref}@${r.version}`) }), onSuccess: done }),
  };
}

// ------------------------------------------------------------ feedback inbox (§19.7) --
export type FeedbackKind = 'bug' | 'feature' | 'confusion' | 'complaint' | 'praise';
export type FeedbackState = 'new' | 'triaged' | 'in_backlog' | 'done' | 'wont_do';
export type FeedbackItem = {
  id: string; ref: string; company: string; kind: FeedbackKind; area: string; title_fa: string; count: number; first_seen: string; last_seen: string;
  quotes: string[]; sources: string[]; state: FeedbackState; work_ref: string | null; version: number; // quotes masked, ≤ 3; sources SC-… / NP-…
};
/** Most frequent first. */
export const useFeedback = (f: { company?: string | null; kind?: FeedbackKind | null; state?: FeedbackState | null }) =>
  useInfiniteQuery({
    queryKey: ['feedback', f.company ?? '', f.kind ?? '', f.state ?? ''],
    queryFn: ({ pageParam }) => call<Page<FeedbackItem>>('GET', `/feedback${qs({ company: f.company, kind: f.kind, state: f.state, limit: 50, cursor: pageParam })}`),
    initialPageParam: null as string | null, getNextPageParam: (l) => l.next_cursor, placeholderData: keepPreviousData,
  });
export function useFeedbackAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { item: FeedbackItem; patch: { state?: FeedbackState; work_ref?: string | null } }) => call<FeedbackItem>('PATCH', `/feedback/${enc(v.item.ref)}`, v.patch, ifMatch(v.item.version)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['feedback'] }),
  });
}

// ------------------------------------------------------------- intake (§19.8) --
export type IntakeKind = 'telegram' | 'chatwoot' | 'product';
export type IntakeSource = { company: string; kind: IntakeKind; configured: boolean; last_event_at: string | null; events_24h: number; rejected_24h: number };
export type IntakeSourceIn = { company: string; kind: IntakeKind; allowed_ips: string[]; kinds: string[] };
export const PRODUCT_EVENTS = ['signup', 'uid_submitted', 'referral_verified', 'referral_failed', 'vip_activated', 'support_message'] as const;
export const useIntakeSources = () => useQuery({ queryKey: ['intake', 'sources'], queryFn: async () => items(await call<IntakeSource[] | Page<IntakeSource>>('GET', '/intake/sources')), refetchInterval: 120_000 });
export function useIntakeAction() {
  const qc = useQueryClient();
  return useMutation({
    // Sealed on the exact body (allowed IPs and kinds); the source's secret is set in the owner's terminal, never here.
    mutationFn: async (body: IntakeSourceIn) => call<IntakeSource>('POST', '/intake/sources', body, { 'X-Step-Up': await stepUp('intake.source', await bodyTarget(JSON.stringify(body))) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['intake'] }),
  });
}

// ------------------------------------------------------------- codes (§19.9, §14) --
/** The outbound guard's refusals (§19.6). Without an override: the owner edits the text and the guard runs again. */
export const GUARD_FA: Record<string, string> = {
  asks_secret: 'رمز، کلید خصوصی، عبارت بازیابی، کد تأیید یا شماره‌ی کارت خواسته شده',
  unknown_link: 'لینکی که در لینک‌های تأییدشده‌ی همین شرکت نیست',
  unknown_code: 'کدی شبیه رفرال که عیناً تأیید نشده',
  profit_promise: 'وعده‌ی سود (مثل «سود تضمینی» یا «بدون ضرر»)',
  customer_data: 'داده‌ی مشتری دیگر (نام کاربری، UID یا تماس)',
  internal_data: 'داده‌ی داخلی هلدینگ',
  too_long: 'بیش از اندازه بلند',
  red_line: 'خط قرمز اساسنامه؛ برای بازبینی نگه داشته شد',
};
/** No exception exists for these, not even for the owner. */
export const NO_OVERRIDE = new Set(['asks_secret', 'profit_promise', 'red_line']);
const CODE_FA: Record<string, string> = {
  send_blocked: 'نگهبان خروجی این پیام را رد کرد و فرستاده نشد.',
  shadow_not_passed: 'این کانال هنوز آزمون سایه را قبول نشده؛ شروع کانال فقط با کارت go-live بعد از قبولی است.',
  template_not_sealed: 'نسخه‌ی قالب این قاعده هنوز مُهر نشده؛ اول قالب را مُهر کن.',
  channel_not_live: 'این کانال روشن نیست؛ از آن پیامی به مشتری نمیرود.',
  opted_out: 'این مشتری لغو کرده؛ هیچ پیام قاعده‌ای به او نمیرود.',
  send_limit: 'سقف ارسال پر شده است',
};
/** The Persian sentence for a failed §19 call; the server's own sentence for everything else. */
export function faError(e: unknown): string {
  if (!(e instanceof ApiError)) return e instanceof Error ? e.message : 'انجام نشد.';
  const base = CODE_FA[e.code] ?? e.messageFa;
  if ((e.code === 'send_limit' || e.code === 'rate_limited') && e.retryAfter) return `${base}؛ ${e.retryAfter < 90 ? `${e.retryAfter} ثانیه‌ی` : `${Math.ceil(e.retryAfter / 60)} دقیقه‌ی`} دیگر دوباره امتحان کن.`;
  return base;
}
/** The guard's reasons on a `422 send_blocked`, else none. */
export const blockedReasons = (e: unknown): string[] => (e instanceof ApiError && e.code === 'send_blocked' ? e.blockedReasons : []);
