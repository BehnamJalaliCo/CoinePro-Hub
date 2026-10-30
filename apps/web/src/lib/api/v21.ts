'use client';

// The Android app's 0.3.0–0.6.0 on the web (contract §5.2 ⟨1.7.3⟩, §4 ⟨1.7.4⟩, §6, §9, §24, §25): outputs seen and filed, the owner's
// orders (`created_by=owner`, children two levels down, tree events), notifications read by ids, deleting or archiving a company, the
// founding's own fields, the control history, and the browser's push subscription. The hub serves all of it (prompts 15.1 and 15.2);
// until the OpenAPI file is regenerated here, the shapes live in this file, written from the contract and the hub's routes.

import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSyncExternalStore } from 'react';
import { bodyTarget, stepUp } from '@/lib/auth';
import { isUuid, isWorkRef, refPrefix } from '@/lib/refs';
import { ApiError, type Schemas } from './client';
import { call } from './v13';
import { qs } from './v15';

type Page<T> = { items: T[]; next_cursor: string | null };
const enc = encodeURIComponent;

// =================================================================================================== outputs ⟨1.7.3⟩ ==
export type Category = 'report' | 'work';
/** A deliverable as a ⟨1.7.3⟩ hub serves it: its category, when the owner marked it seen, and the archive record it was filed as. */
export type Output = Schemas['Deliverable'] & { category?: Category | null; seen_at?: string | null; filed_as?: string | null };

export type OutputQuery = {
  seen?: boolean | null; category?: Category | null; unrated?: boolean; company?: string | null; producer?: string | null; q?: string | null;
  /** YYYY-MM-DD in the owner's zone. */
  from?: string | null; to?: string | null;
};

/** The category of an output: the hub's, or (an older hub) a report when the hub's own reporting wrote it. */
export const categoryOf = (d: Output): Category => d.category ?? (d.producer.code.endsWith('-SYS') || d.producer.kind === 'system' ? 'report' : 'work');

/** The filters that narrow the list beyond its tab (the badge on «فیلترها»). */
export const activeFilters = (q: OutputQuery) => [q.category, q.company, q.producer, q.from].filter(Boolean).length + (q.unrated ? 1 : 0);

// «خوانده‌شده» kept in this browser while the hub cannot keep it (a hub before ⟨1.7.3⟩ answers POST /deliverables/seen with 404); only
// refs and instants. Once the hub sends `seen_at`, the outputs page sends these up in one call and forgets them (Android's SeenStore).
const SEEN_KEY = 'hq.seen';
const seenListeners = new Set<() => void>();
let seenCache: Record<string, string> | null = null;
function readSeen(): Record<string, string> {
  if (seenCache) return seenCache;
  try { seenCache = JSON.parse(localStorage.getItem(SEEN_KEY) ?? '{}') as Record<string, string>; } catch { seenCache = {}; }
  return seenCache;
}
function writeSeen(next: Record<string, string>) {
  seenCache = next;
  try { localStorage.setItem(SEEN_KEY, JSON.stringify(next)); } catch { /* private mode: memory only */ }
  for (const l of seenListeners) l();
}
export const localSeen = {
  get: readSeen,
  mark(refs: string[], seen: boolean) {
    const next = { ...readSeen() };
    const at = new Date().toISOString();
    for (const r of refs) if (seen) next[r] ??= at; else delete next[r];
    writeSeen(next);
  },
  forget(refs: string[]) { const next = { ...readSeen() }; for (const r of refs) delete next[r]; writeSeen(next); },
};
const EMPTY: Record<string, string> = {};
export function useLocalSeen(): Record<string, string> {
  return useSyncExternalStore((l) => { seenListeners.add(l); return () => seenListeners.delete(l); }, readSeen, () => EMPTY);
}

export const outputsKey = (q: OutputQuery) => ['deliverables', 'v21', q] as const;
export const useOutputs = (q: OutputQuery) =>
  useInfiniteQuery({
    queryKey: outputsKey(q),
    queryFn: ({ pageParam }) => call<Page<Output>>('GET', `/deliverables${qs({
      seen: q.seen ?? null, category: q.category, unrated: q.unrated ? true : null, company: q.company ? [q.company] : null, producer: q.producer,
      q: q.q?.trim() || null, from: q.from, to: q.to, limit: 100, cursor: pageParam,
    })}`),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
  });
