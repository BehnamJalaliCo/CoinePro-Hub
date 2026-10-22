'use client';

import { QueryClientContext } from '@tanstack/react-query';
import { useContext, type ReactNode } from 'react';
import { BRAND } from '@/generated/brand';
import { useBrands, type BrandColors, type BrandMark } from '@/lib/api/brand';

/** What a company's mark is drawn from, with the colours that pick the accent per theme. */
export type MarkSource = { mark: BrandMark; colors: BrandColors | null };

function builtIn(code: string, kind: 'mark' | 'wordmark'): MarkSource | null {
  const b = BRAND.companies[code];
  const mark = (kind === 'wordmark' ? b?.wordmark : undefined) ?? b?.mark;
  return mark ? { mark, colors: null } : null;
}

/** Contract §18.14: a company's mark comes from its record (GET /brands), then from the marks built into the app
 *  (design/brand/companies/), and when neither has one the company shows its code. Needs a QueryClientProvider. */
export function useMarkSource(code: string, kind: 'mark' | 'wordmark' = 'mark'): MarkSource | null {
  const live = useBrands().data?.companies[code];
  const mark = live ? (kind === 'wordmark' ? live.wordmark : null) ?? live.mark : null;
  return mark && live ? { mark, colors: live } : builtIn(code, kind);
}

const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();

/** The accent layer's fill: the brand's own accent_night / accent_day where it fails 3:1 on that theme's page, picked by
 *  --hq-day (globals.css) so it follows the theme of the nearest themed element without JavaScript. */
function accentFill(color: string, c: BrandColors | null): string {
  if (!c?.accent || !same(color, c.accent) || (!c.accent_night && !c.accent_day)) return color;
  return `color-mix(in srgb, ${c.accent_day ?? color} calc(var(--hq-day, 0) * 100%), ${c.accent_night ?? color})`;
}

/** One vector mark. Mono = one ink (lists, seals, ≤ 24px); otherwise the ink layer takes the text colour and accent layers
 *  their own colour (design/brand/SEAL.md, "the company's mark outside the seal"). */
export function MarkSvg({ mark, height, mono = false, ink, colors = null, title, className }: { mark: BrandMark; height: number; mono?: boolean; ink?: string; colors?: BrandColors | null; title?: string; className?: string }) {
  const [, , w, h] = mark.vb.split(' ').map(Number) as [number, number, number, number];
  const color = ink ?? 'currentColor';
  return (
    <svg viewBox={mark.vb} height={height} width={(height * w) / h} role={title ? 'img' : undefined} aria-label={title} aria-hidden={title ? undefined : true} className={className} style={{ flex: 'none', display: 'block' }}>
      {mark.layers.map((l, i) => {
        const fill = mono || l.role === 'ink' ? color : accentFill(l.color, colors);
        return <path key={i} fillRule="evenodd" d={l.d} fill={fill.startsWith('color-mix') ? undefined : fill} style={fill.startsWith('color-mix') ? { fill } : undefined} />;
      })}
    </svg>
  );
}

type Props = { code: string; height?: number; mono?: boolean; ink?: string; kind?: 'mark' | 'wordmark'; title?: string; fallback?: ReactNode };

function Drawn({ source, code, height = 16, mono = false, ink, title, fallback }: Props & { source: MarkSource | null }) {
  if (!source) {
    return fallback ?? (
      <span className="fig inline-flex items-center rounded-[5px] border border-strong px-[5px] text-[10px] font-bold tracking-wide text-ink" style={{ height: Math.max(16, height) }} aria-label={title ?? code}>
        {code}
      </span>
    );
  }
  return <MarkSvg mark={source.mark} height={height} mono={mono} ink={ink} colors={source.colors} title={title ?? code} />;
}

function Live(p: Props) {
  return <Drawn {...p} source={useMarkSource(p.code, p.kind)} />;
}

/** A company's own mark: its brand from GET /brands, then the built-in marks, then the code ([fallback] in its place when
 *  given). Mono = one ink (lists, seals). Outside a QueryClientProvider it draws from the built-in marks only. */
export function CompanyMark(p: Props) {
  const client = useContext(QueryClientContext);
  return client ? <Live {...p} /> : <Drawn {...p} source={builtIn(p.code, p.kind ?? 'mark')} />;
}
