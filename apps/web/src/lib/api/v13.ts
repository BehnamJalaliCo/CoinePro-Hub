'use client';

// Contract v1.3 (§17): uploads and attachments, voice to text, the Code Workshop and voice orders.
// The server implements these in prompt 6; until it regenerates the OpenAPI file, the types live here,
// written from the contract. Same conventions as the typed client: X-HQ-Client and Idempotency-Key on
// writes, Problem errors as ApiError.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { ApiError, isMock, type Problem } from './client';

export type FileKind = 'image' | 'video' | 'audio' | 'document';
export type MediaRef = {
  id: string; name: string; mime: string; size: number; sha256: string;
  kind: FileKind; status: 'processing' | 'ready' | 'failed';
  width?: number; height?: number; duration_s?: number;
  variants?: { thumb?: string; poster?: string };
  transcript?: string;
};
export type Transcript = {
  text: string; language: 'fa'; duration_s: number; confidence: number;
  segments: Array<{ start_s: number; end_s: number; text: string }>;
  file_id: string; engine: { name: string; model: string; version: string };
};

export type Actor = { kind: string; code: string; display_fa?: string | null };
export type Workspace = {
  id: string; code: string; company: string; repo: string; default_branch: string; title_fa: string;
  policy: { branch_prefix: string; may_open_pr: boolean; merge: string; deploy: string }; status: 'active' | 'paused';
};
export type Grant = {
  id: string; ref: string; workspace: string; actions: string[]; driver: Actor | null; budget_usd: number;
  expires_at: string; granted_by: Actor; decision_ref: string | null; revoked_at: string | null;
};
export type SessionState = 'starting' | 'working' | 'waiting_approval' | 'idle' | 'done' | 'failed' | 'stopped';
export type CodeSession = {
  id: string; ref: string; workspace: string; grant: string; title: string; brief: string;
  opened_by: Actor; driver: Actor; runtime: 'managed' | 'self_hosted'; model: string; effort: string;
  state: SessionState; branch: string | null; pr_url: string | null;
  usage: { usd: number; input_tokens: number; output_tokens: number }; created_at: string; updated_at: string;
};
export type SessionEventType = 'message' | 'progress' | 'command' | 'file_change' | 'approval_request' | 'approval_result' | 'state' | 'error';
export type SessionEvent = { seq: number; at: string; type: SessionEventType; actor: Actor; summary_fa: string; data: Record<string, unknown> };
export type OrderRoute = { company: string; to: string; kind: 'work' | 'code' | 'meeting' | 'question'; work_ref?: string; session_ref?: string; decision_ref?: string };
export type OrderOut = {
  ref: string; summary_fa: string;
  routes: OrderRoute[];
};

// Same path as the typed client, so next.config's alias swaps the fixtures out of production builds.
const mockHandle = isMock ? async (r: Request) => (await import('@/lib/api/mock')).handle(r) : undefined;

async function problem(res: Response): Promise<never> {
  let p: Partial<Problem> | undefined;
  try { p = (await res.json()) as Partial<Problem>; } catch { /* not JSON */ }
  throw new ApiError(res.status, p);
}

/** One JSON call against /api/v1 with the contract's headers. */
export async function call<T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
  const h = new Headers(headers);
  h.set('Accept', 'application/json');
  if (method !== 'GET') {
    h.set('X-HQ-Client', 'web');
    h.set('Content-Type', 'application/json');
    if (method === 'POST' && !h.has('Idempotency-Key')) h.set('Idempotency-Key', crypto.randomUUID());
  }
  const req = new Request(new URL(`/api/v1${path}`, window.location.origin), {
    method, headers: h, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body),
  });
  let res: Response;
  try {
    res = mockHandle ? await mockHandle(req) : await fetch(req);
  } catch {
    throw new ApiError(0, undefined);
  }
  if (!res.ok) return problem(res);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

/** Where a file (or one of its variants) is served. Demo ids are already URLs. */
export function fileUrl(id: string, variant: 'original' | 'thumb' | 'poster' = 'original'): string {
  if (id.startsWith('blob:') || id.startsWith('data:')) return id;
  return `/api/v1/files/${encodeURIComponent(id)}${variant === 'original' ? '' : `?variant=${variant}`}`;
}

