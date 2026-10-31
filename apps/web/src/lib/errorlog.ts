// «خطاخوان» on the web (0.3.0, 0.4.0; the Android app's core/diag/ErrorLog.kt): every failure of this version of the panel, kept in this
// browser (localStorage); ⟨1.10⟩ its errors and warnings, masked as below, also go to the hub in batches for the overseer's app-health
// check unless the owner turns that off in Settings (../lib/error-upload.ts). A new version starts an empty log and keeps the previous ones apart (the last three). Every
// failed API call is recorded with its exact time (Tehran and UTC, to the millisecond), the request id the panel sent (`X-Request-Id`; the
// hub echoes it and writes it in its own log), the page and the steps before it; a burst of 502s while the hub restarts becomes one entry;
// uncaught errors and rejected promises are kept with their stack. Never a body, a token, a cookie, passkey data or customer data: paths
// are masked, free text is redacted and masked, and only an allow-list of response headers is kept.

export type Level = 'error' | 'warning' | 'info';
export type ErrorEntry = {
  /** The sequence number within this version's log (1 is the session that opened it). */
  id: number;
  /** UTC with milliseconds. */
  at: string;
  /** http · network · unreachable · hub · stream · crash · passkey · speech · session · app */
  kind: string;
  level: Level;
  app: string;
  screen?: string | null;
  method?: string | null;
  path?: string | null;
  status?: number | null;
  code?: string | null;
  title?: string | null;
  message?: string | null;
  requestId?: string | null;
  durationMs?: number | null;
  network?: string | null;
  foreground?: boolean | null;
  breadcrumbs?: string[];
  headers?: Record<string, string>;
  detail?: string | null;
  stack?: string | null;
  count: number;
  lastAt?: string | null;
  tally?: Record<string, number>;
  paths?: string[];
};
export type ApiFailure = {
  kind: 'http' | 'network'; method: string; path: string; status?: number | null; code?: string | null; title?: string | null; message?: string | null;
  requestId?: string | null; durationMs?: number | null; headers?: Headers | null;
};

export const APP = process.env.NEXT_PUBLIC_APP_VERSION ?? 'dev';
export const OWNER_ZONE = 'Asia/Tehran';
/** Entries kept per version. */
export const MAX = 1000;
/** Earlier versions kept in this browser. */
export const KEEP_VERSIONS = 3;
const CRUMBS = 10;
const BURST_WINDOW_S = 30;
const BURST_MIN = 3;
const BURST_PATHS = 8;
const KEY = 'hq.errors';

type Stored = { app: string; entries: ErrorEntry[] };
type Archive = { app: string; entries: ErrorEntry[]; archived: string };

