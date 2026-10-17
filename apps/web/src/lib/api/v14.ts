'use client';

// Contract v1.4 (§18): oversight, inquiries, the personal assistant, stars, skills, the academy, egress and MCP, founding and
// provisioning, backups. Prompts 7–9 implement them; until the OpenAPI file is regenerated, the types live here, written from the
// contract. Same conventions as v13: X-HQ-Client and Idempotency-Key on writes, Problem errors as ApiError.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { bodyTarget, stepUp } from '@/lib/auth';
import { call, type Actor, type MediaRef } from './v13';

export type Evidence = { kind: string; ref: string; note?: string | null };
export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type Area = 'truth' | 'authority' | 'money' | 'safety' | 'quality' | 'delivery' | 'security' | 'data' | 'people' | 'product' | 'owner';

// ------------------------------------------------------------ oversight --
export type Protocol = {
  id: string; ref: string; title_fa: string; area: Area; check_md: string; method: string; schedule: string; scope: string;
  evidence_md: string; severity: Severity; answerable: string; status: 'active' | 'paused' | 'draft'; version: number;
  sealed_at: string | null; last_run: { at: string; result: 'pass' | 'fail' | 'partial'; findings: number } | null;
};
export type FindingStatus = 'open' | 'acknowledged' | 'fixing' | 'fixed' | 'verified' | 'disputed' | 'closed';
export type Finding = {
  id: string; ref: string; company: string; protocol: string | null; severity: Severity; title_fa: string; body_md: string;
  evidence: Evidence[]; status: FindingStatus; answerable: Actor; due_at: string; opened_at: string; closed_at: string | null;
  history: Array<{ at: string; by: Actor; status: FindingStatus; note: string }>;
};
export type Challenge = {
  id: string; ref: string; company: string; period: 'week' | 'month'; title_fa: string; brief_md: string;
  criteria: Array<{ name_fa: string; weight: number }>; due_at: string;
  status: 'issued' | 'accepted' | 'submitted' | 'scored' | 'missed'; score: number | null; judge: Actor; work_ref: string | null;
};
export type StandingOrder = {
  id: string; ref: string; text_md: string; source: 'voice' | 'text'; file_id: string | null; applies_to: 'overseer' | 'all';
  status: 'proposed' | 'sealed' | 'retired'; version: number; sealed_at: string | null; created_at: string;
};
export type Hold = {
  id: string; ref: string; company: string; action: { kind: string; summary_fa: string; payload_digest: string }; reason_md: string;
  held_by: Actor; held_at: string; state: 'held' | 'released' | 'cancelled'; decided_by: Actor | null; decided_at: string | null;
};
export type Compliance = {
  company: string; score: number; by_area: Partial<Record<Area, number>>;
  findings_open: { critical: number; high: number; medium: number; low: number }; protocols: { passed: number; failed: number }; trend: number[];
};
export type WatchReport = { on: boolean; since: string | null; until: string | null; summary_md: string; held: string[]; urgent: string[]; findings: string[] };
export type OversightSummary = {
  watch: WatchReport; compliance: Compliance[]; findings_open: Record<Severity, number>; holds_waiting: number;
  challenges_week: { issued: number; accepted?: number; submitted: number; scored: number; missed: number }; protocols: { active: number; failed_today: number };
};

export const useOversight = () => useQuery({ queryKey: ['oversight', 'summary'], queryFn: () => call<OversightSummary>('GET', '/oversight/summary'), refetchInterval: 60_000 });
export const useProtocols = () => useQuery({ queryKey: ['oversight', 'protocols'], queryFn: () => call<Protocol[]>('GET', '/oversight/protocols'), staleTime: 60_000 });
export const useFindings = (status?: string) => useQuery({ queryKey: ['oversight', 'findings', status ?? 'all'], queryFn: () => call<{ items: Finding[] }>('GET', `/oversight/findings${status ? `?status=${status}` : ''}`) });
export const useChallenges = () => useQuery({ queryKey: ['oversight', 'challenges'], queryFn: () => call<{ items: Challenge[] }>('GET', '/oversight/challenges') });
export const useOrders = () => useQuery({ queryKey: ['oversight', 'orders'], queryFn: () => call<StandingOrder[]>('GET', '/oversight/orders') });
export const useHolds = () => useQuery({ queryKey: ['oversight', 'holds'], queryFn: () => call<Hold[]>('GET', '/oversight/holds?state=held') });

