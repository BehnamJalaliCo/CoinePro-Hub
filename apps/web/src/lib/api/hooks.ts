'use client';

import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import type { paths } from '@/generated/api';
import { api, ok, type Schemas } from './client';

/** The query parameters of a GET path, straight from the OpenAPI types. */
type Query<P extends keyof paths> = paths[P] extends { get: { parameters: { query?: infer Q } } } ? NonNullable<Q> : never;

type Opts<T> = Omit<UseQueryOptions<T, Error, T, readonly unknown[]>, 'queryKey' | 'queryFn'>;

// ------------------------------------------------------------------ session --
export const useSession = (o?: Opts<Schemas['SessionInfo']>) =>
  useQuery({ queryKey: ['session'], queryFn: () => ok(api.GET('/api/v1/auth/session')), retry: false, staleTime: 60_000, ...o });
export const useMeta = () => useQuery({ queryKey: ['meta'], queryFn: () => ok(api.GET('/api/v1/meta')), staleTime: 300_000 });

// -------------------------------------------------------------------- inbox --
export const useInbox = () => useQuery({ queryKey: ['inbox'], queryFn: () => ok(api.GET('/api/v1/inbox/summary')), refetchInterval: 60_000 });
export const useAway = () => useQuery({ queryKey: ['away'], queryFn: () => ok(api.GET('/api/v1/owner/away-summary')) });
export const usePresence = () => useQuery({ queryKey: ['presence'], queryFn: () => ok(api.GET('/api/v1/owner/presence')) });
export function useSetKhalvat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (khalvat: boolean) => ok(api.PUT('/api/v1/owner/presence', { body: { khalvat } })),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['presence'] }); void qc.invalidateQueries({ queryKey: ['inbox'] }); },
  });
}

// ---------------------------------------------------------------- decisions --
export type DecisionFilter = Query<'/api/v1/decisions'>;
export const useDecisions = (f: DecisionFilter = {}) =>
  useQuery({ queryKey: ['decisions', f], queryFn: () => ok(api.GET('/api/v1/decisions', { params: { query: f } })) });
export const useDecision = (ref: string | null) =>
  useQuery({ queryKey: ['decisions', 'one', ref], enabled: !!ref, queryFn: () => ok(api.GET('/api/v1/decisions/{ref}', { params: { path: { ref: ref! } } })) });

export function useDecide() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { ref: string; verdict: 'approve' | 'reject' | 'return'; note?: string; reasonCode?: string; amendments?: Record<string, unknown> | null; stepUpToken?: string }) => {
      const path = { ref: v.ref };
      const headers = v.stepUpToken ? { 'X-Step-Up': v.stepUpToken } : undefined;
      if (v.verdict === 'approve') return ok(api.POST('/api/v1/decisions/{ref}/approve', { params: { path }, body: { note: v.note ?? null, amendments: v.amendments ?? null }, headers }));
      if (v.verdict === 'reject') return ok(api.POST('/api/v1/decisions/{ref}/reject', { params: { path }, body: { reason: v.note ?? null, reason_code: (v.reasonCode ?? null) as never } }));
      return ok(api.POST('/api/v1/decisions/{ref}/return', { params: { path }, body: { note: v.note ?? '' } }));
    },
    // ⟨1.7⟩ 'archive': sealing an archive_schema or archive_disposal card changes the schema or the records (§23.11).
    onSuccess: () => { for (const k of ['decisions', 'inbox', 'away', 'resolutions', 'archive']) void qc.invalidateQueries({ queryKey: [k] }); },
  });
}
export function useAskAboutDecision() {
  return useMutation({ mutationFn: (v: { ref: string; question: string }) => ok(api.POST('/api/v1/decisions/{ref}/ask', { params: { path: { ref: v.ref } }, body: { question: v.question } })) });
}
export function useReviewWithAdvisor() {
  return useMutation({ mutationFn: (ref: string) => ok(api.POST('/api/v1/decisions/{ref}/review-with-advisor', { params: { path: { ref } } })) });
}

