'use client';

// ⟨1.0.1⟩ Part C: the one ring of the look. A share as an arc with something in its middle: a Claude account's window, a deadline
// that empties, the build ring of a workshop turn. It moves only for a reason: the arc follows its real value (M12), and the small
// turning arc (M7) runs only while [live] says work is going on.

import type { ReactNode } from 'react';
import { cx } from '@/lib/format';

export type RingTone = 'silver' | 'gold' | 'warn' | 'near' | 'neg' | 'muted';
const STROKE: Record<RingTone, string> = {
  silver: 'var(--hq-silver-ink)', gold: 'var(--hq-gold-ink)', warn: 'var(--hq-warning)', near: 'color-mix(in srgb, var(--hq-warning) 55%, var(--hq-negative))',
  neg: 'var(--hq-negative)', muted: 'var(--hq-line-strong)',
};
export const ringColor = (tone: RingTone) => STROKE[tone];

/**
 * [value]: the share drawn, 0..1 (null: unknown, only the track). [live]: a quarter arc turns on the ring while a call is in flight.
 * [broken]: the track is dashed (a ring that stands for something stuck or off). The middle is [children].
 */
export function Ring({ value, size = 72, stroke = 5, tone = 'silver', live = false, broken = false, label, children, className }: {
  value: number | null | undefined; size?: number; stroke?: number; tone?: RingTone; live?: boolean; broken?: boolean; label?: string; children?: ReactNode; className?: string;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = value == null || !Number.isFinite(value) ? null : Math.max(0, Math.min(1, value));
  return (
    <span className={cx('relative inline-flex flex-none items-center justify-center', className)} style={{ width: size, height: size }}
      role="img" aria-label={label} data-ring={v == null ? '' : v.toFixed(2)} data-ring-live={live ? '' : undefined}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="absolute inset-0 -rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--hq-surface-raised)" strokeWidth={stroke} strokeDasharray={broken ? '3 5' : undefined} />
        {v != null && v > 0 ? (
          <circle className="hq-m12" cx={size / 2} cy={size / 2} r={r} fill="none" stroke={STROKE[tone]} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={`${c * v} ${c}`} />
        ) : null}
        {live ? (
          <circle className="hq-m7" cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--hq-text-primary)" strokeOpacity=".7" strokeWidth={Math.max(1.5, stroke - 2.5)} strokeLinecap="round" strokeDasharray={`${c * 0.16} ${c}`} />
        ) : null}
      </svg>
      <span className="relative flex flex-col items-center justify-center text-center leading-none">{children}</span>
    </span>
  );
}

/** A tiny line of a series (the last 24 hours of a figure): no axis, no dots, the last point marked. Nothing is drawn for fewer than two points. */
export function Spark({ series, width = 56, height = 18, tone = 'silver', label }: { series: number[] | null | undefined; width?: number; height?: number; tone?: 'silver' | 'gold'; label?: string }) {
  const s = (series ?? []).filter((x) => Number.isFinite(x));
  if (s.length < 2) return null;
  const min = Math.min(...s);
  const max = Math.max(...s);
  const span = max - min || 1;
  const pad = 2;
  const pts = s.map((y, i) => [pad + (i * (width - 2 * pad)) / (s.length - 1), height - pad - ((y - min) / span) * (height - 2 * pad)] as const);
  const col = tone === 'gold' ? 'var(--hq-gold-ink)' : 'var(--hq-silver-ink)';
  const last = pts[pts.length - 1]!;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label} data-spark className="flex-none" style={{ direction: 'ltr' }}>
      <polyline points={pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')} fill="none" stroke={col} strokeOpacity=".75" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="1.8" fill={col} />
    </svg>
  );
}

/** A tick that draws itself (M8), for a thing that was just done. */
export function DrawnTick({ size = 18, tone = 'currentColor' }: { size?: number; tone?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden className="flex-none" data-tick>
      <path className="hq-m8" pathLength={1} d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke={tone} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