export function useOversightAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['oversight'] });
  return {
    findingStatus: useMutation({ mutationFn: (v: { ref: string; status: FindingStatus; note: string }) => call<Finding>('POST', `/oversight/findings/${v.ref}/status`, { status: v.status, note: v.note }), onSuccess: done }),
    newOrder: useMutation({ mutationFn: (v: { text_md: string; source: 'voice' | 'text'; file_id?: string | null; applies_to: 'overseer' | 'all' }) => call<StandingOrder>('POST', '/oversight/orders', v), onSuccess: done }),
    sealOrder: useMutation({ mutationFn: async (ref: string) => call<StandingOrder>('POST', `/oversight/orders/${ref}/seal`, {}, { 'X-Step-Up': await stepUp('oversight.order', ref) }), onSuccess: done }),
    retireOrder: useMutation({ mutationFn: (ref: string) => call<StandingOrder>('POST', `/oversight/orders/${ref}/retire`, {}), onSuccess: done }),
    release: useMutation({ mutationFn: async (ref: string) => call<Hold>('POST', `/oversight/holds/${ref}/release`, {}, { 'X-Step-Up': await stepUp('oversight.release', ref) }), onSuccess: done }),
    cancel: useMutation({ mutationFn: (ref: string) => call<Hold>('POST', `/oversight/holds/${ref}/cancel`, {}), onSuccess: done }),
  };
}

// ------------------------------------------------------------ inquiries --
export type Inquiry = {
  id: string; ref: string; from: Actor; to: Actor; company: string; question_md: string; due_at: string;
  status: 'open' | 'answered' | 'late' | 'withdrawn'; answer_md: string | null; evidence: Evidence[]; answered_at: string | null; thread_ref: string;
};
export const useInquiries = (from?: string) => useQuery({ queryKey: ['inquiries', from ?? 'all'], queryFn: () => call<{ items: Inquiry[] }>('GET', `/inquiries${from ? `?from=${from}` : ''}`) });

// ------------------------------------------------------------- errands --
export type ErrandStep = { at: string; kind: 'search' | 'read' | 'browse' | 'request' | 'draft' | 'note' | 'proposal'; summary_fa: string; data: Record<string, unknown> };
export type Errand = {
  id: string; ref: string; title_fa: string; brief_md: string; source: 'voice' | 'text'; file_ids: string[]; due_at: string | null;
  status: 'queued' | 'working' | 'waiting_owner' | 'done' | 'failed' | 'cancelled'; steps: ErrandStep[]; result_md: string | null;
  attachments: MediaRef[]; decision_ref: string | null; usage: { usd: number }; created_at: string; updated_at: string;
};
export const useErrands = () => useQuery({ queryKey: ['errands'], queryFn: () => call<{ items: Errand[] }>('GET', '/errands'), refetchInterval: 15_000 });
export function useErrandAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['errands'] });
  return {
    create: useMutation({ mutationFn: (v: { brief_md: string; source: 'voice' | 'text'; file_ids?: string[] }) => call<Errand>('POST', '/errands', v), onSuccess: done }),
    cancel: useMutation({ mutationFn: (ref: string) => call<Errand>('POST', `/errands/${ref}/cancel`, {}), onSuccess: done }),
  };
}

// --------------------------------------------------------------- stars --
export type StarRubric = { company: string; version: number; criteria: Array<{ key: string; name_fa: string; weight: number; description_md: string }>; rules_md: string; by: Actor; status: string; updated_at: string };
// ⟨1.4.3⟩ efficiency: spending the envelope well, with results and without waste (0–100, from the ledger).
export type CompanyStanding = { company: string; stars: number; score: number; parts: { kpi: number; challenges: number; compliance: number; people: number; efficiency: number }; rank: number; trend: number[] };
export type EmployeeStanding = { code: string; company: string; title_fa: string; stars: number; count: number; rank_company: number; rank_holding: number; trend: number[]; efficiency?: number | null };
export type StarRollup = { period: 'week' | 'month'; key: string; best_company: string; companies: CompanyStanding[]; employees: EmployeeStanding[]; lessons: string[] };
export type Lesson = { id: string; ref: string; source_company: string; period: string; title_fa: string; body_md: string; evidence: Evidence[]; adoption: Array<{ company: string; status: 'proposed' | 'adopted' | 'rejected'; decision_ref: string | null }> };
export const useRollup = (period: 'week' | 'month') => useQuery({ queryKey: ['stars', 'rollup', period], queryFn: () => call<StarRollup>('GET', `/stars/rollup?period=${period}`) });
export const useRubrics = () => useQuery({ queryKey: ['stars', 'rubrics'], queryFn: () => call<StarRubric[]>('GET', '/stars/rubrics'), staleTime: 300_000 });
export const useLessons = () => useQuery({ queryKey: ['stars', 'lessons'], queryFn: () => call<{ items: Lesson[] }>('GET', '/lessons') });

