'use client';

// ⟨1.13⟩ Contract §31 (prompt 22): growth — the learning loop of a line, a ready company from a kit, the owned newsletter, SEO rank and
// competitors, one campaign calendar, ad budgets that stop by themselves, and automations from one sentence. Until the OpenAPI file is
// regenerated the shapes live here, written from §31. Every route group is feature-gated like §29/§30: a hub that answers 404/405/501
// shows a calm «after the hub update» state.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { stepUp } from '@/lib/auth';
import { ApiError } from './client';
import { handled } from './observe';
import { call } from './v13';
import { notServed } from './v28';
import type { CalendarDay, Line } from './v30';

const enc = encodeURIComponent;
async function served<T>(p: Promise<T>): Promise<T | null> {
  try { return await p; } catch (e) { if (notServed(e)) return null; throw e; }
}
const listOf = <T,>(x: T[] | { items?: T[] } | null | undefined): T[] => (Array.isArray(x) ? x : x?.items ?? []);
async function withStepUp<T>(action: string, target: string, run: (h?: Record<string, string>) => Promise<T>): Promise<T> {
  try { return await run(); } catch (e) {
    if (!(e instanceof ApiError && e.status === 403 && e.code === 'step_up_required')) throw e;
    handled(e);
    return run({ 'X-Step-Up': await stepUp(action, target) });
  }
}
const inval = (qc: ReturnType<typeof useQueryClient>) => () => qc.invalidateQueries({ queryKey: ['g31'] });
const list = <T,>(path: string) => async () => { const r = await served(call<T[] | { items: T[] }>('GET', path)); return r ? listOf(r) : null; };

// ============================================================================================ §31.1 insights ==
export type Insights = {
  line: string; metric: string; window_runs: number; updated_at: string;
  best: { hour: number | null; length_bucket: string | null; voice: string | null; pattern_source: string | null };
  top_hooks: string[]; lessons_fa: string[];
};
export const METRIC_FA: Record<string, string> = { views: 'بازدید', reach: 'دسترسی', clicks: 'کلیک', watch_s: 'زمان تماشا' };
export const useInsights = (ref: string) => useQuery({ queryKey: ['g31', 'insights', ref], staleTime: 30_000, queryFn: () => served(call<Insights>('GET', `/lines/${enc(ref)}/insights`)) });

// ============================================================================================== §31.2 kits ==
export type Kit = {
  key: string; title_fa: string; purpose_fa: string; team_template: string; groups: string[];
  lines: Array<{ template: string; platform: string; title_fa: string }>; kpis: string[]; connections: string[]; defaults: Record<string, unknown>;
};
export type KitBody = { kit: string; code: string; name_fa: string; name_en: string; color_index?: number; order?: string };
/** What the preview and the result carry beyond §31.2 (assumed): the team, the lines and `todo_fa`, what is still to be connected. */
export type KitPreview = { company: { code: string; name_fa: string; name_en: string }; team?: Array<{ title_fa: string; count?: number }>; groups: string[]; lines: Array<{ title_fa: string; platform: string }>; kpis: string[]; connections: string[]; todo_fa: string[]; code_free?: boolean; problems?: string[] };
export type KitResult = { company: { code: string; name_fa: string }; todo_fa: string[]; team?: unknown; groups?: unknown; kpis?: unknown; connections?: unknown; lines?: Array<Line | { ref: string }>; lines_pending?: unknown; groups_pending?: unknown };
/** The step-up for a company from a kit is sealed on the SHA-256 of the exact body bytes (what `call` sends: JSON.stringify). */
export async function bodyHash(body: unknown): Promise<string> {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(body)));
  return [...new Uint8Array(d)].map((x) => x.toString(16).padStart(2, '0')).join('');
}
export const useKits = () => useQuery({ queryKey: ['g31', 'kits'], staleTime: 60_000, queryFn: list<Kit>('/kits') });
export const previewKit = (b: KitBody) => call<KitPreview>('POST', '/companies/from-kit/preview', b);
export function useCreateFromKit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (b: KitBody) => withStepUp('company.create', await bodyHash(b), (h) => call<KitResult>('POST', '/companies/from-kit', b, h)),
    onSettled: () => Promise.all([qc.invalidateQueries({ queryKey: ['companies'] }), qc.invalidateQueries({ queryKey: ['lines'] }), qc.invalidateQueries({ queryKey: ['orders'] })]),
  });
}

