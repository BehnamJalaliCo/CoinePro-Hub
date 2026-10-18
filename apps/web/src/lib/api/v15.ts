'use client';

// The owner's tools on APIs the hub already serves (docs/GAP_ANALYSIS_v2.md §5A): resolutions, notification settings, message
// search, deploy freezes, work and employee actions, agent runs, the treasury's what-if, calls, quota, connections and budgets,
// site checks and incidents. Types come from the generated OpenAPI file; calls go through `call` (X-HQ-Client, Idempotency-Key).

import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { bodyTarget, stepUp } from '@/lib/auth';
import type { Schemas } from './client';
import { call } from './v13';

export type Resolution = Schemas['Resolution'];
export type SearchHit = Schemas['SearchHit'];
export type Run = Schemas['Run'];
export type RunDetail = Schemas['RunDetail'];
export type Site = Schemas['Site'];
export type SiteIn = Schemas['SiteIn'];
export type Incident = Schemas['Incident'];
export type Call = Schemas['Call'];
export type WhatIf = Schemas['WhatIf'];
export type QuotaView = Schemas['QuotaView'];
export type Connection = Schemas['Connection'];
export type BudgetUse = Schemas['BudgetUse'];
export type LevelSettings = Schemas['LevelSettings'];
export type NotificationSettings = Schemas['NotificationSettings'];
export type Level = 'urgent' | 'decision' | 'report' | 'info' | 'learning';
export const LEVELS: Level[] = ['urgent', 'decision', 'report', 'info', 'learning'];
type Page<T> = { items: T[]; next_cursor: string | null };

const qs = (o: Record<string, string | number | boolean | null | undefined | string[]>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) {
    if (v == null || v === '') continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : '';
};
const ifMatch = (version: number) => ({ 'If-Match': `"${version}"` });

// ------------------------------------------------------------ resolutions --
export const useResolutionList = (f: { q?: string; company?: string | null } = {}) =>
  useQuery({ queryKey: ['resolutions', f.q ?? '', f.company ?? ''], queryFn: () => call<Page<Resolution>>('GET', `/resolutions${qs({ q: f.q, company: f.company })}`), placeholderData: keepPreviousData });
export const useResolution = (ref: string | null) =>
  useQuery({ queryKey: ['resolutions', 'one', ref], queryFn: () => call<Resolution>('GET', `/resolutions/${ref}`), enabled: !!ref });
export function useRecordResolution() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { title: string; body: string; source_message?: string | null }) => call<Resolution>('POST', '/resolutions', b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resolutions'] }),
  });
}

// --------------------------------------------------- notification settings --
export const useNotificationSettings = () => useQuery({ queryKey: ['notification-settings'], queryFn: () => call<NotificationSettings>('GET', '/notification-settings') });
export function useSaveNotificationSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (s: NotificationSettings) => call<NotificationSettings>('PUT', '/notification-settings', { matrix: s.matrix }, ifMatch(s.version)),
    onSuccess: (s) => qc.setQueryData(['notification-settings'], s),
  });
}
/** What one level does for one company: its own row over the "*" row over the contract's defaults (§6). */
export function effective(m: NotificationSettings['matrix'] | undefined, scope: string, level: Level): Required<{ [K in keyof LevelSettings]: NonNullable<LevelSettings[K]> | null }> {
  const base = { in_app: true, push: level === 'urgent' || level === 'decision', sound: level === 'urgent', muted_until: null as string | null };
  const all = m?.['*']?.[level] ?? {};
  const own = scope === '*' ? {} : m?.[scope]?.[level] ?? {};
  const pick = <K extends keyof LevelSettings>(k: K) => (own[k] ?? all[k] ?? base[k]) as never;
  return { in_app: pick('in_app'), push: pick('push'), sound: pick('sound'), muted_until: pick('muted_until') };
}

// ----------------------------------------------------------------- search --
export const useMessageSearch = (q: string, f: { thread?: string | null; company?: string | null } = {}) =>
  useQuery({
    queryKey: ['search', 'messages', q, f.thread ?? '', f.company ?? ''],
    queryFn: () => call<Page<SearchHit>>('GET', `/search/messages${qs({ q, thread: f.thread, company: f.company, limit: 20 })}`),
    enabled: q.trim().length >= 2, staleTime: 30_000, placeholderData: keepPreviousData,
  });

