// The owner's orders, followed from the moment they are given to the moment they are closed (0.4.0; contract §4 ⟨1.7.4⟩, §5.2, §16.2):
// the stage on a stepper, an honest estimate of how far along it is, who holds it now, when it last moved, and where its output went.
// The same rules as the Android app's core/data/Orders.kt; here the hub's ⟨1.7.4⟩ detail carries the children two levels down (with
// their titles, progress and outputs) and `/tree-events` the whole tree's moments, so one order is two calls.

import { DEPT_FA } from './labels';
import type { ChildWork, EmployeeRef, TreeEvent, WorkDetail } from './api/v21';

export type OrderStage = 'received' | 'taken' | 'delegated' | 'working' | 'delivered' | 'done';
export const STAGES: OrderStage[] = ['received', 'taken', 'delegated', 'working', 'delivered', 'done'];
export const STAGE_FA: Record<OrderStage, string> = {
  received: 'ثبت شد', taken: 'مدیرعامل گرفت', delegated: 'واگذار شد', working: 'در حال انجام', delivered: 'تحویل شد', done: 'تمام',
};
export type OrderEnd = 'none' | 'failed' | 'cancelled';

const CLOSED = new Set(['done', 'delivered', 'cancelled', 'failed']);
const FINISHED = new Set(['done', 'delivered']);
const MOVING = new Set(['in_progress', 'waiting']);

/** One order and what is known under it: its detail (children two levels down) and, on its own page, its tree's events. */
export type OrderTrack = { root: WorkDetail; events?: TreeEvent[] };

export const endOf = (w: { status: string }): OrderEnd => (w.status === 'failed' ? 'failed' : w.status === 'cancelled' ? 'cancelled' : 'none');

/** A child's own progress report, 0..100 (⟨1.7.4⟩ `progress` 0..1). */
const pctOf = (k: ChildWork): number | null => (k.progress == null ? null : Math.round(k.progress * 100));

/**
 * The stage an order has reached. Delivered and done are the order's own status; before that it is read from below: somebody under it at
 * work (a child in progress or finished, a progress report) is «در حال انجام»; children that have not started yet are «واگذار شد»; the
 * order accepted (or a run step on it) without children is «گرفت»; otherwise it waits in the queue. A failed or cancelled order keeps
 * the stage it had reached ([endOf] says how it ended).
 */
export function stageOf(t: OrderTrack): OrderStage {
  const r = t.root;
  if (r.status === 'done') return 'done';
  if (r.status === 'delivered') return 'delivered';
  const kids = r.children ?? [];
  const grand = kids.flatMap((k) => k.children ?? []);
  const kidsMoving = kids.some((k) => MOVING.has(k.status) || FINISHED.has(k.status) || (pctOf(k) ?? 0) > 0) || grand.some((g) => g.status === 'in_progress' || FINISHED.has(g.status));
  const selfMoving = !kids.length && ((r.progress_pct ?? 0) > 0 || !!r.progress_note?.trim());
  if (kidsMoving || selfMoving) return 'working';
  if (kids.length) return 'delegated';
  const accepted = (t.events ?? []).some((e) => (e.kind === 'work.accepted' || e.kind === 'run.step') && e.depth === r.depth);
  if (MOVING.has(r.status) || accepted) return 'taken';
  return 'received';
}

/** The second stage's name: who took it. */
export function takenFa(w: { assignee: EmployeeRef | null }): string {
  const k = w.assignee?.kind;
  return !k || k === 'ceo' ? 'مدیرعامل گرفت' : k === 'manager' ? 'مدیر گرفت' : 'مجری گرفت';
}
export const stageLabel = (s: OrderStage, w: { assignee: EmployeeRef | null }) => (s === 'taken' ? takenFa(w) : STAGE_FA[s]);

const stepFraction = (s: string) => (FINISHED.has(s) ? 1 : MOVING.has(s) ? 0.3 : 0);