// ========================================================================================== §31.3 newsletter ==
export type NlList = { id: string; name: string; subscribers: number; size_limit?: number | null };
export type NlCampaign = { id: string; list: string; subject: string; subject_b?: string | null; state: 'draft' | 'scheduled' | 'sending' | 'sent'; scheduled_at: string | null; sent?: number | null; opens?: number | null; clicks?: number | null };
export type Newsletter = { lists: NlList[]; campaigns: NlCampaign[] };
export const useNewsletter = (code: string) => useQuery({ queryKey: ['g31', 'newsletter', code], staleTime: 20_000, queryFn: () => served(call<Newsletter>('GET', `/companies/${enc(code)}/newsletter`)) });
export function useNewsletterActions(code: string) {
  const qc = useQueryClient();
  const settle = inval(qc);
  return {
    create: useMutation({ mutationFn: (b: { list: string; subject: string; subject_b?: string; body_md: string }) => call<NlCampaign>('POST', `/companies/${enc(code)}/newsletter/campaigns`, b), onSettled: settle }),
    schedule: useMutation({ mutationFn: (v: { id: string; at: string }) => withStepUp('newsletter.send', v.id, (h) => call<NlCampaign>('POST', `/newsletter/campaigns/${enc(v.id)}/schedule`, { at: v.at }, h)), onSettled: settle }),
  };
}

// ============================================================================================= §31.4 SEO ==
export type Keyword = { id: string; company: string; phrase: string; site: string; target_url: string | null; state: 'on' | 'paused' };
export type RankDaily = { keyword: string; day: string; source: 'search_console' | 'searxng'; position: number | null; url: string | null };
export type Competitor = { id: string; company: string; name_fa: string; site: string | null; instagram: string | null; youtube: string | null; telegram: string | null; state: 'on' | 'paused' };
export type CompetitorDaily = { competitor: string; day: string; key: string; value: number; source: string };
export const useKeywords = (c: string) => useQuery({ queryKey: ['g31', 'keywords', c], staleTime: 20_000, queryFn: list<Keyword>(`/companies/${enc(c)}/keywords`) });
export const useRanks = (c: string, days = 30) => useQuery({ queryKey: ['g31', 'ranks', c, days], staleTime: 60_000, queryFn: list<RankDaily>(`/companies/${enc(c)}/ranks?days=${days}`) });
export const useCompetitors = (c: string) => useQuery({ queryKey: ['g31', 'competitors', c], staleTime: 20_000, queryFn: list<Competitor>(`/companies/${enc(c)}/competitors`) });
export const useCompetitorDaily = (c: string, days = 30) => useQuery({ queryKey: ['g31', 'competitor-daily', c, days], staleTime: 60_000, queryFn: list<CompetitorDaily>(`/companies/${enc(c)}/competitors/daily?days=${days}`) });
/** Add, edit (PUT) or remove (DELETE) a keyword or a competitor. */
export function useCrud<T extends { id: string }>(code: string, what: 'keywords' | 'competitors' | 'ad-rules') {
  const qc = useQueryClient();
  const settle = inval(qc);
  const base = `/companies/${enc(code)}/${what}`;
  return {
    add: useMutation({ mutationFn: (b: Partial<T>) => call<T>('POST', base, b), onSettled: settle }),
    edit: useMutation({ mutationFn: (b: Partial<T> & { id: string }) => call<T>('PUT', `${base}/${enc(b.id)}`, b), onSettled: settle }),
    remove: useMutation({ mutationFn: (id: string) => call<void>('DELETE', `${base}/${enc(id)}`), onSettled: settle }),
  };
}

// ========================================================================================= §31.5 campaigns ==
export type CampaignKind = 'line' | 'newsletter' | 'ad' | 'campaign' | 'manual';
export const CAMPAIGN_KIND_FA: Record<CampaignKind, string> = { line: 'خط تولید', newsletter: 'خبرنامه', ad: 'تبلیغ', campaign: 'کمپین', manual: 'دستی' };
export type CampaignItem = { day: string; at: string | null; company: string; kind: CampaignKind; ref: string; title_fa: string; platform: string | null; state: string; conflict_fa: string | null };
export type Campaign = { id: string; company: string; title_fa: string; goal_fa: string; starts: string; ends: string; channels: string[]; budget: number | null; state: string };
/** `GET /campaign-calendar`; a hub without it falls back to §30's `GET /calendar/lines` (lines only, no conflicts). */
export const useCampaignCalendar = (from: string, to: string, company: string | null) =>
  useQuery({
    queryKey: ['g31', 'calendar', from, to, company], staleTime: 20_000,
    queryFn: async (): Promise<{ items: CampaignItem[]; lines_only: boolean } | null> => {
      const qs = `from=${enc(from)}&to=${enc(to)}${company ? `&company=${enc(company)}` : ''}`;
      const r = await served(call<{ days: Array<{ day: string; items: CampaignItem[] }> } | CampaignItem[]>('GET', `/campaign-calendar?${qs}`));
      if (r) return { items: Array.isArray(r) ? r : r.days.flatMap((d) => d.items.map((i) => ({ ...i, day: i.day ?? d.day }))), lines_only: false };
      const old = await served(call<{ days: CalendarDay[] }>('GET', `/calendar/lines?${qs}`));
      if (!old) return null;
      return { lines_only: true, items: old.days.flatMap((d) => d.items.map((i): CampaignItem => ({ day: d.day, at: i.at, company: i.company, kind: 'line', ref: i.line, title_fa: i.title_fa ?? i.line, platform: i.platform, state: i.state, conflict_fa: null }))) };
    },
  });
