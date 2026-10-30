import createClient, { type Middleware } from 'openapi-fetch';
import type { components, paths } from '@/generated/api';
import { observed } from './observe';

export type Schemas = components['schemas'];
export type Problem = Schemas['Problem'];

/** A failed API call, carrying the contract's stable `code` and Persian `message_fa`. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly messageFa: string;
  readonly fields?: Record<string, string> | null;
  readonly requestId?: string | null;
  /** ⟨1.4.6⟩ `409 not_ready`: what is still missing (§18.8, e.g. ["brand"]). */
  readonly missing?: string[];
  /** ⟨1.5⟩ `422 send_blocked`: the outbound guard's refusal codes (§19.6). */
  readonly blockedReasons: string[];
  /** A `429` (`rate_limited`, `send_limit`, …): seconds from `Retry-After`, when the server sent one. */
  readonly retryAfter: number | null;

  constructor(status: number, problem: Partial<Problem> | undefined) {
    super(problem?.title ?? `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = problem?.code ?? (status === 0 ? 'network_error' : 'internal_error');
    this.messageFa = problem?.message_fa ?? (status === 0 ? 'اتصال برقرار نشد. اینترنت را بررسی کن.' : 'خطای غیرمنتظره؛ دوباره تلاش کن.');
    this.fields = problem?.fields;
    this.requestId = problem?.request_id;
    this.missing = (problem as { missing?: string[] } | undefined)?.missing;
    const extra = problem as { blocked_reasons?: string[]; retry_after?: number } | undefined;
    this.blockedReasons = extra?.blocked_reasons ?? [];
    this.retryAfter = extra?.retry_after ?? null;
  }
}

const MOCK = process.env.NEXT_PUBLIC_HQ_MOCK === '1';

/** Contract §1–§2: web mutations carry X-HQ-Client and a same-origin Origin (the browser sets it);
 *  every state-changing POST carries an Idempotency-Key. */
const contract: Middleware = {
  onRequest({ request }) {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      request.headers.set('X-HQ-Client', 'web');
      if (request.method === 'POST' && !request.headers.has('Idempotency-Key')) {
        request.headers.set('Idempotency-Key', crypto.randomUUID());
      }
    }
    return request;
  },
};

// Inlined at build time: in production the branch and the fixtures module are compiled away.
const mockFetch =
  process.env.NEXT_PUBLIC_HQ_MOCK === '1'
    ? async (input: Request): Promise<Response> => (await import('@/lib/api/mock-v21')).handle(input)
    : undefined;

// 0.4.0: every call carries its X-Request-Id and its failures reach «خطاخوان» and the hub's health (./observe).
export const api = createClient<paths>({
  baseUrl: typeof window === 'undefined' ? 'http://localhost' : window.location.origin,
  credentials: 'same-origin',
  fetch: observed(mockFetch ?? ((r: Request) => globalThis.fetch(r))),
});
api.use(contract);

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Unwraps an openapi-fetch result or throws ApiError. */
export async function ok<T>(p: Promise<Result<T>>): Promise<T> {
  let r: Result<T>;
  try {
    r = await p;
  } catch {
    throw new ApiError(0, undefined);
  }
  if (r.response.ok) return r.data as T;
  const pr = (r.error ?? undefined) as Partial<Problem> | undefined;
  throw new ApiError(r.response.status, { ...pr, request_id: pr?.request_id ?? r.response.headers.get('X-Request-Id') });
}

export const isMock = MOCK;