export function kindOf(mime: string): FileKind {
  if (mime.startsWith('image/')) return 'image';
  if (mime.startsWith('video/')) return 'video';
  if (mime.startsWith('audio/')) return 'audio';
  return 'document';
}

/** Raw-body upload with progress (fetch has no upload progress, so XHR). */
export function uploadFile(file: Blob, name: string, onProgress?: (pct: number) => void, signal?: AbortSignal): Promise<MediaRef> {
  if (isMock) {
    return new Promise((resolve, reject) => {
      let p = 0;
      const t = setInterval(() => {
        p = Math.min(100, p + 18);
        onProgress?.(p);
        if (p >= 100) {
          clearInterval(t);
          const url = URL.createObjectURL(file);
          const ref: MediaRef = { id: url, name, mime: file.type, size: file.size, sha256: '', kind: kindOf(file.type), status: 'ready', variants: {} };
          void import('@/lib/api/mock').then((m) => m.register(ref));
          resolve(ref);
        }
      }, 120);
      signal?.addEventListener('abort', () => { clearInterval(t); reject(new ApiError(0, { code: 'aborted', message_fa: 'لغو شد.' })); });
    });
  }
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/v1/files');
    xhr.withCredentials = true;
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
    xhr.setRequestHeader('X-File-Name', encodeURIComponent(name));
    xhr.setRequestHeader('X-HQ-Client', 'web');
    xhr.setRequestHeader('Idempotency-Key', crypto.randomUUID());
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress?.(Math.round((e.loaded / e.total) * 100)); };
    xhr.onload = () => {
      let body: unknown;
      try { body = JSON.parse(xhr.responseText); } catch { body = undefined; }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as MediaRef);
      else reject(new ApiError(xhr.status, body as Partial<Problem> | undefined));
    };
    xhr.onerror = () => reject(new ApiError(0, undefined));
    xhr.onabort = () => reject(new ApiError(0, { code: 'aborted', message_fa: 'لغو شد.' }));
    signal?.addEventListener('abort', () => xhr.abort());
    xhr.send(file);
  });
}

/** Exact Persian text from the owner's voice (contract §17.2). */
export async function transcribe(audio: Blob, purpose: 'message' | 'order' | 'note', signal?: AbortSignal): Promise<Transcript> {
  if (isMock) {
    const t = await call<Transcript>('POST', `/transcribe?purpose=${purpose}`, { size: audio.size });
    const url = URL.createObjectURL(audio);
    (await import('@/lib/api/mock')).register({ id: url, name: 'voice', mime: audio.type, size: audio.size, sha256: '', kind: 'audio', status: 'ready', duration_s: t.duration_s, transcript: t.text });
    return { ...t, file_id: url };
  }
  let res: Response;
  try {
    res = await fetch(`/api/v1/transcribe?purpose=${purpose}`, {
      method: 'POST', credentials: 'same-origin', body: audio, signal,
      headers: { 'Content-Type': audio.type || 'audio/webm', 'X-HQ-Client': 'web', 'Idempotency-Key': crypto.randomUUID(), Accept: 'application/json' },
    });
  } catch (e) {
    throw signal?.aborted ? e : new ApiError(0, undefined);
  }
  if (!res.ok) return problem(res);
  return (await res.json()) as Transcript;
}

// ------------------------------------------------------------ workshop --
export type WorkshopMeta = { runtime: 'managed' | 'self_hosted' | null };
export const useWorkshopMeta = () => useQuery({ queryKey: ['workshop', 'meta'], queryFn: async () => (await call<{ workshop?: WorkshopMeta }>('GET', '/meta')).workshop ?? { runtime: null }, staleTime: 300_000 });
export const useWorkspaces = () => useQuery({ queryKey: ['workshop', 'workspaces'], queryFn: () => call<Workspace[]>('GET', '/workshop/workspaces'), staleTime: 60_000 });
export const useGrants = () => useQuery({ queryKey: ['workshop', 'grants'], queryFn: () => call<Grant[]>('GET', '/workshop/grants?active=true') });
export const useSessions = () => useQuery({ queryKey: ['workshop', 'sessions'], queryFn: () => call<{ items: CodeSession[] }>('GET', '/workshop/sessions') });
export const useCodeSession = (ref: string) => useQuery({ queryKey: ['workshop', 'session', ref], queryFn: () => call<CodeSession>('GET', `/workshop/sessions/${encodeURIComponent(ref)}`) });