export const useCampaigns = () => useQuery({ queryKey: ['g31', 'campaigns'], staleTime: 20_000, queryFn: list<Campaign>('/campaigns') });
export function useCampaignActions() {
  const qc = useQueryClient();
  const settle = inval(qc);
  return {
    add: useMutation({ mutationFn: (b: Omit<Campaign, 'id'>) => call<Campaign>('POST', '/campaigns', b), onSettled: settle }),
    edit: useMutation({ mutationFn: (b: Campaign) => call<Campaign>('PUT', `/campaigns/${enc(b.id)}`, b), onSettled: settle }),
    remove: useMutation({ mutationFn: (id: string) => call<void>('DELETE', `/campaigns/${enc(id)}`), onSettled: settle }),
  };
}

// ============================================================================================== §31.6 ads ==
export type AdAccount = { company: string; platform: 'google_ads' | 'meta_ads'; account_id: string; state: string };
export type AdRule = { id: string; company: string; scope: string; daily_cap: number; window_days: number; min_roas: number; min_spend_before_judging: number; action: 'pause' | 'notify'; state: 'on' | 'off' };
export type AdDaily = { company: string; platform: string; campaign_id: string; day: string; spend: number; clicks: number; conversions: number; revenue: number; roas: number };
/** Beyond §31.6 (assumed): the campaign rows of `GET …/ads` with their state and whether a rule paused them. */
export type AdCampaign = { platform: 'google_ads' | 'meta_ads'; id: string; title_fa: string; state: 'active' | 'paused'; paused_by_rule?: boolean; spend: number; revenue: number; roas: number };
export type Ads = { accounts: AdAccount[]; campaigns: AdCampaign[]; daily?: AdDaily[] };
export const PLATFORM_AD_FA: Record<string, string> = { google_ads: 'گوگل ادز', meta_ads: 'متا ادز' };
export const useAds = (c: string) => useQuery({ queryKey: ['g31', 'ads', c], staleTime: 30_000, queryFn: () => served(call<Ads>('GET', `/companies/${enc(c)}/ads`)) });
export const useAdRules = (c: string) => useQuery({ queryKey: ['g31', 'ad-rules', c], staleTime: 20_000, queryFn: list<AdRule>(`/companies/${enc(c)}/ad-rules`) });
export function useResumeCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { platform: string; id: string }) => withStepUp('ads.resume', v.id, (h) => call<unknown>('POST', `/ads/campaigns/${enc(v.platform)}/${enc(v.id)}/resume`, {}, h)),
    onSettled: inval(qc),
  });
}

// ========================================================================================= §31.7 automations ==
export type AutomationRule = { trigger: { kind: 'schedule' | 'event' | 'metric'; [k: string]: unknown }; conditions: unknown[]; actions: Array<{ kind: string; args?: Record<string, unknown> }> };
export type Automation = { ref: string; company: string | null; sentence_fa: string; rule: AutomationRule; state: 'proposed' | 'on' | 'off'; runs: number | Array<{ at: string; ok?: boolean; note_fa?: string }>; last_run_at: string | null; n8n_workflow: string | null; preview_fa?: string };
export type Compiled = { rule: AutomationRule; preview_fa: string; refused_fa: string[] };
export const AUTOMATION_STATE: Record<Automation['state'], { fa: string; tone: 'silver' | 'pos' | 'warn' }> = { proposed: { fa: 'منتظر مُهر', tone: 'warn' }, on: { fa: 'روشن', tone: 'pos' }, off: { fa: 'خاموش', tone: 'silver' } };
export const useAutomations = () => useQuery({ queryKey: ['g31', 'automations'], staleTime: 15_000, queryFn: list<Automation>('/automations') });
export const useAutomation = (ref: string | null) => useQuery({ queryKey: ['g31', 'automation', ref], enabled: !!ref, staleTime: 10_000, queryFn: () => call<Automation>('GET', `/automations/${enc(ref!)}`) });
export const compileAutomation = (sentence_fa: string, company?: string | null) => call<Compiled>('POST', '/automations/compile', { sentence_fa, ...(company ? { company } : {}) });
export function useAutomationActions() {
  const qc = useQueryClient();
  const settle = inval(qc);
  return {
    /** Registers it as proposed, then the seal (behind the passkey) turns it on. */
    register: useMutation({
      mutationFn: async (b: { rule: AutomationRule; sentence_fa: string; company?: string | null }) => {
        const a = await call<Automation>('POST', '/automations', b);
        return withStepUp('automation.seal', a.ref, (h) => call<Automation>('POST', `/automations/${enc(a.ref)}/seal`, {}, h));
      },
      onSettled: settle,
    }),
    seal: useMutation({ mutationFn: (ref: string) => withStepUp('automation.seal', ref, (h) => call<Automation>('POST', `/automations/${enc(ref)}/seal`, {}, h)), onSettled: settle }),
    state: useMutation({ mutationFn: (v: { ref: string; state: 'on' | 'off' }) => call<Automation>('POST', `/automations/${enc(v.ref)}/state`, { state: v.state }), onSettled: settle }),
  };
}
