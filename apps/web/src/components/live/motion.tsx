'use client';

// ⟨1.24⟩ K-1, the motion grammar as components (design/LIVE_VIEWS.md §2; the CSS primitives are `.hq-m1`…`.hq-m13` in globals.css, the
// particle layer is lib/live/particles.ts). Each piece moves only for a real change of state or while a real process lasts; under reduced
// motion every one of them is an instant change, and a loop becomes a still glyph with a word.

import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { cx } from '@/lib/format';

// ------------------------------------------------------------------------------------------------ environment --
const RM_QUERY = '(prefers-reduced-motion: reduce)';
const subscribeRm = (l: () => void) => {
  const m = window.matchMedia(RM_QUERY);
  m.addEventListener('change', l);
  return () => m.removeEventListener('change', l);
};
/** The system asks for less motion (rule 8). */
export const prefersReducedMotion = () => typeof window !== 'undefined' && !!window.matchMedia?.(RM_QUERY).matches;
export const useReducedMotion = () => useSyncExternalStore(subscribeRm, prefersReducedMotion, () => false);

const subscribeVis = (l: () => void) => { document.addEventListener('visibilitychange', l); return () => document.removeEventListener('visibilitychange', l); };
/** The tab is on screen (rule 7: a hidden tab draws nothing). */
export const useVisible = () => useSyncExternalStore(subscribeVis, () => document.visibilityState === 'visible', () => true);

/** A clock that ticks every [ms] while [on] (a real clock for countdowns and ages; nothing else moves at rest). */
export function useTick(ms: number, on = true): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!on) return;
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms, on]);
  return now;
}

// ----------------------------------------------------------------------------------------- M2 + M13 figures --
/**
 * A headline figure (OF-1, MO-1): when [sig] changes the value crossfades in (M2, 200 ms) and the tahrir under it glints once (M13,
 * 600 ms) in gold (the owner's) or silver (the agents'). Never a count-up; the first value just shows.
 */
export function LiveFigure({ sig, children, glint = 'silver', className, rule = true }: { sig: string; children: ReactNode; glint?: 'gold' | 'silver'; className?: string; rule?: boolean }) {
  const changes = useChanges(sig);
  const moved = changes > 0;
  return (
    <span className={cx('flex flex-col', className)}>
      <span key={sig} className={moved ? 'hq-m2-in' : undefined} data-figure={sig}>{children}</span>
      {rule ? (
        <span aria-hidden key={`g${changes}`} data-glint={moved ? glint : undefined}
          className={cx('mt-1.5 block h-px w-full', moved ? 'hq-m13' : 'opacity-35')}
          style={{ background: moved ? (glint === 'gold' ? 'var(--hq-gold-ink)' : 'var(--hq-silver-ink)') : 'var(--hq-line-tahrir)' }} />
      ) : null}
    </span>
  );
}

/** How many times [sig] has changed since the component mounted (the first value is not a change). */
export function useChanges(sig: string): number {
  const [prev, setPrev] = useState(sig);
  const [n, setN] = useState(0);
  if (prev !== sig) { setPrev(sig); setN(n + 1); }
  return n;
}

/** A word or state that crossfades when it changes (M2). */
export function Crossfade({ sig, children, className }: { sig: string; children: ReactNode; className?: string }) {
  const changes = useChanges(sig);
  return <span key={sig} className={cx(changes > 0 && 'hq-m2-in', className)}>{children}</span>;
}

// --------------------------------------------------------------------------------------------- M5 M6 M7 loops --
/** M7 «چرخه»: a 12 px arc turning while a step or a job runs; still glyph + «در حال انجام» under reduced motion. */
export function Arc({ size = 14, color = 'var(--hq-silver-ink)', word = 'در حال انجام', className }: { size?: number; color?: string; word?: string; className?: string }) {
  const rm = useReducedMotion();
  return (
    <span className={cx('inline-flex flex-none items-center gap-1', className)} data-loop="arc">
      <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden>
        <circle cx={8} cy={8} r={6} fill="none" stroke="var(--hq-line-divider)" strokeWidth={2} />
        <circle cx={8} cy={8} r={6} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeDasharray="12 26" className={rm ? undefined : 'hq-m7'} />
      </svg>
      {rm ? <span className="text-[11px] text-muted">{word}</span> : <span className="sr-only">{word}</span>}
    </span>
  );
}

