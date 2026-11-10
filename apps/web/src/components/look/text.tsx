'use client';

// ⟨1.0.1⟩ Part C, numbers and text (C0.4): a Latin token inside Persian text is one isolated left-to-right run; the separator between
// facts is a thin hairline (never «·», which reads as a zero beside a Persian digit); an amount is never cut with «…», it shrinks to
// fit; a table wider than the screen scrolls sideways inside its card.

import { Children, Fragment, useEffect, useLayoutEffect, useRef, type CSSProperties, type ReactNode } from 'react';
import { cx } from '@/lib/format';

const useIsoLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect;

// ------------------------------------------------------------------------------------------------- the isolate --
const LRI = '⁦';
const PDI = '⁩';
/** [text] as one isolated left-to-right run, for a place that takes only a string (a toast, an aria-label, a title, a placeholder). */
export const ltr = (text: string | number | null | undefined): string => (text == null || text === '' ? '' : `${LRI}${text}${PDI}`);

/** A Latin token in the page: isolated, left to right, Latin tabular digits (money, a rank, a percent, a clock time, a handle). */
export function Ltr({ children, className, tabular = true }: { children: ReactNode; className?: string; tabular?: boolean }) {
  return <bdi dir="ltr" className={cx(tabular ? 'fig' : 'latin', className)}>{children}</bdi>;
}

// ----------------------------------------------------------------------------------------------- the separator --
/** The hairline between two facts. A screen reader (and a copy of the text) gets a Persian comma. */
export function Sep({ className }: { className?: string }) {
  return <span className={cx('hq-sep', className)} data-sep><span className="sr-only">، </span></span>;
}

/** Facts in one line with the hairline between them; empty ones are left out. */
export function Facts({ children, className }: { children: ReactNode; className?: string }) {
  // toArray drops null, undefined and booleans itself; an empty string is the one left to drop.
  const items = Children.toArray(children).filter((c) => c !== '');
  return (
    <span className={className}>
      {items.map((c, i) => <Fragment key={i}>{i ? <Sep /> : null}{c}</Fragment>)}
    </span>
  );
}

const DOT = /\s+[·•|]\s+/;
const BARE_DOT = /^[·•|\s]+|[·•|\s]+$/g;
const EDGE_DOT = /^\s*[·•|]\s+|\s+[·•|]\s*$/g;
/** A line of the hub's that still joins its facts with «·»: the same words with the hairline between them. */
export function seps(text: string | null | undefined, each?: (part: string, i: number) => ReactNode): ReactNode {
  if (!text) return null;
  // A dot left at an end (a ref that stood there was dropped) is no separator of anything.
  const parts = text.replace(EDGE_DOT, '').split(DOT).map((x) => x.replace(BARE_DOT, '').trim()).filter(Boolean);
  if (parts.length < 2) return each ? each(parts[0] ?? '', 0) : parts[0] ?? '';
  return parts.map((x, i) => <Fragment key={i}>{i ? <Sep /> : null}{each ? each(x, i) : x}</Fragment>);
}
/** The same for a place that takes only a string (a sentence): a spaced Persian comma. */
export const sepsFa = (text: string | null | undefined): string => (text ?? '').replace(EDGE_DOT, '').split(DOT).map((x) => x.replace(BARE_DOT, '').trim()).filter(Boolean).join('، ');

// -------------------------------------------------------------------------------------------------- the amount --
/**
 * A figure that is never cut: one line, and when its box is narrower than the figure the font shrinks to fit, down to [floor] (a
 * share of its own size). Below the floor it wraps instead of being cut. Whatever it holds keeps its own direction and digits.
 */
export function Fit({ children, className, floor = 0.6, style }: { children: ReactNode; className?: string; floor?: number; style?: CSSProperties }) {
  const box = useRef<HTMLSpanElement>(null);
  const ink = useRef<HTMLSpanElement>(null);
  // The fit is set on the node itself (React does not manage the ink's style), so a resize never waits for a render.
  useIsoLayoutEffect(() => {
    const b = box.current;
    const i = ink.current;
    if (!b || !i) return;
    const fit = () => {
      i.style.fontSize = '';
      i.style.whiteSpace = 'nowrap';
      i.style.overflowWrap = '';
      const room = b.clientWidth;
      const need = i.scrollWidth;
      if (!room || !need || need <= room) { delete b.dataset.fit; return; }
      const next = Math.max(floor, room / need);
      i.style.fontSize = `${next}em`;
      b.dataset.fit = next.toFixed(2);
      // At the floor and still too wide: it wraps rather than being cut.
      if (next <= floor) { i.style.whiteSpace = 'normal'; i.style.overflowWrap = 'anywhere'; }
    };
    fit();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(fit);
    ro.observe(b);
    return () => ro.disconnect();
  }, [children, floor]);
  return (
    <span ref={box} className={cx('block min-w-0 max-w-full', className)} style={style} data-fit-box>
      <span ref={ink} className="inline-block max-w-full">{children}</span>
    </span>
  );
}

/** An amount (money, a rank, a count of tokens): Latin tabular digits, one isolated run, never cut. */
export function Amount({ children, className, floor, style }: { children: ReactNode; className?: string; floor?: number; style?: CSSProperties }) {
  return <Fit className={className} floor={floor} style={style}><bdi dir="ltr" className="fig" data-amount>{children}</bdi></Fit>;
}

// ---------------------------------------------------------------------------------------------- the wide table --
/** A table (or any wide block) that is wider than the screen scrolls sideways inside its card; the page itself never does. */
export function ScrollX({ children, label, className }: { children: ReactNode; label: string; className?: string }) {
  return (
    <div role="region" aria-label={label} tabIndex={0} className={cx('max-w-full overflow-x-auto overscroll-x-contain [-webkit-overflow-scrolling:touch]', className)} data-scroll-x>
      {children}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------ digits --
const FA = '۰۱۲۳۴۵۶۷۸۹';
/** A count inside a sentence, in Persian digits whatever face draws it («۳ جلسه»). */
export const faCount = (n: number | null | undefined): string => (n == null || !Number.isFinite(n) ? '—' : String(Math.round(n)).replace(/\d/g, (d) => FA[Number(d)]!));
/** «HH:MM» of an instant on the owner's clock, for an isolated Latin run. */
const CLOCK = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'Asia/Tehran' });
export const clock = (iso: string | number | Date | null | undefined): string => {
  if (iso == null || iso === '') return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : CLOCK.format(d);
};