/** How far a child is, 0..1, from what is known of it: its status, its own progress report, or its children's statuses. */
function fractionOf(k: ChildWork): number {
  if (FINISHED.has(k.status)) return 1;
  if (k.status === 'queued' || k.status === 'failed' || k.status === 'cancelled') return 0;
  const p = pctOf(k);
  if (p != null) return Math.min(1, Math.max(0, p / 100));
  const kids = k.children ?? [];
  if (kids.length) {
    const live = kids.filter((x) => x.status !== 'cancelled');
    const list = live.length ? live : kids;
    return (list.reduce((a, x) => a + stepFraction(x.status), 0) / list.length) * 0.9;
  }
  return 0.25;
}

/**
 * An estimate of how far the order is, 0..100: received 5, taken 15, delegated 25, at work between 30 and 90 by the share of its children
 * done (or its own progress report when nobody is under it), delivered 95, done 100. It moves only when something happens, in steps of 5,
 * so it never pretends to more precision than it has. A failed or cancelled order keeps the value it had reached.
 */
export function progressOf(t: OrderTrack): number {
  const s = stageOf(t);
  let v: number;
  if (s === 'received') v = 5;
  else if (s === 'taken') v = 15;
  else if (s === 'delegated') v = 25;
  else if (s === 'delivered') v = 95;
  else if (s === 'done') v = 100;
  else {
    const kids = t.root.children ?? [];
    const live = kids.filter((k) => k.status !== 'cancelled');
    const frac = !kids.length ? (t.root.progress_pct ?? 0) / 100 : !live.length ? 0 : live.reduce((a, k) => a + fractionOf(k), 0) / live.length;
    v = 30 + 60 * Math.min(1, Math.max(0, frac));
  }
  return Math.min(100, Math.max(0, Math.round(v / 5) * 5));
}

/**
 * Who holds it now: each open path from the order's assignee down to whoever is working on a piece of it (at most two levels, as delegation
 * is). An order nobody under it holds is with its own assignee; a closed one is with nobody.
 */
export function holdersOf(t: OrderTrack): EmployeeRef[][] {
  const r = t.root;
  if (CLOSED.has(r.status) || !r.assignee) return [];
  const top = r.assignee;
  const open = (r.children ?? []).filter((k) => !CLOSED.has(k.status));
  if (!open.length) return [[top]];
  const paths = open.flatMap((k) => {
    const head = [top, ...(k.assignee ? [k.assignee] : [])];
    const deeper = (k.children ?? []).filter((g) => !CLOSED.has(g.status)).map((g) => g.assignee).filter((a): a is EmployeeRef => !!a);
    return deeper.length ? deeper.map((d) => [...head, d]) : [head];
  });
  const seen = new Set<string>();
  return paths.filter((p) => { const k = p.map((e) => e.code).join('>'); if (seen.has(k)) return false; seen.add(k); return true; });
}

/** When anything last happened on it or under it. */
export function lastActivityOf(t: OrderTrack): string {
  const all = (k: ChildWork): string[] => [k.updated_at ?? '', k.created_at, ...(k.children ?? []).flatMap(all)];
  const times = [t.root.updated_at, t.root.created_at, ...(t.root.children ?? []).flatMap(all), ...(t.events ?? []).map((e) => e.at)].filter(Boolean);
  return times.reduce((a, b) => (new Date(b).getTime() > new Date(a).getTime() ? b : a), t.root.updated_at);
}

const str = (v: unknown) => (typeof v === 'string' && v.trim() ? v.trim() : null);

/** Why it failed or was cancelled, in the agent's or the owner's words, from its events. */
export function reasonOf(t: OrderTrack): string | null {
  const own = (t.events ?? []).filter((e) => e.depth === t.root.depth && ['work.failed', 'work.declined', 'work.cancelled'].includes(e.kind));
  return own.length ? str(own[own.length - 1]!.data.reason) : null;
}

/** Every output of the order and under it, by ref. */
export function outputsOf(t: OrderTrack): string[] {
  const under = (k: ChildWork): string[] => [...(k.deliverable_refs ?? []), ...(k.children ?? []).flatMap(under)];
  const delivered = (t.events ?? []).filter((e) => e.kind === 'work.delivered');
  const refs = (list: TreeEvent[]) => list.map((e) => str(e.data.deliverable)).filter((x): x is string => !!x);
  // The order's own first: they are what the owner gave it for.
  return [...new Set([...(t.root.deliverable_refs ?? []), ...refs(delivered.filter((e) => e.depth === t.root.depth)), ...(t.root.children ?? []).flatMap(under), ...refs(delivered)])];
}