// -------------------------------------------------------------- skills --
export type Skill = {
  id: string; ref: string; name_fa: string; summary_fa: string; body_md: string; resources: MediaRef[];
  scope: { roles: string[]; companies: 'all' | string[]; departments: string[] }; version: number;
  status: 'draft' | 'in_review' | 'approved' | 'active' | 'retired';
  review: { by: Actor; at: string; verdict: 'pass' | 'changes' | 'reject'; notes_md: string; checks: Record<'injection' | 'secrets' | 'conflicts' | 'policy', boolean> } | null;
  eval: { suite: string; score: number; baseline: number } | null; created_by: Actor; created_at: string; activated_at: string | null;
};
export const useSkills = () => useQuery({ queryKey: ['skills'], queryFn: () => call<Skill[]>('GET', '/skills') });
export function useSkillAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['skills'] });
  return {
    create: useMutation({ mutationFn: (v: { name_fa: string; body_md: string; roles: string[]; companies: 'all' | string[]; file_ids: string[] }) => call<Skill>('POST', '/skills', v), onSuccess: done }),
    activate: useMutation({ mutationFn: async (s: Skill) => call<Skill>('POST', `/skills/${s.ref}/activate`, { version: s.version }, { 'X-Step-Up': await stepUp('skill.activate', `${s.ref}@${s.version}`) }), onSuccess: done }),
    retire: useMutation({ mutationFn: (ref: string) => call<Skill>('POST', `/skills/${ref}/retire`, {}), onSuccess: done }),
  };
}

// ------------------------------------------------------------- academy --
export type Curriculum = { role: string; version: number; modules: Array<{ key: string; title_fa: string; skills: string[]; evals: string[] }> };
export type EvalSuite = { ref: string; role: string; title_fa: string; cases: number; baseline: { version: string; score: number } | null; runs: Array<{ at: string; subject: string; score: number; passed: boolean }> };
export type Teaching = {
  id: string; ref: string; target: { kind: 'role' | 'employee'; ref: string }; source: 'voice' | 'text'; text_md: string;
  proposal: { kind: string; diff_md: string } | null; eval_run: { score: number; baseline: number; passed: boolean } | null;
  status: 'drafting' | 'proposed' | 'approved' | 'rejected'; created_at: string;
};
export const useCurricula = () => useQuery({ queryKey: ['academy', 'curricula'], queryFn: () => call<Curriculum[]>('GET', '/academy/curricula'), staleTime: 300_000 });
export const useEvals = () => useQuery({ queryKey: ['academy', 'evals'], queryFn: () => call<EvalSuite[]>('GET', '/academy/evals') });
export const useTeachings = () => useQuery({ queryKey: ['academy', 'teach'], queryFn: () => call<Teaching[]>('GET', '/academy/teach') });
export function useTeachAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['academy'] });
  return {
    teach: useMutation({ mutationFn: (v: { target: { kind: 'role' | 'employee'; ref: string }; text: string; source: 'voice' | 'text'; file_id?: string | null }) => call<Teaching>('POST', '/academy/teach', v), onSuccess: done }),
    approve: useMutation({ mutationFn: async (ref: string) => call<Teaching>('POST', `/academy/teach/${ref}/approve`, {}, { 'X-Step-Up': await stepUp('academy.approve', ref) }), onSuccess: done }),
    reject: useMutation({ mutationFn: (ref: string) => call<Teaching>('POST', `/academy/teach/${ref}/reject`, {}), onSuccess: done }),
  };
}