// ------------------------------------------------------------------------------------------------------------ masking --
const UUID = /\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b/g;
const HEX = /\b[0-9a-fA-F]{16,}\b/g;
const EMAIL = /[\w.+-]+@[\w-]+(\.[\w-]+)+/g;
const PHONE = /\+\d[\d ()-]{7,}\d|\b09\d{9}\b/g;
const TOKEN = /\b(?=[A-Za-z_-]*\d)[A-Za-z0-9_-]{28,}\b/g;
const LONGNUM = /(?<![A-Z]-)\b\d{7,}\b/g;
const SECRET = /("?(?:authorization|proxy-authorization|cookie|set-cookie|x-step-up|x-api-key|api[_-]?key|access[_-]?token|refresh[_-]?token|session[_-]?token|token|password|passwd|pass|secret|client[_-]?secret|passkey|credential|otp|signature|private[_-]?key)"?\s*[:=]\s*)("[^"]*"|(?:bearer|basic)\s+[^\s,;&"}]+|[^\s,;&"}]+)/gi;
const SAFE_HEADERS = new Set(['server', 'via', 'retry-after', 'content-type', 'x-request-id', 'date', 'x-hq-offline']);
const SAFE_QUERY = new Set(['period', 'status', 'state', 'kind', 'unrated', 'seen', 'category', 'limit', 'company', 'risk', 'level', 'scope', 'mode', 'purpose', 'active', 'day', 'from', 'to', 'role', 'latest', 'subject_kind', 'channel', 'department', 'month', 'type', 'unread', 'created_by', 'by']);

/** `Authorization: Bearer abc` → `Authorization: {redacted}`; `"password": "x"` → `"password": {redacted}`. */
export const redact = (s: string) => s.replace(SECRET, (_m, name: string) => `${name}{redacted}`);
/** Secrets named in a sentence lose their values; then ids, hashes, tokens, e-mail addresses and phone numbers are masked. Refs and codes stay. */
export const mask = (s: string) =>
  redact(s).replace(UUID, '{id}').replace(EMAIL, '{email}').replace(HEX, '{hash}').replace(TOKEN, '{token}').replace(PHONE, '{phone}').replace(LONGNUM, '{n}');

/** A request path with its ids masked and its query reduced to the parameters that carry no data about anyone. */
export function maskPath(path: string): string {
  const [p = '', q = ''] = path.split('?', 2);
  const one = (re: RegExp, s: string) => { re.lastIndex = 0; const r = re.test(s); re.lastIndex = 0; return r; };
  const segs = p.split('/').map((seg) => {
    let s = seg;
    try { s = decodeURIComponent(seg); } catch { /* keep */ }
    if (/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(s)) return '{id}';
    if (one(EMAIL, s)) return '{email}';
    if (/^[0-9a-fA-F]{16,}$/.test(s)) return '{hash}';
    if (/^(?=[A-Za-z_-]*\d)[A-Za-z0-9_-]{28,}$/.test(s)) return '{token}';
    if (/^\d{7,}$/.test(s)) return '{n}';
    return mask(s);
  }).join('/');
  if (!q) return segs;
  const kept = q.split('&').filter(Boolean).map((kv) => {
    const [k = '', v = ''] = kv.split('=', 2);
    let dv = v;
    try { dv = decodeURIComponent(v); } catch { /* keep */ }
    return SAFE_QUERY.has(k) ? `${k}=${mask(dv)}` : `${k}=…`;
  });
  return kept.length ? `${segs}?${kept.join('&')}` : segs;
}

/** The response headers the log may keep: the allow-list only, values redacted and masked. */
export function safeHeaders(h: Headers | null | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  h?.forEach((v, k) => { if (SAFE_HEADERS.has(k.toLowerCase())) out[k.toLowerCase()] = mask(v).slice(0, 120); });
  return out;
}

// -------------------------------------------------------------------------------------------------------------- times --
const pad = (n: number, w = 2) => String(n).padStart(w, '0');
function parts(iso: string, zone: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const f = new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' });
  const o = Object.fromEntries(f.formatToParts(d).map((x) => [x.type, x.value]));
  return `${o.year}-${o.month}-${o.day} ${o.hour}:${o.minute}:${o.second}.${pad(d.getUTCMilliseconds(), 3)}`;
}
/** "2026-10-29 14:03:12.345" in the owner's zone (Latin digits). */
export const local = (iso: string) => parts(iso, OWNER_ZONE) ?? iso;
/** "2026-10-29 10:33:12.345" in UTC. */
export const utc = (iso: string) => parts(iso, 'UTC') ?? iso;
const clock = (iso: string) => local(iso).slice(11);
const nowIso = () => new Date().toISOString();
const secondsBetween = (a: string, b: string) => (new Date(b).getTime() - new Date(a).getTime()) / 1000;

// ------------------------------------------------------------------------------------------------------------- device --
export function device(): string {
  if (typeof navigator === 'undefined') return 'server';
  const ua = navigator.userAgent;
  const os = /Android/i.test(ua) ? 'Android' : /iPhone|iPad/i.test(ua) ? 'iOS' : /Mac OS X/i.test(ua) ? 'macOS' : /Windows/i.test(ua) ? 'Windows' : /Linux/i.test(ua) ? 'Linux' : 'Other';
  const br = /Edg\/([\d.]+)/.exec(ua) ?? /Firefox\/([\d.]+)/.exec(ua) ?? /Chrome\/([\d.]+)/.exec(ua) ?? /Version\/([\d.]+).*Safari/.exec(ua);
  const name = /Edg\//.test(ua) ? 'Edge' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'Browser';
  return `${name} ${br?.[1]?.split('.')[0] ?? ''} · ${os} · ${window.screen?.width ?? 0}×${window.screen?.height ?? 0}`.replace('  ', ' ');
}
function network(): string {
  if (typeof navigator === 'undefined') return 'other';
  if (!navigator.onLine) return 'offline';
  const c = (navigator as Navigator & { connection?: { type?: string; effectiveType?: string } }).connection;
  return c?.type && c.type !== 'unknown' ? c.type : c?.effectiveType ?? 'online';
}
const foreground = () => (typeof document === 'undefined' ? true : document.visibilityState === 'visible');

// ------------------------------------------------------------------------------------------------------------- store --
const transient = (e: Pick<ErrorEntry, 'kind' | 'status' | 'code'>) =>
  e.kind === 'network' || (e.kind === 'http' && e.status != null && e.status >= 502 && e.status <= 504 && (e.code == null || e.code === 'hub_unreachable' || e.code === 'internal_error'));
const tallyKey = (e: ErrorEntry) => (e.kind === 'network' || e.status == null ? 'network' : String(e.status));
const pathLine = (e: ErrorEntry) => (e.path ? `${[e.method, e.path].filter(Boolean).join(' ')} → ${e.status ?? 'no answer'}` : null);
const same = (a: ErrorEntry, b: ErrorEntry) =>
  a.kind === b.kind && a.level === b.level && a.method === b.method && a.path === b.path && a.status === b.status && a.code === b.code && a.title === b.title && a.detail === b.detail && a.kind !== 'crash' && a.kind !== 'session';

function burstOf(first: ErrorEntry): ErrorEntry {
  return {
    id: first.id, at: first.at, kind: 'unreachable', level: 'warning', app: first.app, screen: first.screen, code: 'hub_unreachable', title: 'hub unreachable',
    network: first.network, foreground: first.foreground, breadcrumbs: first.breadcrumbs, count: first.count, lastAt: first.lastAt ?? first.at,
    tally: first.kind === 'unreachable' ? first.tally : { [tallyKey(first)]: first.count }, paths: first.kind === 'unreachable' ? first.paths : [pathLine(first)].filter((x): x is string => !!x),
    requestId: first.requestId, headers: first.headers,
  };
}
function merge(b: ErrorEntry, x: ErrorEntry): ErrorEntry {
  const base = b.kind === 'unreachable' ? b : burstOf(b);
  const tally = { ...(base.tally ?? {}) };
  if (x.kind !== 'unreachable') tally[tallyKey(x)] = (tally[tallyKey(x)] ?? 0) + x.count;
  const paths = [...new Set([...(base.paths ?? []), ...[pathLine(x)].filter((p): p is string => !!p)])].slice(0, BURST_PATHS);
  return { ...base, count: base.count + x.count, lastAt: x.lastAt ?? x.at, tally, paths, screen: x.screen ?? base.screen, network: x.network ?? base.network };
}

class ErrorLog {
  private entries: ErrorEntry[] = [];
  private seq = 0;
  private crumbs: string[] = [];
  private listeners = new Set<() => void>();
  private started = false;
  screen: string | null = null;

  /** Opens this version's log once, in the browser; a log of another version is archived first. */
  start() {
    if (this.started || typeof window === 'undefined') return;
    this.started = true;
    let stored: Stored | null = null;
    try { stored = JSON.parse(localStorage.getItem(`${KEY}.current`) ?? 'null') as Stored | null; } catch { stored = null; }
    if (stored && stored.app !== APP) {
      if (stored.entries.length) this.archive(stored);
      stored = null;
    }
    this.entries = stored?.entries ?? [];
    this.seq = this.entries.reduce((m, e) => Math.max(m, e.id), 0);
    this.note('session', 'info', 'app started', `panel started v${APP} on ${device()}`);
    window.addEventListener('error', (ev) => this.crash(ev.error ?? ev.message, 'error'));
    window.addEventListener('unhandledrejection', (ev) => this.crash(ev.reason, 'unhandled rejection'));
    document.addEventListener('visibilitychange', () => this.crumb(document.visibilityState === 'visible' ? 'tab foreground' : 'tab background'));
  }

  subscribe = (l: () => void) => { this.listeners.add(l); return () => { this.listeners.delete(l); }; };
  /** Newest first. */
  list = () => this.entries;

  /** A step before a failure: a page, a sheet, the stream's state, an action. The last ten are kept with each entry. */
  crumb(text: string) {
    this.crumbs.push(`${clock(nowIso())} ${mask(text).slice(0, 80)}`);
    if (this.crumbs.length > CRUMBS) this.crumbs.shift();
  }
  setScreen(path: string) {
    if (path !== this.screen) this.crumb(`page ${path}`);
    this.screen = path;
  }

  /** A failed API call. Returns its entry's id (a retry that then succeeds can take a lone network entry back with [forget]). */
  record(f: ApiFailure): number {
    const level: Level = f.kind === 'http' && (f.status ?? 0) >= 500 && f.code !== 'hub_unreachable' && !((f.status ?? 0) >= 502 && (f.status ?? 0) <= 504) ? 'error' : 'warning';
    return this.add({
      id: 0, at: nowIso(), kind: f.kind, level, app: APP, screen: this.screen, method: f.method, path: maskPath(f.path), status: f.status ?? null,
      code: f.code?.slice(0, 60) ?? null, title: f.title ? mask(f.title).slice(0, 120) : null, message: f.message ? mask(f.message).slice(0, 300) : null,
      requestId: f.requestId?.slice(0, 80) ?? null, durationMs: f.durationMs ?? null, network: network(), foreground: foreground(), breadcrumbs: [...this.crumbs],
      headers: safeHeaders(f.headers), count: 1,
    });
  }

  /** Anything that is not an API call: the stream dropped or came back, the hub came back, a passkey or speech failure, a session. */
  note(kind: string, level: Level, title: string, detail?: string | null, code?: string | null): number {
    return this.add({
      id: 0, at: nowIso(), kind, level, app: APP, screen: this.screen, code: code?.slice(0, 60) ?? null, title: mask(title).slice(0, 120), detail: detail ? mask(detail).slice(0, 300) : null,
      network: network(), foreground: foreground(), breadcrumbs: level === 'info' ? [] : [...this.crumbs], count: 1,
    });
  }

  forget(id: number) { this.update(this.entries.filter((e) => e.id !== id || e.kind === 'unreachable')); }
  /** Empties this version's log (the archived versions stay). */
  clear() { this.update([]); }

  private crash(err: unknown, how: string) {
    const e = err instanceof Error ? err : null;
    const text = e ? `${e.name}: ${e.message}` : String(err);
    // A chunk that failed to load after a deploy is the hub restarting, not a fault of the page.
    this.add({
      id: 0, at: nowIso(), kind: 'crash', level: 'error', app: APP, screen: this.screen, detail: `${mask(text).slice(0, 280)} (${how})`,
      stack: e?.stack ? mask(e.stack).split('\n').slice(0, 30).join('\n').slice(0, 6000) : null, network: network(), foreground: foreground(), breadcrumbs: [...this.crumbs], count: 1,
    });
  }

  private add(e0: ErrorEntry): number {
    const e = { ...e0, id: ++this.seq };
    const list = this.entries;
    const head = list[0];
    let next: ErrorEntry[];
    let id = e.id;
    if (transient(e)) {
      if (head && head.kind === 'unreachable' && secondsBetween(head.lastAt ?? head.at, e.at) <= BURST_WINDOW_S) {
        id = head.id;
        next = [merge(head, e), ...list.slice(1)];
      } else {
        let n = 0;
        while (n < list.length && transient(list[n]!) && secondsBetween(list[n]!.lastAt ?? list[n]!.at, e.at) <= BURST_WINDOW_S) n++;
        const recent = list.slice(0, n);
        if (recent.reduce((a, x) => a + x.count, 0) + 1 >= BURST_MIN) {
          const chrono = [...recent].reverse();
          let burst = burstOf(chrono[0]!);
          for (const x of [...chrono.slice(1), e]) burst = merge(burst, x);
          id = burst.id;
          next = [burst, ...list.slice(n)];
        } else { next = this.plain(list, e); id = next[0]!.id; }
      }
    } else { next = this.plain(list, e); id = next[0]!.id; }
    this.update(next.slice(0, MAX));
    return id;
  }

  /** The same failure again within a minute (a retry, a refresh loop) raises the count of the newest entry. */
  private plain(list: ErrorEntry[], e: ErrorEntry): ErrorEntry[] {
    const head = list[0];
    if (head && same(head, e) && secondsBetween(head.lastAt ?? head.at, e.at) < 60) {
      return [{ ...head, count: head.count + 1, lastAt: e.at, screen: e.screen ?? head.screen, durationMs: e.durationMs ?? head.durationMs }, ...list.slice(1)];
    }
    return [e, ...list];
  }

  private update(next: ErrorEntry[]) {
    this.entries = next;
    try { localStorage.setItem(`${KEY}.current`, JSON.stringify({ app: APP, entries: next } satisfies Stored)); } catch { /* full or private: memory only */ }
    for (const l of this.listeners) l();
  }

  // ---------------------------------------------------------------------------------------------------- versions --
  /** The logs of earlier versions, newest first. */
  archives(): Archive[] {
    try { return (JSON.parse(localStorage.getItem(`${KEY}.versions`) ?? '[]') as Archive[]).slice(0, KEEP_VERSIONS); } catch { return []; }
  }
  private archive(s: Stored) {
    const next = [{ ...s, archived: nowIso() }, ...this.archives().filter((a) => a.app !== s.app)].slice(0, KEEP_VERSIONS);
    try { localStorage.setItem(`${KEY}.versions`, JSON.stringify(next)); } catch { /* keep going */ }
  }

  // ------------------------------------------------------------------------------------------------------- report --
  /** The log as one plain-text report, newest first: a header with the panel, the browser, the zone and the export time, then one block per entry. */
  report(list: ErrorEntry[], version: string = APP): string {
    const stamp = nowIso();
    const e = list.filter((x) => x.level === 'error').length;
    const w = list.filter((x) => x.level === 'warning').length;
    const i = list.filter((x) => x.level === 'info').length;
    const head = [
      'CoinePro HQ — web panel error log (خطاخوان)',
      `panel ${version}${version !== APP ? ` (an earlier version; this browser runs ${APP})` : ''} · ${typeof location === 'undefined' ? '' : location.host}`,
      `browser ${device()}`,
      `time zone ${OWNER_ZONE} (the owner's) · browser ${Intl.DateTimeFormat().resolvedOptions().timeZone}`,
      `exported ${local(stamp)} ${OWNER_ZONE} · ${utc(stamp)} UTC`,
      `${list.length} ${list.length === 1 ? 'entry' : 'entries'} (${e} error, ${w} warning, ${i} info), newest first`,
    ];
    return `${[...head, ...list.map((x) => `\n${block(x)}`)].join('\n').trimEnd()}\n`;
  }
}

/** What an entry is, in English for the report. */
export function what(e: ErrorEntry): string {
  switch (e.kind) {
    case 'http': return 'HTTP error';
    case 'network': return 'network failure (no answer)';
    case 'unreachable': return `hub unreachable, ${e.count} ${e.count === 1 ? 'request' : 'requests'}, ${clock(e.at)}–${clock(e.lastAt ?? e.at)}`;
    case 'hub': return `hub back: ${e.title ?? ''}`;
    case 'stream': return `live stream: ${e.title ?? 'dropped'}`;
    case 'crash': return 'crash';
    case 'passkey': return `passkey: ${e.title ?? 'failed'}`;
    case 'speech': return `speech recognition: ${e.title ?? 'failed'}`;
    case 'session': return `session: ${e.title ?? 'started'}`;
    default: return e.title ?? e.kind;
  }
}

/** One entry as the report shows it: a heading line and the facts beneath, each on its own line. */
export function block(e: ErrorEntry): string {
  const l: string[] = [];
  l.push(`#${e.id} · ${e.level} · ${what(e)}${e.count > 1 && e.kind !== 'unreachable' ? ` ×${e.count}` : ''}`);
  l.push(`  time: ${local(e.at)} ${OWNER_ZONE} · ${utc(e.at)} UTC${e.lastAt && e.lastAt !== e.at ? ` (last ${local(e.lastAt)} · ${utc(e.lastAt)} UTC)` : ''}`);
  l.push(`  panel: ${e.app}${[e.screen ? `page: ${e.screen}` : null, e.foreground == null ? null : e.foreground ? 'foreground' : 'background', e.network ? `network: ${e.network}` : null].filter(Boolean).map((x) => ` · ${x}`).join('')}`);
  if (e.method || e.path) l.push(`  request: ${e.method ?? ''} ${e.path ?? ''}${e.status != null ? ` → ${e.status}` : ''}${e.durationMs != null ? ` · ${e.durationMs} ms` : ''}`);
  if (e.tally && Object.keys(e.tally).length) l.push(`  failures: ${Object.entries(e.tally).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ×${v}`).join(', ')}`);
  if (e.paths?.length) l.push(`  requests: ${e.paths.join(' | ')}`);
  if (e.code || e.title) l.push(`  problem: ${[e.code, e.title].filter(Boolean).join(' — ')}`);
  if (e.message) l.push(`  message: ${e.message}`);
  if (e.detail) l.push(`  detail: ${e.detail}`);
  if (e.requestId) l.push(`  request-id: ${e.requestId}`);
  if (e.headers && Object.keys(e.headers).length) l.push(`  headers: ${Object.entries(e.headers).map(([k, v]) => `${k}=${v}`).join(', ')}`);
  if (e.breadcrumbs?.length) l.push(`  before: ${e.breadcrumbs.join(' › ')}`);
  if (e.stack) { l.push('  stack:'); l.push(...e.stack.split('\n').map((s) => `    ${s}`)); }
  return l.join('\n');
}

/** Whether an entry matches the search: its path, code, title, message, detail, page or request id. */
export function matches(e: ErrorEntry, q: string, kindFa = ''): boolean {
  const t = q.trim().toLowerCase();
  if (!t) return true;
  return [e.path, e.code, e.title, e.message, e.detail, e.screen, e.requestId, e.method, e.status?.toString(), kindFa, `#${e.id}`, ...(e.paths ?? [])]
    .some((x) => x?.toLowerCase().includes(t));
}

/** The panel's one log. */
export const errorLog = new ErrorLog();