/** An agent's code as a title: "TY-CEO" → «مدیرعامل»; "TY-GROWTH-MGR" → «مدیر رشد»; another code has none. */
export function agentTitleOf(code: string | null | undefined): string | null {
  if (!code) return null;
  const parts = code.split('-');
  if (code.endsWith('-CEO')) return 'مدیرعامل';
  if (code.endsWith('-MGR') && parts.length >= 3) return `مدیر ${DEPT_FA[parts[1]!] ?? parts[1]}`;
  return null;
}

// ---------------------------------------------------------------------------------------------------------- timeline --
/** One piece of a timeline line: Persian words, or a figure (a ref, a code, a percentage) set Latin. */
export type Part = { text: string; fig?: boolean };
/** One line of an order's timeline: when, what kind of moment (for its icon), and the words. */
export type Moment = { at: string; kind: string; parts: Part[]; sub: boolean; ref: string | null };

const w = (text: string): Part => ({ text });
const f = (text: string): Part => ({ text, fig: true });

/** The order's life, newest first: its events and its children's, and the agents' run steps (summaries only, never a prompt, §16.2). */
export function timelineOf(t: OrderTrack): Moment[] {
  const r = t.root;
  const people = new Map<string, string>();
  const add = (e: EmployeeRef | null | undefined) => { if (e) people.set(e.code, e.title_fa); };
  add(r.assignee);
  const walk = (k: ChildWork) => { add(k.assignee); (k.children ?? []).forEach(walk); };
  (r.children ?? []).forEach(walk);
  const title = (code: string | null | undefined) => (code ? agentTitleOf(code) ?? people.get(code) ?? null : null);
  const who = (code: string): Part[] => { const tt = title(code); return tt ? [w(`${tt} `), f(code)] : [f(code)]; };
  const out: Moment[] = [];
  for (const e of t.events ?? []) {
    const sub = e.depth > r.depth;
    const ref = e.work_ref || r.ref;
    const d = e.data;
    const kind = e.kind.replace(/^work\./, '');
    let p: Part[];
    switch (kind) {
      case 'created': p = sub ? [w('کار '), f(ref), w(' ساخته شد')] : [w('فرمان ثبت شد و به '), w(title(str(d.assignee)) ?? 'مجری'), w(' رسید')]; break;
      case 'accepted': p = [w(title(e.actor_code) ?? 'مجری'), w(sub ? ' کار ' : ' فرمان '), f(ref), w(' را گرفت')]; break;
      case 'delegated': p = [w('سپرده شد به '), ...(str(d.to) ? who(str(d.to)!) : []), ...(str(d.child) ? [w(' با کار '), f(str(d.child)!)] : [])]; break;
      case 'progress': p = d.pct != null ? [w(`گزارش پیشرفت ${String(d.pct)}٪ روی `), f(ref)] : [w('گزارش پیشرفت روی '), f(ref)]; break;
      case 'delivered': p = [w(sub ? 'کار ' : 'فرمان '), f(ref), w(' تحویل شد'), ...(str(d.deliverable) ? [w('؛ خروجی '), f(str(d.deliverable)!)] : [])]; break;
      case 'completed': p = [w(sub ? 'کار ' : 'فرمان '), f(ref), w(' تمام شد')]; break;
      case 'failed': p = [w('ناموفق: '), w(str(d.reason) ?? 'بی‌دلیل ثبت‌شده')]; break;
      case 'declined': p = [w('رد شد: '), w(str(d.reason) ?? '')]; break;
      case 'cancelled': p = [w('لغو شد'), w(str(d.reason) ? `: ${str(d.reason)}` : '')]; break;
      case 'updated': p = [w('ویرایش شد')]; break;
      case 'run.step': {
        const acts = Array.isArray(d.actions) ? (d.actions as Array<{ tool?: string }>).map((a) => a.tool).filter(Boolean).join('، ') : '';
        p = [w(title(e.actor_code) ?? e.actor_code), w(' · قدم '), w(String(d.n ?? '')), w(': '), w(str(d.summary_fa) ?? acts)];
        out.push({ at: e.at, kind: 'run.step', parts: p, sub: true, ref });
        continue;
      }
      default: p = [w('رویداد '), f(kind)];
    }
    out.push({ at: e.at, kind, parts: p, sub, ref });
  }
  if (!(t.events ?? []).some((e) => e.kind === 'work.created' && e.depth === r.depth)) out.push({ at: r.created_at, kind: 'created', parts: [w('فرمان ثبت شد')], sub: false, ref: r.ref });
  return out.filter((m) => m.at).sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
}