// ---------------------------------------------------------------- control --
export function useDeployFreeze() {
  const qc = useQueryClient();
  return useMutation({
    // A past `until` lifts the company's freezes (§9): the owner lifts any of them.
    mutationFn: (b: { company: string; until: string; reason: string }) => call<{ company: string; active: boolean; until: string }>('POST', '/control/deploy-freeze', b),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: ['control'] }), qc.invalidateQueries({ queryKey: ['companies'] })]),
  });
}

// ------------------------------------------------------------------- work --
export type EvidenceIn = { kind: 'deliverable' | 'link' | 'metric' | 'log'; ref: string; note?: string | null };
export function useWorkAction() {
  const qc = useQueryClient();
  const done = () => Promise.all(['work', 'planner', 'companies', 'inbox'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    cancel: useMutation({ mutationFn: (v: { id: string; reason: string }) => call<unknown>('POST', `/work/${v.id}/cancel`, { reason: v.reason }), onSuccess: done }),
    complete: useMutation({ mutationFn: (v: { id: string; evidence: EvidenceIn[] }) => call<unknown>('POST', `/work/${v.id}/complete`, { evidence: v.evidence }), onSuccess: done }),
    edit: useMutation({
      mutationFn: (v: { id: string; version: number; patch: { title?: string; brief?: string; priority?: string; due_at?: string | null } }) =>
        call<unknown>('PATCH', `/work/${v.id}`, v.patch, ifMatch(v.version)),
      onSuccess: done,
    }),
  };
}

// -------------------------------------------------------------- employees --
export function useEmployeeAction() {
  const qc = useQueryClient();
  const done = () => Promise.all(['employees', 'companies', 'stories', 'work'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    pause: useMutation({ mutationFn: (code: string) => call<unknown>('POST', `/employees/${code}/pause`, {}), onSuccess: done }),
    resume: useMutation({ mutationFn: (code: string) => call<unknown>('POST', `/employees/${code}/resume`, {}), onSuccess: done }),
    // Dismissal is sealed on the code (§4): open work returns to the manager or goes to `transfer_to`, and a knowledge-transfer item is created.
    dismiss: useMutation({
      mutationFn: async (v: { code: string; reason: string; transfer_to?: string | null }) =>
        call<{ employee: unknown; work_returned: number; transfer_work: string | null }>('POST', `/employees/${v.code}/dismiss`, { reason: v.reason, ...(v.transfer_to ? { transfer_to: v.transfer_to } : {}) }, { 'X-Step-Up': await stepUp('employee.dismiss', v.code) }),
      onSuccess: done,
    }),
  };
}

// ------------------------------------------------------------------- runs --
export type RunState = 'queued' | 'running' | 'done' | 'failed' | 'refused';
export const useRuns = (f: { employee?: string | null; company?: string | null; state?: RunState | null; limit?: number } = {}) =>
  useQuery({
    queryKey: ['runs', f.employee ?? '', f.company ?? '', f.state ?? '', f.limit ?? 50],
    queryFn: () => call<Page<Run>>('GET', `/runs${qs({ employee: f.employee, company: f.company ? [f.company] : null, state: f.state, limit: f.limit ?? 50 })}`),
    refetchInterval: 20_000, placeholderData: keepPreviousData,
  });
export const useRun = (id: string | null) => useQuery({ queryKey: ['runs', 'one', id], queryFn: () => call<RunDetail>('GET', `/runs/${id}`), enabled: !!id, refetchInterval: (q) => (q.state.data?.state === 'running' ? 4_000 : false) });
export const useWorkRuns = (id: string) => useQuery({ queryKey: ['runs', 'work', id], queryFn: () => call<RunDetail[]>('GET', `/work/${id}/runs`), refetchInterval: 15_000 });

// --------------------------------------------------------------- treasury --
export const useQuota = () => useQuery({ queryKey: ['treasury', 'quota'], queryFn: () => call<QuotaView>('GET', '/treasury/quota'), refetchInterval: 60_000 });
export const useWhatIf = (f: { model: string | null; from: string; to: string; company?: string | null }) =>
  useQuery({ queryKey: ['treasury', 'what-if', f], queryFn: () => call<WhatIf>('GET', `/treasury/what-if${qs({ model: f.model, from: f.from, to: f.to, company: f.company })}`), enabled: !!f.model });
export const useCallPages = (f: { company?: string | null; actor?: string | null; status?: string | null }) =>
  useInfiniteQuery({
    queryKey: ['treasury', 'calls', f],
    queryFn: ({ pageParam }) => call<Page<Call>>('GET', `/treasury/calls${qs({ company: f.company, actor: f.actor, status: f.status, limit: 25, cursor: pageParam })}`),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
export const useBudgets = () => useQuery({ queryKey: ['treasury', 'budgets'], queryFn: () => call<BudgetUse[]>('GET', '/budgets') });
export type BudgetIn = { company: string; scope_type: 'holding' | 'company'; scope_ref: string; period: 'day' | 'month'; token_limit: number | null; usd_limit: string | null; enabled: boolean };
export function useTreasuryAction() {
  const qc = useQueryClient();
  const done = () => Promise.all(['treasury', 'hiring'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    // PUT /budgets is sealed on the SHA-256 of the exact body (§9 ⟨1.1⟩).
    budgets: useMutation({
      mutationFn: async (items: BudgetIn[]) => {
        const body = { budgets: items };
        return call<BudgetUse[]>('PUT', '/budgets', body, { 'X-Step-Up': await stepUp('budgets.update', await bodyTarget(JSON.stringify(body))) });
      },
      onSuccess: done,
    }),
    connection: useMutation({
      mutationFn: async (v: { c: Connection; patch: { status?: 'enabled' | 'disabled'; display_name?: string } }) =>
        call<Connection>('PATCH', `/connections/${v.c.id}`, v.patch, { ...ifMatch(v.c.version), 'X-Step-Up': await stepUp('connection.update', v.c.id) }),
      onSuccess: done,
    }),
    // Write-only: the key goes to the secret store and never comes back (§10).
    secret: useMutation({
      mutationFn: async (v: { id: string; secret: string }) => call<{ connection: string; stored: boolean }>('POST', `/connections/${v.id}/secret`, { secret: v.secret }, { 'X-Step-Up': await stepUp('connection.secret', v.id) }),
      onSuccess: done,
    }),
  };
}

// -------------------------------------------------------------------- ops --
export const useSites = (company?: string | null) => useQuery({ queryKey: ['ops', 'sites', company ?? ''], queryFn: () => call<Site[]>('GET', `/ops/sites${qs({ company })}`), refetchInterval: 60_000 });
export const useIncidents = (f: { company?: string | null; open?: boolean } = {}) =>
  useQuery({ queryKey: ['ops', 'incidents', f.company ?? '', f.open ?? null], queryFn: () => call<Incident[]>('GET', `/ops/incidents${qs({ company: f.company, open: f.open, limit: 100 })}`), refetchInterval: 60_000 });
export function usePutSites() {
  const qc = useQueryClient();
  return useMutation({
    // Sites left out are switched off, never deleted; canaries are untouched. Sealed on the body's SHA-256 (§16.6).
    mutationFn: async (body: { company: string; sites: SiteIn[] }) => call<Site[]>('PUT', '/ops/sites', body, { 'X-Step-Up': await stepUp('sites.update', await bodyTarget(JSON.stringify(body))) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ops'] }),
  });
}

// ----------------------------------------------------------------- export --
/** CSV with a BOM so Excel opens Persian text correctly; every cell is quoted. */
export function downloadCsv(name: string, header: string[], rows: Array<Array<string | number | null | undefined>>): void {
  const cell = (v: string | number | null | undefined) => `"${String(v ?? '').replaceAll('"', '""')}"`;
  const text = '﻿' + [header, ...rows].map((r) => r.map(cell).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
  const a = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
