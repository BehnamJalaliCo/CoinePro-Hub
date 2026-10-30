'use client';

import { errorLog } from '@/lib/errorlog';
import { hubHealth, isTransientStatus } from '@/lib/hub-health';

// Every API call goes through here (the typed client and `call`): it carries its own `X-Request-Id` (the hub keeps it, writes it in its
// log and echoes it back), and a failure is written to «خطاخوان» with its time, page, duration and request id; 502/503/504 and "no answer"
// feed the hub's health (a restart shows one calm banner, not an error on every card).

const QUIET = new Set<string>();

/** Calls whose failure is expected and handled (an older hub's 404 for a newer route): their entry is taken back. */
export function forgetRequest(requestId: string | null | undefined) {
  if (!requestId) return;
  const id = logged.get(requestId);
  if (id != null) { errorLog.forget(id); logged.delete(requestId); }
  else QUIET.add(requestId);
}
const logged = new Map<string, number>();

async function problemOf(res: Response): Promise<{ code?: string; title?: string; message?: string }> {
  try {
    const p = (await res.clone().json()) as { code?: string; title?: string; message_fa?: string; detail?: string };
    return { code: p.code, title: p.title, message: p.detail ?? p.message_fa };
  } catch { return {}; }
}

export function observed(inner: (r: Request) => Promise<Response>): (r: Request) => Promise<Response> {
  return async (req: Request) => {
    const rid = req.headers.get('X-Request-Id') ?? crypto.randomUUID();
    req.headers.set('X-Request-Id', rid);
    const u = new URL(req.url);
    const path = `${u.pathname.replace(/^\/api\/v1/, '')}${u.search}`;
    const t0 = performance.now();
    let res: Response;
    try {
      res = await inner(req);
    } catch (e) {
      // The demo's fixtures threw: say so where a developer looks (the hub itself never throws here).
      if (process.env.NEXT_PUBLIC_HQ_MOCK === '1') console.error('mock', req.method, path, e);
      hubHealth.transient();
      if (!QUIET.delete(rid)) logged.set(rid, errorLog.record({ kind: 'network', method: req.method, path, requestId: rid, durationMs: Math.round(performance.now() - t0), message: e instanceof Error ? e.message : null }));
      throw e;
    }
    // The mock answers without the header the hub sets: the panel's own id stands in, so the log and the error agree.
    if (!res.headers.get('X-Request-Id')) {
      const h = new Headers(res.headers);
      h.set('X-Request-Id', rid);
      res = new Response(res.status === 204 ? null : res.body, { status: res.status, statusText: res.statusText, headers: h });
    }
    if (isTransientStatus(res.status)) hubHealth.transient();
    else hubHealth.ok();
    if (!res.ok) {
      const p = await problemOf(res);
      const id = errorLog.record({
        kind: 'http', method: req.method, path, status: res.status, code: p.code ?? (isTransientStatus(res.status) ? 'hub_unreachable' : null), title: p.title, message: p.message,
        requestId: res.headers.get('X-Request-Id') ?? rid, durationMs: Math.round(performance.now() - t0), headers: res.headers,
      });
      if (QUIET.delete(rid)) errorLog.forget(id); else logged.set(rid, id);
      if (logged.size > 200) logged.delete(logged.keys().next().value!);
    }
    return res;
  };
}
