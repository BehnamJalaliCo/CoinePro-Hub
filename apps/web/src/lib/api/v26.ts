'use client';

// ⟨1.8⟩ Contract §26: the companies' servers (pull runners), the owner's terminal, the server policy and the holding's network map.
// The hub has these routes (prompt 17); until the OpenAPI file is regenerated their types live in v26-model.ts, written from §26.5
// and §26.6. Same conventions as the typed client: X-HQ-Client and Idempotency-Key on writes, step-ups as X-Step-Up.

import { useQuery } from '@tanstack/react-query';
import { ApiError, isMock, type Problem } from './client';
import { handled } from './observe';
import { call, type CodeSession } from './v13';
import { bodyTarget, stepUp } from '@/lib/auth';
import { useControl } from './hooks';
import {
  awaitingOf, parseServerMap, SseParser, termEventOf, termEventsOfJson,
  type ExecIn, type HubServer, type NetworkMap, type ServerCall, type ServerMap, type ServerPolicy, type TermEvent,
} from './v26-model';

export * from './v26-model';

const mockHandle = isMock ? async (r: Request) => (await import('@/lib/api/mock')).handle(r) : undefined;

/** A Claude Code session on a company's own server (§26.5): the Workshop's session plus the server and its company. */
export type ServerSession = Omit<CodeSession, 'runtime'> & { runtime: CodeSession['runtime'] | 'company_server'; server?: string | null; company?: string | null };
export const onServer = (s: { runtime: string }) => s.runtime === 'company_server';

// ------------------------------------------------------------------ reads --
/** Every server of the holding (`{items, inventory}`, a Page or a bare list). */
export async function listServers(): Promise<HubServer[]> {
  const out = await call<HubServer[] | { items: HubServer[] }>('GET', '/infra/servers');
  return (Array.isArray(out) ? out : out.items ?? []).map((s) => ({ ...s, origin: s.origin ?? 'attached', state: s.state ?? 'pending', via: s.via ?? null, hub_rtt_ms: s.hub_rtt_ms ?? null }));
}

/** The latest `server.map`; null before the first one (`404`). */
export async function serverMap(id: string): Promise<ServerMap | null> {
  try {
    return parseServerMap(await call<unknown>('GET', `/infra/servers/${encodeURIComponent(id)}/map`));
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) { handled(e); return null; }
    throw e;
  }
}

/** Queues a `map` job (§26.4): the map when the runner answers in time, else `202 {job}` (null; `server.state` follows). */
export async function refreshMap(id: string): Promise<ServerMap | null> {
  const out = await call<Record<string, unknown>>('POST', `/infra/servers/${encodeURIComponent(id)}/map`, {});
  if (!out || (out.job && !out.map && !out.at)) return null;
  return parseServerMap(out);
}

export const serverActivity = (id: string, actor?: string | null, limit = 50) =>
  call<{ items: ServerCall[]; next_cursor: string | null }>('GET', `/infra/servers/${encodeURIComponent(id)}/activity?limit=${limit}${actor ? `&actor=${encodeURIComponent(actor)}` : ''}`);

export const network = () => call<NetworkMap>('GET', '/infra/network');
export const serverPolicy = () => call<ServerPolicy>('GET', '/control/server-policy');

/** A transcript the hub stores (§26.3: owner-readable): an API path on the hub's own origin, read with the session. */
export async function transcript(url: string): Promise<string> {
  const u = new URL(url, window.location.origin);
  if (u.origin !== window.location.origin || !u.pathname.startsWith('/api/')) throw new ApiError(422, { code: 'validation_failed', message_fa: 'این نشانی بیرون از هاب است؛ پنل آن را باز نمیکند.' });
  const req = new Request(u, { headers: { Accept: 'text/plain, application/json' }, credentials: 'same-origin' });
  let res: Response;
  try { res = mockHandle ? await mockHandle(req) : await fetch(req); } catch { throw new ApiError(0, undefined); }
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => undefined)) as Partial<Problem> | undefined);
  return res.text();
}

// ------------------------------------------------------------------ writes --
/** Pairing (§26.1): the code `hq-runner pair` printed, approved with the passkey, 🔏 `server.attach` on `company:<CODE>`. */
export async function approveRunner(company: string, userCode: string): Promise<HubServer> {
  const token = await stepUp('server.attach', `company:${company}`);
  const out = await call<{ server?: HubServer } & HubServer>('POST', '/runners/approve', { user_code: userCode }, { 'X-Step-Up': token });
  return out.server ?? out;
}

/** 🔏 `server.detach` on `<CODE>:<server>`: revokes the runner's token at once; the runner stops on its next poll. */
export async function detachServer(s: HubServer): Promise<void> {
  const token = await stepUp('server.detach', `${s.company}:${s.name}`);
  await call<unknown>('DELETE', `/infra/servers/${encodeURIComponent(s.id)}`, undefined, { 'X-Step-Up': token, 'Idempotency-Key': crypto.randomUUID() });
}