/** M6 «دم»: a dot that breathes while a model call is in flight; still under reduced motion. */
export function BreathDot({ size = 8, color = 'var(--hq-silver-ink)', on = true, className }: { size?: number; color?: string; on?: boolean; className?: string }) {
  const rm = useReducedMotion();
  return <span aria-hidden className={cx('inline-block flex-none rounded-full', on && !rm && 'hq-m6', className)} style={{ width: size, height: size, background: color }} />;
}

/** M5 «نوار کار»: a thin band that runs only while a run is queued or running ([on]); a still hairline under reduced motion. */
export function WorkBand({ on, color = 'var(--hq-silver-ink)', height = 3, className, label = 'در جریان' }: { on: boolean; color?: string; height?: number; className?: string; label?: string }) {
  const rm = useReducedMotion();
  if (!on) return null;
  return (
    <span className={cx('block w-full overflow-hidden', className)} data-loop="band" aria-hidden={!rm}>
      <svg width="100%" height={height} preserveAspectRatio="none" aria-hidden>
        {/* Drawn from the start edge (right, RTL) so the band runs the way the owner reads. */}
        <line x1="100%" y1={height / 2} x2={0} y2={height / 2} stroke={color} strokeWidth={height} strokeLinecap="round" className={rm ? undefined : 'hq-m5'} opacity={rm ? 0.5 : 0.9} />
      </svg>
      {rm ? <span className="sr-only">{label}</span> : null}
    </span>
  );
}

// ------------------------------------------------------------------------------------------------ M8 marks --
/** M8 «ترسیم»: a tick that draws in once (when [draw]); a cross for a failed step. */
export function TickMark({ size = 14, draw = false, failed = false }: { size?: number; draw?: boolean; failed?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden className="flex-none" data-mark={failed ? 'failed' : 'done'}>
      {failed
        ? <path d="M4.5 4.5l7 7M11.5 4.5l-7 7" fill="none" stroke="var(--hq-negative)" strokeWidth={2} strokeLinecap="round" pathLength={1} className={draw ? 'hq-m8' : undefined} />
        : <path d="M3 8.4l3.2 3.2L13 4.8" fill="none" stroke="var(--hq-positive)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" pathLength={1} className={draw ? 'hq-m8' : undefined} />}
    </svg>
  );
}

// ------------------------------------------------------------------------------------------------- M11 FLIP --
/**
 * M11 «جابه‌جایی»: children marked `data-flip="<key>"` inside the returned ref slide from where they were to where they are (320 ms) when
 * [order] changes. Instant under reduced motion and in a hidden tab.
 */
export function useFlip<T extends HTMLElement>(order: string) {
  const ref = useRef<T | null>(null);
  const last = useRef(new Map<string, { x: number; y: number }>());
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const next = new Map<string, { x: number; y: number }>();
    const still = prefersReducedMotion() || document.hidden;
    el.querySelectorAll<HTMLElement>('[data-flip]').forEach((k) => {
      const r = k.getBoundingClientRect();
      const key = k.dataset.flip!;
      next.set(key, { x: r.left, y: r.top });
      const p = last.current.get(key);
      if (!p || still) return;
      const dx = p.x - r.left, dy = p.y - r.top;
      if (Math.abs(dx) + Math.abs(dy) < 1) return;
      k.animate?.([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }], { duration: 320, easing: 'cubic-bezier(.2,0,0,1)' });
    });
    last.current = next;
  }, [order]);
  return ref;
}