export const useOutput = (ref: string | null) =>
  useQuery({ queryKey: ['deliverables', 'one', ref], enabled: !!ref, queryFn: () => call<Output>('GET', `/deliverables/${enc(ref!)}`) });

/** `GET /inbox/summary` with ⟨1.7.3⟩ `deliverables_unseen`. */
export type Inbox21 = Schemas['InboxSummary'] & { deliverables_unseen?: number | null };

export function useOutputActions() {
  const qc = useQueryClient();
  const done = () => Promise.all(['deliverables', 'inbox', 'archive'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    /** Marks one or many seen (or new again). A hub before ⟨1.7.3⟩ answers 404 or 405: the browser keeps it; `local` says so. */
    seen: useMutation({
      mutationFn: async (v: { refs: string[]; seen: boolean }): Promise<{ local: boolean }> => {
        if (!v.refs.length) return { local: false };
        try {
          await call<{ updated: number }>('POST', '/deliverables/seen', { refs: v.refs, seen: v.seen });
          localSeen.forget(v.refs);
          return { local: false };
        } catch (e) {
          if (e instanceof ApiError && (e.status === 404 || e.status === 405)) { localSeen.mark(v.refs, v.seen); return { local: true }; }
          throw e;
        }
      },
      onSettled: done,
    }),
    /** Files it in the archive (§23): a draft with the body as a PDF; a second call answers the same record. */
    file: useMutation({ mutationFn: (ref: string) => call<{ record: string }>('POST', `/deliverables/${enc(ref)}/file`, {}), onSuccess: done }),
  };
}

// ===================================================================================================== work ⟨1.7.4⟩ ==
export type EmployeeRef = Schemas['EmployeeRef'];
/** A sub-work as the order tracker shows it (prompt 15.1), with its own sub-works, two levels below the work at most. */
export type ChildWork = {
  id: string; ref: string; depth: number; status: string; assignee: EmployeeRef | null; created_at: string; tokens_used: number; usd_used: number;
  title?: string; updated_at?: string; progress?: number | null; deliverable_refs?: string[]; children?: ChildWork[];
};
export type Work = Schemas['Work'] & { deliverable_refs?: string[]; key_result?: string | null };
export type WorkDetail = Omit<Schemas['WorkDetail'], 'children'> & { children: ChildWork[]; deliverable_refs?: string[] };
/** One event of a work's tree: a work event (`work.<kind>`) or an agent run's step (`run.step`, its summary and tool metadata only, §16). */
export type TreeEvent = { id: string; at: string; kind: string; work_id: string; work_ref: string; depth: number; actor_kind: string; actor_code: string; data: Record<string, unknown> };

/** Whether the owner gave this work (an order), as opposed to an agent's delegation. */
export const isOwnerOrder = (w: { created_by?: { kind?: string } | null }) => w.created_by?.kind === 'owner';

/** The owner's orders, newest first: `created_by=owner` (⟨1.7.4⟩); an older hub ignores it and the list is filtered here too. */
export const useOwnerOrders = () =>
  useQuery({
    queryKey: ['work', 'orders'],
    queryFn: async () => (await call<Page<Work>>('GET', `/work${qs({ created_by: 'owner', limit: 100 })}`)).items.filter(isOwnerOrder),
    staleTime: 15_000,
  });

/** Work by id, or by its ref (`W-000104`, as planner rows and messages carry it): the API addresses work by UUID, so a ref is resolved
 *  through the list's search first. Any other ref is not a work: it never reaches the hub as one (its 422). */
export async function fetchWork(key: string): Promise<WorkDetail> {
  if (refPrefix(key) && !isWorkRef(key)) throw new ApiError(404, { code: 'not_found', message_fa: 'این مورد کار نیست؛ از صفحه‌ی خودش باز کن.' });
  if (isWorkRef(key)) {
    const hit = (await call<Page<Work>>('GET', `/work${qs({ q: key, limit: 5 })}`)).items.find((w) => w.ref === key);
    if (!hit) throw new ApiError(404, { code: 'not_found', message_fa: 'این کار پیدا نشد.' });
    return call<WorkDetail>('GET', `/work/${enc(hit.id)}`);
  }
  return call<WorkDetail>('GET', `/work/${enc(key)}`);
}
export const useWorkDetail = (key: string | null) =>
  useQuery({ queryKey: ['work', 'detail', key], enabled: !!key, queryFn: () => fetchWork(key!), staleTime: 10_000 });

/** The work's and its sub-works' events, oldest first (⟨1.7.4⟩). A hub without the route answers 404: the page falls back to its own events. */
export const useTreeEvents = (id: string | null | undefined) =>
  useQuery({
    queryKey: ['work', 'tree-events', id],
    enabled: !!id && (isUuid(id) || !refPrefix(id)),
    queryFn: async () => {
      try {
        return (await call<Page<TreeEvent>>('GET', `/work/${enc(id!)}/tree-events${qs({ limit: 200 })}`)).items;
      } catch (e) {
        if (!(e instanceof ApiError) || (e.status !== 404 && e.status !== 405)) throw e;
        const own = await call<Page<Schemas['WorkEvent']>>('GET', `/work/${enc(id!)}/events`);
        return own.items.map((x): TreeEvent => ({ id: `e${x.id}`, at: x.at, kind: `work.${x.kind}`, work_id: id!, work_ref: '', depth: 0, actor_kind: x.actor_kind, actor_code: x.actor_code, data: x.data }));
      }
    },
    refetchInterval: 20_000,
  });

/** A work item's ref and title for a line that carries only its id or ref (the live stream): looked up once, cached for the session. */
export function useWorkLabel(key: string | null | undefined) {
  return useQuery({
    queryKey: ['work-label', key],
    enabled: !!key && (isUuid(key) || isWorkRef(key)),
    queryFn: async () => {
      try { const w = await fetchWork(key!); return { id: w.id, ref: w.ref, title: w.title } as const; } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    staleTime: Infinity, gcTime: 60 * 60_000, retry: 1,
  });
}

// ============================================================================================= notifications §6, §25 ==
export type Notification = Schemas['Notification'];
export const useNotificationPages = (f: { unread: boolean; level?: string | null }) =>
  useInfiniteQuery({
    queryKey: ['notifications', 'v21', f.unread, f.level ?? ''],
    queryFn: ({ pageParam }) => call<Page<Notification>>('GET', `/notifications${qs({ unread: f.unread, level: f.level, limit: f.unread ? 200 : 100, cursor: pageParam })}`),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });

export function useNotificationActions() {
  const qc = useQueryClient();
  const done = () => Promise.all(['notifications', 'inbox'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    /** ⟨1.7.5⟩ several read in one call; a hub before it (404/405) gets one call per id. */
    read: useMutation({
      mutationFn: async (ids: string[]) => {
        if (!ids.length) return;
        try { await call<{ updated: number }>('POST', '/notifications/read', { ids }); } catch (e) {
          if (!(e instanceof ApiError) || (e.status !== 404 && e.status !== 405)) throw e;
          await Promise.all(ids.map((id) => call<unknown>('POST', `/notifications/${enc(id)}/read`, {})));
        }
      },
      onSettled: done,
    }),
    /** Everything unread up to [before] (the newest the owner saw, so what arrives meanwhile stays unread), of one level or all. */
    readAll: useMutation({ mutationFn: (v: { before?: string | null; level?: string | null }) => call<unknown>('POST', '/notifications/read-all', { ...(v.before ? { before: v.before } : {}), ...(v.level ? { level: v.level } : {}) }), onSettled: done }),
    answer: useMutation({ mutationFn: (v: { id: string; choice: string }) => call<Notification>('POST', `/notifications/${enc(v.id)}/answer`, { choice_id: v.choice }), onSettled: done }),
  };
}

// ======================================================================================================= companies §25 ==
export type Company = Schemas['Company'];
export type DeleteOutcome = 'deleted' | 'has_history' | 'not_served' | 'gone' | 'failed';
export function deleteOutcome(e: unknown): DeleteOutcome {
  if (!e) return 'deleted';
  if (!(e instanceof ApiError)) return 'failed';
  if (e.status === 409 && e.code === 'company_has_history') return 'has_history';
  if (e.status === 405) return 'not_served';
  if (e.status === 404 && e.code === 'not_found') return 'gone';
  if (e.status === 404) return 'not_served';
  return 'failed';
}
/** What the owner typed is the code (any case: the code is what they read on the screen). */
export const codeMatches = (typed: string, code: string) => !!code && typed.trim().toUpperCase() === code.toUpperCase();

export function useCompanyRemoval() {
  const qc = useQueryClient();
  const done = () => Promise.all(['companies', 'control', 'brands', 'founding'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    /** `DELETE /companies/{code}` 🔏 `company.delete` on the code. Asked first without the passkey: a hub without the route answers 405 at
     *  once and the owner is not asked for a seal it cannot use; one that has it answers `403 step_up_required`, and it is sealed and sent. */
    remove: useMutation({
      mutationFn: async (code: string) => {
        try { await call<void>('DELETE', `/companies/${enc(code)}`, undefined, { 'Idempotency-Key': crypto.randomUUID() }); } catch (e) {
          if (!(e instanceof ApiError) || e.status !== 403 || e.code !== 'step_up_required') throw e;
          await call<void>('DELETE', `/companies/${enc(code)}`, undefined, { 'Idempotency-Key': crypto.randomUUID(), 'X-Step-Up': await stepUp('company.delete', code) });
        }
      },
      onSuccess: done,
    }),
    /** `PATCH /companies/{code}` `{status: archived}` 🔏 `company.archive`, with If-Match on the fresh version. */
    archive: useMutation({
      mutationFn: async (code: string) => {
        const fresh = await call<Company>('GET', `/companies/${enc(code)}`);
        return call<Company>('PATCH', `/companies/${enc(code)}`, { status: 'archived' }, { 'If-Match': `"${fresh.version}"`, 'X-Step-Up': await stepUp('company.archive', code) });
      },
      onSuccess: done,
    }),
  };
}

// ======================================================================================================== founding §25 ==
export type FoundingIn = {
  source: { kind: 'idea' | 'repo' | 'blank'; repo?: string | null; brief_md?: string | null };
  name_fa?: string | null; code?: string | null; tagline?: string | null; color_index?: number | null; logo_file_id?: string | null;
};
export type FoundingOut = { ref: string; state: string; company?: string | null };
export function useStartFounding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: FoundingIn) => call<FoundingOut>('POST', '/foundings', b),
    onSuccess: () => Promise.all(['founding', 'companies', 'control', 'brands'].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}

// ========================================================================================================= control §9 ==
export type AuditEntry = Schemas['AuditEntry'];
export type Interaction = { id: string; at: string; company?: string | null; kind: string; action: string; target: { kind?: string; ref?: string }; data: Record<string, unknown> };
/** One change of a switch or of deploys, as the history shows it. */
export type ControlEvent = { at: string; kind: 'engage' | 'release' | 'freeze' | 'unfreeze'; by: Schemas['Actor']; reason: string | null; until: string | null; stepUp: boolean };

const audit = (company: string, action: string, limit: number) => call<Page<AuditEntry>>('GET', `/audit${qs({ company: [company], action, limit })}`).then((p) => p.items);
const ms = (iso: string) => new Date(iso).getTime();

/**
 * A company's control history (newest first): the audit rows of its kill switch and deploy freezes (who and when, every actor), with the
 * reasons: ⟨1.7.3⟩ the audit summary carries `<summary>: <reason>`; the owner's own reasons also come from `GET /owner/interactions?kind=control`.
 */
export async function controlHistory(code: string, holding: boolean, limit = 12): Promise<ControlEvent[]> {
  const scope = holding ? 'holding' : `company:${code}`;
  const [engage, release, freeze, mine] = await Promise.all([
    audit(code, 'kill_switch.engage', limit), audit(code, 'kill_switch.release', limit), holding ? Promise.resolve([]) : audit(code, 'deploy_freeze.set', limit),
    call<Page<Interaction>>('GET', `/owner/interactions${qs({ kind: 'control', limit: 100 })}`).then((p) => p.items).catch(() => [] as Interaction[]),
  ]);
  const reasonOf = (at: string, action: string, ref: string) => {
    const t = ms(at);
    const hit = mine.filter((i) => i.action === action && i.target?.ref === ref).sort((a, b) => Math.abs(ms(a.at) - t) - Math.abs(ms(b.at) - t))[0];
    if (!hit || Math.abs(ms(hit.at) - t) > 5_000) return { reason: null, until: null };
    return { reason: typeof hit.data.reason === 'string' ? hit.data.reason : null, until: typeof hit.data.until === 'string' ? hit.data.until : null };
  };
  // ⟨1.7.3⟩ "changed: engaged: <reason>" — what follows the summary's second colon is the reason.
  const fromSummary = (s: string) => { const m = /^[^:]+:\s*[^:]+:\s*(.+)$/.exec(s); return m?.[1]?.trim() || null; };
  const switches = [...engage, ...release].filter((e) => (e.target?.ref ?? scope) === scope).map((e): ControlEvent => {
    const own = e.actor.kind === 'owner' ? reasonOf(e.at, 'kill_switch.set', scope) : { reason: null, until: null };
    return { at: e.at, kind: e.action.endsWith('engage') ? 'engage' : 'release', by: e.actor, reason: own.reason ?? fromSummary(e.summary), until: null, stepUp: e.step_up };
  });
  const freezes = freeze.filter((e) => (e.target?.ref ?? code) === code).map((e): ControlEvent => {
    const own = e.actor.kind === 'owner' ? reasonOf(e.at, 'deploy_freeze.set', code) : { reason: null, until: null };
    return { at: e.at, kind: e.summary.startsWith('lifted') ? 'unfreeze' : 'freeze', by: e.actor, reason: own.reason ?? fromSummary(e.summary), until: own.until, stepUp: e.step_up };
  });
  return [...switches, ...freezes].sort((a, b) => ms(b.at) - ms(a.at)).slice(0, limit);
}
export const useControlHistory = (code: string, holding: boolean) =>
  useQuery({ queryKey: ['control', 'history', code], queryFn: () => controlHistory(code, holding), staleTime: 30_000 });

/** Lifting every freeze of the company (a past `until`) is sealed with the passkey: `deploy_freeze.lift` on `company:<CODE>` ⟨1.7.3⟩. */
export async function liftFreezes(company: string, reason: string) {
  const token = await stepUp('deploy_freeze.lift', `company:${company}`);
  return call<{ company: string; active: boolean; until: string }>('POST', '/control/deploy-freeze', { company, until: new Date(Date.now() - 60_000).toISOString(), reason }, { 'X-Step-Up': token });
}
export const freezeDeploys = (company: string, hours: number, reason: string) =>
  call<{ company: string; active: boolean; until: string }>('POST', '/control/deploy-freeze', { company, until: new Date(Date.now() + hours * 3_600_000).toISOString(), reason });

/** One month envelope through `PUT /budgets`, sealed on the SHA-256 of the exact body (`budgets.update`). */
export async function putMonthBudget(code: string, holding: boolean, tokenLimit: number | null, usdLimit: string | null) {
  const body = { budgets: [{ company: code, scope_type: holding ? 'holding' : 'company', scope_ref: code, period: 'month', token_limit: tokenLimit, usd_limit: usdLimit, enabled: true }] };
  return call<Schemas['BudgetUse'][]>('PUT', '/budgets', body, { 'X-Step-Up': await stepUp('budgets.update', await bodyTarget(JSON.stringify(body))) });
}

// ========================================================================================================= web push §6 ==
export type PushDevice = { id: string; device_name: string; created_at: string; revoked_at: string | null };
export const vapidKey = () => call<{ public_key: string }>('GET', '/push/vapid-public-key');
export const subscribePush = (b: { endpoint: string; keys: { p256dh: string; auth: string }; device_name: string }) => call<PushDevice>('POST', '/push/web-subscriptions', b);
export const revokePush = (id: string) => call<void>('POST', `/push/web-subscriptions/${enc(id)}/revoke`, {});
