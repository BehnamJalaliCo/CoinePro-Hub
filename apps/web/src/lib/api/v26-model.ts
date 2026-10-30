// ⟨1.8⟩ Contract §26: the companies' servers under the holding's control, each through its own `hq-runner`. The pure model the web
// panel draws from, ported from the Android app's Models21.kt so both read the hub the same way: pairing codes, the server policy, a
// server's activity rows, the seal card, the owner's terminal (SSE and its buffer), `server.map` (§26.5) and the network map (§26.6).
// Servers and companies are data: nothing here counts them.

import type { Actor } from './v13';

// ------------------------------------------------------------------ servers --
export type ServerState = 'pending' | 'online' | 'offline' | 'revoked';

/** One server of the holding (§26.4 `GET /infra/servers`): made by the provisioner, or a company server paired through its runner. */
export type HubServer = {
  id: string;
  company: string;
  name: string;
  origin: 'provisioned' | 'attached';
  private_ip: string | null;
  /** The server's own work user the runner runs as (`forex` on FX), never root. */
  user: string | null;
  hostname: string | null;
  runner_version: string | null;
  state: ServerState;
  last_seen_at: string | null;
  map_at: string | null;
  /** How the runner reached the hub on its last poll (§26.1a): `private` · `public` (the fallback); null before the first. */
  via: 'private' | 'public' | null;
  hub_rtt_ms: number | null;
};

export const isOnline = (s: HubServer) => s.state === 'online';

/** The step-up target of every seal scoped to this server (`server.destructive`, `server.detach`: `<CODE>:<server>`). */
export const serverTarget = (s: Pick<HubServer, 'company' | 'name'>) => `${s.company}:${s.name}`;

/** `forex@coinepro-fx`, as the server's own shell prompt writes it (the private address when the runner sent no hostname). */
export function loginOf(s: HubServer): string {
  const host = s.hostname?.trim() || s.private_ip || '';
  return s.user ? `${s.user}@${host}` : host;
}

/** Servers as a list shows them: online first, then pending, offline, and the revoked last; the hub's order inside each. */
const ORDER: ServerState[] = ['online', 'pending', 'offline', 'revoked'];
export const byState = (list: HubServer[]) => [...list].sort((a, b) => rank(a.state) - rank(b.state));
const rank = (s: string) => { const i = ORDER.indexOf(s as ServerState); return i < 0 ? 3 : i; };

/**
 * The owner's rule (2026-10-30): a server is called by its company — «تریدیار», «کوینه‌پرو FX» — never by its hostname or address. When
 * the company has more than one server, the server's own name follows, small: «تریدیار · ty-web». Hostname and address are details of
 * the server's own page. [siblings]: how many servers the company has (the revoked too: their history is still listed).
 */
export type ServerName = { company: string; companyFa: string; server: string | null; text: string };
export function serverNameOf(company: string, companyFa: string | null | undefined, server: string | null | undefined, siblings: number): ServerName {
  const fa = companyFa?.trim() || company;
  const s = siblings > 1 && server?.trim() ? server : null;
  return { company, companyFa: fa, server: s, text: s ? `${fa} · ${s}` : fa };
}

// ------------------------------------------------------------------ pairing --
/**
 * The short code `hq-runner pair` prints on the server (§26.1, `ABCD-1234`): Latin letters and digits, two groups of four. The field
 * formats as the owner types — Persian or Arabic digits become Latin, letters upper case, anything else dropped, the dash put in after
 * the fourth character.
 */