// ------------------------------------------------------- egress and MCP --
export type EgressSummary = { period: string; requests: number; blocked: number; needs_owner: number; bytes_in: number; by_company: Array<{ company: string; requests: number; blocked: number }>; by_tool: Record<string, number> };
export type EgressEntry = { id: string; at: string; company: string; actor: string; tool: string; method: string; host: string; status: number; ms: number; blocked_reason: string | null; class: string };
export type McpServer = { id: string; key: string; title_fa: string; transport: 'http' | 'container'; url: string | null; tools: Array<{ name: string; class: string; enabled: boolean }>; companies: 'all' | string[]; status: 'pending' | 'enabled' | 'disabled'; has_secret: boolean; added_at: string };
export type ServiceAccount = { id: string; key: string; site: string; title_fa: string; companies: 'all' | string[]; has_secret: boolean; last_used_at: string | null };
export type ToolInfo = { name: string; class: string; roles: string[]; status: 'on' | 'off' | 'pending'; via: 'gateway' | 'egress' | 'mcp' };
export const useEgressSummary = () => useQuery({ queryKey: ['tools', 'egress', 'summary'], queryFn: () => call<EgressSummary>('GET', '/egress/summary?period=day'), refetchInterval: 60_000 });
export const useEgress = () => useQuery({ queryKey: ['tools', 'egress'], queryFn: () => call<{ items: EgressEntry[] }>('GET', '/egress?limit=40') });
export const useMcp = () => useQuery({ queryKey: ['tools', 'mcp'], queryFn: () => call<McpServer[]>('GET', '/tools/mcp') });
export const useAccounts = () => useQuery({ queryKey: ['tools', 'accounts'], queryFn: () => call<ServiceAccount[]>('GET', '/tools/accounts') });
export const useCatalog = () => useQuery({ queryKey: ['tools', 'catalog'], queryFn: () => call<ToolInfo[]>('GET', '/tools/catalog'), staleTime: 300_000 });
export function useMcpAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['tools'] });
  return {
    enable: useMutation({ mutationFn: async (key: string) => call<McpServer>('POST', `/tools/mcp/${key}/enable`, {}, { 'X-Step-Up': await stepUp('mcp.enable', key) }), onSuccess: done }),
    disable: useMutation({ mutationFn: (key: string) => call<McpServer>('POST', `/tools/mcp/${key}/disable`, {}), onSuccess: done }),
  };
}

// --------------------------------------------- founding and provisioning --
export type FoundingState = 'auditing' | 'proposed' | 'sealed' | 'provisioning' | 'ready_for_login' | 'active' | 'cancelled';
export type Founding = {
  id: string; ref: string; name_fa: string; name_en: string; code: string; source: { kind: 'repo' | 'idea'; repo: string | null; brief_md: string };
  state: FoundingState;
  audit: { session_ref: string; report_md: string; scores: Record<'architecture' | 'quality' | 'security' | 'tests' | 'debt', number> } | null;
  proposal: { departments: string[]; kpis: Array<{ name_fa: string; target: string }>; team: Array<{ role: string; model: string; monthly_usd: number }>; roadmap_md: string; monthly_usd: number } | null;
  decision_ref: string | null; plan: string | null; company: string | null; created_at: string; updated_at: string;
};
export type ServerPlan = {
  id: string; ref: string; founding: string | null; company: string; name: string; type: string; location: string; image: string; private_network: boolean;
  firewall: Array<{ direction: 'in'; protocol: string; port: string; sources: string[]; note_fa: string }>; software: string[]; work_user: string;
  repo: string | null; monthly_eur: number; digest: string; state: 'proposed' | 'sealed' | 'running' | 'done' | 'failed'; decision_ref: string | null; run: string | null;
};
export type ProvisionRun = {
  id: string; plan: string; state: 'running' | 'done' | 'failed';
  steps: Array<{ key: string; title_fa: string; state: 'pending' | 'running' | 'done' | 'failed'; started_at: string | null; finished_at: string | null; log_tail: string }>;
  server: { name: string; ipv4: string; ipv6: string; private_ip: string | null } | null; login: { ssh: string; then: string[] } | null;
};
export const useFoundings = () => useQuery({ queryKey: ['founding'], queryFn: () => call<{ items: Founding[] }>('GET', '/foundings') });
export const useFounding = (ref: string) => useQuery({ queryKey: ['founding', ref], queryFn: () => call<Founding>('GET', `/foundings/${ref}`), refetchInterval: 5_000 });
export const usePlan = (ref: string | null) => useQuery({ queryKey: ['founding', 'plan', ref], enabled: !!ref, queryFn: () => call<ServerPlan>('GET', `/provisioning/plans/${ref}`) });
export const useRun = (id: string | null) => useQuery({ queryKey: ['founding', 'run', id], enabled: !!id, queryFn: () => call<ProvisionRun>('GET', `/provisioning/runs/${id}`), refetchInterval: (q) => (q.state.data?.state === 'running' ? 2_000 : false) });
export function useFoundingAction() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ['founding'] });
  return {
    start: useMutation({ mutationFn: (source: Founding['source']) => call<Founding>('POST', '/foundings', { source }), onSuccess: done }),
    // The seal is bound to the exact plan the owner saw: its digest, which the server recomputes.
    sealPlan: useMutation({ mutationFn: async (plan: ServerPlan) => call<ServerPlan>('POST', `/provisioning/plans/${plan.ref}/seal`, {}, { 'X-Step-Up': await stepUp('provision.seal', plan.digest) }), onSuccess: done }),
    activate: useMutation({ mutationFn: async (ref: string) => call<Founding>('POST', `/foundings/${ref}/activate`, {}, { 'X-Step-Up': await stepUp('founding.activate', ref) }), onSuccess: done }),
    cancel: useMutation({ mutationFn: (ref: string) => call<Founding>('POST', `/foundings/${ref}/cancel`, {}), onSuccess: done }),
  };
}

