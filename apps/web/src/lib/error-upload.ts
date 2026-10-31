'use client';

// ⟨1.10⟩ §28.3 the panel's own error reports: «خطاخوان» sends its entries (already masked here: ./errorlog) to `POST /client/errors` in
// batches, so the overseer's daily app-health protocol can group them and find the cause in code. Only errors and warnings, never the
// info lines; an entry goes once, and again only when it happened more times since (its count grew); the same failure logged twice
// goes as one line. The owner turns it off in Settings (this browser only). The call goes straight to the hub, outside the observed
// client: a failed report is never itself a report.

import { useSyncExternalStore } from 'react';
import { APP, errorLog, type ErrorEntry } from '@/lib/errorlog';

const PREF = 'hq.errors.upload';
const SENT = 'hq.errors.sent';
/** The first batch waits a little after the panel opens; then one every minute at most. */
const FIRST_MS = 8_000;
const EVERY_MS = 60_000;
const BATCH = 50;

export type UploadState = { on: boolean; lastAt: string | null; lastCount: number; pending: number; served: boolean | null; failing: boolean };

type SentMap = { app: string; sent: Record<string, number>; lastAt: string | null; lastCount: number };
const listeners = new Set<() => void>();
let state: UploadState = { on: true, lastAt: null, lastCount: 0, pending: 0, served: null, failing: false };
let started = false;
let timer: ReturnType<typeof setTimeout> | null = null;
let busy = false;

function emit(next: Partial<UploadState>) { state = { ...state, ...next }; for (const l of listeners) l(); }
function readPref(): boolean { try { return localStorage.getItem(PREF) !== 'off'; } catch { return true; } }
function readSent(): SentMap {
  try {
    const s = JSON.parse(localStorage.getItem(SENT) ?? 'null') as SentMap | null;
    if (s && s.app === APP) return s;
  } catch { /* fall through */ }
  return { app: APP, sent: {}, lastAt: null, lastCount: 0 };
}
function writeSent(s: SentMap) { try { localStorage.setItem(SENT, JSON.stringify(s)); } catch { /* memory only */ } }

/** What would go now: errors and warnings not sent yet, or that happened again since (their count grew). */
export function due(entries: ErrorEntry[], sent: Record<string, number>): ErrorEntry[] {
  return entries.filter((e) => e.level !== 'info' && (sent[String(e.id)] ?? 0) < e.count).reverse(); // oldest first
}

const signature = (e: ErrorEntry) => [e.kind, e.level, e.method, e.path, e.status, e.code, e.title, e.detail, e.screen].join('|');
/**
 * One line per failure in a batch: the same failure logged apart (more than a minute between, so «خطاخوان» kept two entries) goes as one
 * entry with the counts added and its first and last time; `ids` are the log's entries it stands for.
 */
export function dedupe(list: ErrorEntry[]): Array<{ entry: ErrorEntry; ids: Array<[number, number]> }> {
  const by = new Map<string, { entry: ErrorEntry; ids: Array<[number, number]> }>();
  for (const e of list) {
    const k = e.kind === 'crash' ? `crash|${e.id}` : signature(e);
    const g = by.get(k);
    if (!g) { by.set(k, { entry: { ...e }, ids: [[e.id, e.count]] }); continue; }
    const last = (e.lastAt ?? e.at) > (g.entry.lastAt ?? g.entry.at) ? e.lastAt ?? e.at : g.entry.lastAt ?? g.entry.at;
    g.entry = { ...g.entry, count: g.entry.count + e.count, lastAt: last, requestId: e.requestId ?? g.entry.requestId, breadcrumbs: e.breadcrumbs ?? g.entry.breadcrumbs };
    g.ids.push([e.id, e.count]);
  }
  return [...by.values()];
}

async function post(body: unknown): Promise<Response> {
  const req = new Request(new URL('/api/v1/client/errors', window.location.origin), {
    method: 'POST', credentials: 'same-origin', keepalive: true, body: JSON.stringify(body),
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-HQ-Client': 'web', 'Idempotency-Key': crypto.randomUUID() },
  });
  if (process.env.NEXT_PUBLIC_HQ_MOCK === '1') return (await import('@/lib/api/mock-v21')).handle(req);
  return fetch(req);
}

/** Sends what is due, in batches of fifty. */
export async function flush(): Promise<void> {
  if (busy || !state.on || typeof window === 'undefined') return;
  busy = true;
  try {
    const s = readSent();
    let batch = dedupe(due(errorLog.list(), s.sent));
    while (batch.length) {
      const part = batch.slice(0, BATCH);
      let res: Response;
      try { res = await post({ app: 'web', version: APP, entries: part.map((g) => g.entry) }); } catch { emit({ failing: true }); return; }
      // A hub before ⟨1.10⟩: the entries stay queued, quietly, and the panel asks again later.
      if (res.status === 404 || res.status === 405) { emit({ served: false, failing: false }); retryLater(); return; }
      if (!res.ok) { emit({ failing: true }); return; }
      for (const g of part) for (const [id, count] of g.ids) s.sent[String(id)] = count;
      s.lastAt = new Date().toISOString();
      s.lastCount = part.length;
      writeSent(s);
      emit({ served: true, failing: false, lastAt: s.lastAt, lastCount: s.lastCount });
      batch = batch.slice(BATCH);
    }
  } finally {
    busy = false;
    emit({ pending: due(errorLog.list(), readSent().sent).length });
  }
}

/** After a 404/405: try again in half an hour (the hub may have been updated meanwhile). */
const LATER_MS = 30 * 60_000;
let later: ReturnType<typeof setTimeout> | null = null;
function retryLater() {
  if (later) return;
  later = setTimeout(() => { later = null; void flush(); }, LATER_MS);
}

function schedule(ms: number) {
  if (timer || !state.on) return;
  timer = setTimeout(() => { timer = null; void flush(); }, ms);
}

/** Started once by the shell, after «خطاخوان» opens its log. */
export function startUploads() {
  if (started || typeof window === 'undefined') return;
  started = true;
  const s = readSent();
  emit({ on: readPref(), lastAt: s.lastAt, lastCount: s.lastCount, pending: due(errorLog.list(), s.sent).length });
  errorLog.subscribe(() => {
    const n = due(errorLog.list(), readSent().sent).length;
    if (n !== state.pending) emit({ pending: n });
    if (n && state.served !== false) schedule(EVERY_MS);
  });
  // A tab put away sends what it has, so a report is not lost with a closed tab.
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden' && state.pending) void flush(); });
  schedule(FIRST_MS);
}

export function setUploads(on: boolean) {
  try { localStorage.setItem(PREF, on ? 'on' : 'off'); } catch { /* memory only */ }
  emit({ on });
  if (on) { if (timer) { clearTimeout(timer); timer = null; } void flush(); }
  else if (timer) { clearTimeout(timer); timer = null; }
}

const SERVER: UploadState = { on: true, lastAt: null, lastCount: 0, pending: 0, served: null, failing: false };
export const useUploads = () => useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l); }, () => state, () => SERVER);
