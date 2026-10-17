'use client';

import { useState, type ReactNode } from 'react';
import { cx } from '@/lib/format';

export type Seg = { key: string; label: ReactNode; value: number; color: string; fmt?: string };

/** One stacked bar with a legend underneath (identity never by colour alone). 2px surface gaps. */
export function StackedBar({ segs, height = 14, label }: { segs: Seg[]; height?: number; label: string }) {
  const total = segs.reduce((a, s) => a + s.value, 0) || 1;
  const [hover, setHover] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-3">
      <div role="img" aria-label={label} className="flex w-full gap-[2px]" style={{ direction: 'ltr', height }}>
        {segs.filter((s) => s.value > 0).map((s, i, a) => (
          <span
            key={s.key}
            onMouseEnter={() => setHover(s.key)}
            onMouseLeave={() => setHover(null)}
            className={cx('h-full transition-opacity', hover && hover !== s.key && 'opacity-40', i === 0 && 'rounded-l-[4px]', i === a.length - 1 && 'rounded-r-[4px]')}
            style={{ width: `${(s.value / total) * 100}%`, background: s.color }}
          />
        ))}
      </div>
      <ul className="flex flex-wrap gap-x-5 gap-y-2">
        {segs.map((s) => (
          <li key={s.key} className={cx('flex items-center gap-2 text-[12px] transition-opacity', hover && hover !== s.key && 'opacity-50')} onMouseEnter={() => setHover(s.key)} onMouseLeave={() => setHover(null)}>
            <span className="size-2.5 rounded-[3px]" style={{ background: s.color }} />
            <span className="text-sec">{s.label}</span>
            <span className="fig text-ink">{s.fmt ?? s.value}</span>
            <span className="text-muted">{Math.round((s.value / total) * 100)}٪</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Horizontal bars, growing from the start edge (RTL), each with its value as a direct label. */
export function HBars({ rows, max }: { rows: Array<{ key: string; label: ReactNode; value: number; fmt: string; color?: string; sub?: ReactNode }>; max?: number }) {
  const m = max ?? Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((r) => (
        <li key={r.key} className="flex flex-col gap-1.5" title={`${r.fmt}`}>
          <div className="flex items-baseline gap-2 text-[13px]">
            <span className="min-w-0 flex-1 truncate text-ink">{r.label}</span>
            {r.sub ? <span className="text-[11px] text-muted">{r.sub}</span> : null}
            <span className="fig font-semibold text-ink">{r.fmt}</span>
          </div>
          <div className="h-2.5 rounded-full bg-tile">
            <span className="block h-full rounded-l-[4px] rounded-r-full" style={{ width: `${Math.max(1.5, (r.value / m) * 100)}%`, background: r.color ?? 'var(--hq-silver-ink)' }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Cumulative use against a budget line, with a dashed forecast to the end of the period.
 *  Time runs left→right (market convention for data charts). Crosshair + tooltip on hover. */
export function CumulativeChart({ days, budget, forecastTo, fmt, height = 240 }: { days: Array<{ key: string; label: string; value: number }>; budget?: number | null; forecastTo?: number; fmt: (v: number) => string; height?: number }) {
  const [hi, setHi] = useState<number | null>(null);
  const W = 720, H = height, P = { l: 48, r: 16, t: 16, b: 28 };
  const cum = days.reduce<number[]>((a, d) => [...a, (a.at(-1) ?? 0) + d.value], []);
  const n = Math.max(forecastTo ?? days.length, days.length);
  const last = cum.at(-1) ?? 0;
  const rate = days.length ? last / days.length : 0;
  const fc = n > days.length ? last + rate * (n - days.length) : last;
  const yMax = Math.max(budget ?? 0, fc, last, 1) * 1.08;
  const x = (i: number) => P.l + (i / Math.max(n - 1, 1)) * (W - P.l - P.r);
  const y = (v: number) => H - P.b - (v / yMax) * (H - P.t - P.b);
  const path = cum.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
  const area = `${path}L${x(cum.length - 1).toFixed(1)},${y(0)}L${x(0)},${y(0)}Z`;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => yMax * t);
  return (
    <div className="relative" style={{ direction: 'ltr' }}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="مصرف تجمعی در برابر بودجه" onMouseLeave={() => setHi(null)}
        onMouseMove={(e) => { const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const px = ((e.clientX - r.left) / r.width) * W; const i = Math.round(((px - P.l) / (W - P.l - P.r)) * (n - 1)); setHi(i >= 0 && i < cum.length ? i : null); }}>
        {ticks.map((t) => <g key={t}><line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="var(--hq-line-divider)" /><text x={P.l - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--hq-text-muted)" fontFamily="IRANYekanX">{fmt(t)}</text></g>)}
        {budget ? <g><line x1={P.l} x2={W - P.r} y1={y(budget)} y2={y(budget)} stroke="var(--hq-negative)" strokeDasharray="6 5" strokeWidth={1.5} /><text x={W - P.r} y={y(budget) - 6} textAnchor="end" fontSize="11" fill="var(--hq-negative)" fontFamily="IRANYekanX">budget {fmt(budget)}</text></g> : null}
        <path d={area} fill="var(--hq-chart-1)" opacity={0.12} />
        <path d={path} fill="none" stroke="var(--hq-chart-1)" strokeWidth={2} strokeLinejoin="round" />
        {n > cum.length ? <line x1={x(cum.length - 1)} y1={y(last)} x2={x(n - 1)} y2={y(fc)} stroke="var(--hq-chart-1)" strokeWidth={2} strokeDasharray="4 6" opacity={0.7} /> : null}
        {days.map((d, i) => (i % Math.ceil(days.length / 7) === 0 ? <text key={d.key} x={x(i)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--hq-text-muted)" fontFamily="IRANYekanX">{d.label}</text> : null))}
        {hi != null ? <g><line x1={x(hi)} x2={x(hi)} y1={P.t} y2={H - P.b} stroke="var(--hq-line-strong)" /><circle cx={x(hi)} cy={y(cum[hi]!)} r={5} fill="var(--hq-chart-1)" stroke="var(--hq-surface-card)" strokeWidth={2} /></g> : null}
      </svg>
      {hi != null ? (
        <div className="pointer-events-none absolute top-2 rounded-[10px] bg-raised px-3 py-2 text-[12px] shadow-[0_8px_24px_rgba(0,0,0,.35)]" style={{ left: `clamp(8px, ${(x(hi) / W) * 100}% - 70px, calc(100% - 160px))` }}>
          <div className="text-muted">{days[hi]!.label}</div>
          <div className="fig font-semibold text-ink">{fmt(cum[hi]!)}</div>
          <div className="fig text-sec">+{fmt(days[hi]!.value)}</div>
        </div>
      ) : null}
    </div>
  );
}