// ------------------------------------------------------------- deliverables --
export const useDeliverables = (f: Query<'/api/v1/deliverables'> = {}) =>
  useQuery({ queryKey: ['deliverables', f], queryFn: () => ok(api.GET('/api/v1/deliverables', { params: { query: f } })) });
export const useDeliverable = (ref: string | null) =>
  useQuery({ queryKey: ['deliverables', 'one', ref], enabled: !!ref, queryFn: () => ok(api.GET('/api/v1/deliverables/{ref}', { params: { path: { ref: ref! } } })) });
export function useRate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { ref: string; score: number; comment?: string }) => ok(api.POST('/api/v1/deliverables/{ref}/rating', { params: { path: { ref: v.ref } }, body: { score: v.score, comment: v.comment ?? null } })),
    onSuccess: () => { for (const k of ['deliverables', 'inbox', 'employees']) void qc.invalidateQueries({ queryKey: [k] }); },
  });
}

// ------------------------------------------------------------- organisation --
export const useCompanies = () => useQuery({ queryKey: ['companies'], queryFn: () => ok(api.GET('/api/v1/companies')), staleTime: 30_000 });
export const useCompany = (code: string) => useQuery({ queryKey: ['companies', code], queryFn: () => ok(api.GET('/api/v1/companies/{code}', { params: { path: { code } } })) });
export const useDepartments = (code: string) => useQuery({ queryKey: ['companies', code, 'departments'], queryFn: () => ok(api.GET('/api/v1/companies/{code}/departments', { params: { path: { code } } })) });
export const useOrgChart = (company: string) => useQuery({ queryKey: ['employees', 'chart', company], queryFn: () => ok(api.GET('/api/v1/org/{company}/chart', { params: { path: { company } } })) });
export const useEmployees = (f: Query<'/api/v1/employees'> = {}) =>
  useQuery({ queryKey: ['employees', f], queryFn: () => ok(api.GET('/api/v1/employees', { params: { query: f } })) });
export const useEmployee = (code: string) => useQuery({ queryKey: ['employees', 'one', code], queryFn: () => ok(api.GET('/api/v1/employees/{code}', { params: { path: { code } } })) });

// --------------------------------------------------------------------- work --
export const useWorkList = (f: Query<'/api/v1/work'> = {}) =>
  useQuery({ queryKey: ['work', f], queryFn: () => ok(api.GET('/api/v1/work', { params: { query: f } })) });
export const useWork = (id: string) => useQuery({ queryKey: ['work', 'one', id], queryFn: () => ok(api.GET('/api/v1/work/{id}', { params: { path: { id } } })) });
export const useWorkEvents = (id: string) => useQuery({ queryKey: ['work', 'events', id], queryFn: () => ok(api.GET('/api/v1/work/{id}/events', { params: { path: { id } } })) });
export function useCreateWork() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas['WorkCreate']) => ok(api.POST('/api/v1/work', { body })),
    onSuccess: () => { for (const k of ['work', 'planner', 'companies']) void qc.invalidateQueries({ queryKey: [k] }); },
  });
}
export const usePlanner = (f: Query<'/api/v1/planner'> = {}) =>
  useQuery({ queryKey: ['planner', f], queryFn: () => ok(api.GET('/api/v1/planner', { params: { query: f } })) });

// ----------------------------------------------------------------- messages --
export const useThreads = () => useQuery({ queryKey: ['threads'], queryFn: () => ok(api.GET('/api/v1/threads')) });
export const useMessages = (code: string | null) =>
  useQuery({ queryKey: ['messages', code], enabled: !!code, queryFn: () => ok(api.GET('/api/v1/threads/{code}/messages', { params: { path: { code: code! } } })) });