// -------------------------------------------------------------- backups --
export type BackupStatus = {
  hourly: { last_at: string | null; next_at: string | null; ok: boolean; snapshot: string | null; size_bytes: number };
  wal: { last_archived_at: string | null; lag_s: number };
  destinations: Array<{ key: 'gdrive' | 'hetzner' | 'local'; configured: boolean; last_ok_at: string | null; used_bytes: number; quota_bytes: number | null }>;
  retention: { hourly: number; daily: number; weekly: number; monthly: number; yearly: number };
  restore_test: { last_at: string | null; ok: boolean; duration_s: number; notes: string };
  openbao_snapshot: { last_at: string | null; ok: boolean }; encryption: string;
};
export const useBackups = () => useQuery({ queryKey: ['backups'], queryFn: () => call<BackupStatus>('GET', '/backups/status'), refetchInterval: 120_000 });

// -------------------------------------------------------------- hiring --
// Contract §18.11 (v1.4.2, v1.4.3): closed until the owner opens it. `delegated`: each company's CEO hires with full authority inside the
// company's monthly token envelope (its month budget) and picks the model each job needs; `proposals`: every hire is the owner's card.
export type Envelope = { company: string; tokens_month: number | null; committed_month: number; used_month: number; hires_month: number };
export type Hiring = { state: 'closed' | 'open'; mode: 'delegated' | 'proposals' | null; changed_at: string | null; changed_by: Actor | null; withdrawn: string[]; envelopes: Envelope[] };
export type RoleInfo = {
  role: string; title_fa: string; title_en: string; kind: string; scope: 'company' | 'holding' | string; department: string | null;
  model: string; effort: string; priority: string; tools: string[]; limits: { steps_per_run: number; tokens_per_step: number; tokens_per_run: number }; version: number;
};
export type HireIn = { company: string; department: string; role: string; title_fa: string; title_en?: string; model?: string; effort?: string; reason?: string; duties?: string[] };
export type HireOut = { employee: { code: string; company: string; department: string | null; title_fa: string; status: string }; decision: { ref: string; status: string; resolution: string | null } };

// A server before contract v1.4.3 sends no envelopes; the card then shows none rather than failing.
export const useHiring = () => useQuery({ queryKey: ['hiring'], queryFn: async () => { const h = await call<Hiring>('GET', '/owner/hiring'); return { ...h, envelopes: h.envelopes ?? [], withdrawn: h.withdrawn ?? [] }; }, staleTime: 30_000 });
export const useRoles = () => useQuery({ queryKey: ['roles'], queryFn: () => call<RoleInfo[]>('GET', '/roles'), staleTime: 300_000 });