/** The owner asks every online runner to check its roads now (§26.6 `netcheck`); results follow on `GET /infra/network`. */
export const checkNetwork = () => call<{ queued: number }>('POST', '/infra/network/check', {});

/** 🔏 PUT on the SHA-256 of the exact body (`server.policy`). */
export async function putServerPolicy(p: ServerPolicy): Promise<ServerPolicy> {
  const body = { seal_required: p.seal_required };
  const token = await stepUp('server.policy', await bodyTarget(JSON.stringify(body)));
  return call<ServerPolicy>('PUT', '/control/server-policy', body, { 'X-Step-Up': token });
}

/** Claude Code on the company's server (§26.5 `runtime: "company_server"`), driven by an agent of the company or the owner (null). */
export const startServerSession = (s: HubServer, v: { driver: string | null; title: string; brief: string; attachments: string[]; cwd: string | null }) =>
  call<ServerSession>('POST', '/workshop/sessions', {
    runtime: 'company_server', server: s.id, company: s.company, driver: v.driver, title: v.title, brief: v.brief, attachments: v.attachments, ...(v.cwd ? { cwd: v.cwd } : {}),
  });

/**
 * The owner's own command, 🔏 `server.exec` bound to the SHA-256 of the exact body (a passkey per command, for exactly that command),
 * streamed as SSE: stdout and stderr as they come, then the exit. A `202 awaiting_seal` (a destructive command the policy holds) is one
 * awaiting_seal event; a refusal (`423 company_locked`) throws.
 */
export async function execOnServer(s: HubServer, body: ExecIn, onEvent: (e: TermEvent) => void, signal: AbortSignal): Promise<void> {
  const text = JSON.stringify(body);
  const token = await stepUp('server.exec', await bodyTarget(text));
  const req = new Request(new URL(`/api/v1/infra/servers/${encodeURIComponent(s.id)}/exec`, window.location.origin), {
    method: 'POST', body: text, credentials: 'same-origin', signal,
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', 'X-HQ-Client': 'web', 'Idempotency-Key': crypto.randomUUID(), 'X-Step-Up': token },
  });
  let res: Response;
  try { res = mockHandle ? await mockHandle(req) : await fetch(req); } catch (e) { if (signal.aborted) throw e; throw new ApiError(0, undefined); }
  if (res.status === 202) { onEvent(awaitingOf((await res.json().catch(() => null)) as Record<string, unknown> | null)); return; }
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => undefined)) as Partial<Problem> | undefined);
  if ((res.headers.get('Content-Type') ?? '').includes('json')) { termEventsOfJson((await res.json()) as Record<string, unknown>).forEach(onEvent); return; }
  if (!res.body) return;
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  const p = new SseParser();
  let rest = '';
  const onAbort = () => { void reader.cancel(); };
  signal.addEventListener('abort', onAbort);
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      const lines = (rest + value).split('\n');
      rest = lines.pop() ?? '';
      for (const l of lines) { const m = p.line(l); const e = m && termEventOf(m); if (e) onEvent(e); }
    }
    if (rest) p.line(rest);
    const m = p.end(); const e = m && termEventOf(m); if (e) onEvent(e);
  } finally {
    signal.removeEventListener('abort', onAbort);
  }
}

// ------------------------------------------------------------------ hooks --
export const useServers = () => useQuery({ queryKey: ['servers', 'list'], queryFn: listServers, staleTime: 30_000 });
export const useServerMap = (id: string | null, enabled = true) =>
  useQuery({ queryKey: ['servers', 'map', id], queryFn: () => serverMap(id!), enabled: !!id && enabled, staleTime: 60_000 });
export const useServerActivity = (id: string, actor: string | null = null, limit = 50) =>
  useQuery({ queryKey: ['servers', 'activity', id, actor, limit], queryFn: () => serverActivity(id, actor, limit), staleTime: 15_000, refetchInterval: 15_000 });
export const useNetwork = () => useQuery({ queryKey: ['network'], queryFn: network, staleTime: 30_000 });
export const useServerPolicy = () => useQuery({ queryKey: ['servers', 'policy'], queryFn: serverPolicy, staleTime: 120_000 });
export const useTranscript = (url: string | null) => useQuery({ queryKey: ['servers', 'transcript', url], queryFn: () => transcript(url!), enabled: !!url, staleTime: 300_000 });

/** Whether the company's kill switch (or the holding's) stands: then its servers are locked (§26.3 `423 company_locked`). */
export function useLocked(company: string | null | undefined): boolean {
  const { data } = useControl();
  if (!company || !data) return false;
  if (data.holding.state === 'engaged') return true;
  return data.companies.some((k) => (k.scope === `company:${company}` || k.company === company) && k.state === 'engaged');
}