export function useSend(code: string) {
  const qc = useQueryClient();
  return useMutation({
    // ⟨1.3⟩ attachments: owner file ids (contract §17.1); ⟨1.5⟩ `mode: "devil"`, thread A only (§21.1). The generated types catch up
    // when the server regenerates them.
    mutationFn: (v: { body: string; attachments?: string[]; mode?: 'devil' | null }) =>
      ok(api.POST('/api/v1/threads/{code}/messages', { params: { path: { code } }, body: { body: v.body, ...(v.attachments?.length ? { attachments: v.attachments } : {}), ...(v.mode ? { mode: v.mode } : {}) } as Schemas['MessageIn'] })),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['messages', code] }); void qc.invalidateQueries({ queryKey: ['threads'] }); },
  });
}
export function useMarkRead(code: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (upTo: string) => ok(api.POST('/api/v1/threads/{code}/read', { params: { path: { code } }, body: { up_to_ref: upTo } })),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['threads'] }); void qc.invalidateQueries({ queryKey: ['inbox'] }); },
  });
}

// ------------------------------------------------------------ notifications --
export const useNotifications = (f: Query<'/api/v1/notifications'> = {}) =>
  useQuery({ queryKey: ['notifications', f], queryFn: () => ok(api.GET('/api/v1/notifications', { params: { query: f } })) });
export function useReadAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => ok(api.POST('/api/v1/notifications/read-all', { body: {} })),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['notifications'] }); void qc.invalidateQueries({ queryKey: ['inbox'] }); },
  });
}

// ------------------------------------------------------------------ control --
export const useControl = () => useQuery({ queryKey: ['control'], queryFn: () => ok(api.GET('/api/v1/control/state')) });
export function useKillSwitch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { scope: string; state: 'engaged' | 'released'; reason: string; stepUpToken?: string }) =>
      ok(api.POST('/api/v1/control/kill-switch', { body: { scope: v.scope, state: v.state, reason: v.reason }, headers: v.stepUpToken ? { 'X-Step-Up': v.stepUpToken } : undefined })),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['control'] }); void qc.invalidateQueries({ queryKey: ['companies'] }); },
  });
}

// ----------------------------------------------------------------- treasury --
export const useTreasury = (f: Query<'/api/v1/treasury/summary'> = {}) =>
  useQuery({ queryKey: ['treasury', 'summary', f], queryFn: () => ok(api.GET('/api/v1/treasury/summary', { params: { query: f } })) });
export const useBreakdown = (f: Query<'/api/v1/treasury/breakdown'>) =>
  useQuery({ queryKey: ['treasury', 'breakdown', f], queryFn: () => ok(api.GET('/api/v1/treasury/breakdown', { params: { query: f } })) });
export const useCalls = (f: Query<'/api/v1/treasury/calls'> = {}) =>
  useQuery({ queryKey: ['treasury', 'calls', f], queryFn: () => ok(api.GET('/api/v1/treasury/calls', { params: { query: f } })) });
export const useConnections = () => useQuery({ queryKey: ['treasury', 'connections'], queryFn: () => ok(api.GET('/api/v1/connections')) });

// -------------------------------------------------------------- audit, misc --
export const useAudit = (f: Query<'/api/v1/audit'> = {}) =>
  useQuery({ queryKey: ['audit', f], queryFn: () => ok(api.GET('/api/v1/audit', { params: { query: f } })) });
export const useAuditVerify = () => useQuery({ queryKey: ['audit', 'verify'], queryFn: () => ok(api.GET('/api/v1/audit/verify')) });
export const useResolutions = () => useQuery({ queryKey: ['resolutions'], queryFn: () => ok(api.GET('/api/v1/resolutions')) });
export const useDevices = () => useQuery({ queryKey: ['devices'], queryFn: () => ok(api.GET('/api/v1/auth/devices')) });
export const useOwnerSettings = () => useQuery({ queryKey: ['owner-settings'], queryFn: () => ok(api.GET('/api/v1/owner/settings')) });