// ----------------------------------------------------------------------------------------------------------- notices --
/** A change of stage worth telling the owner about (0.4.0 notices; 0.6.0 browser notifications). */
export type NoticeKind = 'delegated' | 'delivered' | 'failed' | 'done';
export type OrderNotice = { kind: NoticeKind; ref: string; title: string; company: string | null; workId: string | null; deliverable?: string | null; to?: string | null };
export type OrderBrief = { id: string; ref: string; title: string; company: string | null };

export const noticeKey = (n: OrderNotice) => `${n.ref}:${n.kind}`;
export function noticeText(n: OrderNotice): string {
  switch (n.kind) {
    case 'delegated': return `«${n.title}» به ${agentTitleOf(n.to) ?? n.to ?? 'مجری'} سپرده شد.`;
    case 'delivered': return `«${n.title}» تحویل شد${n.deliverable ? '؛ خروجی آماده است.' : '.'}`;
    case 'failed': return `«${n.title}» ناموفق ماند؛ ببین چرا.`;
    default: return `«${n.title}» تمام شد.`;
  }
}
export function noticeHeadline(n: OrderNotice): string {
  return { delegated: `فرمان ${n.ref} واگذار شد`, delivered: `فرمان ${n.ref} تحویل شد`, failed: `فرمان ${n.ref} ناموفق ماند`, done: `فرمان ${n.ref} تمام شد` }[n.kind];
}

type Ev = { type: string; ref: string | null; company: string | null; data: Record<string, unknown> };

/**
 * The notice a stream event makes for one of the owner's [orders] (by ref), or null: the first delegation, a delivery (`work.updated` with
 * status delivered, or a `deliverable.created` for it, ⟨1.7.4⟩ by its `root_ref`), a failure, and done. Each kind is told once per order.
 */
export function noticeOf(e: Ev, orders: Map<string, OrderBrief>, told: Set<string>): OrderNotice | null {
  const ref = e.type.startsWith('work.') ? e.ref : e.type === 'deliverable.created' ? (str(e.data.root_ref) && orders.has(str(e.data.root_ref)!) ? str(e.data.root_ref) : str(e.data.work)) : null;
  if (!ref) return null;
  const o = orders.get(ref);
  if (!o) return null;
  const status = str(e.data.status);
  const base = { ref, title: o.title, company: o.company, workId: o.id };
  let n: OrderNotice | null = null;
  if (e.type === 'work.delegated') n = { ...base, kind: 'delegated', to: str(e.data.to) };
  else if (e.type === 'deliverable.created') n = { ...base, kind: 'delivered', deliverable: e.ref };
  else if (e.type === 'work.updated' && status === 'delivered') n = { ...base, kind: 'delivered' };
  else if (e.type === 'work.updated' && status === 'failed') n = { ...base, kind: 'failed' };
  else if (e.type === 'work.completed' || (e.type === 'work.updated' && status === 'done')) n = { ...base, kind: 'done' };
  if (!n) return null;
  const k = noticeKey(n);
  if (told.has(k)) return null;
  told.add(k);
  return n;
}

/** The notices an order's status already implies (so opening the panel never repeats them). */
export function alreadyReached(w: { ref: string; status: string }): string[] {
  const reached: NoticeKind[] = w.status === 'done' ? ['delegated', 'delivered', 'failed', 'done']
    : w.status === 'delivered' ? ['delegated', 'delivered'] : w.status === 'failed' ? ['delegated', 'failed'] : w.status === 'waiting' ? ['delegated'] : [];
  return reached.map((k) => `${w.ref}:${k}`);
}