export const PairCode = {
  LENGTH: 8,
  format(raw: string): string {
    let out = '';
    for (const ch of raw) {
      const c = ch.codePointAt(0)!;
      if (/[0-9A-Z]/.test(ch)) out += ch;
      else if (/[a-z]/.test(ch)) out += ch.toUpperCase();
      else if (c >= 0x6f0 && c <= 0x6f9) out += String(c - 0x6f0);
      else if (c >= 0x660 && c <= 0x669) out += String(c - 0x660);
      if (out.length >= 8) break;
    }
    return out.length > 4 ? `${out.slice(0, 4)}-${out.slice(4)}` : out;
  },
  valid: (code: string) => /^[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(code),
  /** Why the hub refused the code, in Persian, from the Problem's code (and its status when the code is not one of these). */
  refusal(e: { code: string; status: number }): string | null {
    if (['expired_token', 'code_expired', 'user_code_expired', 'expired'].includes(e.code) || e.status === 410) return 'این کد منقضی شده؛ هر کد فقط ۱۵ دقیقه اعتبار دارد. روی سرور دوباره hq-runner pair را اجرا کن و کد تازه را بنویس.';
    if (['invalid_user_code', 'unknown_user_code', 'user_code_unknown', 'invalid_code', 'not_found'].includes(e.code) || e.status === 404) return 'این کد پیدا نشد. همان کدی را بنویس که hq-runner pair روی سرور نشان داد.';
    if (['code_used', 'already_approved', 'user_code_used'].includes(e.code)) return 'این کد یک بار تأیید شده است؛ سرورش در فهرست هست.';
    if (e.code === 'company_mismatch') return 'این کد برای شرکت دیگری ساخته شده؛ شرکت درست را انتخاب کن.';
    return null;
  },
  /** The command the server's own Claude runs (§26.1 step 1), the company's code filled in. */
  pairCommand: (company: string | null | undefined) => `hq-runner pair --company ${company?.trim() || '<CODE>'} --name <name>`,
};

// ------------------------------------------------------------------ policy (§26.3) --
export type SealCategory = { key: string; titleFa: string; catches: string; whyFa: string };

/** The six categories of §26.3, in the contract's order. */
export const SEAL_CATEGORIES: SealCategory[] = [
  { key: 'db_drop', titleFa: 'پاک کردن یا خالی کردن دیتابیس', catches: 'DROP DATABASE · DROP TABLE · TRUNCATE', whyFa: 'داده‌ی مشتری‌ها و تاریخچه، بی‌بازگشت از دست میرود.' },
  { key: 'volume_delete', titleFa: 'پاک کردن volume داده', catches: 'docker volume rm · docker compose down -v', whyFa: 'هر چه کانتینرها نگه داشته‌اند با volume میرود.' },
  { key: 'backup_delete', titleFa: 'پاک کردن پشتیبان', catches: 'rm -rf …/backups · restic forget --prune', whyFa: 'آخرین راه برگشت است.' },
  { key: 'disk_wipe', titleFa: 'پاک کردن یا پارتیشن کردن دیسک', catches: 'mkfs · fdisk · parted · wipefs', whyFa: 'کل دیسک و هر چه رویش است.' },
  { key: 'access_change', titleFa: 'تغییر SSH، کاربرها یا فایروال همین سرور', catches: 'sshd_config · authorized_keys · userdel · passwd · ufw · iptables', whyFa: 'ممکن است راه ورود خودت به سرور بسته شود.' },
  { key: 'server_delete', titleFa: 'حذف سرور', catches: 'Hetzner API · delete server', whyFa: 'سرور و هر چه رویش است میرود.' },
];
export const sealCategory = (key: string | null | undefined) => SEAL_CATEGORIES.find((c) => c.key === key) ?? null;

/** What runs without a card (§26.3), said to the owner in one place. */
export const FREE_ON_SERVERS = ['کد زدن', 'commit و push', 'merge', 'deploy', 'ریستارت سرویس‌ها', 'تغییر تنظیمات', 'نصب بسته', 'اتوماسیون تازه'];

export type ServerPolicy = { seal_required: string[] };

/** The policy with [key] on or off: the six categories in their canonical order, any key a newer hub adds kept after them. */
export function policyWith(p: ServerPolicy, key: string, on: boolean): ServerPolicy {
  const set = new Set(p.seal_required);
  if (on) set.add(key); else set.delete(key);
  const known = SEAL_CATEGORIES.map((c) => c.key);
  return { seal_required: [...known.filter((k) => set.has(k)), ...[...new Set(p.seal_required)].filter((k) => !known.includes(k) && set.has(k)), ...(on && !known.includes(key) && !p.seal_required.includes(key) ? [key] : [])] };
}

/** What changes from [a] to [b]: each key with whether it now waits for the seal. */
export function policyChanges(a: ServerPolicy, b: ServerPolicy): Array<[string, boolean]> {
  const all = [...new Set([...SEAL_CATEGORIES.map((c) => c.key), ...a.seal_required, ...b.seal_required])];
  return all.filter((k) => a.seal_required.includes(k) !== b.seal_required.includes(k)).map((k) => [k, b.seal_required.includes(k)]);
}

// ------------------------------------------------------------------ activity (§26.2) --
/** One row of a server's activity (§26.4 `GET …/activity`): a job (`kind`, `args`, `state`) or a command inside a job (`tool`, `cmd_masked`). */
export type ServerCall = {
  id?: string | null; at?: string | null; actor: Actor; tool?: string | null; kind?: string | null; args?: Record<string, unknown> | null;
  summary_fa?: string | null; cmd_masked?: string | null; exit_code?: number | null; duration_ms?: number | null; session_ref?: string | null;
  transcript_url?: string | null; server?: string | null; state?: string | null; created_at?: string | null; started_at?: string | null; finished_at?: string | null;
};

export const SERVER_TOOL_FA: Record<string, string> = {
  'server.exec': 'فرمان', 'server.read': 'خواندن فایل', 'server.write': 'نوشتن فایل', 'server.claude': 'Claude Code', 'server.map': 'نقشه', 'server.publish': 'انتشار',
};

export type CallOutcome = 'queued' | 'running' | 'awaiting_seal' | 'ok' | 'failed' | 'cancelled' | 'refused';

export type ServerCallRow = {
  at: string; actor: Actor; tool: string; toolFa: string; summaryFa: string; cmd: string | null; outcome: CallOutcome; exitCode: number | null;
  /** `41s`, `1m 12s`: a figure, Latin. */
  duration: string | null; sessionRef: string | null; transcriptUrl: string | null; server: string | null;
  /** The folder the job runs in (`args.cwd`). */
  cwd: string | null; byOwner: boolean;
};

function outcomeOf(exit: number | null | undefined, durationMs: number | null | undefined, state: string | null | undefined, code: string | null | undefined): CallOutcome {
  if (state === 'awaiting_seal' || code === 'awaiting_seal') return 'awaiting_seal';
  if (state === 'refused' || code === 'company_locked' || code === 'deploy_frozen') return 'refused';
  if (state === 'queued') return 'queued';
  if (state === 'running') return 'running';
  if (state === 'cancelled') return 'cancelled';
  if (state === 'failed') return 'failed';
  if (state === 'done') return exit != null && exit !== 0 ? 'failed' : 'ok';
  if (exit == null && durationMs == null) return 'running';
  return exit == null || exit === 0 ? 'ok' : 'failed';
}

const argStr = (a: Record<string, unknown> | null | undefined, k: string) => { const v = a?.[k]; return typeof v === 'string' && v.trim() ? v : null; };
const spanMs = (from?: string | null, to?: string | null) => {
  if (!from || !to) return null;
  const d = new Date(to).getTime() - new Date(from).getTime();
  return Number.isFinite(d) && d >= 0 ? d : null;
};

/** `380ms`, `2.4s`, `41s`, `3m 12s`, `1h 05m` — a figure (Latin). */
export function duration(ms: number | null | undefined): string | null {
  if (ms == null || ms < 0) return null;
  if (ms < 1_000) return `${Math.round(ms)}ms`;
  if (ms < 10_000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 60_000) return `${Math.floor(ms / 1000)}s`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ${Math.floor(ms / 1000) % 60}s`;
  return `${Math.floor(ms / 3_600_000)}h ${String(Math.floor(ms / 60_000) % 60).padStart(2, '0')}m`;
}

export function callRow(c: ServerCall): ServerCallRow {
  const tool = c.tool ?? (c.kind ? `server.${c.kind}` : 'server.exec');
  const ms = c.duration_ms ?? spanMs(c.started_at, c.finished_at);
  return {
    at: c.at || c.started_at || c.created_at || '', actor: c.actor, tool, toolFa: SERVER_TOOL_FA[tool] ?? tool,
    summaryFa: c.summary_fa ?? argStr(c.args, 'title') ?? '', cmd: c.cmd_masked?.trim() || argStr(c.args, 'cmd') || argStr(c.args, 'path'),
    outcome: outcomeOf(c.exit_code, ms, c.state, null), exitCode: c.exit_code ?? null, duration: duration(ms), sessionRef: c.session_ref ?? null,
    transcriptUrl: c.transcript_url ?? null, server: c.server ?? null, cwd: argStr(c.args, 'cwd'), byOwner: c.actor?.kind === 'owner',
  };
}

/** The stream's `server.call` (§26.4: one per call, summary only); null for any other event. `actor` may be an Actor or its code. */
export function callRowOfEvent(e: { type: string; at: string; ref: string | null; data: Record<string, unknown> }): ServerCallRow | null {
  if (e.type !== 'server.call') return null;
  const d = e.data;
  const s = (k: string) => (typeof d[k] === 'string' && (d[k] as string).trim() ? (d[k] as string) : null);
  const n = (k: string) => { const v = d[k]; const x = typeof v === 'number' ? v : typeof v === 'string' ? Number(v) : NaN; return Number.isFinite(x) ? x : null; };
  const a = d.actor;
  const actor: Actor = a && typeof a === 'object' ? (a as Actor) : typeof a === 'string' ? { code: a, kind: a === 'owner' ? 'owner' : 'agent', display_fa: s('actor_fa') } : { kind: 'system', code: 'system' };
  const tool = s('tool') ?? 'server.exec';
  const exit = n('exit_code');
  const ms = n('duration_ms');
  return {
    at: e.at, actor, tool, toolFa: SERVER_TOOL_FA[tool] ?? tool, summaryFa: s('summary_fa') ?? '', cmd: s('cmd_masked'), outcome: outcomeOf(exit, ms, s('state'), s('code')),
    exitCode: exit, duration: duration(ms), sessionRef: s('session_ref'), transcriptUrl: s('transcript_url'), server: s('server') ?? e.ref, cwd: s('cwd'), byOwner: actor.kind === 'owner',
  };
}

// ------------------------------------------------------------------ the seal card (§26.3) --
export const SERVER_DESTRUCTIVE = 'server_destructive';

/** A `server_destructive` card read for the owner: the exact command, where, what kind of loss, who asked and from which session. */
export type SealCard = {
  ref: string; company: string; serverId: string | null; serverName: string; category: SealCategory | null; categoryKey: string | null;
  cmd: string; cwd: string | null; tool: string; actor: Actor; sessionRef: string | null; detectedBy: string | null; pattern: string | null;
  pending: boolean; createdAt: string; expiresAt: string | null; target: string;
};

type DecisionLike = { ref: string; kind: string; company: string; status: string; created_at: string; expires_at?: string | null; proposer: Actor; payload?: unknown };

export function sealCardOf(d: DecisionLike): SealCard | null {
  if (d.kind !== SERVER_DESTRUCTIVE) return null;
  const p = (d.payload ?? {}) as Record<string, unknown>;
  const s = (k: string) => (typeof p[k] === 'string' && (p[k] as string).trim() ? (p[k] as string) : null);
  const server = p.server;
  let id: string | null = null;
  let name = s('server_name');
  if (server && typeof server === 'object') {
    const o = server as Record<string, unknown>;
    id = typeof o.id === 'string' ? o.id : null;
    name = (typeof o.name === 'string' ? o.name : null) ?? name;
  } else if (typeof server === 'string') id = server;
  const actor = p.actor && typeof p.actor === 'object' ? (p.actor as Actor) : d.proposer;
  const company = s('company') ?? d.company;
  const serverName = name ?? id ?? '—';
  const cat = s('category');
  return {
    ref: d.ref, company, serverId: id, serverName, category: sealCategory(cat), categoryKey: cat, cmd: s('cmd') ?? s('cmd_masked') ?? s('command') ?? '',
    cwd: s('cwd'), tool: s('tool') ?? 'server.exec', actor, sessionRef: s('session_ref'), detectedBy: s('detected_by'), pattern: s('pattern'),
    pending: d.status === 'pending', createdAt: d.created_at, expiresAt: d.expires_at ?? null, target: `${company}:${serverName}`,
  };
}

// ------------------------------------------------------------------ the owner's terminal (§26.4 exec) --
export type ExecIn = { cmd: string; cwd?: string; timeout_s: number; sudo: boolean };

export type TermEvent =
  | { t: 'out'; text: string; err: boolean }
  | { t: 'exit'; code: number; durationMs: number | null }
  | { t: 'failed'; code: string; messageFa: string }
  | { t: 'awaiting_seal'; decisionRef: string | null; messageFa: string };

export type SseMessage = { event: string | null; data: string; id: string | null };

/** A line-by-line reader of `text/event-stream` (several `data:` lines join with a newline; a blank line ends an event; `:` lines are comments). */
export class SseParser {
  private event: string | null = null;
  private id: string | null = null;
  private data: string[] = [];
  private any = false;
  line(raw: string): SseMessage | null {
    const l = raw.endsWith('\r') ? raw.slice(0, -1) : raw;
    if (!l) return this.flush();
    if (l.startsWith(':')) return null;
    const i = l.indexOf(':');
    const k = i < 0 ? l : l.slice(0, i);
    const v = i < 0 ? '' : l.slice(i + 1).replace(/^ /, '');
    if (k === 'event') this.event = v;
    else if (k === 'id') this.id = v;
    else if (k === 'data') { this.data.push(v); this.any = true; }
    return null;
  }
  end(): SseMessage | null { return this.flush(); }
  private flush(): SseMessage | null {
    const m = this.any || this.event != null ? { event: this.event, data: this.data.join('\n'), id: this.id } : null;
    this.event = null; this.data = []; this.any = false;
    return m;
  }
}

const AWAITING_FA = 'این فرمان ویرانگر است و منتظر مُهر تو ماند.';
function jsonOf(s: string): Record<string, unknown> | null { try { const o = JSON.parse(s) as unknown; return o && typeof o === 'object' && !Array.isArray(o) ? (o as Record<string, unknown>) : null; } catch { return null; } }
const num = (v: unknown) => (typeof v === 'number' ? v : null);
const str = (o: Record<string, unknown> | null, k: string) => { const v = o?.[k]; return typeof v === 'string' && v ? v : null; };

/** An exec stream's event: `stdout`/`stderr` (raw text or `{text}`), `exit` (`{exit_code|code, duration_ms}`), `error` and `awaiting_seal`. */
export function termEventOf(m: SseMessage): TermEvent | null {
  const o = jsonOf(m.data);
  const text = () => str(o, 'text') ?? str(o, 'data') ?? m.data;
  const exit = (): TermEvent => ({ t: 'exit', code: num(o?.exit_code) ?? num(o?.code) ?? 0, durationMs: num(o?.duration_ms) });
  switch (m.event ?? str(o, 'type') ?? str(o, 'stream')) {
    case 'stdout': case 'out': case 'output': return { t: 'out', text: text(), err: false };
    case 'stderr': case 'err': return { t: 'out', text: text(), err: true };
    case 'exit': case 'done': case 'end': return exit();
    case 'error': return { t: 'failed', code: str(o, 'code') ?? 'internal_error', messageFa: str(o, 'message_fa') ?? str(o, 'message') ?? str(o, 'detail') ?? m.data };
    case 'awaiting_seal': return { t: 'awaiting_seal', decisionRef: str(o, 'decision_ref') ?? str(o, 'decision') ?? str(o, 'ref'), messageFa: str(o, 'message_fa') ?? AWAITING_FA };
    case null: case 'message':
      if (!o) return m.data ? { t: 'out', text: m.data, err: false } : null;
      if (o.exit_code != null) return exit();
      if (o.stderr != null) return { t: 'out', text: str(o, 'stderr') ?? '', err: true };
      if (o.stdout != null) return { t: 'out', text: str(o, 'stdout') ?? '', err: false };
      return null;
    default: return null;
  }
}

/** The events of an answer that came whole as JSON (`{stdout, stderr, exit_code, duration_ms}`) instead of a stream. */
export function termEventsOfJson(o: Record<string, unknown>): TermEvent[] {
  const out: TermEvent[] = [];
  const so = str(o, 'stdout'); if (so) out.push({ t: 'out', text: so.endsWith('\n') ? so : `${so}\n`, err: false });
  const se = str(o, 'stderr'); if (se) out.push({ t: 'out', text: se.endsWith('\n') ? se : `${se}\n`, err: true });
  const x = num(o.exit_code); if (x != null) out.push({ t: 'exit', code: x, durationMs: num(o.duration_ms) });
  return out;
}

export const awaitingOf = (o: Record<string, unknown> | null): TermEvent => ({ t: 'awaiting_seal', decisionRef: str(o, 'decision_ref') ?? str(o, 'decision') ?? str(o, 'ref'), messageFa: str(o, 'message_fa') ?? AWAITING_FA });

export type TermKind = 'cmd' | 'out' | 'err' | 'info' | 'ok' | 'fail';
export type TermLine = { kind: TermKind; text: string };

const ANSI = /\u001B\[[0-9;?]*[ -/]*[@-~]/g;

/**
 * What the terminal shows: the command typed, then its output line by line as it streams. A chunk without a newline waits for the rest of
 * its line; a carriage return (a progress bar) rewrites the line; colour codes are dropped. The oldest lines go past [max].
 */
export class TerminalBuffer {
  private done: TermLine[] = [];
  private pending: Record<'out' | 'err', string> = { out: '', err: '' };
  running = false;
  lastExit: number | null = null;
  constructor(private max = 4_000) {}
  get lines(): TermLine[] {
    const tail: TermLine[] = [];
    if (this.pending.out) tail.push({ kind: 'out', text: this.pending.out });
    if (this.pending.err) tail.push({ kind: 'err', text: this.pending.err });
    return [...this.done, ...tail];
  }
  command(cmd: string, login: string) { this.flush(); this.push({ kind: 'cmd', text: `${login}$ ${cmd}` }); this.running = true; this.lastExit = null; }
  info(text: string) { this.push({ kind: 'info', text }); }
  apply(e: TermEvent) {
    if (e.t === 'out') return this.out(e.text, e.err);
    this.flush();
    if (e.t === 'exit') { this.lastExit = e.code; this.push({ kind: e.code === 0 ? 'ok' : 'fail', text: `exit ${e.code}${duration(e.durationMs) ? ` · ${duration(e.durationMs)}` : ''}` }); }
    else if (e.t === 'failed') this.push({ kind: 'fail', text: e.messageFa });
    else this.push({ kind: 'info', text: e.messageFa });
    this.running = false;
  }
  /** The stream closed without an exit (the owner stopped it, or the line dropped). */
  ended(note: string | null) { this.flush(); if (this.running && note) this.push({ kind: 'info', text: note }); this.running = false; }
  clear() { this.done = []; this.pending = { out: '', err: '' }; }
  private out(chunk: string, err: boolean) {
    const k = err ? 'err' : 'out';
    const parts = (this.pending[k] + chunk.replace(ANSI, '').replace(/\r\n/g, '\n')).split('\n');
    for (const p of parts.slice(0, -1)) this.push({ kind: k, text: p.slice(p.lastIndexOf('\r') + 1) });
    const last = parts[parts.length - 1]!;
    this.pending[k] = last.slice(last.lastIndexOf('\r') + 1);
  }
  private flush() {
    for (const k of ['out', 'err'] as const) { if (this.pending[k]) this.push({ kind: k, text: this.pending[k] }); this.pending[k] = ''; }
  }
  private push(l: TermLine) { this.done.push(l); if (this.done.length > this.max) this.done.splice(0, this.done.length - this.max); }
}

/** The owner's last commands on one server, newest first, each once. Kept in memory only: a command can hold a secret. */
export class TermHistory {
  private list: string[] = [];
  constructor(private max = 20) {}
  get items() { return [...this.list]; }
  add(cmd: string) { const c = cmd.trim(); if (!c) return; this.list = [c, ...this.list.filter((x) => x !== c)].slice(0, this.max); }
  /** Merged with what the hub recorded for the owner (`cmd_masked`), this browser's own first. */
  with(recorded: string[]) { return [...new Set([...this.list, ...recorded.map((x) => x.trim()).filter(Boolean)])].slice(0, this.max); }
}

// ------------------------------------------------------------------ server.map (§26.5) --
export type DiskUsage = { label: string; usedBytes: number; totalBytes: number; pct: number };
export type MapContainer = { name: string; image: string | null; state: string; status: string | null; project: string | null; health: string | null };
export type MapCompose = { project: string; dir: string | null; services: number | null; running: number | null };
export type MapUnit = { name: string; state: string | null };
export type MapTimer = { unit: string; next: string | null; activates: string | null };
export type MapCron = { schedule: string; command: string; user: string | null };
export type MapPort = { port: number; proto: string; address: string | null; process: string | null; public: boolean | null };
export type MapRepo = { path: string; remote: string | null; branch: string | null; head: string | null; dirty: boolean | null; lastCommitAt: string | null };
export type MapAutomation = { kind: string; name: string; active: boolean | null; detail: string | null };
export type MapSite = { domain: string; upstream: string | null; tls: boolean | null; server: string | null };

/** The latest `server.map` read for the owner. §26 names the parts; the parser reads the shapes a mapper is likely to write and leaves out
 *  what it cannot read; nothing it meets makes it fail. */
export type ServerMap = {
  at: string | null; hostname: string | null; os: string | null; kernel: string | null; cpus: number | null; uptimeS: number | null; load: number | null;
  disks: DiskUsage[]; memory: DiskUsage | null; swap: DiskUsage | null; containers: MapContainer[]; compose: MapCompose[]; units: MapUnit[]; timers: MapTimer[];
  cron: MapCron[]; ports: MapPort[]; repos: MapRepo[]; automations: MapAutomation[]; sites: MapSite[];
};
export const runningContainers = (m: ServerMap) => m.containers.filter((c) => c.state === 'running').length;
export const mapEmpty = (m: ServerMap) => m.os == null && !m.disks.length && !m.memory && !m.containers.length && !m.repos.length && !m.sites.length;

type J = Record<string, unknown>;
const KIB = 1024;
const isObj = (e: unknown): e is J => !!e && typeof e === 'object' && !Array.isArray(e);
const sOf = (o: J | null | undefined, k: string) => { const v = o?.[k]; return typeof v === 'string' && v.trim() ? v : typeof v === 'number' ? String(v) : null; };
const bOf = (o: J, k: string) => (typeof o[k] === 'boolean' ? (o[k] as boolean) : null);
const iOf = (o: J | null | undefined, k: string) => { const v = o?.[k]; return typeof v === 'number' ? Math.trunc(v) : typeof v === 'string' && /^\d+$/.test(v) ? Number(v) : null; };
const nOf = (o: J | null | undefined, k: string) => { const v = o?.[k]; return typeof v === 'number' ? v : null; };
const textOf = (e: unknown) => (typeof e === 'string' && e.trim() ? e.trim() : null);
const listOf = (e: unknown): unknown[] => (Array.isArray(e) ? e : isObj(e) && Array.isArray(e.items) ? e.items : []);

/** Bytes from a number (bytes) or a human size ("150G", "15.6GiB", "512 MB", "800K"). */
export function bytes(e: unknown): number | null {
  if (typeof e === 'number') return e;
  if (typeof e !== 'string') return null;
  const m = /^\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGTP]?)(i?B?|b)?\s*$/i.exec(e);
  if (!m) return null;
  const mul = { K: KIB, M: KIB ** 2, G: KIB ** 3, T: KIB ** 4, P: KIB ** 5 }[m[2]!.toUpperCase() as 'K'] ?? 1;
  return Math.round(Number(m[1]) * mul);
}

/** "41 GB", "1.2 TB", "512 MB" — a figure (Latin), binary units as `df -h` and `free -h` count them. */
export function size(b: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let v = b;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  const s = v >= 100 || i === 0 ? v.toFixed(0) : v.toFixed(1).replace(/\.0$/, '');
  return `${s} ${units[i]}`;
}

const mb = (o: J, k: string) => { const v = nOf(o, k); return v == null ? null : v * KIB * KIB; };
const gb = (o: J, k: string) => { const v = nOf(o, k); return v == null ? null : v * KIB ** 3; };
function usage(o: unknown, label: string): DiskUsage | null {
  if (!isObj(o)) return null;
  const total = bytes(o.total_bytes) ?? bytes(o.size_bytes) ?? bytes(o.total) ?? bytes(o.size) ?? mb(o, 'total_mb') ?? gb(o, 'total_gb');
  if (total == null) return null;
  const avail = bytes(o.available_bytes) ?? bytes(o.available) ?? bytes(o.avail) ?? bytes(o.free_bytes) ?? bytes(o.free) ?? mb(o, 'available_mb') ?? gb(o, 'available_gb');
  const used = bytes(o.used_bytes) ?? bytes(o.used) ?? mb(o, 'used_mb') ?? gb(o, 'used_gb') ?? (avail != null ? total - avail : null);
  if (used == null) return null;
  const u = Math.max(0, used);
  return { label: sOf(o, 'mount') ?? sOf(o, 'mountpoint') ?? sOf(o, 'path') ?? sOf(o, 'device') ?? label, usedBytes: u, totalBytes: total, pct: total <= 0 ? 0 : Math.min(100, Math.max(0, (u * 100) / total)) };
}

function container(e: unknown): MapContainer | null {
  const t = textOf(e); if (t) return { name: t, image: null, state: 'running', status: null, project: null, health: null };
  if (!isObj(e)) return null;
  const name = sOf(e, 'name') ?? (Array.isArray(e.names) ? textOf(e.names[0]) : null) ?? sOf(e, 'names');
  if (!name) return null;
  const labels = isObj(e.labels) ? e.labels : null;
  const status = sOf(e, 'status');
  const state = sOf(e, 'state') ?? (status ? (/^up/i.test(status) ? 'running' : 'exited') : 'unknown');
  return { name: name.replace(/^\//, ''), image: sOf(e, 'image'), state: state.toLowerCase(), status, project: sOf(e, 'compose_project') ?? sOf(e, 'project') ?? sOf(labels, 'com.docker.compose.project'), health: sOf(e, 'health') };
}
function compose(e: unknown): MapCompose | null {
  const t = textOf(e); if (t) return { project: t, dir: null, services: null, running: null };
  if (!isObj(e)) return null;
  const name = sOf(e, 'project') ?? sOf(e, 'name'); if (!name) return null;
  const dir = sOf(e, 'dir') ?? sOf(e, 'path') ?? sOf(e, 'working_dir') ?? (Array.isArray(e.config_files) ? textOf(e.config_files[0]) : sOf(e, 'config_files'));
  const services = Array.isArray(e.services) ? e.services.length : iOf(e, 'services');
  const rs = /running\((\d+)\)/.exec(sOf(e, 'status') ?? '');
  return { project: name, dir, services, running: iOf(e, 'running') ?? (rs ? Number(rs[1]) : null) };
}
const unit = (e: unknown): MapUnit | null => { const t = textOf(e); if (t) return { name: t, state: null }; if (!isObj(e)) return null; const n = sOf(e, 'name') ?? sOf(e, 'unit'); return n ? { name: n, state: sOf(e, 'state') ?? sOf(e, 'active') ?? sOf(e, 'sub') } : null; };
const timer = (e: unknown): MapTimer | null => { const t = textOf(e); if (t) return { unit: t, next: null, activates: null }; if (!isObj(e)) return null; const n = sOf(e, 'unit') ?? sOf(e, 'name') ?? sOf(e, 'timer'); return n ? { unit: n, next: sOf(e, 'next') ?? sOf(e, 'next_at'), activates: sOf(e, 'activates') ?? sOf(e, 'service') } : null; };
function cron(e: unknown): MapCron | null {
  const line = textOf(e);
  if (line) {
    if (line.startsWith('#')) return null;
    const parts = line.split(/\s+/);
    if (line.startsWith('@')) return { schedule: parts[0]!, command: parts.slice(1).join(' '), user: null };
    return parts.length > 5 ? { schedule: parts.slice(0, 5).join(' '), command: parts.slice(5).join(' '), user: null } : null;
  }
  if (!isObj(e)) return null;
  const cmd = sOf(e, 'cmd_masked') ?? sOf(e, 'command') ?? sOf(e, 'cmd'); if (!cmd) return null;
  return { schedule: sOf(e, 'schedule') ?? sOf(e, 'when') ?? '?', command: cmd, user: sOf(e, 'user') };
}
function port(e: unknown): MapPort | null {
  if (typeof e === 'number') return { port: e, proto: 'tcp', address: null, process: null, public: null };
  if (typeof e === 'string') {
    const s = e.trim();
    const proto = s.includes('/') ? s.slice(s.indexOf('/') + 1) : 'tcp';
    const hp = s.split('/')[0]!;
    const p = Number(hp.slice(hp.lastIndexOf(':') + 1));
    if (!Number.isInteger(p) || !hp.includes(':') && !/^\d+$/.test(hp)) return null;
    return { port: p, proto, address: hp.includes(':') ? hp.slice(0, hp.lastIndexOf(':')) || null : null, process: null, public: null };
  }
  if (!isObj(e)) return null;
  const p = iOf(e, 'port'); if (p == null) return null;
  return { port: p, proto: sOf(e, 'proto') ?? sOf(e, 'protocol') ?? 'tcp', address: sOf(e, 'address') ?? sOf(e, 'bind') ?? sOf(e, 'host'), process: sOf(e, 'process') ?? sOf(e, 'program') ?? sOf(e, 'service'), public: bOf(e, 'public') };
}
function repo(e: unknown): MapRepo | null {
  const t = textOf(e); if (t) return { path: t, remote: null, branch: null, head: null, dirty: null, lastCommitAt: null };
  if (!isObj(e)) return null;
  const path = sOf(e, 'path') ?? sOf(e, 'dir'); if (!path) return null;
  const r = e.remotes;
  const fromRemotes = Array.isArray(r) ? (textOf(r[0]) ?? (isObj(r[0]) ? sOf(r[0], 'url') ?? sOf(r[0], 'fetch') : null)) : isObj(r) ? sOf(r, 'origin') ?? textOf(Object.values(r)[0]) : null;
  return { path, remote: sOf(e, 'remote') ?? sOf(e, 'origin') ?? fromRemotes, branch: sOf(e, 'branch'), head: (sOf(e, 'head') ?? sOf(e, 'commit'))?.slice(0, 12) ?? null, dirty: bOf(e, 'dirty'), lastCommitAt: sOf(e, 'last_commit_at') };
}
function automation(e: unknown, kind: string | null): MapAutomation | null {
  const t = textOf(e); if (t) return { kind: kind ?? 'automation', name: t, active: null, detail: null };
  if (!isObj(e)) return null;
  const name = sOf(e, 'name') ?? sOf(e, 'title'); if (!name) return null;
  return { kind: sOf(e, 'kind') ?? sOf(e, 'type') ?? kind ?? 'automation', name, active: bOf(e, 'active') ?? bOf(e, 'enabled'), detail: sOf(e, 'detail') ?? sOf(e, 'trigger') ?? sOf(e, 'schedule') };
}
function site(e: unknown): MapSite | null {
  const t = textOf(e); if (t) return { domain: t, upstream: null, tls: null, server: null };
  if (!isObj(e)) return null;
  const domain = sOf(e, 'domain') ?? sOf(e, 'host') ?? sOf(e, 'server_name') ?? (Array.isArray(e.domains) ? textOf(e.domains[0]) : null); if (!domain) return null;
  return { domain, upstream: sOf(e, 'upstream') ?? sOf(e, 'proxy_pass') ?? sOf(e, 'root') ?? sOf(e, 'target'), tls: bOf(e, 'tls') ?? bOf(e, 'https'), server: sOf(e, 'server') ?? sOf(e, 'via') };
}
const keep = <T,>(xs: Array<T | null>): T[] => xs.filter((x): x is T => x != null);

export function parseServerMap(e: unknown): ServerMap | null {
  if (!isObj(e)) return null;
  const o = isObj(e.map) ? e.map : e;
  const at = sOf(e, 'taken_at') ?? sOf(e, 'at') ?? sOf(e, 'map_at') ?? sOf(o, 'taken_at') ?? sOf(o, 'at');
  const osEl = o.os;
  const os = isObj(osEl) ? sOf(osEl, 'pretty_name') ?? ([sOf(osEl, 'name') ?? sOf(osEl, 'distro'), sOf(osEl, 'version')].filter(Boolean).join(' ') || null) : textOf(osEl);
  const systemd = isObj(o.systemd) ? o.systemd : null;
  const systemdList = Array.isArray(o.systemd) ? o.systemd : [];
  const isTimer = (x: unknown) => isObj(x) && x.timer === true;
  const cpu = isObj(o.cpu) ? o.cpu : null;
  const mem = [o.memory, o.mem, o.ram].find(isObj) ?? null;
  const docker = isObj(o.docker) ? o.docker : null;
  const n8n = o.n8n;
  const disksEl = o.disks ?? o.disk;
  const swap = usage(o.swap ?? mem?.swap, 'swap') ?? (mem && nOf(mem, 'swap_total_mb') != null ? usage({ total_mb: mem.swap_total_mb, used_mb: mem.swap_used_mb ?? 0 }, 'swap') : null);
  const load = nOf(o, 'load') ?? (Array.isArray(o.load) && typeof o.load[0] === 'number' ? o.load[0] : null) ?? nOf(cpu, 'load1');
  return {
    at, hostname: sOf(o, 'hostname') ?? sOf(o, 'host'), os, kernel: (isObj(osEl) ? sOf(osEl, 'kernel') : null) ?? sOf(o, 'kernel'),
    cpus: iOf(o, 'cpus') ?? iOf(cpu, 'cores') ?? iOf(cpu, 'count'), uptimeS: nOf(o, 'uptime_s') ?? nOf(o, 'uptime'), load,
    disks: Array.isArray(disksEl) ? keep(disksEl.map((d) => usage(d, '/'))) : keep([usage(disksEl, '/')]),
    memory: usage(mem, 'RAM'), swap: swap && swap.totalBytes > 0 ? swap : null,
    containers: keep(listOf(o.containers ?? docker?.containers).map(container)),
    compose: keep(listOf(o.compose ?? o.compose_projects ?? docker?.compose).map(compose)),
    units: [...keep(listOf(systemd?.units ?? systemd?.services ?? o.units ?? o.services).map(unit)), ...keep(systemdList.filter((x) => !isTimer(x)).map(unit))],
    timers: [...keep(listOf(systemd?.timers ?? o.timers).map(timer)), ...keep(systemdList.filter(isTimer).map(timer))],
    cron: keep(listOf(o.cron ?? o.crontab).map(cron)),
    ports: keep(listOf(o.ports ?? o.listening).map(port)).filter((p, i, xs) => xs.findIndex((q) => q.port === p.port && q.proto === p.proto && q.address === p.address) === i).sort((a, b) => a.port - b.port),
    repos: keep(listOf(o.repos ?? o.repositories).map(repo)),
    automations: [...keep(listOf(o.automations).map((x) => automation(x, null))), ...keep(listOf(isObj(n8n) ? n8n.workflows : n8n).map((x) => automation(x, 'n8n')))],
    sites: keep(listOf(o.sites).map(site)),
  };
}

/** Whether a port is open beyond the machine: §26.5 says so; else the address decides. */
export const portPublic = (p: MapPort) => p.public ?? (p.address == null || ['0.0.0.0', '*', '[::]', '::'].includes(p.address));

/** The repository a task runs in: the one picked if the map still has it, else the only one, else none (the hub picks). */
export const defaultRepo = (paths: string[], picked: string | null) => paths.find((p) => p === picked) ?? (paths.length === 1 ? paths[0]! : null);

// ------------------------------------------------------------------ refusals (§26, §14) --
const CODE_FA: Record<string, string> = {
  company_locked: 'کلید توقف این شرکت زده شده؛ هر کاری روی سرورهایش ایستاده است.',
  deploy_frozen: 'deploy این شرکت بسته است؛ فرمان‌های انتشار رد میشوند.',
  awaiting_seal: 'این کار ویرانگر است و منتظر مُهر تو ماند.',
  server_offline: 'runner این سرور الان آفلاین است؛ تا دوباره تماس نگیرد کاری رویش اجرا نمیشود.',
  server_unreachable: 'runner این سرور الان آفلاین است؛ تا دوباره تماس نگیرد کاری رویش اجرا نمیشود.',
  runner_revoked: 'runner این سرور باطل شده؛ برای کار دوباره، روی سرور از نو جفتش کن.',
};
/** A §26 refusal in Persian (the hub's sentence for any other code). */
export const serverError = (e: unknown) => {
  const x = e as { code?: string; messageFa?: string; message?: string };
  return (x?.code && CODE_FA[x.code]) || x?.messageFa || x?.message || 'انجام نشد.';
};

// ------------------------------------------------------------------ the holding's network map (§26.6) --
export const HUB = 'hub';
export const HUB_IP = '10.10.1.4';
/** The ports every runner tries on every other server (§26.6); the hub is tried on 443. */
export const NET_PORTS = [22, 80, 443] as const;
/** Slower than this (ms) is amber on the map. */
export const SLOW_MS = 150;
/** A check is followed every few seconds, for at most a minute. */
export const POLL_MS = 3_000;
export const MAX_WAIT_MS = 60_000;

export type NetNode = { id: string; company: string; name: string; private_ip: string | null; via: 'private' | 'public' | null; state: string; hub_rtt_ms: number | null };
export type NetLink = { from: string; to: string; port: number; ok: boolean | null; ms: number | null; error: string | null; at: string | null };
export type NetworkMap = { at: string | null; nodes: NetNode[]; links: NetLink[] };

export const isHub = (n: NetNode) => n.id === HUB;
export const nodeOnline = (n: NetNode) => isHub(n) || n.state === 'online';
/** Not on the holding's private network at all: no private address (it reaches the hub over the internet until the owner adds it). */
export const nodeOutside = (n: NetNode) => !isHub(n) && !n.private_ip?.trim();
/** On the private network, but its runner came over the public address this time (the private one did not answer). */
export const nodeFellBack = (n: NetNode) => !isHub(n) && !nodeOutside(n) && n.via === 'public';

/** The hub first (made up from the contract when the hub leaves itself out), then the attached servers; the revoked are gone. */
export const netServers = (m: NetworkMap) => m.nodes.filter((n) => !isHub(n) && n.state !== 'revoked');
export const netAll = (m: NetworkMap): NetNode[] => [m.nodes.find(isHub) ?? { id: HUB, company: 'HQ', name: 'hub', private_ip: HUB_IP, via: null, state: 'online', hub_rtt_ms: null }, ...netServers(m)];
export const netNode = (m: NetworkMap, id: string) => netAll(m).find((n) => n.id === id) ?? null;
/** What [from] found when it tried [to] on [port]; null when that was never checked. */
export const netLink = (m: NetworkMap, from: string, to: string, port: number) => [...m.links].reverse().find((l) => l.from === from && l.to === to && l.port === port) ?? null;
const t = (s: string | null | undefined) => { const v = s ? new Date(s).getTime() : NaN; return Number.isFinite(v) ? v : -Infinity; };
/** When the latest result came in. */
export const netLastAt = (m: NetworkMap) => m.links.reduce<string | null>((a, l) => (l.at && t(l.at) > t(a) ? l.at : a), null) ?? m.at;

export type LinkHealth = 'ok' | 'slow' | 'fail' | 'unknown';
export type HubLine = { node: NetNode; health: LinkHealth; via: string | null; rttMs: number | null; error: string | null };
export type NetPath = { from: NetNode; to: NetNode; ports: number[]; error: string | null; toHub: boolean };
export type NetSummary = { servers: number; failed: NetPath[]; slow: HubLine[]; outside: NetNode[]; fellBack: NetNode[]; unknown: NetNode[]; nextFreeIp: string | null; allOk: boolean };
export type CheckProgress = { expected: Set<string>; reported: Set<string> };
export const checkDone = (p: CheckProgress) => p.expected.size > 0 && [...p.expected].every((x) => p.reported.has(x));
export const checkFraction = (p: CheckProgress) => (p.expected.size ? [...p.expected].filter((x) => p.reported.has(x)).length / p.expected.size : 0);

export function linkHealth(ok: boolean | null | undefined, ms: number | null | undefined): LinkHealth {
  if (ok == null) return 'unknown';
  if (!ok) return 'fail';
  return ms != null && ms > SLOW_MS ? 'slow' : 'ok';
}

/** `3 ms`, `0.4 ms`, `41 ms`, `1.2 s` — a figure, Latin. */
export function msFig(v: number | null | undefined): string | null {
  if (v == null || v < 0) return null;
  if (v < 10) return `${v.toFixed(1).replace(/\.0$/, '')} ms`;
  if (v < 1_000) return `${Math.round(v)} ms`;
  return `${(v / 1000).toFixed(1).replace(/\.0$/, '')} s`;
}

/** The hub ↔ [n] line: a runner that stopped polling is a broken line; one that never polled is unknown; otherwise its own check of the
 *  hub (443) if there is one, else the round trip its polls report. */
export function hubLine(m: NetworkMap, n: NetNode): HubLine {
  const l = [...NET_PORTS].reverse().map((p) => netLink(m, n.id, HUB, p)).find((x) => x) ?? null;
  const rtt = n.hub_rtt_ms ?? (l?.ok ? l.ms : null);
  const h: LinkHealth = n.state === 'offline' ? 'fail' : n.state !== 'online' ? 'unknown' : l?.ok === false ? 'fail' : rtt != null || l?.ok ? linkHealth(true, rtt) : 'unknown';
  const err = n.state === 'offline' ? 'offline' : l?.ok === false ? l.error ?? 'failed' : null;
  return { node: n, health: h, via: n.via, rttMs: h === 'fail' ? null : rtt, error: err };
}

/** The lowest free address in the hub's /24 (the hub's own and every server's taken). */
export function nextFreeIp(m: NetworkMap): string | null {
  const hubIp = netAll(m)[0]!.private_ip?.trim() || HUB_IP;
  const prefix = hubIp.includes('.') ? hubIp.slice(0, hubIp.lastIndexOf('.')) : '';
  if (!prefix) return null;
  const taken = new Set(netAll(m).map((n) => (n.private_ip?.startsWith(`${prefix}.`) ? Number(n.private_ip.slice(prefix.length + 1)) : NaN)).filter(Number.isFinite));
  for (let i = 1; i <= 254; i++) if (!taken.has(i)) return `${prefix}.${i}`;
  return null;
}

/** The map in words. A server outside the private network cannot reach the others' private addresses: that is one issue (add it to the
 *  network), not a broken road per address. */
export function netSummary(m: NetworkMap): NetSummary {
  const servers = netServers(m);
  const lines = servers.map((n) => hubLine(m, n));
  const hub = netAll(m)[0]!;
  const failed: NetPath[] = lines.filter((l) => l.health === 'fail').map((l) => ({ from: l.node, to: hub, ports: [443], error: l.error, toHub: true }));
  const byId = new Map(servers.map((n) => [n.id, n]));
  const groups = new Map<string, NetLink[]>();
  for (const l of m.links) if (l.ok === false && l.to !== HUB && l.from !== HUB) groups.set(`${l.from}\u0000${l.to}`, [...(groups.get(`${l.from}\u0000${l.to}`) ?? []), l]);
  for (const [k, ls] of groups) {
    const [a, b] = k.split('\u0000') as [string, string];
    const from = byId.get(a); const to = byId.get(b);
    if (!from || !to || nodeOutside(from) || nodeOutside(to) || from.state === 'offline' || to.state === 'offline') continue;
    // The latest result of each port decides: a port that answered since is not broken.
    const ports = [...new Set(ls.map((l) => l.port))].filter((p) => netLink(m, a, b, p)?.ok === false).sort((x, y) => x - y);
    if (ports.length) failed.push({ from, to, ports, error: ls[ls.length - 1]!.error, toHub: false });
  }
  const slow = lines.filter((l) => l.health === 'slow');
  const outside = servers.filter(nodeOutside);
  const fellBack = servers.filter((n) => nodeFellBack(n) && nodeOnline(n));
  const unknown = servers.filter((n) => n.state === 'pending');
  return { servers: servers.length, failed, slow, outside, fellBack, unknown, nextFreeIp: nextFreeIp(m), allOk: !failed.length && !slow.length && !outside.length && !fellBack.length && !unknown.length };
}

/** Which online runners have reported since [before] (the map as it was when the check was queued). */
export function checkProgress(before: NetworkMap | null, now: NetworkMap): CheckProgress {
  const base = t(before ? netLastAt(before) : null);
  return { expected: new Set(netServers(now).filter(nodeOnline).map((n) => n.id)), reported: new Set(now.links.filter((l) => t(l.at) > base).map((l) => l.from)) };
}

/** A connect error in Persian. */
export function netErrorFa(e: string | null | undefined): string {
  if (!e) return 'وصل نشد';
  if (e === 'offline') return 'runner تماس نمیگیرد';
  if (/refused/i.test(e)) return 'پورت بسته است';
  if (/timeout|timed out/i.test(e)) return 'پاسخی نیامد';
  if (/unreachable|no route/i.test(e)) return 'راهی به مقصد نیست';
  return 'وصل نشد';
}

export const viaFa = (via: string | null | undefined) => (via === 'private' ? 'خصوصی' : via === 'public' ? 'عمومی' : '—');

/** Where each server sits: around the hub, the servers of one company next to each other with a gap between companies. */
export function ringAngles(nodes: Array<{ company: string }>): number[] {
  if (!nodes.length) return [];
  const groups = new Set(nodes.map((n) => n.company)).size;
  const slots = nodes.length + (groups > 1 ? groups : 0);
  let slot = 0;
  let last: string | null = null;
  return nodes.map((n) => {
    if (last != null && n.company !== last) slot++;
    last = n.company;
    return -90 + (360 * slot++) / slots;
  });
}
