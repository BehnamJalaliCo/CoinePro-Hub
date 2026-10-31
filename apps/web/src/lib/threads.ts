// The messages page per company (the owner, 2026-10-31: not one long list), as the Android app's core/data ThreadGroups:
// - the holding first: the advisor, the overseer, the assistant, the legal counsel and anything else of the holding (or of no company);
// - then each company in the order the hub lists them: its CEO, then its managers by department (the departments' usual order), then
//   everyone else; inside each rank the latest conversation first;
// - a company with no conversation is left out; a thread of a company the panel does not know yet gets its own group.

import type { Schemas } from '@/lib/api/client';
import { DEPT_FA } from '@/lib/labels';

export type Thread = Schemas['Thread'];
type Company = Pick<Schemas['Company'], 'code' | 'kind'>;
export type ThreadGroup = { company: string; holding: boolean; threads: Thread[]; unread: number };

const HOLDING_KINDS = ['advisor', 'overseer', 'assistant', 'legal'];
const DEPT_ORDER = Object.keys(DEPT_FA);

/** The rank of a thread inside its company: the holding's counterparts in the order the owner meets them; the CEO, the managers, the rest. */
export function rank(t: Pick<Thread, 'kind' | 'code'>, holding: boolean): number {
  if (holding && HOLDING_KINDS.includes(t.kind)) return HOLDING_KINDS.indexOf(t.kind);
  if (t.kind === 'ceo' || t.code.endsWith('-CEO')) return 10;
  if (t.kind === 'manager' || t.code.endsWith('-MGR')) return 20;
  return 30;
}
/** A manager's department from the thread's code ("TY-GROWTH-MGR" → GROWTH), for their order. */
export const departmentOf = (t: Pick<Thread, 'code'>) => { const p = t.code.split('-'); return p.length >= 3 ? p[1]! : null; };

const deptIndex = (t: Thread) => { const d = departmentOf(t); if (!d) return -1; const i = DEPT_ORDER.indexOf(d); return i < 0 ? DEPT_ORDER.length : i; };
const time = (iso: string | null | undefined) => (iso ? new Date(iso).getTime() || 0 : 0);

export function groupThreads(threads: Thread[], companies: Company[] | null | undefined): ThreadGroup[] {
  const holdingCode = companies?.find((c) => c.kind === 'holding')?.code ?? 'HQ';
  const by = new Map<string, Thread[]>();
  for (const t of threads) { const k = t.company?.trim() || holdingCode; by.set(k, [...(by.get(k) ?? []), t]); }
  const order = [...new Set([holdingCode, ...(companies ?? []).filter((c) => c.kind !== 'holding').map((c) => c.code), ...[...by.keys()].sort()])];
  return order.flatMap((code) => {
    const list = by.get(code);
    if (!list?.length) return [];
    const holding = code === holdingCode;
    const sorted = [...list].sort((a, b) => rank(a, holding) - rank(b, holding) || deptIndex(a) - deptIndex(b) || time(b.last_message_at) - time(a.last_message_at) || a.title_fa.localeCompare(b.title_fa, 'fa'));
    return [{ company: code, holding, threads: sorted, unread: sorted.reduce((n, t) => n + (t.unread ?? 0), 0) }];
  });
}
