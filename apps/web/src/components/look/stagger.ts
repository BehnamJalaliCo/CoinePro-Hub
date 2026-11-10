// ⟨1.0.1⟩ Part C, M17 «پله‌پله»: the rows of a list settle one after another the first time it is shown, 30 ms apart, at most eight
// rows (the rest are simply there). Spread it on each row: `<li {...stagger(i)}>`; with classes of the row's own, `cx(STAGGER, …)` and
// `style={staggerStyle(i)}`.

import type { CSSProperties } from 'react';

export const STAGGER = 'hq-m17';
export const STAGGER_ROWS = 8;

export const staggerStyle = (i: number): CSSProperties | undefined => (i < STAGGER_ROWS ? ({ '--hq-i': i } as CSSProperties) : undefined);

export function stagger(i: number): { className?: string; style?: CSSProperties } {
  return i < STAGGER_ROWS ? { className: STAGGER, style: staggerStyle(i) } : {};
}
