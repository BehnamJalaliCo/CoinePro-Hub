'use client';

// ⟨1.10⟩ Contract §28 (prompt 19): the owner's clean-up of outputs (several at once: archive, seen, or delete for good), the company's deep
// catalogue, the watch (دیده‌بان: security, app health, code review, growth and the holding's proposals, each with a proposed fix), the
// panel's own error reports to the hub, and the council's failures in plain Persian. Until the OpenAPI file is regenerated the shapes live
// here, written from §28 and §27.2; the same conventions as the typed client (X-HQ-Client, Idempotency-Key, step-ups as X-Step-Up).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSyncExternalStore } from 'react';
import { bodyTarget, stepUp } from '@/lib/auth';
import { ApiError } from './client';
import { handled } from './observe';
import { refRoute } from '@/lib/refs';
import type { Finding, Protocol, Severity } from './v14';
import { call } from './v13';
import { localSeen } from './v21';

const enc = encodeURIComponent;

/** A route the hub does not serve yet (an older hub): the panel says so instead of failing. */
export const notServed = (e: unknown) => { const yes = e instanceof ApiError && (e.status === 404 || e.status === 405 || e.status === 501); if (yes) handled(e); return yes; };

// The hub deploys §28 after the panel. A §28 action whose route answers 404/405 is hidden from then on (this tab's session; a reload
// after the hub's update asks again) and never shown to the owner as an error.
export type Feature28 = 'delete' | 'catalogue';
const MISSING_KEY = 'hq.v28.missing';
const missingListeners = new Set<() => void>();
let missing: ReadonlySet<Feature28> | null = null;
function readMissing(): ReadonlySet<Feature28> {
  if (missing) return missing;
  try { missing = new Set(JSON.parse(sessionStorage.getItem(MISSING_KEY) ?? '[]') as Feature28[]); } catch { missing = new Set(); }
  return missing;
}
/** Records that the hub does not serve [f] yet. */
export function markMissing(f: Feature28) {
  const next = new Set(readMissing());
  if (next.has(f)) return;
  next.add(f);
  missing = next;
  try { sessionStorage.setItem(MISSING_KEY, JSON.stringify([...next])); } catch { /* memory only */ }
  for (const l of missingListeners) l();
}
const NONE: ReadonlySet<Feature28> = new Set();
/** Whether the hub serves [f] as far as the panel knows (true until a 404/405 says otherwise). */
export function useServed(f: Feature28): boolean {
  const m = useSyncExternalStore((l) => { missingListeners.add(l); return () => missingListeners.delete(l); }, readMissing, () => NONE);
  return !m.has(f);
}
/** Runs [p]; a 404/405 marks [f] missing and resolves to null instead of throwing. */
async function gated<T>(f: Feature28, p: () => Promise<T>): Promise<T | null> {
  try { return await p(); } catch (e) { if (e instanceof ApiError && (e.status === 404 || e.status === 405)) { handled(e); markMissing(f); return null; } throw e; }
}

// =========================================================================================== §28.1 outputs, several at once ==
/** The set as the hub binds it: unique refs in code-point order (the step-up's target is the SHA-256 of their canonical JSON). */
export const sortedRefs = (refs: string[]) => [...new Set(refs)].sort();

/** `POST /deliverables/file {refs}`; an older hub (404/405) files them one by one through `/{ref}/file`. */
export async function fileOutputs(refs: string[]): Promise<Array<{ ref: string; record: string }>> {
  const list = sortedRefs(refs);
  try {
    const out = await call<{ records: Array<{ ref: string; record: string | { ref?: string } }> }>('POST', '/deliverables/file', { refs: list });
    return (out?.records ?? []).map((r) => ({ ref: r.ref, record: typeof r.record === 'string' ? r.record : r.record?.ref ?? '' }));
  } catch (e) {
    if (!notServed(e)) throw e;
    const out: Array<{ ref: string; record: string }> = [];
    for (const r of list) out.push({ ref: r, record: (await call<{ record: string }>('POST', `/deliverables/${enc(r)}/file`, {})).record });
    return out;
  }
}

