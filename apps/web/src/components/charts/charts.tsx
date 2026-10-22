'use client';

import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
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
  // Drawn at the container's real width so labels stay 11px on a phone instead of shrinking with a viewBox.
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(720);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => { if (e) setW(Math.round(e.contentRect.width)); });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const W = Math.max(w, 280), H = height, P = { l: 48, r: 16, t: 16, b: 28 };
  const every = Math.ceil(days.length / (W < 480 ? 4 : 7));
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
    <div ref={box} className="relative" style={{ direction: 'ltr' }}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="block w-full touch-pan-y" role="img" aria-label="مصرف تجمعی در برابر بودجه" onPointerLeave={() => setHi(null)}
        onPointerMove={(e) => { const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const px = ((e.clientX - r.left) / r.width) * W; const i = Math.round(((px - P.l) / (W - P.l - P.r)) * (n - 1)); setHi(i >= 0 && i < cum.length ? i : null); }}>
        {ticks.map((t) => <g key={t}><line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="var(--hq-line-divider)" /><text x={P.l - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--hq-text-muted)" fontFamily="IRANYekanX">{fmt(t)}</text></g>)}
        {budget ? <g><line x1={P.l} x2={W - P.r} y1={y(budget)} y2={y(budget)} stroke="var(--hq-negative)" strokeDasharray="6 5" strokeWidth={1.5} /><text x={W - P.r} y={y(budget) - 6} textAnchor="end" fontSize="11" fill="var(--hq-negative)" fontFamily="IRANYekanX">{fmt(budget)}{' سقف'}</text></g> : null}
        <path d={area} fill="var(--hq-chart-1)" opacity={0.12} />
        <path d={path} fill="none" stroke="var(--hq-chart-1)" strokeWidth={2} strokeLinejoin="round" />
        {n > cum.length ? <line x1={x(cum.length - 1)} y1={y(last)} x2={x(n - 1)} y2={y(fc)} stroke="var(--hq-chart-1)" strokeWidth={2} strokeDasharray="4 6" opacity={0.7} /> : null}
        {days.map((d, i) => (i % every === 0 ? <text key={d.key} x={x(i)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--hq-text-muted)" fontFamily="IRANYekanX">{d.label}</text> : null))}
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

export type Line = { key: string; label: ReactNode; color: string; values: Array<number | null> };
const nice = (v: number) => { const e = 10 ** Math.floor(Math.log10(v)); const m = v / e; return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * e; };

/** Several series over the same days on one axis: a legend above (identity never by colour alone), each line's last value as a direct
 *  label in the end gutter (a leader joins a label that had to move, or a line that ended early), a crosshair and a tooltip on hover.
 *  Time runs left→right; a missing day is a gap in the line, never a zero. */
export function LinesChart({ days, lines, fmt, tick, height = 240, label }: { days: Array<{ key: string; label: string }>; lines: Line[]; fmt: (v: number) => string; tick?: (v: number) => string; height?: number; label: string }) {
  const [hi, setHi] = useState<number | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(720);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => { if (e) setW(Math.round(e.contentRect.width)); });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const W = Math.max(w, 280), H = height, P = { l: 44, r: 64, t: 12, b: 26 };
  const n = days.length;
  const yMax = nice(Math.max(1, ...lines.flatMap((l) => l.values.filter((v): v is number => v != null))) * 1.06);
  const x = (i: number) => P.l + (n <= 1 ? 0 : (i / (n - 1)) * (W - P.l - P.r));
  const y = (v: number) => H - P.b - (v / yMax) * (H - P.t - P.b);
  const path = (vs: Array<number | null>) => vs.reduce<{ d: string; pen: boolean }>((a, v, i) => (v == null ? { d: a.d, pen: false } : { d: `${a.d}${a.pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`, pen: true }), { d: '', pen: false }).d;
  const ends = lines.flatMap((l) => {
    const i = l.values.findLastIndex((v) => v != null);
    return i < 0 ? [] : [{ key: l.key, color: l.color, i, v: l.values[i]!, at: y(l.values[i]!), ly: y(l.values[i]!) }];
  }).sort((a, b) => a.at - b.at);
  ends.forEach((e, k) => { if (k && e.ly - ends[k - 1]!.ly < 14) e.ly = ends[k - 1]!.ly + 14; });
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => yMax * t);
  const every = Math.ceil(n / (W < 480 ? 4 : 7));
  const gx = x(n - 1) + 10;
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-wrap gap-x-4 gap-y-1.5" aria-label="راهنما">
        {lines.map((l) => (
          <li key={l.key}>
            <button type="button" onMouseEnter={() => setFocus(l.key)} onMouseLeave={() => setFocus(null)} onFocus={() => setFocus(l.key)} onBlur={() => setFocus(null)}
              className={cx('flex items-center gap-2 text-[12px] text-sec transition-opacity', focus && focus !== l.key && 'opacity-50')}>
              <span className="h-[2px] w-3.5 rounded-full" style={{ background: l.color }} />{l.label}
            </button>
          </li>
        ))}
      </ul>
      <div ref={box} className="relative" style={{ direction: 'ltr' }}>
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="block w-full touch-pan-y" role="img" aria-label={label} onPointerLeave={() => setHi(null)}
          onPointerMove={(e) => { const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const px = ((e.clientX - r.left) / r.width) * W; const i = Math.round(((px - P.l) / (W - P.l - P.r)) * (n - 1)); setHi(i >= 0 && i < n ? i : null); }}>
          {ticks.map((t) => <g key={t}><line x1={P.l} x2={x(n - 1)} y1={y(t)} y2={y(t)} stroke="var(--hq-line-divider)" /><text x={P.l - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--hq-text-muted)" fontFamily="IRANYekanX">{(tick ?? fmt)(t)}</text></g>)}
          {days.map((d, i) => (i % every === 0 || i === n - 1) && (i === n - 1 || n - 1 - i >= every / 2) ? <text key={d.key} x={x(i)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--hq-text-muted)" fontFamily="IRANYekanX">{d.label}</text> : null)}
          {lines.map((l) => <path key={l.key} d={path(l.values)} fill="none" stroke={l.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" opacity={focus && focus !== l.key ? 0.25 : 1} />)}
          {hi != null ? <line x1={x(hi)} x2={x(hi)} y1={P.t} y2={H - P.b} stroke="var(--hq-line-strong)" /> : null}
          {ends.map((e) => (
            <g key={e.key} opacity={focus && focus !== e.key ? 0.3 : 1}>
              {e.i < n - 1 || Math.abs(e.ly - e.at) > 1 ? <polyline points={`${x(e.i) + 5},${e.at} ${gx - 3},${e.ly}`} fill="none" stroke="var(--hq-line-strong)" /> : null}
              <circle cx={x(e.i)} cy={e.at} r={4} fill={e.color} stroke="var(--hq-surface-card)" strokeWidth={2} />
              <text x={gx} y={e.ly + 4} fontSize="11" fontWeight={600} fill="var(--hq-text-secondary)" fontFamily="IRANYekanX">{fmt(e.v)}</text>
            </g>
          ))}
          {hi != null ? lines.map((l) => (l.values[hi] != null ? <circle key={l.key} cx={x(hi)} cy={y(l.values[hi]!)} r={4} fill={l.color} stroke="var(--hq-surface-card)" strokeWidth={2} /> : null)) : null}
        </svg>
        {hi != null ? (
          <div className="pointer-events-none absolute top-2 min-w-[150px] rounded-[10px] bg-raised px-3 py-2 text-[12px] shadow-[0_8px_24px_rgba(0,0,0,.35)]" style={{ left: `clamp(8px, ${(x(hi) / W) * 100}% - 75px, calc(100% - 170px))`, direction: 'rtl' }}>
            <div className="pb-1 text-muted">{days[hi]!.label}</div>
            {[...lines].sort((a, b) => (b.values[hi] ?? -1) - (a.values[hi] ?? -1)).map((l) => (
              <div key={l.key} className="flex items-center gap-2">
                <span className="h-[2px] w-3 rounded-full" style={{ background: l.color }} />
                <span className="flex-1 text-sec">{l.label}</span>
                <span className="fig font-semibold text-ink">{l.values[hi] != null ? fmt(l.values[hi]!) : '—'}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