/** The roles the owner can hire into a department: `employee` charters whose scope fits the company and whose department (if any) is this one. */
export function hireableRoles(roles: RoleInfo[], companyKind: string, department: string | null): RoleInfo[] {
  const scope = companyKind === 'holding' ? 'holding' : 'company';
  return roles.filter((r) => r.kind === 'employee' && r.scope === scope && (!r.department || r.department === department));
}

export function useHiringAction() {
  const qc = useQueryClient();
  const done = () => Promise.all([qc.invalidateQueries({ queryKey: ['hiring'] }), qc.invalidateQueries({ queryKey: ['decisions'] }), qc.invalidateQueries({ queryKey: ['inbox'] })]);
  return {
    start: useMutation({ mutationFn: async (mode: 'delegated' | 'proposals') => call<Hiring>('POST', '/owner/hiring/start', { mode }, { 'X-Step-Up': await stepUp('hiring.start', 'holding') }), onSuccess: done }),
    // The envelopes are company month budgets (§9 PUT /budgets): the seal is bound to the exact body.
    envelopes: useMutation({
      mutationFn: async (items: Array<{ company: string; tokens_month: number }>) => {
        const body = { budgets: items.map((e) => ({ company: e.company, scope_type: 'company', scope_ref: e.company, period: 'month', token_limit: e.tokens_month, enabled: true })) };
        return call<unknown>('PUT', '/budgets', body, { 'X-Step-Up': await stepUp('budgets.update', await bodyTarget(JSON.stringify(body))) });
      },
      onSuccess: () => Promise.all([done(), qc.invalidateQueries({ queryKey: ['treasury'] })]),
    }),
    close: useMutation({ mutationFn: () => call<Hiring>('POST', '/owner/hiring/close', {}), onSuccess: done }),
    // The seal is bound to the exact body: the server hashes what it received and compares.
    hire: useMutation({
      mutationFn: async (body: HireIn) => call<HireOut>('POST', '/org/hires', body, { 'X-Step-Up': await stepUp('hire.direct', await bodyTarget(JSON.stringify(body))) }),
      onSuccess: async () => { await done(); await qc.invalidateQueries({ queryKey: ['employees'] }); await qc.invalidateQueries({ queryKey: ['companies'] }); },
    }),
  };
}

// ------------------------------------------------------------- stories --
// Contract §18.12 (v1.4.3): designed cards per company, system and CEO posts, 24 hours, pulled and never pushed.
export type StoryKind = 'hire' | 'deliverable' | 'stars' | 'milestone' | 'post';
export type Story = {
  id: string; ref: string; company: string; kind: StoryKind; author: Actor; title_fa: string; body_fa: string;
  figures: Array<{ label_fa: string; value: string }>; media: MediaRef | null;
  links: { employee?: string; deliverable?: string; decision?: string; work?: string; period?: string };
  created_at: string; expires_at: string; seen: boolean; welcomed: boolean;
};
export type StoryRing = { company: string; unseen: number; latest_at: string; items: Story[] };
export const useStories = () => useQuery({ queryKey: ['stories'], queryFn: () => call<StoryRing[]>('GET', '/stories'), refetchInterval: 120_000 });
export function useStoryAction() {
  const qc = useQueryClient();
  return {
    // Seen is quiet: the rings update without refetching the open viewer's data.
    seen: useMutation({ mutationFn: (refs: string[]) => call<unknown>('POST', '/stories/seen', { refs }),
      onSuccess: (_d, refs) => qc.setQueryData<StoryRing[]>(['stories'], (rings) => rings?.map((r) => {
        const items = r.items.map((it) => (refs.includes(it.ref) ? { ...it, seen: true } : it));
        return { ...r, items, unseen: items.filter((it) => !it.seen).length };
      })) }),
    welcome: useMutation({ mutationFn: (ref: string) => call<Story>('POST', `/stories/${ref}/welcome`, {}), onSuccess: () => qc.invalidateQueries({ queryKey: ['stories'] }) }),
    // Undoing a hire is the employee's dismissal (§4), sealed on the code.
    dismiss: useMutation({
      mutationFn: async (code: string) => call<unknown>('POST', `/employees/${code}/dismiss`, { reason: 'مالک: از استوری' }, { 'X-Step-Up': await stepUp('employee.dismiss', code) }),
      onSuccess: () => Promise.all(['stories', 'employees', 'companies', 'hiring'].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
    }),
  };
}