/**
 * 🔏 `deliverables.delete` on the SHA-256 of the sorted refs: rows, files and ratings leave the database; one Audit row each stays.
 * null: the hub does not delete outputs yet (404/405); the action is hidden from then on.
 */
export async function deleteOutputs(refs: string[]): Promise<number | null> {
  const list = sortedRefs(refs);
  if (!list.length) return 0;
  const token = await stepUp('deliverables.delete', await bodyTarget(JSON.stringify(list)));
  const out = await gated('delete', () => call<{ deleted?: number } | undefined>('DELETE', '/deliverables', { refs: list }, { 'X-Step-Up': token, 'Idempotency-Key': crypto.randomUUID() }));
  return out === null ? null : out?.deleted ?? list.length;
}

export function useBulkOutputs() {
  const qc = useQueryClient();
  const done = () => Promise.all(['deliverables', 'inbox', 'archive', 'work'].map((k) => qc.invalidateQueries({ queryKey: [k] })));
  return {
    file: useMutation({ mutationFn: fileOutputs, onSettled: done }),
    remove: useMutation({
      mutationFn: deleteOutputs,
      onSuccess: (n, refs) => {
        if (n === null) return;
        localSeen.forget(refs);
        for (const r of refs) qc.removeQueries({ queryKey: ['deliverables', 'one', r] });
      },
      onSettled: done,
    }),
  };
}

// =========================================================================================== §28.2 the company catalogue ==
export type CatalogueCell = string | number | boolean | null;
export type CatalogueTable = { title_fa?: string | null; columns: string[]; rows: CatalogueCell[][] };
export type CatalogueSection = {
  key: string; title_fa?: string | null; server?: string | null; summary_md?: string | null; body_md?: string | null; tables: CatalogueTable[]; count?: number | null;
};
export type CatalogueServer = { id?: string | null; name: string; state?: 'queued' | 'running' | 'done' | 'failed' | 'offline' | null; reason?: string | null };
/** Per part: the items (the first column of its tables) that appeared or went since the previous catalogue. */
export type CatalogueChange = { key: string; added: string[]; removed: string[] };
export type Catalogue = {
  company: string; at: string | null; state: 'running' | 'done' | 'failed'; record: string | null; deliverable_ref?: string | null;
  servers?: CatalogueServer[]; sections: CatalogueSection[]; diff_md?: string | null; changes?: CatalogueChange[]; reason?: string | null; started_at?: string | null;
};

/** The six parts of §28.2's fixed brief, in its order. */
export const CATALOGUE_PARTS: Array<{ key: string; fa: string; icon: 'server' | 'time' | 'memory' | 'globe' | 'code' | 'urgent'; note: string }> = [
  { key: 'products', fa: 'محصولات و سرویس‌ها', icon: 'server', note: 'کانتینر، پروژه‌ی compose، سرویس systemd، پردازه، پورت، دامنه و سایت' },
  { key: 'automations', fa: 'خودکارسازی و زمان‌بندی', icon: 'time', note: 'گردش‌کارهای n8n، cron و timerها' },
  { key: 'data', fa: 'داده', icon: 'memory', note: 'دیتابیس، جدول و تعداد ردیف (بدون محتوا)، صف و باکت' },
  { key: 'interfaces', fa: 'رابط‌ها', icon: 'globe', note: 'API و مسیرها، ربات و دستورها، وب‌هوک، سرویس‌های بیرونی (فقط نام)' },
  { key: 'code', fa: 'کد', icon: 'code', note: 'مخزن، شاخه، آخرین commit، خروجی‌ها و خطاهای تکراری لاگ' },
  { key: 'risks', fa: 'ریسک‌ها', icon: 'urgent', note: 'گواهی رو به انقضا، سرویس خراب، پورت عمومی، بسته‌ی کهنه با CVE' },
];
const PART_ALIAS: Record<string, string> = {
  services: 'products', product: 'products', automation: 'automations', schedules: 'automations', database: 'data', databases: 'data',
  apis: 'interfaces', interface: 'interfaces', integrations: 'interfaces', repositories: 'code', repos: 'code', risk: 'risks',
};
export const partOf = (key: string) => CATALOGUE_PARTS.find((p) => p.key === (PART_ALIAS[key] ?? key)) ?? null;