/** A session's events: the stored history, then the live SSE (resumes from the last seq). Mock mode plays a script. */
export function useSessionEvents(ref: string): { events: SessionEvent[]; live: boolean; error: unknown } {
  const qc = useQueryClient();
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [live, setLive] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const last = useRef(0);
  useEffect(() => {
    let closed = false;
    let es: EventSource | null = null;
    let timer: ReturnType<typeof setInterval> | undefined;
    const add = (e: SessionEvent) => {
      if (e.seq <= last.current) return;
      last.current = e.seq;
      setEvents((xs) => [...xs, e]);
      if (e.type === 'state' || e.type === 'approval_result') void qc.invalidateQueries({ queryKey: ['workshop'] });
    };
    void call<{ items: SessionEvent[] }>('GET', `/workshop/sessions/${encodeURIComponent(ref)}/events`)
      .then((page) => {
        if (closed) return;
        page.items.forEach(add);
        if (isMock) {
          setLive(true);
          timer = setInterval(() => {
            void call<{ items: SessionEvent[] }>('GET', `/workshop/sessions/${encodeURIComponent(ref)}/events?after=${last.current}`).then((p) => p.items.forEach(add));
          }, 2200);
          return;
        }
        es = new EventSource(`/api/v1/workshop/sessions/${encodeURIComponent(ref)}/live`, { withCredentials: true });
        es.onopen = () => setLive(true);
        es.onerror = () => setLive(false);
        for (const t of ['message', 'progress', 'command', 'file_change', 'approval_request', 'approval_result', 'state', 'error'] as const) {
          es.addEventListener(t, (m) => { try { add(JSON.parse((m as MessageEvent).data) as SessionEvent); } catch { /* ignore malformed */ } });
        }
      })
      .catch((e: unknown) => { if (!closed) setError(e); });
    return () => { closed = true; es?.close(); if (timer) clearInterval(timer); };
  }, [ref, qc]);
  return { events, live, error };
}

export const sendToSession = (ref: string, body: string, attachments: string[]) =>
  call<SessionEvent>('POST', `/workshop/sessions/${encodeURIComponent(ref)}/messages`, { body, attachments });
export const answerApproval = (ref: string, id: string, allow: boolean, stepUp?: string, note?: string) =>
  call<SessionEvent>('POST', `/workshop/sessions/${encodeURIComponent(ref)}/approvals/${encodeURIComponent(id)}`, { allow, note: note ?? null }, stepUp ? { 'X-Step-Up': stepUp } : undefined);
export const stopSession = (ref: string) => call<CodeSession>('POST', `/workshop/sessions/${encodeURIComponent(ref)}/stop`, {});
export const createGrant = (body: { workspace: string; actions: string[]; driver: string | null; budget_usd: number; expires_at: string }, stepUp: string) =>
  call<Grant>('POST', '/workshop/grants', body, { 'X-Step-Up': stepUp });
export const revokeGrant = (ref: string) => call<Grant>('POST', `/workshop/grants/${encodeURIComponent(ref)}/revoke`, {});
export const createSession = (body: { grant: string; title: string; brief: string; attachments?: string[] }) => call<CodeSession>('POST', '/workshop/sessions', body);

// -------------------------------------------------------- voice orders --
export type OrderRecord = OrderOut & { text: string; source: 'voice' | 'text'; file_id: string | null; created_at: string };
export const sendOrder = (text: string, source: 'voice' | 'text', fileId?: string | null) => call<OrderOut>('POST', '/orders', { text, source, file_id: fileId ?? null });
export const useOrders = () => useQuery({ queryKey: ['orders'], queryFn: () => call<{ items: OrderRecord[] }>('GET', '/orders') });
