'use client';

// ⟨1.24⟩ PE-1 «چراغ حال هر نفر» (design/LIVE_VIEWS.md §4 H): each person's state by shape and word, never colour alone. Thinking = a silver
// dot that breathes (a model call in flight); working = a silver ring turning slowly (a tool or a server job runs); waiting = a hollow lapis
// ring; stuck = a negative «!» (the reason on hover and in the word); done = a positive tick; idle = a small muted dot. The loops live only
// while the state lasts; under reduced motion they are still. The state is the hub's (§29.14 on the record, then `employee.state` live).

import type { PersonState } from '@/lib/api/v42';
import { useLiveState } from '@/lib/live/store';
import { cx } from '@/lib/format';
import { useReducedMotion } from './motion';

export const PERSON_FA: Record<PersonState, string> = { thinking: 'فکر میکند', working: 'کار میکند', waiting: 'منتظر', stuck: 'گیر کرده', done: 'تمام کرد', idle: 'بیکار' };
const KNOWN: PersonState[] = ['thinking', 'working', 'waiting', 'stuck', 'done', 'idle'];
export const asPerson = (s: string | null | undefined): PersonState | null => (s && (KNOWN as string[]).includes(s) ? (s as PersonState) : null);

/** The shape of a state (14 px by default). */
export function StateGlyph({ state, size = 14, className }: { state: PersonState; size?: number; className?: string }) {
  const rm = useReducedMotion();
  const silver = 'var(--hq-silver-ink)';
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" aria-hidden data-glyph={state} className={cx('flex-none', className)}>
      {state === 'thinking' ? <circle cx={7} cy={7} r={3.5} fill={silver} className={rm ? undefined : 'hq-m6'} />
        : state === 'working' ? <><circle cx={7} cy={7} r={5} fill="none" stroke={silver} strokeWidth={1.6} strokeDasharray="16 12" style={{ transformBox: 'fill-box', transformOrigin: 'center', animation: rm ? undefined : 'hq-spin 2s linear infinite' }} /><circle cx={7} cy={7} r={1.6} fill={silver} /></>
        : state === 'waiting' ? <circle cx={7} cy={7} r={5} fill="none" stroke="var(--hq-lapis)" strokeWidth={1.6} />
        : state === 'stuck' ? <><circle cx={7} cy={7} r={6} fill="var(--hq-negative)" /><line x1={7} y1={3.6} x2={7} y2={7.6} stroke="var(--hq-surface-card)" strokeWidth={1.6} strokeLinecap="round" /><line x1={7} y1={10} x2={7} y2={10.2} stroke="var(--hq-surface-card)" strokeWidth={1.8} strokeLinecap="round" /></>
        : state === 'done' ? <path d="M3 7.4l2.6 2.6L11 4.4" fill="none" stroke="var(--hq-positive)" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
        : <circle cx={7} cy={7} r={2.4} fill="var(--hq-text-muted)" opacity={0.6} />}
    </svg>
  );
}

/**
 * A person's state now: the live one when the stream told it after [seedAt] (the record's own time), else the record's. Null when neither
 * knows (no glyph is drawn then).
 */
export function useLivePerson(code: string | null | undefined, seed?: PersonState | null, seedAt?: string | null): { state: PersonState | null; stuckFa: string | null; since: string | null } {
  const live = useLiveState((s) => (code ? s.employees[code] ?? null : null));
  if (live && live.at && (!seedAt || Date.parse(live.at) >= Date.parse(seedAt))) return { state: live.state, stuckFa: live.stuck_fa, since: live.since };
  return { state: seed ?? null, stuckFa: null, since: seedAt ?? null };
}

/** The shape and the word side by side (a medal's corner, a row, a worker). */
export function PersonStateMark({ state, stuckFa, word = true, size = 14, className }: { state: PersonState; stuckFa?: string | null; word?: boolean; size?: number; className?: string }) {
  const fa = PERSON_FA[state];
  return (
    <span className={cx('inline-flex items-center gap-1', className)} title={stuckFa ? `${fa}: ${stuckFa}` : fa} data-person={state} role="img" aria-label={stuckFa ? `${fa}: ${stuckFa}` : fa}>
      <StateGlyph state={state} size={size} />
      {word ? <span className="text-[11px] text-sec">{fa}</span> : null}
    </span>
  );
}

/** PE-1 on a medal: the glyph in the medal's corner, the word for screen readers and on hover. */
export function MedalState({ code, seed, seedAt, size = 14 }: { code: string; seed?: PersonState | null; seedAt?: string | null; size?: number }) {
  const p = useLivePerson(code, seed, seedAt);
  if (!p.state || p.state === 'idle') return null;
  return (
    <span className="absolute -bottom-0.5 -start-0.5 flex items-center justify-center rounded-full bg-card p-px" data-medal-state={p.state}>
      <PersonStateMark state={p.state} stuckFa={p.stuckFa} word={false} size={size} />
    </span>
  );
}