const cell = (v: unknown): CatalogueCell => (v == null || typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean' ? (v as CatalogueCell) : JSON.stringify(v));
function tableOf(t: Record<string, unknown>): CatalogueTable {
  const raw = Array.isArray(t.rows) ? (t.rows as unknown[]) : [];
  let columns = Array.isArray(t.columns) ? (t.columns as unknown[]).map(String) : [];
  // Rows may come as objects: their keys are the columns.
  if (!columns.length && raw[0] && typeof raw[0] === 'object' && !Array.isArray(raw[0])) columns = Object.keys(raw[0] as object);
  const rows = raw.map((r) => (Array.isArray(r) ? r.map(cell) : r && typeof r === 'object' ? columns.map((c) => cell((r as Record<string, unknown>)[c])) : [cell(r)]));
  return { title_fa: (t.title_fa as string | null | undefined) ?? (t.title as string | null | undefined) ?? null, columns, rows };
}
/**
 * The hub's catalogue, read leniently: a section with one table or many, rows as arrays or objects, notes as `notes_md` or `body_md`,
 * the deliverable as `deliverable` or `deliverable_ref`, reasons as `reason_fa`, the difference as words or as `{part: {added, removed}}`.
 */
export function parseCatalogue(x: unknown): Catalogue | null {
  if (!x || typeof x !== 'object') return null;
  const o = x as Record<string, unknown>;
  const sections = (Array.isArray(o.sections) ? (o.sections as Array<Record<string, unknown>>) : []).map((s) => ({
    key: String(s.key ?? s.kind ?? ''), title_fa: (s.title_fa as string | null) ?? null, server: (s.server as string | null) ?? null,
    summary_md: (s.summary_md as string | null) ?? null, body_md: (s.body_md as string | null) ?? (s.notes_md as string | null) ?? null,
    count: typeof s.count === 'number' ? s.count : null,
    tables: [...(Array.isArray(s.tables) ? (s.tables as Array<Record<string, unknown>>) : []), ...(s.table && typeof s.table === 'object' ? [s.table as Record<string, unknown>] : [])].map(tableOf),
  }));
  const diff = o.diff ?? o.diff_md;
  const changes = diff && typeof diff === 'object' && !Array.isArray(diff)
    ? Object.entries(diff as Record<string, { added?: unknown; removed?: unknown }>).map(([key, v]) => ({
      key, added: Array.isArray(v?.added) ? v.added.map(String) : [], removed: Array.isArray(v?.removed) ? v.removed.map(String) : [],
    })).filter((c) => c.added.length || c.removed.length)
    : [];
  const state = (o.state as Catalogue['state']) ?? 'done';
  const at = (o.at as string | null) ?? null;
  return {
    company: String(o.company ?? ''), at, state, record: (o.record as string | null) ?? null,
    deliverable_ref: (o.deliverable_ref as string | null) ?? (o.deliverable as string | null) ?? null,
    servers: ((o.servers as Array<CatalogueServer & { reason_fa?: string | null }> | undefined) ?? []).map((s) => ({ ...s, reason: s.reason ?? s.reason_fa ?? null })), sections,
    diff_md: typeof diff === 'string' ? diff : null, changes,
    reason: (o.reason as string | null) ?? (o.reason_fa as string | null) ?? null, started_at: (o.started_at as string | null) ?? (state === 'running' ? at : null),
  };
}

/** The latest catalogue; null before the first (`404`). */
export async function catalogue(code: string): Promise<Catalogue | null> {
  try { return parseCatalogue(await call<unknown>('GET', `/companies/${enc(code)}/catalogue`)); } catch (e) {
    if (e instanceof ApiError && e.status === 405) { handled(e); markMissing('catalogue'); return null; }
    if (e instanceof ApiError && e.status === 404) { handled(e); return null; }
    throw e;
  }
}
export const useCatalogue = (code: string) =>
  useQuery({
    queryKey: ['companies', 'catalogue', code], queryFn: () => catalogue(code), staleTime: 30_000,
    // While a run reads the servers, look again every few seconds.
    refetchInterval: (q) => (q.state.data?.state === 'running' ? 4_000 : false),
  });
export function useStartCatalogue(code: string) {
  const qc = useQueryClient();
  return useMutation({
    // null: the hub does not build catalogues yet (404/405); the section is hidden from then on.
    mutationFn: async () => { const out = await gated('catalogue', () => call<unknown>('POST', `/companies/${enc(code)}/catalogue`, {})); return out === null ? null : parseCatalogue(out); },
    onSuccess: (c) => { if (c) qc.setQueryData(['companies', 'catalogue', code], (old: Catalogue | null | undefined) => (c.sections.length || !old ? c : { ...old, state: c.state, started_at: c.started_at ?? c.at })); },
    onSettled: () => qc.invalidateQueries({ queryKey: ['companies', 'catalogue', code] }),
  });
}

// ================================================================================================ §28.3 the watch ==
export type WatchGroup = 'security' | 'app_health' | 'code' | 'growth' | 'holding';
export const WATCH_GROUPS: Array<{ key: WatchGroup; fa: string; icon: 'lock' | 'urgent' | 'code' | 'chart' | 'holding'; who: string; rhythm: string }> = [
  { key: 'security', fa: 'امنیت', icon: 'lock', who: 'ناظر کل', rhythm: 'هر روز: پورت‌های عمومی، CVE، انقضای TLS، ورودهای ناموفق، رمز در مخزن، تازگی پشتیبان' },
  { key: 'app_health', fa: 'سلامت اپ', icon: 'urgent', who: 'ناظر کل', rhythm: 'هر روز: خطاهایی که اپ‌ها میفرستند، گروه‌بندی‌شده با علت در کد' },
  { key: 'code', fa: 'کد', icon: 'code', who: 'ناظر کل', rhythm: 'هر هفته: بازبینی فقط‌خواندنی هر مخزن؛ باگ، کد مرده، تست جاافتاده، الگوی پرخطر' },
  { key: 'growth', fa: 'رشد', icon: 'chart', who: 'مشاور کل', rhythm: 'هر هفته: سه حرکت پرارزش هر شرکت با اثر پیش‌بینی‌شده' },
  { key: 'holding', fa: 'پیشنهاد هلدینگ', icon: 'holding', who: 'مدیر کل دیجیتال', rhythm: 'هر ماه: فرصت‌های میان شرکت‌ها' },
];
/** The overseer's proposed fix as something for the owner's seal: a work item, a Code Workshop session or a card (its ref once made). */
export type FindingFix = { kind: 'work' | 'workshop' | 'decision'; ref?: string | null; summary_fa?: string | null };
/** A finding as a ⟨1.10⟩ hub serves it: the watch's `kind` and the proposed fix, in words (`fix_md`) and as `fix`. */
export type WatchFinding = Finding & { kind?: WatchGroup | null; fix_md?: string | null; fix?: FindingFix | null };
export const SEVERITY_RANK: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
/** Whether the owner still has something to do with it. */
export const isOpenFinding = (f: Finding) => f.status !== 'verified' && f.status !== 'closed';
export const bySeverity = (a: WatchFinding, b: WatchFinding) => (SEVERITY_RANK[a.severity] ?? 9) - (SEVERITY_RANK[b.severity] ?? 9) || b.opened_at.localeCompare(a.opened_at);
const TITLES: Array<[WatchGroup, RegExp]> = [
  ['app_health', /سلامت\s*اپ|خطای\s*اپ|خطاهای\s*اپ|app[ _-]?health|client errors/i],
  ['code', /بازبینی\s*کد|code[ _-]?review/i],
  ['growth', /رشد|growth/i],
  ['holding', /پیشنهاد\s*هلدینگ|holding proposal/i],
  ['security', /امنیت|security/i],
];
/**
 * What a finding watches: the hub's `kind`; a finding without it is placed by its protocol (the protocol's title, or the security area),
 * and anything else is not the watch's (the Android app's Watch.kindOf).
 */
export function groupOf(f: WatchFinding, protocols?: Protocol[] | null): WatchGroup | null {
  if (WATCH_GROUPS.some((g) => g.key === f.kind)) return f.kind as WatchGroup;
  const p = protocols?.find((x) => x.ref === f.protocol);
  if (!p) return null;
  return TITLES.find(([, re]) => re.test(p.title_fa))?.[0] ?? (p.area === 'security' ? 'security' : null);
}
/** The fix in words: the overseer's own text, or the fix's summary. */
export const fixText = (f: WatchFinding) => (f.fix_md?.trim() || f.fix?.summary_fa?.trim() || null);
/** The priority a fix's work item takes from the finding's severity. */
export const priorityOf = (s: Severity) => (s === 'critical' ? 'P1' : s === 'high' ? 'P2' : s === 'medium' ? 'P3' : 'P4') as 'P1' | 'P2' | 'P3' | 'P4';

export type WatchItem = WatchFinding & { group: WatchGroup };
/** The watch's findings, from the same `/oversight/findings` the overseer's page reads, each with its group. */
export async function watchFindings(): Promise<WatchItem[]> {
  const [out, protocols] = await Promise.all([
    call<{ items: WatchFinding[] }>('GET', '/oversight/findings?limit=200'),
    call<Protocol[] | { items: Protocol[] }>('GET', '/oversight/protocols').catch(() => [] as Protocol[]),
  ]);
  const ps = Array.isArray(protocols) ? protocols : protocols.items ?? [];
  return (out.items ?? []).flatMap((f) => { const g = groupOf(f, ps); return g ? [{ ...f, group: g }] : []; });
}
export const useWatch = () => useQuery({ queryKey: ['oversight', 'watch'], queryFn: watchFindings, staleTime: 30_000 });

/**
 * «تأیید اصلاح»: a fix that is already a card or a session opens it, for the owner's seal there; one that is only words becomes a work
 * item for the company, from the finding, at its severity's priority. Either way the answer is where to go.
 */
export function useApproveFix() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (f: WatchFinding): Promise<{ route: string; made: string | null }> => {
      const ref = f.fix?.ref?.trim();
      const route = ref ? refRoute(ref) : null;
      if (route) return { route, made: null };
      const words = fixText(f) ?? f.title_fa;
      const w = await call<{ id: string; ref: string }>('POST', '/work', {
        company: f.company, kind: 'one_off', priority: priorityOf(f.severity),
        title: `اصلاح ${f.ref}: ${f.title_fa}`.slice(0, 140), brief: `${words}\n\nیافته‌ی دیده‌بان: ${f.ref}`,
      });
      return { route: `/work/${w.ref ?? w.id}`, made: w.ref ?? null };
    },
    onSettled: () => Promise.all(['oversight', 'work', 'orders'].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}

// ============================================================================================ §27.2 / §28.4 the council ==
export type CouncilMember = {
  player: string; model?: string | null; state: 'queued' | 'working' | 'done' | 'failed' | 'skipped'; run_id?: string | null;
  deliverable_ref?: string | null; reason?: string | null; creative_ref?: string | null;
};
export type Council = { work_ref: string; members: CouncilMember[]; synthesis_ref: string | null; state: 'running' | 'synthesising' | 'done' | 'failed'; media?: string | null };

export async function council(work: string): Promise<Council | null> {
  try { return await call<Council>('GET', `/work/${enc(work)}/council`); } catch (e) { if (notServed(e)) return null; throw e; }
}
export const useCouncil = (work: string | null) =>
  useQuery({
    queryKey: ['work', 'council', work], queryFn: () => council(work!), enabled: !!work, staleTime: 15_000,
    refetchInterval: (q) => (q.state.data && (q.state.data.state === 'running' || q.state.data.state === 'synthesising') ? 6_000 : false),
  });

export const PLAYER_FA: Record<string, string> = { claude: 'Claude', gpt: 'GPT', gemini: 'Gemini', deepseek: 'DeepSeek', auto: 'خودکار' };
export const PROVIDER_OF: Record<string, string> = { claude: 'anthropic', gpt: 'openai', gemini: 'google', deepseek: 'deepseek' };
export const playerFa = (p: string) => PLAYER_FA[p] ?? p;
export const MEMBER_STATE: Record<CouncilMember['state'], { fa: string; tone: 'neutral' | 'gold' | 'pos' | 'neg' | 'silver' }> = {
  queued: { fa: 'در صف', tone: 'neutral' }, working: { fa: 'کار میکند', tone: 'gold' }, done: { fa: 'تحویل داد', tone: 'pos' }, failed: { fa: 'پاسخ نداد', tone: 'neg' }, skipped: { fa: 'کنار ماند', tone: 'silver' },
};
export const COUNCIL_STATE: Record<Council['state'], string> = { running: 'بازیکن‌ها کار میکنند', synthesising: 'Claude جمع‌بندی مینویسد', done: 'جمع‌بندی آماده است', failed: 'ناموفق' };

const PERSIAN = /[؀-ۿ]/;
const LATIN = /[A-Za-z]/g;
/** Codes a hub or a CLI may send in a failure, each with what it means for the owner. */
const CAUSE_FA: Array<[RegExp, string]> = [
  [/recipe_failed/i, 'دستورالعمل مرورگرش روی سایت جواب نداد'],
  [/model.*(not supported|unsupported|not_found|does not exist|refus)|unsupported_model/i, 'مدلش با این اشتراک پشتیبانی نمیشود'],
  [/signed[_ ]?out|login|unauthori[sz]ed|401|session expired/i, 'ورودش به حساب باطل شده'],
  [/rate[_ ]?limit|429|quota|limited|cap/i, 'سقف امروزش پر شده'],
  [/time[d]?[_ ]?out|deadline/i, 'در زمانش جواب نداد'],
  [/budget|envelope/i, 'از پاکت بودجه بیرون میزد'],
  [/overloaded|503|502|unavailable/i, 'سرویسش در دسترس نبود'],
];
/** Whether a reason is for a person (Persian prose) or for a machine (JSON, a stack, English). */
export function isMachineText(s: string): boolean {
  const t = s.trim();
  if (!t) return false;
  if (/^[[{]/.test(t) || /"\w+"\s*:/.test(t) || /\bat [\w.$]+\(|Traceback|Error:|Exception/.test(t)) return true;
  if (!PERSIAN.test(t)) return true;
  // Persian with an English sentence pasted in (more Latin letters than a model name or two).
  return (t.match(LATIN)?.length ?? 0) > Math.max(24, t.length * 0.45);
}
/**
 * A member's failure as the owner reads it (§28.4: never raw JSON): the hub's Persian reason as it is; anything else becomes «پاسخ نداد»
 * (or «کنار ماند»), with the cause when it is a known one, and the raw text kept for «جزئیات».
 */
export function humanReason(m: Pick<CouncilMember, 'state' | 'reason'>): { text: string; raw: string | null } | null {
  if (m.state !== 'failed' && m.state !== 'skipped') return null;
  const head = m.state === 'failed' ? 'پاسخ نداد' : 'کنار ماند';
  const r = (m.reason ?? '').trim();
  if (!r) return { text: head, raw: null };
  if (!isMachineText(r)) return { text: r, raw: null };
  const cause = CAUSE_FA.find(([re]) => re.test(r))?.[1];
  let raw = r;
  try { raw = JSON.stringify(JSON.parse(r), null, 2); } catch { /* not JSON */ }
  return { text: cause ? `${head}: ${cause}` : head, raw };
}
/** How many answered, of those that played (a skipped one is not waited for). */
export function councilProgressFa(c: Council): string {
  const playing = c.members.filter((m) => m.state !== 'skipped');
  const done = playing.filter((m) => m.state === 'done').length;
  const skipped = c.members.length - playing.length;
  const base = playing.length ? `${done.toLocaleString('fa-IR')} از ${playing.length.toLocaleString('fa-IR')} پاسخ داده‌اند` : 'هیچ بازیکنی نماند';
  return skipped ? `${base}؛ ${skipped.toLocaleString('fa-IR')} بازیکن کنار ماند` : base;
}
/** §28.4: with one answer the synthesis says so plainly and does not pretend there was a council. */
export function soloOf(c: Council): { player: string; text: string } | null {
  const done = c.members.filter((m) => m.state === 'done');
  const ended = c.members.every((m) => m.state === 'done' || m.state === 'failed' || m.state === 'skipped');
  if (done.length !== 1 || !ended) return null;
  const p = playerFa(done[0]!.player);
  return { player: p, text: `فقط ${p} پاسخ داد` };
}
